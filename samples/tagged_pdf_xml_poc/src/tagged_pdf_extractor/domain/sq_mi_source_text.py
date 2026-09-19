"""SQ MI source glyph order; no translated strings or invented characters."""
from collections import Counter
from dataclasses import replace
import re
import unicodedata as ud
from tagged_pdf_extractor.domain.models import ContentFragment, Diagnostic
from tagged_pdf_extractor.domain.tk_sheet import fragments
from tagged_pdf_extractor.domain.tk_arabic_source import source_inventory, contiguous

def visible(value):
    return ''.join(c for c in value if not c.isspace() and ud.category(c)!='Cf')

def repair_sq_mi_source(children,diagnostics):
    runs,actual=source_inventory(diagnostics)
    changes=[]
    def update(f,value,kind,rr):
        if Counter(visible(value))!=Counter(visible(f.text)):
            raise ValueError('SQ MI source glyph inventory changed')
        if value==f.text:return f
        styles={s for p,s in zip(f.text_parts,f.text_styles) if visible(p) and s.font_name is not None}
        if len(styles)>1:return f
        changes.append({'kind':kind,'page_index':f.page_index,'mcid':f.mcid,'before':f.text,'after':value,'source_runs':rr})
        return replace(f,text_parts=(value,),text_styles=(next(iter(styles)),) if styles else (),text_bboxes=(f.bbox,))
    def fragment(f):
        rr=runs.get((f.page_index,f.mcid),[])
        if not rr:return f
        # Source RLM-only ActualText is a control, not a painted glyph. Keep
        # its original control inventory while interpreting the visible run.
        controls=''.join(c for c in f.text if ud.category(c)=='Cf')
        pure_runs=[r for r in rr if not (r['actual_text'] and not visible(''.join(r['glyphs'])))]
        if not pure_runs:return f
        from tagged_pdf_extractor.domain.africa_rtl import _marks_anchor_to_following_base
        pairs=[(g,b) for r in pure_runs for g,b in zip(r['glyphs'],r['glyph_boxes'])]
        bases=[(g,b) for g,b in pairs if not all(ud.category(c).startswith('M') for c in g)]
        height=min((b[3]-b[1] for g,b in bases),default=0)
        rtl_contiguous=bool(bases and height>0
            and all(r['axis_aligned'] for r in pure_runs)
            and max(b[1] for g,b in bases)-min(b[1] for g,b in bases)<.05
            and all(b[0]>=a[0] and -.2*height<=b[0]-a[2]<=.2*height for (_,a),(_,b) in zip(bases,bases[1:]))
            and _marks_anchor_to_following_base(pairs,height))
        if not contiguous(rr) and not rtl_contiguous:return f
        glyphs=[g for r in pure_runs for g in r['glyphs']]
        # Whole RTL fragments with punctuation. Each PDF glyph (including
        # multi-codepoint combining sequences) stays intact when order changes.
        if (rtl_contiguous and all(not r['actual_text'] or all(ud.category(c).startswith('M') for c in ''.join(r['glyphs'])) for r in pure_runs)
                and any(ud.bidirectional(c) in {'R','AL'} for g in glyphs for c in g)
                and all(ud.bidirectional(c) in {'R','AL','NSM','WS'} or c.isspace() or c in '.,،؛!؟?:;©-\"\'()[]/*' for g in glyphs for c in g)):
            proposal=controls+''.join(reversed(glyphs))
            if Counter(visible(proposal))==Counter(visible(f.text)):
                return update(f,proposal,'whole_rtl_glyph_fragment',rr)
        if not any(r['actual_text'] for r in rr):
            proposal=''.join(glyphs)
            if proposal.isascii() and Counter(visible(proposal))==Counter(visible(f.text)):
                return update(f,proposal,'contiguous_latin_source',rr)
        # A complete decimal is proved by original glyphs plus PDF ActualText;
        # its pypdf-generated internal whitespace is not source whitespace.
        if re.fullmatch(r'\d+\.\d+',visible(f.text)):
            values=actual.get((f.page_index,f.mcid),[]);proposal='';active=False;ix=0
            for r in rr:
                if r['actual_text']:
                    if not active:
                        if ix>=len(values):return f
                        proposal+=values[ix];ix+=1
                else:proposal+=''.join(r['glyphs'])
                active=r['actual_text']
            if ix==len(values) and proposal==visible(f.text):
                return update(f,proposal,'source_actual_decimal',rr)
        return f
    def placement(n):
        rr=[r for f in fragments(n) for r in runs.get((f.page_index,f.mcid),[])]
        boxes=[b for r in rr for b in r['glyph_boxes']]
        if not boxes or max(b[1] for b in boxes)-min(b[1] for b in boxes)>.05:
            raise ValueError('SQ MI model atom geometry changed')
        return -round(boxes[0][1],1),-min(b[0] for b in boxes)
    def visit(n):
        if isinstance(n,ContentFragment):return fragment(n)
        cs=tuple(visit(c) for c in n.children)
        if n.object_ref=='1207 0 R':
            by_id={c.mcid:c for c in cs if isinstance(c,ContentFragment)}
            space,number,label=(by_id[i] for i in (1093,1092,1095))
            boxes=lambda f:[b for r in runs[f.page_index,f.mcid] for b in r['glyph_boxes']]
            sb,nb,lb=boxes(space),boxes(number),boxes(label)
            if (space.text!=' ' or number.text!='5.925' or label.text!='Wi-Fi'
                    or len(sb)!=1 or abs(sb[0][2]-min(b[0] for b in lb))>.02
                    or not 0<=sb[0][0]-max(b[2] for b in nb)<.5):
                raise ValueError('SQ MI Wi-Fi source word boundary changed')
            items=list(cs);items.remove(space);items.insert(items.index(number),space);cs=tuple(items)
            changes.append({'kind':'wifi_source_word_space','source_path':n.source_structure_path,
                'page_index':0,'space_mcid':1093,'between_mcids':[1095,1092],'source_space_bbox':sb[0]})
        if n.object_ref in {'1324 0 R','276 0 R'}:
            # Model tokens each keep LTR character order; separators follow
            # their physical RTL atom order across the original line wraps.
            cs=tuple(sorted(cs,key=placement))
            # The final model's star is a separate MCID, physically to its
            # right. Attach it after that model without changing its owner.
            star=next((c for c in cs if visible(''.join(f.text for f in fragments(c)))=='*'),None)
            model=next((c for c in cs if visible(''.join(f.text for f in fragments(c)))=='LS03H'),None)
            if star is None or model is None:raise ValueError('SQ MI microphone model tail changed')
            parts=list(cs);parts.remove(star);i=parts.index(model)
            parts.insert(i+1,replace(star,join_previous=True) if isinstance(star,ContentFragment) else star)
            cs=tuple(parts)
            changes.append({'kind':'microphone_source_atom_order','source_path':n.source_structure_path,'ref':n.object_ref})
        return replace(n,children=cs)
    return tuple(visit(n) for n in children),Diagnostic('warning','sq_mi_source_text',
        'Whole glyph runs and measured RTL atom positions preserve source character inventory.',{'changes':changes})
