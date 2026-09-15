"""Restore source-reviewed paragraph relationships in explicitly verified profiles.

Run before any path-based heading/display hints are built. CE keeps its earlier
repair; this module covers the eight subsequently reviewed cross-buyer gaps.
"""
from dataclasses import replace

from tagged_pdf_extractor.domain.language_interval_resolution import resolve_language_intervals
from tagged_pdf_extractor.domain.models import ContentFragment, Diagnostic, StructureElement
from tagged_pdf_extractor.domain.numbered_heading_promotion import promote_numbered_chapter_headings
from tagged_pdf_extractor.domain.paragraph_eligibility import is_nonempty_inline_paragraph
from tagged_pdf_extractor.domain.verified_paragraph_source import FEE_SOURCE, POWER_SOURCE

_PROFILES = {
    ('ZC_L02', 'A2'): ('ENG', 'C-FRA'),
    ('AFRICA_L05', 'BOOK'): ('ENG', 'FRA', 'SPA', 'POR', 'ARA'),
    ('ZG XN ZT_L05', 'BOOK'): ('ENG', 'DEU', 'FRA', 'ITA', 'DUT'),
    ('XU_ENG', 'A3'): ('ENG',),
}


def _fragments(node):
    if isinstance(node, ContentFragment):
        yield node
    else:
        for child in node.children:
            yield from _fragments(child)


def _text(node):
    return ' '.join(''.join(f.text for f in _fragments(node)).split())


def _paragraph(node, role):
    return (isinstance(node, StructureElement) and node.source_role == role
            and is_nonempty_inline_paragraph(node))


def repair_verified_paragraph_ownership(document, profile):
    if profile is None or _PROFILES.get((profile.source_token, profile.doc_type)) != profile.languages:
        return document
    # These PDFs tag numbered headings as ordinary paragraphs. Resolve language
    # evidence on a temporary promoted view; discard its path hints because
    # reparenting below changes paths. The application builds final hints later.
    resolution = resolve_language_intervals(profile, promote_numbered_chapter_headings(document))
    if resolution.diagnostic is not None:
        return document

    def language_of(nodes):
        pages = {f.page_index for node in nodes for f in _fragments(node)}
        if len(pages) != 1:
            return None
        page = next(iter(pages))
        languages = (profile.languages if profile.language_count == 1 else tuple(
            interval.language for interval in resolution.intervals
            if interval.start_page_index <= page <= interval.end_page_index))
        if len(languages) != 1:
            return None
        language = languages[0]
        def compatible(node):
            return (isinstance(node, ContentFragment) or (
                (node.language is None or node.language == language)
                and all(compatible(child) for child in node.children)))
        return language if all(compatible(node) for node in nodes) else None

    def annotate(node, path):
        if isinstance(node, ContentFragment):
            return node
        return replace(node, source_structure_path=node.source_structure_path or path,
                       children=tuple(annotate(c, (*path, i)) for i, c in enumerate(node.children)))

    changes = []

    def visit(node):
        if isinstance(node, ContentFragment):
            return node
        siblings = tuple(visit(c) for c in node.children)
        result = []
        index = 0
        while index < len(siblings):
            current = siblings[index]
            language = language_of((current,))
            key = (profile.source_token, profile.doc_type, language)
            power = POWER_SOURCE.get(key)
            following = siblings[index + 1] if index + 1 < len(siblings) else None
            if (power and _paragraph(current, 'UnorderList_1-Bullet')
                    and _text(current) == power[1] and result
                    and isinstance(result[-1], StructureElement)
                    and result[-1].semantic_role == 'list'
                    and isinstance(following, StructureElement) and following.semantic_role == 'list'
                    and language_of((result[-1], current, following)) == language
                    and _text(result[-1]) == power[0]):
                preceding = result[-1]
                item = preceding.children[-1] if preceding.children else None
                bodies = ([c for c in item.children if isinstance(c, StructureElement)
                           and c.semantic_role == 'list_body']
                          if isinstance(item, StructureElement) and item.semantic_role == 'list_item' else [])
                # Appending inside an earlier body would move the continuation
                # ahead of trailing item content. Accept the observed final-body
                # shape only (including empty trailing wrappers is unnecessary).
                if len(bodies) == 1 and item.children[-1] is bodies[0]:
                    body = bodies[0]
                    updated_body = replace(body, children=(*body.children, replace(current, semantic_role='span')))
                    updated_item = replace(item, children=tuple(updated_body if c is body else c for c in item.children))
                    result[-1] = replace(preceding, children=(*preceding.children[:-1], updated_item))
                    changes.append(dict(kind='power_continuation', language=language,
                                        source_path=current.source_structure_path,
                                        parent_source_path=body.source_structure_path))
                    index += 1
                    continue
            fee = FEE_SOURCE.get(key)
            conditions = siblings[index + 1:index + 3]
            if (fee and _paragraph(current, 'Description-L') and _text(current) == fee[0]
                    and len(conditions) == 2
                    and all(_paragraph(c, 'UnorderList_1-Bullet') for c in conditions)
                    and language_of((current, *conditions)) == language
                    and tuple(_text(c) for c in conditions) == fee[1:]):
                listing = StructureElement('ReviewList', 'list', language=language, children=tuple(
                    StructureElement('ReviewItem', 'list_item', language=language, children=(c,))
                    for c in conditions))
                result.append(StructureElement('ReviewGroup', 'section', language=language,
                    attributes=(('review-group', 'administration-fee-conditions'),),
                    children=(current, listing)))
                changes.append(dict(kind='fee_conditions', language=language,
                                    intro_source_path=current.source_structure_path,
                                    condition_source_paths=[c.source_structure_path for c in conditions]))
                index += 3
                continue
            result.append(current)
            index += 1
        return replace(node, children=tuple(result))

    children = tuple(visit(annotate(c, (i,))) for i, c in enumerate(document.children))
    if not changes:
        return document
    diagnostic = Diagnostic('warning', 'verified_paragraph_ownership',
        'Restored source-reviewed paragraph ownership without changing source fragments.',
        dict(source_token=profile.source_token, doc_type=profile.doc_type, changes=changes))
    return replace(document, children=children,
                   raw_children=document.raw_children if document.raw_children is not None else document.children,
                   diagnostics=(*document.diagnostics, diagnostic))
