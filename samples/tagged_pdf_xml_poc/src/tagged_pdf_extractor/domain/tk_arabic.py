"""TK Arabic A3: front cover first, source pages 1 then 2, RTL within lines."""
from dataclasses import replace
from tagged_pdf_extractor.domain.models import ContentFragment,Diagnostic
from tagged_pdf_extractor.domain.tk_sheet import fragments

def tk_ara_scope(profile):
    return (profile is not None and profile.source_token=='TK_ARA'
            and profile.doc_type=='A3' and profile.languages==('ARA',))

def prepare_tk_arabic(document,profile):
    if not tk_ara_scope(profile):return document
    if document.raw_children is not None:raise ValueError('TK Arabic already prepared')
    if document.bookmark_page_bounds:raise ValueError('TK Arabic bookmark structure needs review')
    if {f.page_index for n in document.children for f in fragments(n)}!={0,1}:
        raise ValueError('TK Arabic A3 requires the reviewed two-page structure')
    def annotate(n,path):
        if isinstance(n,ContentFragment):return n
        cs=tuple(annotate(c,(*path,i)) for i,c in enumerate(n.children))
        if n.source_role=='Article':
            if (len(cs)!=9 or getattr(cs[0],'source_role',None)!='Story'
                    or ''.join(f.text for f in fragments(cs[0])).strip()!='ARA'
                    or not any(getattr(c,'source_role',None)=='Cover_Title' for c in cs[3].children)):
                raise ValueError('TK Arabic cover/source story layout needs review')
            cs=(cs[0],*cs[2:],cs[1])
        return replace(n,children=cs,language='ARA',source_structure_path=path)
    children=tuple(annotate(n,(i,)) for i,n in enumerate(document.children))
    from tagged_pdf_extractor.domain.africa_rtl import restore_rtl_glyph_lines
    from tagged_pdf_extractor.domain.africa_numeric_text import restore_actual_text_decimals
    from tagged_pdf_extractor.domain.africa_inline_order import restore_inline_order
    from tagged_pdf_extractor.domain.africa_rtl_conditions import restore_rtl_conditions
    evidence=[]
    for repair in (restore_rtl_glyph_lines,restore_actual_text_decimals,restore_inline_order,restore_rtl_conditions):
        children,proof=repair(children,document.diagnostics)
        evidence.append(proof)
    from tagged_pdf_extractor.domain.tk_arabic_source import repair_tk_source, repair_tk_ownership, VERIFIED_SOURCE_SHA256
    children,proof=repair_tk_source(children,document.diagnostics,document.source_sha256)
    evidence.extend(proof)
    if document.source_sha256 == VERIFIED_SOURCE_SHA256:
        children,proof=repair_tk_ownership(children)
        evidence.append(proof)
    return replace(document,raw_children=document.children,children=children,
        diagnostics=(*document.diagnostics,*evidence,Diagnostic('warning','tk_arabic_source_order',
          'A3 cover precedes body; physical page order remains 1 then 2, with RTL source-line restoration.',
          {'source_token':'TK_ARA','doc_type':'A3','language':'ARA','semantic_content_page_order':[0,1]})))
