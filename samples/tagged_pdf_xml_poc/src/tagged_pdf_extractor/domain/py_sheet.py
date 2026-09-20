"""Exact-source PY_ENRU cover order, paragraph ownership and token boundaries."""
from dataclasses import replace
import re
from tagged_pdf_extractor.domain.models import ContentFragment, Diagnostic, StructureElement

SOURCE_SHA = '973824f547bebb72fcd57e8c6ca50a455b2c8b83ea5392822fca2c461ddee1c1'


def py_scope(profile):
    return profile is not None and (profile.source_token, profile.doc_type, profile.languages) == ('PY_ENRU', 'A2', ('RUS', 'ENG'))


def fragments(node):
    if isinstance(node, ContentFragment):
        yield node
    else:
        for child in node.children:
            yield from fragments(child)


def prepare_py_sheet(document, profile):
    if not py_scope(profile):
        return document
    if document.source_sha256 != SOURCE_SHA:
        raise ValueError('PY source revision needs review')
    if document.raw_children is not None:
        raise ValueError('PY sheet already prepared')
    records = [r for d in document.diagnostics if d.code == 'py_source_operations'
               and d.context.get('sha256') == SOURCE_SHA for r in d.context['fragments']]
    runs = {(r['page_index'], r['mcid']): r['runs'] for r in records}
    if not runs:
        raise ValueError('PY source operation evidence is required')
    changes = []

    def visit(node, path):
        if isinstance(node, ContentFragment):
            observed = runs.get((node.page_index, node.mcid), ())
            if observed and not any(r['actual_text'] for r in observed):
                parts = tuple(re.sub(r'(?<=\d) +(?=[.,]\d)', '', p) for p in node.text_parts)
                source = ''.join(''.join(r['glyphs']) for r in observed)
                if parts != node.text_parts and ''.join(parts).strip() == source.strip():
                    changes.append({'kind': 'operation_spacing', 'page_index': node.page_index, 'mcid': node.mcid})
                    return replace(node, text_parts=parts)
            return node
        pages = {f.page_index for f in fragments(node)}
        language = profile.languages[next(iter(pages))] if len(pages) == 1 and pages <= {0, 1} else node.language
        children = tuple(visit(c, (*path, i)) for i, c in enumerate(node.children))
        for i in range(1, len(children)):
            previous, current = children[i-1:i+1]
            if not isinstance(previous, ContentFragment) or not isinstance(current, ContentFragment):
                continue
            suffix = next((s for s in ('network-', 'www.', 'ТВ-') if previous.text.endswith(s)), None)
            expected = {'network-': 'based smart services.', 'www.': 'samsung.com', 'ТВ-': 'контроллер'}.get(suffix)
            if not expected or previous.page_index != current.page_index or not current.text.startswith('\n') or not current.text.lstrip().startswith(expected):
                continue
            before = runs.get((previous.page_index, previous.mcid), ())
            after = runs.get((current.page_index, current.mcid), ())
            if (not before or not after or any(r['actual_text'] for r in (*before, *after))
                    or not ''.join(''.join(r['glyphs']) for r in before).endswith(suffix)
                    or not ''.join(''.join(r['glyphs']) for r in after).startswith(expected)):
                raise ValueError('PY token boundary operation evidence changed')
            children = (*children[:i], replace(current, join_previous=True), *children[i+1:])
            changes.append({'kind': 'source_token_boundary', 'page_index': current.page_index, 'mcid': current.mcid, 'previous_mcid': previous.mcid})
        if node.object_ref in {'691 0 R', '700 0 R'}:
            refs = ('1277 0 R','1278 0 R','1279 0 R') if language == 'RUS' else ('706 0 R','399 0 R','707 0 R')
            listing, continuation, following = children[7:10]
            if (tuple(c.object_ref for c in children[7:10]) != refs
                    or listing.semantic_role != 'list' or following.semantic_role != 'list'
                    or continuation.source_role != 'UnorderList_1-Bullet'
                    or len(listing.children) != 1):
                raise ValueError('PY power continuation topology needs review')
            item = listing.children[-1]; body = item.children[-1]
            if body.semantic_role != 'list_body':
                raise ValueError('PY power body needs review')
            body = replace(body, children=(*body.children, replace(continuation, semantic_role='span')))
            listing = replace(listing, children=(replace(item, children=(*item.children[:-1], body)),))
            children = (*children[:7], listing, *children[9:])
            changes.append({'kind': 'power_continuation', 'language': language, 'source_path': continuation.source_structure_path})
            intro_ref = '1362 0 R' if language == 'RUS' else '626 0 R'
            positions = [i for i,c in enumerate(children) if c.object_ref == intro_ref]
            if len(positions) != 1:
                raise ValueError('PY fee introduction needs review')
            i = positions[0]; intro, first, second = children[i:i+3]
            expected = ('1363 0 R','1364 0 R') if language == 'RUS' else ('627 0 R','628 0 R')
            if intro.source_role != 'Description-L' or tuple(c.object_ref for c in (first,second)) != expected or any(c.source_role != 'UnorderList_1-Bullet' for c in (first,second)):
                raise ValueError('PY fee conditions topology needs review')
            listing = StructureElement('ReviewList', 'list', language=language, children=tuple(
                StructureElement('ReviewItem', 'list_item', language=language, children=(c,)) for c in (first,second)))
            group = StructureElement('ReviewGroup', 'section', language=language,
                attributes=(('review-group','administration-fee-conditions'),), children=(intro,listing))
            children = (*children[:i],group,*children[i+3:])
            changes.append({'kind':'fee_conditions', 'language':language, 'source_paths':[first.source_structure_path,second.source_structure_path]})
        if node.source_role == 'Article':
            expected = ('690 0 R','691 0 R','692 0 R','693 0 R','694 0 R','695 0 R','696 0 R','697 0 R','698 0 R','699 0 R','700 0 R','639 0 R','701 0 R','702 0 R','688 0 R','703 0 R')
            if tuple(c.object_ref for c in children) != expected or any({f.page_index for f in fragments(c)} - {0 if i < 9 else 1} for i,c in enumerate(children)):
                raise ValueError('PY cover/body source layout needs review')
            order = (0,2,3,4,5,6,7,8,1,9,11,12,13,14,15,10)
            children = tuple(children[i] for i in order)
            changes.append({'kind':'cover_order','source_child_order':order})
        return replace(node, children=children, language=language, source_structure_path=path)

    children = tuple(visit(c,(i,)) for i,c in enumerate(document.children))
    return replace(document, children=children, raw_children=document.children,
        diagnostics=(*document.diagnostics, Diagnostic('warning','py_source_structure',
            'PY source-reviewed cover order and paragraph ownership; original raw structure retained.',
            {'sha256':SOURCE_SHA,'page_languages':['RUS','ENG'],'changes':changes})))
