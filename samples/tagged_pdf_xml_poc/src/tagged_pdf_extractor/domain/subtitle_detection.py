from __future__ import annotations

from dataclasses import replace
import re

from tagged_pdf_extractor.domain.models import (
    ContentFragment,
    StructureElement,
    SubtitleHint,
    TaggedDocument,
)


_TRAILING_WEIGHT = re.compile(r"(?:^|[-_\s])([1-9]00)$")
_KEYWORD_WEIGHTS = (
    ("black", 900),
    ("extrabold", 800),
    ("semibold", 600),
    ("demibold", 600),
    ("bold", 700),
    ("medium", 500),
    ("regular", 400),
    ("normal", 400),
    ("light", 300),
)


def normalize_font_weight(font_name: str | None) -> int | None:
    if not font_name:
        return None
    normalized = font_name.rsplit("+", 1)[-1].strip().lower()
    numeric = _TRAILING_WEIGHT.search(normalized)
    if numeric:
        return int(numeric.group(1))
    compact = re.sub(r"[^a-z]", "", normalized)
    for keyword, weight in _KEYWORD_WEIGHTS:
        if compact.endswith(keyword):
            return weight
    return None


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
    return replace(document, subtitle_hints=detect_subtitle_hints(document.children))


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
        if element.semantic_role == "table_row":
            hint = _row_hint(element, path, body)
            if hint is not None:
                hints.append(hint)
            return
        for index, child in enumerate(element.children):
            if isinstance(child, StructureElement):
                visit(child, (*path, index))

    visit(table, table_path)
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
        if not (_is_paragraph(title) and _is_paragraph(qualifier)):
            continue

        title_text = _normalized_text(title)
        if not 1 <= len(title_text) <= 160:
            continue
        title_evidence = _typography_evidence(title)
        body_evidence = _typography_evidence(body)
        if title_evidence is None or body_evidence is None:
            continue
        title_weight, title_lines = title_evidence
        body_weight, _ = body_evidence
        if len(title_lines) > 2 or title_weight < body_weight + 100:
            continue

        return SubtitleHint(
            child_path=(*row_path, index + 1, 0),
            font_weight=title_weight,
            comparison_body_font_weight=body_weight,
            observed_line_count=len(title_lines),
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
                if any(
                    value and value.strip()
                    for value in (child.title, child.alternate_text, child.actual_text)
                ):
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


def _typography_evidence(
    element: StructureElement,
) -> tuple[int, set[tuple[int, int]]] | None:
    samples: list[tuple[int, int]] = []
    line_keys: set[tuple[int, int]] = set()
    valid = True

    def visit(children: tuple[StructureElement | ContentFragment, ...]) -> None:
        nonlocal valid
        for child in children:
            if isinstance(child, StructureElement):
                visit(child.children)
                continue
            for part_index, text in enumerate(child.text_parts):
                visible_count = sum(not character.isspace() for character in text)
                if visible_count == 0:
                    continue
                if (
                    child.page_index < 0
                    or child.mcid is None
                    or not child.text_styles
                    or part_index >= len(child.text_styles)
                ):
                    valid = False
                    continue
                weight = normalize_font_weight(child.text_styles[part_index].font_name)
                if weight is None:
                    valid = False
                    continue
                samples.append((weight, visible_count))
                line_keys.add((child.page_index, child.mcid))

    visit(element.children)
    if not valid or not samples or not line_keys:
        return None
    return _weighted_median(samples), line_keys


def _weighted_median(samples: list[tuple[int, int]]) -> int:
    ordered = sorted(samples)
    total = sum(count for _, count in ordered)
    threshold = (total + 1) // 2
    cumulative = 0
    for weight, count in ordered:
        cumulative += count
        if cumulative >= threshold:
            return weight
    raise AssertionError("weighted median requires at least one sample")
