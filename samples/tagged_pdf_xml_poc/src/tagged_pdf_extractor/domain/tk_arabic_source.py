"""TK_ARA A3 source repairs; every text change retains PDF character ownership."""
from collections import Counter, defaultdict
from dataclasses import replace
import re
import math
import unicodedata as ud

from tagged_pdf_extractor.domain.models import ContentFragment, Diagnostic, StructureElement
from tagged_pdf_extractor.domain.tk_sheet import fragments
from tagged_pdf_extractor.domain.africa_rtl import _marks_anchor_to_following_base
from tagged_pdf_extractor.domain.africa_rtl_conditions import is_rtl_numeric_condition, _ltr_neutral_glyphs
from tagged_pdf_extractor.domain.paragraph_eligibility import is_nonempty_inline_paragraph

# Source identity recorded in xml_review_tk_20260915_evidence/initial_state.json.
VERIFIED_SOURCE_SHA256 = '4e7252d53db9836ba2f093e527cda211867fd9ce5312fcb53e592b91fb7ac552'

# Reviewed source U+0020 boundaries: parent path, preceding, space, following MCID.
VERIFIED_SPACE_BOUNDARIES = {
    '282 0 R': ((0,0,1,81), 960, 959, 969),
    '297 0 R': ((0,0,1,85,0,1,0,2), 1016, 1014, 1015),
    '298 0 R': ((0,0,1,85,0,1,0,3), 1026, 1025, 1024),
    '299 0 R': ((0,0,1,85,0,1,0,4), 1039, 1037, 1038),
    '300 0 R': ((0,0,1,85,0,1,0,5), 1044, 1042, 1043),
    '301 0 R': ((0,0,1,85,0,1,0,6), 1051, 1049, 1050),
    '302 0 R': ((0,0,1,85,0,1,0,7), 1062, 1061, 1060),
    '303 0 R': ((0,0,1,85,0,1,0,8), 1074, 1072, 1073),
}


def key(text):
    return ''.join(c for c in text if not c.isspace() and ud.category(c) != 'Cf')


def source_inventory(diagnostics):
    runs, actual = defaultdict(list), defaultdict(list)
    for d in diagnostics:
        if d.code == 'africa_rtl_glyph_source':
            for line in d.context['lines']:
                for run in line['runs']:
                    runs[d.context['page_index'], run['mcid']].append(run)
        if d.code == 'pdf_actual_text_applied':
            for item in d.context['replacements']:
                actual[d.context['page_index'], item['mcid']].append(item['actual_text'])
    return runs, actual


def contiguous(runs):
    if not runs or any(not r.get('glyph_boxes') or not r.get('axis_aligned') for r in runs):
        return False
    boxes = [b for r in runs for b in r['glyph_boxes']]
    h = min(b[3]-b[1] for b in boxes)
    return (h > 0 and max(b[1] for b in boxes)-min(b[1] for b in boxes) < .05
            and all(-.2*h <= b[0]-a[2] <= .2*h for a,b in zip(boxes,boxes[1:])))


def repair_fragment(fragment, runs, actual):
    """Recover one MCID from its contiguous glyph advances, not replacement words."""
    if not runs or len(set(fragment.text_styles)) > 1:
        return fragment
    value = None
    # PDF-authored ActualText may carry digits absent from the raw font map.
    if ((fragment.page_index, fragment.mcid) in {(0,195),(1,664),(1,1222),(1,1323),(1,1315)}
            and (all(not r.get('actual_text') for r in runs) or actual)):
        assembled, active, ix = '', False, 0
        for r in runs:
            if r.get('actual_text'):
                if not active:
                    if ix >= len(actual):
                        return fragment
                    assembled += actual[ix]
                    ix += 1
            else:
                assembled += ''.join(r['glyphs'])
            active = r.get('actual_text')
        if (re.fullmatch(r'[A-Za-z0-9*]+(?: [A-Za-z0-9*]+)*', assembled)
                and Counter(key(assembled)) == Counter(key(fragment.text)) and contiguous(runs)):
            value = assembled
    # Source Arabic footnotes have diacritic resets; the copyright MCID
    # contains the same complete RTL line plus its copyright symbol.
    if (fragment.page_index, fragment.mcid) in {(0,17),(0,343),(1,660)}:
        for run in runs:
            glyphs, boxes = run.get('glyphs'), run.get('glyph_boxes')
            if (not run.get('axis_aligned') or run.get('actual_text')
                    or not isinstance(glyphs,(list,tuple)) or not glyphs
                    or not isinstance(boxes,(list,tuple)) or len(glyphs)!=len(boxes)
                    or any(not isinstance(g,str) or not g for g in glyphs)
                    or any(not isinstance(b,(list,tuple)) or len(b)!=4
                           or any(not isinstance(v,(int,float)) or not math.isfinite(v) for v in b)
                           or b[3]<=b[1] or b[2]<b[0] for b in boxes)):
                return fragment
        glyphs = [(g,b) for r in runs for g,b in zip(r['glyphs'],r['glyph_boxes'])]
        bases = [(g,b) for g,b in glyphs if not all(ud.category(c).startswith('M') for c in g)]
        if not bases:
            return fragment
        h = min(b[3]-b[1] for _,b in bases)
        if (all(not r.get('actual_text') and r.get('axis_aligned') for r in runs)
                and max(b[1] for _,b in bases)-min(b[1] for _,b in bases) < .05
                and all(-.2*h <= b[0]-a[2] <= .2*h for (_,a),(_,b) in zip(bases,bases[1:]))
                and _marks_anchor_to_following_base(glyphs,h)):
            proposed = ''.join(g for g,_ in reversed(glyphs))
            if Counter(key(proposed)) == Counter(key(fragment.text)):
                value = proposed
    if value is None or fragment.text_parts == (value,):
        return fragment
    return replace(fragment,text_parts=(value,),text_styles=fragment.text_styles[:1],
                   text_bboxes=(fragment.bbox,) if fragment.text_bboxes else ())


def repair_tk_source(children, diagnostics, source_sha256=None):
    if source_sha256 != VERIFIED_SOURCE_SHA256:
        return children,(Diagnostic('warning','tk_arabic_source_revision_unverified',
            'Object-addressed TK Arabic repairs require the reviewed source revision.',
            {'source_sha256':source_sha256,'expected_sha256':VERIFIED_SOURCE_SHA256}),)
    runs, actual = source_inventory(diagnostics)
    changes, splits = [], []
    def visit(node):
        if isinstance(node,ContentFragment):
            result=repair_fragment(node,runs.get((node.page_index,node.mcid),[]),actual.get((node.page_index,node.mcid),[]))
            if result != node:
                changes.append({'kind':'glyph_fragment','page_index':node.page_index,'mcid':node.mcid,
                                'before':node.text,'after':result.text})
            return result
        node=replace(node,children=tuple(visit(c) for c in node.children))
        # Within these model-only portions, physical right-to-left atom order
        # keeps separators outside the complete Latin model tokens.
        if node.object_ref in {'196 0 R','295 0 R','353 0 R','359 0 R','364 0 R','368 0 R','374 0 R'}:
            cs=list(node.children)
            if all(isinstance(c,ContentFragment) or (c.semantic_role=='span' and len(tuple(fragments(c)))==1) for c in cs):
                places=[]
                for c in cs:
                    rr=[r for f in fragments(c) for r in runs.get((f.page_index,f.mcid),[])]
                    if not rr or any(not r.get('glyph_boxes') for r in rr):break
                    bb=[b for r in rr for b in r['glyph_boxes']]
                    places.append((max(r['baseline_y'] for r in rr),max(b[2] for b in bb)))
                else:
                    if node.object_ref=='196 0 R' and any(getattr(c,'mcid',None)==771 and c.text=='*/\u200f' for c in cs):
                        # One source MCID spans a slash and the following model's
                        # wildcard. Disjoint slices retain that same source MCID.
                        i=next(i for i,c in enumerate(cs) if getattr(c,'mcid',None)==771)
                        source=cs[i]
                        rr=runs[1,771]
                        glyphs=[(g,b) for r in rr for g,b in zip(r['glyphs'],r['glyph_boxes']) if g in '*/']
                        if [g for g,_ in glyphs]==['*','/'] and glyphs[0][1][2] <= glyphs[1][1][0]+.05:
                            cs[i]=replace(source,text_parts=(source.text[1:],),text_styles=source.text_styles[:1],text_bboxes=(tuple(glyphs[1][1]),))
                            star=replace(source,text_parts=(source.text[:1],),text_styles=source.text_styles[:1],text_bboxes=(tuple(glyphs[0][1]),),join_previous=True)
                            # Sort slash normally, then attach wildcard after its
                            # adjacent LS03H token, which the PDF draws to its left.
                            order=sorted(range(len(cs)),key=lambda j:(-round(places[j][0],1),-places[j][1]))
                            cs=[cs[j] for j in order]
                            target=next((j for j,c in enumerate(cs) if getattr(c,'mcid',None)==770 and key(c.text)=='LS03H'),None)
                            if target is not None:
                                cs.insert(target+1,star)
                                splits.append({'page_index':1,'mcid':771,'original_text':source.text,
                                    'source_parts':[{'slice':[1,3],'text':source.text[1:],'placement':'before LS03H'},
                                                    {'slice':[0,1],'text':source.text[:1],'placement':'after LS03H'}],
                                    'source_structure_path':node.source_structure_path})
                        else:cs=list(node.children)
                    else:
                        cs=[cs[j] for j in sorted(range(len(cs)),key=lambda j:(-round(places[j][0],1),-places[j][1]))]
                    if Counter(''.join(f.text for c in cs for f in fragments(c))) == Counter(''.join(f.text for f in fragments(node))):
                        if tuple(cs)!=node.children:
                            changes.append({'kind':'model_separators','source_structure_path':node.source_structure_path})
                            if node.object_ref=='196 0 R' and splits:
                                for j in range(len(cs)-1):
                                    token, wildcard = cs[j:j+2]
                                    if (isinstance(token,ContentFragment) and isinstance(wildcard,ContentFragment)
                                            and (token.page_index,token.mcid)==(1,770)
                                            and (wildcard.page_index,wildcard.mcid)==(1,771)
                                            and re.fullmatch(r'[A-Z][A-Z0-9]+',token.text)
                                            and wildcard.text=='*'):
                                        cs[j:j+2]=[StructureElement('ReviewSpan','span',page_index=1,language='ARA',
                                            source_structure_path=node.source_structure_path,
                                            attributes=(('review-inline','ltr-model-token'),
                                                ('review-source-token','TK_ARA'),
                                                ('review-source-sha256',source_sha256)),children=(token,wildcard))]
                                        changes.append({'kind':'ltr_model_span','source_structure_path':node.source_structure_path,
                                            'page_index':1,'mcids':[770,771]})
                                        break
                            node=replace(node,children=tuple(cs))
        if node.object_ref in {'298 0 R','302 0 R'}:
            proposed=[]; places=[]
            for c in node.children:
                rr=[r for f in fragments(c) for r in runs.get((f.page_index,f.mcid),[])]
                if not rr or any(not r.get('glyph_boxes') for r in rr):break
                if not isinstance(c,ContentFragment):
                    if c.semantic_role!='span' or len(tuple(fragments(c)))!=1:break
                elif key(c.text) in {'"(',':)','"-'}:
                    if ('\u200f' not in c.text or not _ltr_neutral_glyphs(rr)
                            or key(''.join(''.join(r['glyphs']) for r in rr)) != key(c.text)):
                        break
                    c=replace(c,text_parts=tuple(p[::-1] for p in reversed(c.text_parts)),
                              text_styles=c.text_styles[::-1],text_bboxes=c.text_bboxes[::-1])
                boxes=[b for r in rr for b in r['glyph_boxes']]
                places.append((min(b[1] for b in boxes),max(b[2] for b in boxes)))
                proposed.append(c)
            else:
                if max(p[0] for p in places)-min(p[0] for p in places) < .05:
                    proposed=tuple(proposed[j] for j in sorted(range(len(proposed)),key=lambda j:-places[j][1]))
                    before=''.join(f.text for f in fragments(node))
                    after=''.join(f.text for c in proposed for f in fragments(c))
                    if Counter(before)==Counter(after) and is_rtl_numeric_condition(after):
                        node=replace(node,children=proposed,display_direction='rtl')
                        changes.append({'kind':'numeric_condition','source_structure_path':node.source_structure_path,
                                        'before':before,'after':after})
        boundary = VERIFIED_SPACE_BOUNDARIES.get(node.object_ref)
        if boundary and node.semantic_role == 'paragraph' and node.source_structure_path == boundary[0]:
            cs = list(node.children)
            for i in range(1, len(cs)-1):
                previous, space, following = cs[i-1:i+2]
                if (all(isinstance(c, ContentFragment) and c.page_index == 1 for c in (previous, space, following))
                        and (previous.mcid, space.mcid, following.mcid) == boundary[1:]
                        and space.text == ('\n ' if node.object_ref == '282 0 R' else ' ')
                        and previous.text.strip() and following.text.strip()):
                    cs[i-1:i+2] = [StructureElement('ReviewSpan', 'span', page_index=1, language='ARA',
                        source_structure_path=node.source_structure_path,
                        attributes=(('review-whitespace', 'source-boundary'),
                            ('review-whitespace-source-token', 'TK_ARA'),
                            ('review-whitespace-source-sha256', source_sha256)), children=(previous, space, following))]
                    node = replace(node, children=tuple(cs))
                    changes.append({'kind': 'source_whitespace_boundary', 'source_structure_path': node.source_structure_path,
                        'page_index': 1, 'preceding_mcid': previous.mcid, 'space_mcid': space.mcid,
                        'following_mcid': following.mcid, 'source_text': space.text})
                    break
        return node
    result=tuple(visit(c) for c in children)
    return result, (Diagnostic('warning','tk_arabic_source_fragments','TK A3 glyph geometry restores source fragments and model separators.',{'changes':changes}),
                    Diagnostic('warning','tk_arabic_split_fragment','Disjoint source slices preserve a wildcard sharing its MCID with a separator.',{'splits':splits}))


def repair_tk_ownership(children):
    changes=[]
    def text(n):return ' '.join(''.join(f.text for f in fragments(n)).split())
    warning='لا تقم بتحميل مآخذ الحائط أو أسلاك التمديد أو المحول فوق جهدها وسعتها. فقد يؤدي هذا إلى نشوب حريق أو حدوث صدمة كهربائية.'
    continuation='راجع قسم مواصفات الطاقة في دليل المستخدم أو ملصق مصدر الطاقة الموجود على المنتج للحصول على معلومات عن الجهد وشدة التيار.'
    fee_a='(أ) استدعاء مهندس بناءً على طلبك، لكن لا توجد أي عيوب في المنتج (مثلاً، في حالة عدم قراءة دليل المستخدم).'
    fee_b='(ب) إحضار الوحدة إلى مركز خدمة Samsung، لكن لم يتم إيجاد أي عيوب في المنتج (مثلاً في حالة عدم قراءة دليل المستخدم).'
    def paragraph(n,role):
        return (isinstance(n,StructureElement) and n.source_role==role
                and is_nonempty_inline_paragraph(n))
    def same_page(nodes):
        pages={f.page_index for n in nodes for f in fragments(n)}
        if len(pages)!=1:return False
        page=next(iter(pages))
        def valid(n):
            return isinstance(n,ContentFragment) or (
                n.page_index in {None,page} and n.language in {None,'ARA'}
                and all(valid(c) for c in n.children))
        return all(valid(n) for n in nodes)
    def power_body(listing):
        if (not isinstance(listing,StructureElement) or listing.semantic_role!='list'
                or len(listing.children)!=1):return None
        item=listing.children[0]
        if (not isinstance(item,StructureElement) or item.semantic_role!='list_item'
                or len(item.children)!=2):return None
        label,body=item.children
        if (not isinstance(label,StructureElement) or label.semantic_role!='label'
                or text(label)!='•' or not is_nonempty_inline_paragraph(replace(label,semantic_role='paragraph'))
                or not isinstance(body,StructureElement) or body.semantic_role!='list_body'
                or not is_nonempty_inline_paragraph(replace(body,semantic_role='paragraph'))
                or text(body)!=warning):return None
        return body
    def visit(n):
        if isinstance(n,ContentFragment):return n
        cs=[visit(c) for c in n.children]
        result=[]; i=0
        while i<len(cs):
            c=cs[i]
            if (getattr(c,'object_ref',None)=='436 0 R' and text(c)==continuation
                    and paragraph(c,'UnorderList_1-Bullet') and result
                    and power_body(result[-1]) is not None and same_page((result[-1],c))):
                listing=result[-1];item=listing.children[-1]
                body=item.children[-1]
                if body.semantic_role=='list_body':
                    body=replace(body,children=(*body.children,replace(c,semantic_role='span')))
                    item=replace(item,children=(*item.children[:-1],body))
                    result[-1]=replace(listing,children=(*listing.children[:-1],item))
                    changes.append({'kind':'power_continuation','source_path':c.source_structure_path});i+=1;continue
            if (text(c)=='قد يتم احتساب رسوم إدارية في الحالات التالية:' and i+2<len(cs)
                    and paragraph(c,'Description-L')
                    and [getattr(x,'object_ref',None) for x in cs[i+1:i+3]]==['339 0 R','340 0 R']
                    and all(paragraph(x,'UnorderList_1-Bullet') for x in cs[i+1:i+3])
                    and tuple(text(x) for x in cs[i+1:i+3])==(fee_a,fee_b)
                    and same_page(cs[i:i+3])):
                listing=StructureElement('ReviewList','list',language='ARA',children=tuple(
                    StructureElement('ReviewItem','list_item',language='ARA',children=(x,)) for x in cs[i+1:i+3]))
                result.append(StructureElement('ReviewGroup','section',language='ARA',
                    attributes=(('review-group','administration-fee-conditions'),),children=(c,listing)))
                changes.append({'kind':'fee_conditions','source_path':c.source_structure_path});i+=3;continue
            result.append(c);i+=1
        return replace(n,children=tuple(result))
    result=tuple(visit(c) for c in children)
    return result,Diagnostic('warning','tk_arabic_paragraph_ownership','Source adjacent continuation and fee conditions retain parent ownership.',{'changes':changes})
