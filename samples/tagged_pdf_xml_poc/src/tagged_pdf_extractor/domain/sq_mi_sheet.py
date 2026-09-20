"""Source-scoped SQ MI Hebrew/Arabic A2 semantic interpretation."""
from dataclasses import replace
from tagged_pdf_extractor.domain.models import ContentFragment, Diagnostic
from tagged_pdf_extractor.domain.tk_sheet import fragments
from tagged_pdf_extractor.domain.role_mapping import is_heading_candidate, heading_candidate_level

SOURCE_SHA='28831342b1433d01fbc93a8276bb4de1692dbc7cc7c5996d95204a468b9bcf18'

def sq_mi_scope(profile):
    return profile is not None and (profile.source_token,profile.doc_type,profile.languages)==('SQ MI_HEAR','A2',('HEB','ARA'))

def prepare_sq_mi_sheet(document,profile):
    if not sq_mi_scope(profile):return document
    if document.source_sha256!=SOURCE_SHA:raise ValueError('SQ MI source revision needs review')
    if document.raw_children is not None:raise ValueError('SQ MI already prepared')
    changes=[]
    def annotate(n,path):
        if isinstance(n,ContentFragment):return n
        pages={f.page_index for f in fragments(n)}
        language=profile.languages[next(iter(pages))] if len(pages)==1 and pages<={0,1} else None
        children=tuple(annotate(c,(*path,i)) for i,c in enumerate(n.children))
        if n.source_role=='Article':
            expected=['623 0 R','624 0 R','625 0 R','626 0 R','627 0 R','628 0 R','629 0 R','630 0 R','631 0 R','632 0 R','633 0 R','610 0 R','634 0 R','635 0 R','621 0 R','636 0 R']
            if [c.object_ref for c in children]!=expected:raise ValueError('SQ MI cover topology changed')
            children=(children[0],*children[2:9],children[1],children[9],*children[11:],children[10])
        if is_heading_candidate(n.source_role) and 'heading' in n.source_role.lower():
            n=replace(n,semantic_role='heading',heading_level=heading_candidate_level(n.source_role))
            changes.append({'kind':'source_heading_role','ref':n.object_ref,'source_role':n.source_role})
        if n.object_ref in {'1641 0 R','1500 0 R','1402 0 R','1310 0 R','1268 0 R'} and language=='HEB':
            n=replace(n,attributes=(*n.attributes,('review-compact-label-sha256',SOURCE_SHA)))
        return replace(n,children=children,language=language,source_structure_path=path)
    children=tuple(annotate(c,(i,)) for i,c in enumerate(document.children))
    from tagged_pdf_extractor.domain.africa_rtl import restore_rtl_glyph_lines
    from tagged_pdf_extractor.domain.africa_inline_order import restore_inline_order
    from tagged_pdf_extractor.domain.africa_numeric_text import restore_actual_text_decimals
    from tagged_pdf_extractor.domain.africa_rtl_conditions import restore_rtl_conditions
    proofs=[]
    children,proof=restore_rtl_glyph_lines(children,document.diagnostics,rtl_classes=frozenset({'AL','R'}),languages=('HEB','ARA'));proofs.append(proof)
    children,proof=restore_inline_order(children,document.diagnostics,rtl_classes=frozenset({'AL','R'}),languages=('HEB','ARA'),roles=frozenset({'paragraph','span','list_body','heading'}));proofs.append(proof)
    for repair in (restore_actual_text_decimals,restore_rtl_conditions):
        children,proof=repair(children,document.diagnostics);proofs.append(proof)
    runs={(d.context['page_index'],r['mcid']):[] for d in document.diagnostics if d.code=='africa_rtl_glyph_source' for line in d.context['lines'] for r in line['runs']}
    for d in document.diagnostics:
        if d.code=='africa_rtl_glyph_source':
            for line in d.context['lines']:
                for r in line['runs']:runs[d.context['page_index'],r['mcid']].append(r)
    labels={**{(0,m):f'{i:02}' for i,m in enumerate([708,81,644,885,445],1)},**{(1,m):f'{i:02}' for i,m in enumerate([1830,1208,1764,2004,1580],1)}}
    def repair(n):
        if isinstance(n,ContentFragment):
            key=n.page_index,n.mcid
            if key not in labels:return n
            label=labels[key];value=label[1];rr=runs[key]
            # This exact revision draws ASCII-encoded 01..05 with a broken
            # font ToUnicode map. Raw bytes, geometry, and source crops agree.
            if bytes.fromhex(''.join(r['raw_hex'] for r in rr)).decode('ascii')!=label or n.text.strip()!=value:
                raise ValueError('SQ MI chapter source glyphs changed')
            visible=[s for p,s in zip(n.text_parts,n.text_styles) if p.strip()]
            style=next((s for s in visible if s.font_size==16.0),None)
            if style is None:raise ValueError('SQ MI chapter typography changed')
            changes.append({'kind':'visible_chapter_glyphs','page_index':key[0],'mcid':key[1],'before':n.text,'after':value,'source_runs':rr})
            return replace(n,text_parts=(value,),text_styles=(style,),text_bboxes=(n.bbox,))
        cs=tuple(repair(c) for c in n.children)
        if n.object_ref in {'624 0 R','633 0 R'}:
            ref,prev=('1121 0 R','1120 0 R') if n.language=='HEB' else ('348 0 R','639 0 R')
            i=next(i for i,c in enumerate(cs) if c.object_ref==ref)
            listing,continuation=cs[i-1:i+1];item=listing.children[-1];body=item.children[-1]
            if listing.object_ref!=prev or body.semantic_role!='list_body':raise ValueError('SQ MI power ownership changed')
            body=replace(body,children=(*body.children,replace(continuation,semantic_role='span')))
            item=replace(item,children=(*item.children[:-1],body))
            cs=(*cs[:i-1],replace(listing,children=(*listing.children[:-1],item)),*cs[i+1:])
            changes.append({'kind':'power_continuation','source_path':continuation.source_structure_path})
        return replace(n,children=cs)
    children=tuple(repair(c) for c in children)
    from tagged_pdf_extractor.domain.sq_mi_source_text import repair_sq_mi_source
    children,proof=repair_sq_mi_source(children,document.diagnostics);proofs.append(proof)
    from tagged_pdf_extractor.domain.sq_mi_brackets import repair_sq_brackets
    children,proof=repair_sq_brackets(children,document.diagnostics);proofs.append(proof)
    from tagged_pdf_extractor.domain.sq_mi_spec_text import repair_sq_mi_specs
    children,proof=repair_sq_mi_specs(children,document.diagnostics);proofs.append(proof)
    from tagged_pdf_extractor.domain.sq_mi_inline import wrap_sq_inline
    children=wrap_sq_inline(children)
    return replace(document,raw_children=document.children,children=children,
        diagnostics=(*document.diagnostics,*proofs,Diagnostic('warning','sq_mi_source_structure',
            'Source verified HEB/ARA cover and body order; heading roles preserve observed strings.',
            {'sha256':SOURCE_SHA,'page_languages':['HEB','ARA'],'changes':changes})))
