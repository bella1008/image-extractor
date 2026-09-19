"""Exact-revision UA A3 English source repairs with original evidence retained."""
from dataclasses import replace
from tagged_pdf_extractor.domain.models import ContentFragment, Diagnostic, StructureElement

SOURCE_SHA = '38b9bdb357c6b9fd0ccfa0fc3fd3e3a0a0c9ce787fe56fb3fc16c4db1c1ee80a'

def ua_scope(profile):
    return profile is not None and (profile.source_token,profile.doc_type,profile.languages)==('UA_ENG','A3',('ENG',))

def fragments(node):
    if isinstance(node,ContentFragment):
        yield node
    else:
        for child in node.children:
            yield from fragments(child)

def _text(node):
    return ' '.join(''.join(f.text for f in fragments(node)).split())

def prepare_ua_sheet(document,profile):
    if not ua_scope(profile):
        return document
    if document.source_sha256 != SOURCE_SHA:
        raise ValueError('UA source revision needs review')
    if document.raw_children is not None:
        raise ValueError('UA sheet already prepared')
    evidence=[d for d in document.diagnostics if d.code=='ua_source_operations' and d.context.get('sha256')==SOURCE_SHA]
    context=evidence[0].context if len(evidence)==1 else {}
    runs=context.get('runs',[])
    if (type(context.get('page_index')) is not int or context['page_index']!=1
            or type(context.get('mcid')) is not int or context['mcid']!=1142
            or not isinstance(runs,list) or not runs):
        raise ValueError('UA source operation evidence is required for page 1 MCID 1142')
    for run in runs:
        if (not isinstance(run,dict) or run.get('actual_text') is not False
                or (not isinstance(run.get('mcid'),int) or isinstance(run.get('mcid'),bool)) or run['mcid']!=1142
                or type(run.get('operation_index')) is not int or run['operation_index']!=11023
                or not isinstance(run.get('glyphs'),list) or not run['glyphs']
                or any(not isinstance(g,str) or len(g)!=1 for g in run['glyphs'])):
            raise ValueError('UA decimal source operation evidence needs review')
    changes=[]
    def visit(node,path):
        if isinstance(node,ContentFragment):
            if (node.page_index,node.mcid)!=(1,1142):
                return node
            before='[Precautions for using Wi-Fi 5.925 - 7 .125 (or 6.425) GHz]'
            expected='[Precautions for using Wi-Fi 5.925 - 7.125 (or 6.425) GHz]'
            source=''.join(''.join(r['glyphs']) for r in runs)
            if (node.text.strip()!=before or source!=expected or any(r.get('actual_text') for r in runs)
                    or any(r.get('mcid')!=1142 for r in runs)
                    or {r.get('operation_index') for r in runs}!={11023}):
                raise ValueError('UA decimal source operation evidence needs review')
            changes.append({'kind':'decimal_spacing','page_index':1,'mcid':1142,'operation_index':11023})
            return replace(node,text_parts=tuple(p.replace(before,expected) for p in node.text_parts))
        children=tuple(visit(c,(*path,i)) for i,c in enumerate(node.children))
        if node.object_ref=='393 0 R':
            listing,continuation,following=children[8:11]
            if (tuple(c.object_ref for c in (listing,continuation,following))!=('521 0 R','522 0 R','523 0 R')
                    or listing.semantic_role!='list' or len(listing.children)!=1
                    or _text(listing)!='• Do not overload wall outlets, extension cords, or adapters beyond their voltage and capacity. It may cause fire or electric shock.'
                    or _text(continuation)!='Refer to the power specifications section of the manual or the power supply label on the product for voltage and amperage information.'):
                raise ValueError('UA power continuation topology needs review')
            item=listing.children[0];body=item.children[-1]
            if item.semantic_role!='list_item' or body.semantic_role!='list_body':
                raise ValueError('UA power list ownership needs review')
            body=replace(body,children=(*body.children,replace(continuation,semantic_role='span')))
            listing=replace(listing,children=(replace(item,children=(*item.children[:-1],body)),))
            children=(*children[:8],listing,*children[10:])
            changes.append({'kind':'power_continuation','source_path':continuation.source_structure_path})
            intro,first,second,closing=children[-4:]
            if (tuple(c.object_ref for c in (intro,first,second,closing))!=('389 0 R','390 0 R','391 0 R','392 0 R')
                    or not _text(intro).startswith('An administration fee may be charged')
                    or not _text(first).startswith('(a) An engineer') or not _text(second).startswith('(b) You bring')
                    or any(c.source_role!='UnorderList_1-Bullet' for c in (first,second))):
                raise ValueError('UA fee conditions topology needs review')
            listing=StructureElement('ReviewList','list',language='ENG',children=tuple(
                StructureElement('ReviewItem','list_item',language='ENG',children=(c,)) for c in (first,second)))
            group=StructureElement('ReviewGroup','section',language='ENG',attributes=(('review-group','administration-fee-conditions'),),children=(intro,listing))
            children=(*children[:-4],group,closing)
            changes.append({'kind':'fee_conditions','source_paths':[first.source_structure_path,second.source_structure_path]})
        if node.source_role=='Article':
            if (tuple(c.object_ref for c in children)!=('395 0 R','393 0 R','396 0 R','397 0 R','398 0 R','399 0 R','400 0 R','401 0 R','402 0 R')
                    or _text(children[0])!='ENG' or _text(children[3])!='Simple User Guide'
                    or {f.page_index for c in children[2:] for f in fragments(c)}!={0}):
                raise ValueError('UA cover/body source layout needs review')
            children=(children[0],*children[2:],children[1])
            changes.append({'kind':'cover_order','body_source_path':children[-1].source_structure_path})
        return replace(node,children=children,language='ENG',source_structure_path=path)
    children=tuple(visit(c,(i,)) for i,c in enumerate(document.children))
    if {c['kind'] for c in changes}!={'decimal_spacing','power_continuation','fee_conditions','cover_order'}:
        raise ValueError('UA reviewed source structures missing')
    return replace(document,children=children,raw_children=document.children,diagnostics=(*document.diagnostics,
        Diagnostic('warning','ua_source_structure','UA source-reviewed cover order, power/fee ownership and decimal; raw structure retained.',{'sha256':SOURCE_SHA,'changes':changes}),
        Diagnostic('warning','ua_graphic_document_code','The visible BN68-26754A part of the cover document code is graphic-only; the tagged -00 suffix remains unchanged.',{'sha256':SOURCE_SHA,'page_index':0,'source_object_ref':'409 0 R','source_mcid':394})))
