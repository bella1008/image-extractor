"""Restore two source-proven CE paragraph relationships without changing raw tags."""
from dataclasses import replace

from tagged_pdf_extractor.domain.ce_paragraph_source import CE_PARAGRAPH_SOURCE
from tagged_pdf_extractor.domain.models import ContentFragment, Diagnostic, StructureElement


def repair_ce_paragraph_ownership(document, profile):
    from tagged_pdf_extractor.domain.ce_book import ce_book_scope, fragments
    if not ce_book_scope(profile):
        return document
    changes = []

    def text(node):
        return ' '.join(''.join(f.text for f in fragments(node)).split())

    def same_page_language(nodes):
        return (all(isinstance(n, StructureElement) for n in nodes)
                and len({n.language for n in nodes}) == 1
                and len({f.page_index for n in nodes for f in fragments(n)}) == 1)

    def paragraph(node):
        return (isinstance(node, StructureElement) and node.semantic_role == 'paragraph'
                and node.source_role == 'UnorderList_1-Bullet')

    def visit(node):
        if isinstance(node, ContentFragment):
            return node
        siblings = tuple(visit(c) for c in node.children)
        result = []
        i = 0
        while i < len(siblings):
            current = siblings[i]
            language = current.language if isinstance(current, StructureElement) else None
            anchor = CE_PARAGRAPH_SOURCE.get(language)
            if anchor and paragraph(current) and text(current) == anchor['power_continuation'] and result:
                preceding = result[-1]
                following = siblings[i + 1] if i + 1 < len(siblings) else None
                if (isinstance(preceding, StructureElement) and preceding.semantic_role == 'list'
                        and isinstance(following, StructureElement) and following.semantic_role == 'list'
                        and following.language == language
                        and same_page_language((preceding, current))
                        and text(preceding) == anchor['power_preceding']
                        and preceding.children
                        and isinstance(preceding.children[-1], StructureElement)):
                    item = preceding.children[-1]
                    bodies = [c for c in item.children if isinstance(c, StructureElement)
                              and c.semantic_role == 'list_body']
                    if item.semantic_role == 'list_item' and len(bodies) == 1:
                        body = bodies[0]
                        continuation = replace(current, semantic_role='span')
                        body_new = replace(body, children=(*body.children, continuation))
                        item_new = replace(item, children=tuple(body_new if c is body else c for c in item.children))
                        result[-1] = replace(preceding, children=(*preceding.children[:-1], item_new))
                        changes.append({'kind': 'power_continuation', 'language': language,
                                        'source_path': current.source_structure_path,
                                        'parent_source_path': body.source_structure_path})
                        i += 1
                        continue
            if anchor and isinstance(current, StructureElement) and current.source_role == 'Description-L' and text(current) == anchor['fee_intro']:
                conditions = siblings[i + 1:i + 3]
                if (len(conditions) == 2 and all(paragraph(c) for c in conditions)
                        and same_page_language((current, *conditions))
                        and [text(c) for c in conditions] == anchor['fee_items']):
                    items = tuple(StructureElement('CEReviewItem', 'list_item', language=language,
                                                   children=(c,)) for c in conditions)
                    listing = StructureElement('CEReviewList', 'list', language=language, children=items)
                    group = StructureElement('CEReviewGroup', 'section', language=language,
                                             attributes=(('review-group', 'administration-fee-conditions'),),
                                             children=(current, listing))
                    result.append(group)
                    changes.append({'kind': 'fee_conditions', 'language': language,
                                    'intro_source_path': current.source_structure_path,
                                    'condition_source_paths': [c.source_structure_path for c in conditions]})
                    i += 3
                    continue
            result.append(current)
            i += 1
        return replace(node, children=tuple(result))

    children = tuple(visit(c) for c in document.children)
    evidence = Diagnostic('warning', 'ce_paragraph_ownership',
                          'Reparented only exact, source-reviewed CE paragraph groups.',
                          {'changes': changes})
    return replace(document, children=children, diagnostics=(*document.diagnostics, evidence))
