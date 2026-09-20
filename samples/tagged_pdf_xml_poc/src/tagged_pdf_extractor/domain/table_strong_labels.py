"""Conservative source-typography labels inside repeated table value groups."""

from dataclasses import dataclass

from tagged_pdf_extractor.domain.models import (
    ContentFragment,
    StructureElement,
    TaggedDocument,
    TextDisplayHint,
)
from tagged_pdf_extractor.domain.paragraph_eligibility import (
    is_nonempty_inline_paragraph,
)
from tagged_pdf_extractor.domain.typography import TypographyEvidence, typography_evidence


_MAX_LABEL_LENGTH = 160
_MAX_LABEL_LINES = 2


@dataclass(frozen=True)
class _Record:
    element: StructureElement
    path: tuple[int, ...]
    text: str
    evidence: TypographyEvidence | None


def detect_table_strong_label_hints(
    document: TaggedDocument,
) -> tuple[TextDisplayHint, ...]:
    """Promote only repeated bold-label/value pairs within one source table."""

    hints: list[TextDisplayHint] = []
    for table, table_path in _tables(document.children):
        candidates: list[tuple[_Record, _Record]] = []
        for cell, cell_path in _cells(table, table_path):
            records = _direct_paragraphs(cell, cell_path)
            for label, detail in zip(records, records[1:]):
                if _is_label_for(label, detail):
                    candidates.append((label, detail))
        candidates.extend(_row_label_candidates(table, table_path))
        candidates = list(
            {label.path: (label, detail) for label, detail in candidates}.values()
        )
        if (
            len(candidates) < 2
            or len(
                {
                    detail.path
                    for _, detail in candidates
                    if _contains_ascii_digit(detail.text)
                }
            )
            < 2
        ):
            continue
        for label, detail in candidates:
            assert label.evidence is not None
            assert label.evidence.font_size is not None
            comparison_weight = (
                detail.evidence.font_weight if detail.evidence is not None else 400
            )
            comparison_size = (
                detail.evidence.font_size
                if detail.evidence is not None and detail.evidence.font_size is not None
                else label.evidence.font_size
            )
            hints.append(
                TextDisplayHint(
                    child_path=label.path,
                    display_role="strong_label",
                    font_weight=label.evidence.font_weight,
                    font_size=label.evidence.font_size,
                    comparison_body_font_weight=comparison_weight,
                    comparison_body_font_size=comparison_size,
                    reason="repeated_table_label_value_typography",
                )
            )
    return tuple(sorted(hints, key=lambda hint: hint.child_path))


def _contains_ascii_digit(value: str) -> bool:
    return any("0" <= character <= "9" for character in value)


def _is_label_for(label: _Record, detail: _Record) -> bool:
    return (
        1 <= len(label.text) <= _MAX_LABEL_LENGTH
        and label.evidence is not None
        and len(label.evidence.observed_lines) <= _MAX_LABEL_LINES
        and label.evidence.font_size is not None
        and (
            (
                detail.evidence is not None
                and detail.evidence.font_size is not None
                and label.evidence.font_weight > detail.evidence.font_weight
                and label.evidence.font_size >= detail.evidence.font_size
            )
            or _source_bold_role_pair(label.element, detail.element)
        )
    )


def _source_bold_role_pair(
    label: StructureElement,
    detail: StructureElement,
) -> bool:
    return (
        label.source_role.endswith("-B")
        and detail.source_role == label.source_role.removesuffix("-B")
    )


def _row_label_candidates(
    table: StructureElement,
    table_path: tuple[int, ...],
) -> tuple[tuple[_Record, _Record], ...]:
    if any(
        token in _text(table).lower()
        for token in ("http://", "https://", "www.")
    ):
        return ()
    candidates: list[tuple[_Record, _Record]] = []
    for row_index, row in enumerate(table.children):
        if not isinstance(row, StructureElement) or row.semantic_role != "table_row":
            continue
        cells = tuple(
            (cell, (*table_path, row_index, cell_index))
            for cell_index, cell in enumerate(row.children)
            if isinstance(cell, StructureElement)
            and cell.semantic_role in {"table_cell", "table_header"}
        )
        if len(cells) < 2:
            continue
        labels = _direct_paragraphs(*cells[0])
        details = tuple(
            record
            for cell, cell_path in cells[1:]
            for record in _direct_paragraphs(cell, cell_path)
        )
        if not labels or not details:
            continue
        detail = next((record for record in details if record.evidence is not None), details[0])
        qualified = tuple(label for label in labels if _is_label_for(label, detail))
        if len(qualified) != len(labels):
            continue
        candidates.extend((label, detail) for label in qualified)
    return tuple(candidates)


def _direct_paragraphs(
    cell: StructureElement,
    cell_path: tuple[int, ...],
) -> tuple[_Record, ...]:
    records: list[_Record] = []
    for index, child in enumerate(cell.children):
        if not isinstance(child, StructureElement) or not is_nonempty_inline_paragraph(child):
            continue
        text = _text(child)
        evidence = typography_evidence(child)
        if not text:
            continue
        records.append(_Record(child, (*cell_path, index), text, evidence))
    return tuple(records)


def _tables(
    children: tuple[StructureElement | ContentFragment, ...],
    parent_path: tuple[int, ...] = (),
) -> tuple[tuple[StructureElement, tuple[int, ...]], ...]:
    found: list[tuple[StructureElement, tuple[int, ...]]] = []
    stack = [(children, parent_path)]
    while stack:
        siblings, path = stack.pop()
        for index in range(len(siblings) - 1, -1, -1):
            child = siblings[index]
            if not isinstance(child, StructureElement):
                continue
            child_path = (*path, index)
            if child.semantic_role == "table":
                found.append((child, child_path))
            stack.append((child.children, child_path))
    return tuple(sorted(found, key=lambda item: item[1]))


def _cells(
    table: StructureElement,
    table_path: tuple[int, ...],
) -> tuple[tuple[StructureElement, tuple[int, ...]], ...]:
    found: list[tuple[StructureElement, tuple[int, ...]]] = []
    stack = [(table.children, table_path)]
    while stack:
        siblings, path = stack.pop()
        for index in range(len(siblings) - 1, -1, -1):
            child = siblings[index]
            if not isinstance(child, StructureElement):
                continue
            child_path = (*path, index)
            if child.semantic_role == "table":
                continue
            if child.semantic_role == "table_cell":
                found.append((child, child_path))
                continue
            stack.append((child.children, child_path))
    return tuple(sorted(found, key=lambda item: item[1]))


def _text(element: StructureElement) -> str:
    parts: list[str] = []
    stack = list(reversed(element.children))
    while stack:
        child = stack.pop()
        if isinstance(child, ContentFragment):
            parts.extend(child.text_parts)
        else:
            stack.extend(reversed(child.children))
    return " ".join("".join(parts).split())
