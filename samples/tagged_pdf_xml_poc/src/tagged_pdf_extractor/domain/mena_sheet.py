"""Source-verified MENA A2 language sections and cover/RTL reading order."""
from dataclasses import replace
from tagged_pdf_extractor.domain.models import ContentFragment, Diagnostic, StructureElement
from tagged_pdf_extractor.domain.tk_sheet import fragments

SOURCE_SHA='b4d6f56c8e7f85b6d8c8b0681954223b0194a9ccc9e7cc2499d121f611f12ecf'

def mena_scope(profile):
    return profile is not None and (profile.source_token,profile.doc_type,profile.languages)==('MENA_L02','A2',('ENG','ARA'))

def prepare_mena_sheet(document,profile):
    if not mena_scope(profile):return document
    if document.source_sha256!=SOURCE_SHA:raise ValueError('MENA source revision needs review')
    if document.raw_children is not None:raise ValueError('MENA already prepared')
    def annotate(n,path):
        if isinstance(n,ContentFragment):return n
        pages={f.page_index for f in fragments(n)}
        language=profile.languages[next(iter(pages))] if len(pages)==1 and pages<={0,1} else None
        children=tuple(annotate(c,(*path,i)) for i,c in enumerate(n.children))
        if n.source_role=='Article':
            if tuple(c.object_ref for c in children)!=('651 0 R','652 0 R','653 0 R','654 0 R','655 0 R','656 0 R','657 0 R','658 0 R','659 0 R','121 0 R','660 0 R','661 0 R','662 0 R','649 0 R','663 0 R'):
                raise ValueError('MENA cover/source topology changed')
            children=(*children[:2],*children[3:8],children[2],*children[8:10],*children[11:],children[10])
        return replace(n,children=children,language=language,source_structure_path=path)
    children=tuple(annotate(c,(i,)) for i,c in enumerate(document.children))
    from tagged_pdf_extractor.domain.africa_rtl import restore_rtl_glyph_lines
    from tagged_pdf_extractor.domain.africa_numeric_text import restore_actual_text_decimals, restore_ltr_decimal_spacing
    from tagged_pdf_extractor.domain.africa_inline_order import restore_inline_order
    from tagged_pdf_extractor.domain.africa_rtl_conditions import restore_rtl_conditions
    proofs=[]
    for repair in (restore_rtl_glyph_lines,restore_actual_text_decimals,restore_ltr_decimal_spacing,restore_inline_order,restore_rtl_conditions):
        children,proof=repair(children,document.diagnostics);proofs.append(proof)
    from tagged_pdf_extractor.domain.mena_source_text import repair_mena_source
    children,proof=repair_mena_source(children,document.diagnostics);proofs.append(proof)
    if {c['kind'] for c in proof.context['changes']}!={'model_suffix_source_ownership','sound_model_boundary_slash','wifi_source_bracket_order','copyright_source_glyph_order','the_frame_note_punctuation_order'}:
        raise ValueError('MENA source punctuation evidence incomplete')
    changes=[]
    def ownership(n):
        if isinstance(n,ContentFragment):return n
        cs=tuple(ownership(c) for c in n.children)
        if n.object_ref=='174 0 R' and n.language=='ARA':
            model=next(c for c in cs if isinstance(c,ContentFragment) and c.mcid==1083)
            if model.text!='LS03H*' or n.source_structure_path!=(0,0,10,62,0,1):
                raise ValueError('MENA isolated model source changed')
            wrapper=StructureElement('ReviewSpan','span',page_index=1,language='ARA',children=(model,),
                source_structure_path=n.source_structure_path,
                attributes=(('review-inline','ltr-model-token'),('review-source-token','MENA_L02'),('review-source-sha256',SOURCE_SHA)))
            cs=tuple(wrapper if c is model else c for c in cs)
        if n.object_ref in {'653 0 R','660 0 R'}:
            ref,prev=('1175 0 R','1174 0 R') if n.language=='ENG' else ('390 0 R','666 0 R')
            indexes=[i for i,c in enumerate(cs) if c.object_ref==ref]
            if len(indexes)!=1:raise ValueError('MENA power continuation missing')
            i=indexes[0];listing,continuation=cs[i-1:i+1]
            item=listing.children[-1];body=item.children[-1]
            if listing.object_ref!=prev or body.semantic_role!='list_body':raise ValueError('MENA power ownership changed')
            body=replace(body,children=(*body.children,replace(continuation,semantic_role='span')))
            item=replace(item,children=(*item.children[:-1],body))
            listing=replace(listing,children=(*listing.children[:-1],item))
            cs=(*cs[:i-1],listing,*cs[i+1:])
            changes.append({'kind':'power_continuation','source_path':continuation.source_structure_path})
        if n.object_ref in {'1056 0 R','647 0 R'}:
            if (len(cs)!=14 or [len(r.children) for r in cs]!=[3]*5+[2]*4+[3]*5
                or sum(dict(c.attributes).get('/RowSpan')=='5' for r in cs for c in r.children)!=1):
                raise ValueError('MENA contact spans changed')
            n=replace(n,attributes=(*n.attributes,('review-table','source-spans')))
            changes.append({'kind':'contact_source_spans','source_path':n.source_structure_path})
        return replace(n,children=cs)
    children=tuple(ownership(c) for c in children)
    return replace(document,raw_children=document.children,children=children,
        diagnostics=(*document.diagnostics,*proofs,Diagnostic('warning','mena_source_structure',
            'Verified MENA ENG/ARA sections; cover precedes body within each source page.',
            {'sha256':SOURCE_SHA,'original_document_language':document.language,'page_languages':['ENG','ARA'],'changes':changes})))
