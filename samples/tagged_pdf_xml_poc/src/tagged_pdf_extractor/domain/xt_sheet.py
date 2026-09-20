"""Exact XT A2 source: cover order and operation-backed Thai glyph recovery."""
from dataclasses import replace
import re
from tagged_pdf_extractor.domain.models import ContentFragment, Diagnostic, TextStyle

SOURCE_SHA = '9a1f4a2bd1d5f097c14768510a44b51147a7b57249d689fefcfacbe7df9c65da'

def xt_scope(profile):
    return (profile is not None and profile.source_token == 'XT_L02'
            and profile.doc_type == 'A2' and profile.languages == ('ENG', 'THA'))

def _fragments(node):
    if isinstance(node, ContentFragment):
        yield node
    else:
        for child in node.children:
            yield from _fragments(child)

def _thai(character):
    return bool(character) and '\u0e00' <= character <= '\u0e7f'

def prepare_xt_sheet(document, profile):
    if not xt_scope(profile):
        return document
    if document.source_sha256 != SOURCE_SHA:
        raise ValueError('XT source revision needs review')
    if document.raw_children is not None:
        raise ValueError('XT sheet already prepared')
    records = [record for d in document.diagnostics if d.code == 'xt_source_operations'
               and d.context.get('sha256') == SOURCE_SHA for record in d.context.get('fragments', ())]
    runs = {(r['page_index'], r['mcid']): r['runs'] for r in records}
    if not runs:
        raise ValueError('XT glyph evidence is required')
    changes = []

    def visit(node, path):
        if isinstance(node, ContentFragment):
            observed = runs.get((node.page_index, node.mcid), ())
            if node.page_index == 1 and node.text.strip() and not observed:
                raise ValueError('XT glyph evidence missing for Thai fragment')
            if node.page_index == 1 and observed:
                styles = {(r['font_name'], r['font_size']) for r in observed}
                if len(styles) != 1 or any(r['glyph_boxes'] is None for r in observed):
                    raise ValueError('XT glyph evidence typography needs review')
                value = ''.join(''.join(r['verified_glyphs']) for r in observed)
                if '\ufffd' in value:
                    raise ValueError('XT glyph evidence retains undecodable text')
                boxes = [b for r in observed for b in r['glyph_boxes']]
                bbox = (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))
                source_styles = {s for part,s in zip(node.text_parts, node.text_styles) if part.strip() and s.font_size}
                if not value.strip():
                    source_styles = {TextStyle(observed[0]['font_name'], observed[0]['font_size'])}
                if len(source_styles) != 1:
                    raise ValueError('XT glyph evidence effective typography needs review')
                style = next(iter(source_styles))
                changes.append({'kind': 'thai_source_glyphs', 'page_index': 1, 'mcid': node.mcid})
                return replace(node, text_parts=(value,), text_styles=(style,), text_bboxes=(bbox,))
            # English decimal spacing and the network-based token are separately
            # verified against original operations, not broad text replacements.
            if observed and not any(r['actual_text'] for r in observed):
                source = ''.join(''.join(r['verified_glyphs']) for r in observed)
                parts = tuple(re.sub(r'(?<=\d) +(?=[.,]\d)', '', p) for p in node.text_parts)
                if parts != node.text_parts and ''.join(parts).strip() == source.strip():
                    changes.append({'kind': 'english_operation_spacing', 'mcid': node.mcid})
                    return replace(node, text_parts=parts)
            return node
        pages = {f.page_index for f in _fragments(node)}
        language = profile.languages[next(iter(pages))] if len(pages) == 1 and pages <= {0, 1} else node.language
        children = tuple(visit(c, (*path, i)) for i, c in enumerate(node.children))
        def inline(items):
            for child in items:
                if isinstance(child, ContentFragment):
                    yield child
                elif child.semantic_role in {'span', 'link'}:
                    yield from inline(child.children)
                else:
                    yield None
        replacements = {}
        previous = None
        for child in inline(children):
            if child is None:
                previous = None
                continue
            if not child.text:
                continue
            if previous is not None and child.page_index == previous.page_index:
                a, b = previous.text, child.text
                thai_join = child.page_index == 1 and _thai(a[-1]) and _thai(b[0])
                network = a.endswith('network-') and b.lstrip().startswith('based smart services.')
                if thai_join or network:
                    replacements[id(child)] = replace(child, join_previous=True)
            previous = child
        def substitute(child):
            if isinstance(child, ContentFragment):
                return replacements.get(id(child), child)
            if child.semantic_role in {'span', 'link'}:
                return replace(child, children=tuple(substitute(c) for c in child.children))
            return child
        children = tuple(substitute(c) for c in children)
        if node.object_ref in {'1093 0 R', '628 0 R'}:
            if (node.semantic_role != 'table' or len(children) != 2
                    or any(r.semantic_role != 'table_row' or len(r.children) != 2
                           or any(c.semantic_role != 'table_cell' for c in r.children) for r in children)):
                raise ValueError('XT contact table topology needs review')
            node = replace(node, attributes=(*node.attributes, ('review-table', 'source-spans')))
            changes.append({'kind': 'contact_source_spans', 'source_path': path})
        if node.object_ref in {'614 0 R', '622 0 R'}:
            preceding, continuation, following = children[8:11]
            expected = ('1122 0 R', '1123 0 R', '1124 0 R') if language == 'ENG' else ('637 0 R', '336 0 R', '638 0 R')
            if (tuple(c.object_ref for c in (preceding, continuation, following)) != expected
                    or preceding.semantic_role != 'list' or following.semantic_role != 'list'
                    or continuation.source_role != 'UnorderList_1-Bullet'
                    or len(preceding.children) != 1):
                raise ValueError('XT power continuation topology needs review')
            item = preceding.children[-1]
            body = item.children[-1]
            if body.semantic_role != 'list_body':
                raise ValueError('XT power continuation body needs review')
            body = replace(body, children=(*body.children, continuation))
            item = replace(item, children=(*item.children[:-1], body))
            preceding = replace(preceding, children=(item,))
            children = (*children[:8], preceding, *children[10:])
            changes.append({'kind': 'power_continuation', 'language': language,
                            'source_path': continuation.source_structure_path})
        if node.source_role == 'Article':
            expected = ('612 0 R','613 0 R','614 0 R','615 0 R','616 0 R','617 0 R','618 0 R','619 0 R','620 0 R',
                        '621 0 R','97 0 R','622 0 R','623 0 R','624 0 R','625 0 R','626 0 R','610 0 R')
            if tuple(c.object_ref for c in children) != expected or any(
                    {f.page_index for f in _fragments(c)} - {0 if i < 9 else 1} for i,c in enumerate(children)):
                raise ValueError('XT cover/body source layout needs review')
            order = (0,1,3,4,5,6,7,2,8,9,10,12,13,14,15,11,16)
            children = tuple(children[i] for i in order)
            changes.append({'kind': 'cover_order', 'source_child_order': order})
        return replace(node, source_structure_path=path, language=language, children=children)
    children = tuple(visit(c, (i,)) for i,c in enumerate(document.children))
    return replace(document, children=children, raw_children=document.children,
                   diagnostics=(*document.diagnostics, Diagnostic('warning', 'xt_source_structure',
                       'Verified XT cover order and Thai glyph recovery; original structure retained.',
                       {'sha256': SOURCE_SHA, 'changes': changes})))
