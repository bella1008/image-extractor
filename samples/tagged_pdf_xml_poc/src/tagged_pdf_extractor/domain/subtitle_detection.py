from __future__ import annotations

from dataclasses import replace

from tagged_pdf_extractor.domain.models import (
    ContentFragment,
    StructureElement,
    SubtitleHint,
    TaggedDocument,
)
from tagged_pdf_extractor.domain.role_mapping import is_heading_candidate
from tagged_pdf_extractor.domain.typography import (
    normalize_font_weight,
    typography_evidence,
)


_SUBTITLE_INLINE_ROLES = frozenset({"span", "link"})


def detect_subtitle_hints(
    children: tuple[StructureElement | ContentFragment, ...],
) -> tuple[SubtitleHint, ...]:
    hints: list[SubtitleHint] = []
    seen_paths: set[tuple[int, ...]] = set()

    def visit_siblings(
        siblings: tuple[StructureElement | ContentFragment, ...],
        parent_path: tuple[int, ...],
    ) -> None:
        for index, child in enumerate(siblings):
            child_path = (*parent_path, index)
            if isinstance(child, StructureElement):
                if index + 1 < len(siblings):
                    following = siblings[index + 1]
                    table = _single_wrapped_table(child)
                    if table is not None and _is_paragraph(following):
                        table_path = (*child_path, 0)
                        for hint in _table_hints(table, table_path, following):
                            if hint.child_path not in seen_paths:
                                seen_paths.add(hint.child_path)
                                hints.append(hint)
                visit_siblings(child.children, child_path)

    visit_siblings(children, ())
    return tuple(hints)


def detect_table_subtitles(document: TaggedDocument) -> TaggedDocument:
    promoted_paths = {promotion.child_path for promotion in document.heading_promotions}
    hints = tuple(
        hint
        for hint in detect_subtitle_hints(document.children)
        if hint.child_path not in promoted_paths
    )
    return replace(document, subtitle_hints=hints)


def has_subtitle_block_descendant(paragraph: StructureElement) -> bool:
    def visit(children: tuple[StructureElement | ContentFragment, ...]) -> bool:
        for child in children:
            if not isinstance(child, StructureElement):
                continue
            if child.semantic_role not in _SUBTITLE_INLINE_ROLES:
                return True
            if visit(child.children):
                return True
        return False

    return visit(paragraph.children)


def subtitle_target_rejection(
    target: StructureElement | ContentFragment,
    *,
    promoted: bool = False,
) -> str | None:
    if (
        not isinstance(target, StructureElement)
        or target.semantic_role != "paragraph"
        or promoted
    ):
        return "not_unpromoted_paragraph"
    if is_heading_candidate(target.source_role):
        return "source_role_heading_candidate"
    if has_subtitle_block_descendant(target):
        return "block_descendant"
    return None


def _single_wrapped_table(wrapper: StructureElement) -> StructureElement | None:
    if not _is_paragraph(wrapper) or len(wrapper.children) != 1:
        return None
    child = wrapper.children[0]
    if isinstance(child, StructureElement) and child.semantic_role == "table":
        return child
    return None


def _is_paragraph(value: StructureElement | ContentFragment) -> bool:
    return isinstance(value, StructureElement) and value.semantic_role == "paragraph"


def _table_hints(
    table: StructureElement,
    table_path: tuple[int, ...],
    body: StructureElement,
) -> tuple[SubtitleHint, ...]:
    hints: list[SubtitleHint] = []

    def visit(element: StructureElement, path: tuple[int, ...]) -> None:
        if element.semantic_role == "table":
            return
        if element.semantic_role == "table_row":
            hint = _row_hint(element, path, body)
            if hint is not None:
                hints.append(hint)
            return
        for index, child in enumerate(element.children):
            if isinstance(child, StructureElement):
                visit(child, (*path, index))

    for index, child in enumerate(table.children):
        if isinstance(child, StructureElement):
            visit(child, (*table_path, index))
    return tuple(hints)


def _row_hint(
    row: StructureElement,
    row_path: tuple[int, ...],
    body: StructureElement,
) -> SubtitleHint | None:
    for index in range(len(row.children) - 1):
        figure_cell = row.children[index]
        text_cell = row.children[index + 1]
        if not (
            isinstance(figure_cell, StructureElement)
            and figure_cell.semantic_role == "table_cell"
            and isinstance(text_cell, StructureElement)
            and text_cell.semantic_role == "table_cell"
            and _is_figure_only_cell(figure_cell)
        ):
            continue

        if len(text_cell.children) < 2:
            continue
        title = text_cell.children[0]
        qualifier = text_cell.children[1]
        if not _is_paragraph(qualifier):
            continue
        if subtitle_target_rejection(title) is not None:
            continue

        title_text = _normalized_text(title)
        if not 1 <= len(title_text) <= 160:
            continue
        title_evidence = typography_evidence(title)
        body_evidence = typography_evidence(body)
        if title_evidence is None or body_evidence is None:
            continue
        if (
            len(title_evidence.observed_lines) > 2
            or title_evidence.font_weight < body_evidence.font_weight + 100
        ):
            continue

        return SubtitleHint(
            child_path=(*row_path, index + 1, 0),
            font_weight=title_evidence.font_weight,
            comparison_body_font_weight=body_evidence.font_weight,
            observed_line_count=len(title_evidence.observed_lines),
        )
    return None


def _is_figure_only_cell(cell: StructureElement) -> bool:
    found_figure = False
    found_text = False

    def visit(children: tuple[StructureElement | ContentFragment, ...]) -> None:
        nonlocal found_figure, found_text
        for child in children:
            if isinstance(child, ContentFragment):
                if child.text.strip():
                    found_text = True
            else:
                if child.semantic_role == "figure":
                    found_figure = True
                if child.actual_text and child.actual_text.strip():
                    found_text = True
                visit(child.children)

    visit(cell.children)
    return found_figure and not found_text


def _normalized_text(element: StructureElement) -> str:
    parts: list[str] = []

    def visit(children: tuple[StructureElement | ContentFragment, ...]) -> None:
        for child in children:
            if isinstance(child, ContentFragment):
                parts.extend(child.text_parts)
            else:
                visit(child.children)

    visit(element.children)
    return " ".join("".join(parts).split())
