"""Source-verified XL A3 English repairs; original fragments remain auditable."""
from dataclasses import replace

from tagged_pdf_extractor.domain.models import ContentFragment, Diagnostic

SOURCE_SHA = 'dce6f5417123809235904c6ce3e7a1ff32aadc57df0a28e2a74d2c676b15a849'

def xl_scope(profile):
    return (profile is not None and profile.source_token == 'XL_ENG'
            and profile.doc_type == 'A3' and profile.languages == ('ENG',))

def fragments(node):
    if isinstance(node, ContentFragment):
        yield node
    else:
        for child in node.children:
            yield from fragments(child)

def _text(node):
    return ' '.join(''.join(f.text for f in fragments(node)).split())

def prepare_xl_sheet(document, profile):
    if not xl_scope(profile):
        return document
    if document.source_sha256 != SOURCE_SHA:
        raise ValueError('XL source revision needs review')
    if document.raw_children is not None:
        raise ValueError('XL sheet already prepared')
    operations = [d for d in document.diagnostics if d.code == 'xl_source_operations'
                  and d.context.get('sha256') == SOURCE_SHA]
    observed_runs = operations[0].context['runs'] if len(operations) == 1 else []
    changes = []

    def annotate(node, path):
        if isinstance(node, ContentFragment):
            return node
        return replace(node, source_structure_path=path, language='ENG',
            children=tuple(annotate(c, (*path, i)) for i, c in enumerate(node.children)))

    def visit(node):
        if isinstance(node, ContentFragment):
            if node.page_index != 1 or node.mcid not in {881, 1054}:
                return node
            runs = [r for r in observed_runs if r['mcid'] == node.mcid]
            before, expected = {
                881: ('7. 3', '7.3'),
                1054: ('[Precautions for using Wi-Fi 5.925 - 7 .125 (or 6.425) GHz]',
                       '[Precautions for using Wi-Fi 5.925 - 7.125 (or 6.425) GHz]'),
            }[node.mcid]
            source = ''.join(''.join(r['glyphs']) for r in runs)
            if (not runs or any(r.get('actual_text') for r in runs)
                    or len({r.get('operation_index') for r in runs}) != 1
                    or runs[0].get('operation_index') is None or source.strip() != expected
                    or node.text.strip() != before):
                raise ValueError('XL decimal source operation evidence needs review')
            changes.append({'kind': 'decimal_spacing', 'page_index': 1, 'mcid': node.mcid,
                            'source_parts': node.text_parts, 'operation_index': runs[0]['operation_index']})
            return replace(node, text_parts=tuple(p.replace(before, expected) for p in node.text_parts))
        children = tuple(visit(c) for c in node.children)
        if node.object_ref == '395 0 R':
            preceding, continuation = children[8:10]
            if (preceding.semantic_role != 'list' or continuation.object_ref != '549 0 R'
                    or _text(preceding) != '• Do not overload wall outlets, extension cords, or adapters beyond their voltage and capacity. It may cause fire or electric shock.'
                    or _text(continuation) != 'Refer to the power specifications section of the manual or the power supply label on the product for voltage and amperage information.'):
                raise ValueError('XL power source topology needs review')
            item = preceding.children[-1]
            body = item.children[-1]
            if item.semantic_role != 'list_item' or body.semantic_role != 'list_body':
                raise ValueError('XL power list ownership needs review')
            body = replace(body, children=(*body.children, replace(continuation, semantic_role='span')))
            item = replace(item, children=(*item.children[:-1], body))
            preceding = replace(preceding, children=(*preceding.children[:-1], item))
            children = (*children[:8], preceding, *children[10:])
            changes.append({'kind': 'power_continuation', 'source_path': continuation.source_structure_path})
        if node.object_ref == '417 0 R':
            spans = tuple(tuple(dict(c.attributes).get('/RowSpan', '1') for c in r.children) for r in children)
            expected = (('1','1','1'),) * 6 + (('1','1','2'), ('1','1')) + (('1','1','1'),) * 7
            if (node.semantic_role != 'table' or spans != expected
                    or _text(children[0]) != 'Country/Region Samsung Service Centre Website'
                    or _text(children[6].children[0]) != 'CAMBODIA'
                    or _text(children[7].children[0]) != 'LAOS'):
                raise ValueError('XL contact source table needs review')
            node = replace(node, attributes=(*node.attributes, ('review-table', 'source-spans')))
            changes.append({'kind': 'contact_source_spans', 'source_path': node.source_structure_path})
        if node.source_role == 'Article':
            if (tuple(c.object_ref for c in children) != ('397 0 R','395 0 R','398 0 R','399 0 R','400 0 R','401 0 R','402 0 R','403 0 R')
                    or _text(children[0]) != 'ENG' or _text(children[3]) != 'Simple User Guide'
                    or {f.page_index for c in children[2:] for f in fragments(c)} != {0}):
                raise ValueError('XL cover/body source layout needs review')
            children = (children[0], *children[2:], children[1])
            changes.append({'kind': 'cover_order', 'body_source_path': children[-1].source_structure_path})
        return replace(node, children=children)

    children = tuple(visit(annotate(c, (i,))) for i, c in enumerate(document.children))
    if {c['kind'] for c in changes} != {'decimal_spacing', 'power_continuation', 'contact_source_spans', 'cover_order'}:
        raise ValueError('XL reviewed source structures missing')
    return replace(document, raw_children=document.children, children=children,
        diagnostics=(*document.diagnostics, Diagnostic('warning', 'xl_source_structure',
            'Restored PDF-verified XL cover order, power ownership, contact spans and decimal spacing.',
            {'sha256': SOURCE_SHA, 'changes': changes})))
