"""Mirrored font brackets in four source-verified SQ MI inline conditions."""
from collections import Counter
from dataclasses import replace
from tagged_pdf_extractor.domain.models import ContentFragment,Diagnostic
from tagged_pdf_extractor.domain.tk_sheet import fragments
from tagged_pdf_extractor.domain.tk_arabic_source import source_inventory

def repair_sq_brackets(children,diagnostics):
    runs,_=source_inventory(diagnostics);changes=[]
    configs={'1425 0 R':(0,119,121,[125,123,124,122,120,119,121,118]),
             '1166 0 R':(0,634,635,[633,634,635,632]),
             '146 0 R':(1,1247,1248,[1252,1250,1251,1249,1248,1247,1246]),
             '381 0 R':(1,1753,1754,[1755,1753,1754,1752])}
    def visit(n):
        if isinstance(n,ContentFragment):return n
        cs=tuple(visit(c) for c in n.children)
        if n.object_ref not in configs:return replace(n,children=cs)
        page,model_id,close_id,order=configs[n.object_ref]
        if any(not isinstance(c,ContentFragment) for c in cs):raise ValueError('SQ MI condition owner topology changed')
        by_id={c.mcid:c for c in cs}
        if sorted(by_id)!=sorted(order):raise ValueError('SQ MI condition MCIDs changed')
        model,close=by_id[model_id],by_id[close_id]
        if model.text!='The Frame (LS03HA' or close.text.count('(')!=1:raise ValueError('SQ MI condition wording changed')
        source=runs.get((page,close_id),[]);mr=runs.get((page,model_id),[])
        glyphs=[(g,b,r) for r in source for g,b in zip(r['glyphs'],r['glyph_boxes'])]
        closing=[(g,b,r) for g,b,r in glyphs if g=='(']
        mb=[b for r in mr for b in r['glyph_boxes']]
        if (len(closing)!=1 or not mb or not all(r['axis_aligned'] and not r['actual_text'] for r in source)
                or abs(closing[0][1][0]-max(b[2] for b in mb))>.02):
            raise ValueError('SQ MI closing glyph adjacency is unproved')
        if n.object_ref!='146 0 R' and ''.join(r['raw_hex'] for r in source)!='29':
            raise ValueError('SQ MI mirrored Latin font bracket changed')
        replacements={close_id:close.text.replace('(',')',1)}
        transfer=None
        if n.object_ref=='1166 0 R':
            outer=by_id[633];rr=runs.get((0,633),[])
            if outer.text!=')' or ''.join(r['raw_hex'] for r in rr)!='28':raise ValueError('SQ MI outer font bracket changed')
            replacements[633]='('
        if n.object_ref=='146 0 R':
            replacements[close_id]=close.text.replace('(','',1)
            replacements[model_id]=model.text+')'
            transfer={'from_mcid':close_id,'to_mcid':model_id,'decoded_glyph':'(','visible_logical_glyph':')','bbox':closing[0][1]}
        def updated(c):
            if c.mcid not in replacements:return c
            styles={s for p,s in zip(c.text_parts,c.text_styles) if p.strip()}
            if len(styles)!=1:raise ValueError('SQ MI condition typography changed')
            return replace(c,text_parts=(replacements[c.mcid],),text_styles=(next(iter(styles)),),text_bboxes=(c.bbox,))
        result=replace(n,children=tuple(updated(by_id[i]) for i in order))
        changes.append({'ref':n.object_ref,'source_path':n.source_structure_path,'page_index':page,
            'logical_mcids':order,'source_runs':source,'model_runs':mr,'source_transfer':transfer,
            'fragment_changes':[{'mcid':i,'before':by_id[i].text,'after':v} for i,v in replacements.items()]})
        return result
    result=tuple(visit(n) for n in children)
    return result,Diagnostic('warning','sq_mi_visible_brackets',
        'Mirrored PDF font codes are interpreted using reviewed physical glyphs and Latin-model adjacency; original owners remain audited.',{'changes':changes})

def verified_sq_special_counts(document,baseline,characters):
    from tagged_pdf_extractor.domain.sq_mi_sheet import SOURCE_SHA
    if document.source_sha256!=SOURCE_SHA or document.raw_children is None:return None
    if not any(d.code=='africa_rtl_glyph_source' for d in document.diagnostics):return None
    restored,proof=repair_sq_brackets(document.raw_children,document.diagnostics)
    if {c['ref'] for c in proof.context['changes']}!={'1425 0 R','1166 0 R','146 0 R','381 0 R'}:return None
    counts=lambda ns:Counter(''.join(f.text for n in ns for f in fragments(n)))
    raw,correct=counts(document.raw_children),counts(restored)
    if any(raw[c]!=baseline.count(c) for c in characters):return None
    return {c:correct[c] for c in characters}
