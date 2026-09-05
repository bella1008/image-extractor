from __future__ import annotations

from dataclasses import dataclass, replace

from tagged_pdf_extractor.domain.models import (
    ContentFragment,
    LineBreakHint,
    StructureElement,
    TaggedDocument,
    TextDisplayHint,
)
from tagged_pdf_extractor.domain.profile_scope import review_formatting_scope
from tagged_pdf_extractor.domain.role_mapping import is_heading_candidate
from tagged_pdf_extractor.domain.typography import (
    TypographyEvidence,
    typography_evidence,
)


_INLINE_ROLES = frozenset({"span", "link"})
_BLOCK_ROLES = frozenset({"list", "table", "section"})
_MAX_SHORT_TEXT_LENGTH = 160
_MAX_SHORT_LINE_COUNT = 2


@dataclass(frozen=True)
class _ParagraphRecord:
    element: StructureElement
    path: tuple[int, ...]
    text: str
    evidence: TypographyEvidence


def apply_profile_review_formatting(document: TaggedDocument) -> TaggedDocument:
    if not review_formatting_scope(document.source_path).enabled:
        return document
    return replace(
        document,
        line_break_hints=detect_rf_line_break_hints(document.children),
        text_display_hints=detect_form_cluster_hints(document),
    )


def detect_form_cluster_hints(
    document: TaggedDocument,
) -> tuple[TextDisplayHint, ...]:
    hints: list[TextDisplayHint] = []
    for section, section_path in _structural_sections(document.children):
        section_hints = _section_form_cluster_hints(
            section,
            section_path,
            document,
        )
        hints.extend(section_hints)
    return tuple(sorted(hints, key=lambda hint: hint.child_path))


def _section_form_cluster_hints(
    section: StructureElement,
    section_path: tuple[int, ...],
    document: TaggedDocument,
) -> tuple[TextDisplayHint, ...]:
    title = _first_direct_text_child(section, section_path)
    if title is None or not _is_short(title):
        return ()
    if _heading_conflict(title.element):
        return ()

    paragraphs = _leaf_paragraph_records(section, section_path)
    if paragraphs is None or title.path not in {record.path for record in paragraphs}:
        return ()
    if any(
        record.path != title.path
        and not (
            title.evidence.font_weight > record.evidence.font_weight
            and title.evidence.font_size is not None
            and record.evidence.font_size is not None
            and title.evidence.font_size > record.evidence.font_size
        )
        for record in paragraphs
    ):
        return ()

    direct_records = {
        record.path[-1]: record
        for record in paragraphs
        if len(record.path) == len(section_path) + 1
        and record.path != title.path
    }
    tiers = {
        _tier(record.evidence)
        for record in direct_records.values()
        if _is_short(record) and _tier(record.evidence) is not None
    }
    accepted: list[tuple[list[_ParagraphRecord], list[_ParagraphRecord], list[_ParagraphRecord]]] = []
    for tier in tiers:
        assert tier is not None
        direct_labels, direct_details = _direct_label_groups(
            section,
            section_path,
            direct_records,
            tier,
        )
        if len(direct_labels) < 3:
            continue
        table_labels, table_details = _table_label_groups(section, section_path, tier)
        if len(table_labels) < 2:
            continue
        accepted.append((direct_labels, table_labels, [*direct_details, *table_details]))
    if len(accepted) != 1:
        return ()

    direct_labels, table_labels, body_records = accepted[0]
    label_records = [*direct_labels, *table_labels]
    targets = [title, *label_records]
    conflict_paths = [
        *(promotion.child_path for promotion in document.heading_promotions),
        *(hint.child_path for hint in document.subtitle_hints),
    ]
    if any(
        _heading_conflict(record.element)
        or any(_paths_overlap(record.path, conflict) for conflict in conflict_paths)
        for record in targets
    ):
        return ()

    body_weight = max(record.evidence.font_weight for record in body_records)
    body_size = max(
        record.evidence.font_size
        for record in body_records
        if record.evidence.font_size is not None
    )
    title_hint = _display_hint(
        title,
        "section_heading",
        body_weight,
        body_size,
        "form_cluster_unique_strongest_title",
    )
    label_hints = tuple(
        _display_hint(
            record,
            "strong_label",
            body_weight,
            body_size,
            "form_cluster_middle_tier_with_weaker_detail",
        )
        for record in label_records
    )
    result = tuple(sorted((title_hint, *label_hints), key=lambda hint: hint.child_path))
    if len({hint.child_path for hint in result}) != len(result):
        return ()
    if any(
        _paths_overlap(left.child_path, right.child_path)
        for index, left in enumerate(result)
        for right in result[index + 1 :]
    ):
        return ()
    return result


def _structural_sections(
    children: tuple[StructureElement | ContentFragment, ...],
    parent_path: tuple[int, ...] = (),
) -> tuple[tuple[StructureElement, tuple[int, ...]], ...]:
    sections: list[tuple[StructureElement, tuple[int, ...]]] = []
    stack = [(children, parent_path)]
    while stack:
        siblings, base_path = stack.pop()
        for index in range(len(siblings) - 1, -1, -1):
            child = siblings[index]
            if not isinstance(child, StructureElement):
                continue
            path = (*base_path, index)
            if child.semantic_role == "section":
                sections.append((child, path))
            stack.append((child.children, path))
    return tuple(sorted(sections, key=lambda item: item[1]))


def _first_direct_text_child(
    section: StructureElement,
    section_path: tuple[int, ...],
) -> _ParagraphRecord | None:
    for index, child in enumerate(section.children):
        if not isinstance(child, StructureElement):
            continue
        text = _normalized_text(child)
        if not text:
            continue
        if not _is_leaf_paragraph(child):
            return None
        evidence = typography_evidence(child)
        if evidence is None:
            return None
        return _ParagraphRecord(child, (*section_path, index), text, evidence)
    return None


def _leaf_paragraph_records(
    section: StructureElement,
    section_path: tuple[int, ...],
) -> tuple[_ParagraphRecord, ...] | None:
    records: list[_ParagraphRecord] = []
    incomplete = False
    stack: list[tuple[StructureElement, tuple[int, ...]]] = [(section, section_path)]
    while stack:
        parent, parent_path = stack.pop()
        for index in range(len(parent.children) - 1, -1, -1):
            child = parent.children[index]
            if not isinstance(child, StructureElement):
                continue
            path = (*parent_path, index)
            if child.semantic_role == "section" and child is not section:
                continue
            if _is_leaf_paragraph(child):
                text = _normalized_text(child)
                if text:
                    evidence = typography_evidence(child)
                    if evidence is None or evidence.font_size is None:
                        incomplete = True
                    else:
                        records.append(_ParagraphRecord(child, path, text, evidence))
                continue
            stack.append((child, path))
    if incomplete:
        return None
    return tuple(sorted(records, key=lambda record: record.path))


def _direct_label_groups(
    section: StructureElement,
    section_path: tuple[int, ...],
    direct_records: dict[int, _ParagraphRecord],
    tier: tuple[int, float],
) -> tuple[list[_ParagraphRecord], list[_ParagraphRecord]]:
    labels: list[_ParagraphRecord] = []
    details: list[_ParagraphRecord] = []
    for index, record in sorted(direct_records.items()):
        if not _is_short(record) or _tier(record.evidence) != tier:
            continue
        linked: list[_ParagraphRecord] = []
        for following_index in range(index + 1, len(section.children)):
            following = section.children[following_index]
            following_record = direct_records.get(following_index)
            if following_record is not None and _tier(following_record.evidence) == tier:
                break
            if not isinstance(following, StructureElement) or not _is_leaf_paragraph(following):
                break
            if following_record is None or not _weaker(following_record.evidence, tier):
                linked = []
                break
            linked.append(following_record)
        if linked:
            labels.append(record)
            details.extend(linked)
    return labels, details


def _table_label_groups(
    section: StructureElement,
    section_path: tuple[int, ...],
    tier: tuple[int, float],
) -> tuple[list[_ParagraphRecord], list[_ParagraphRecord]]:
    qualifying: list[tuple[list[_ParagraphRecord], list[_ParagraphRecord]]] = []
    for table, table_path in _descendants_with_role(section, section_path, "table"):
        labels: list[_ParagraphRecord] = []
        details: list[_ParagraphRecord] = []
        for cell, cell_path in _descendants_with_role(table, table_path, "table_cell"):
            direct = _direct_nonempty_paragraphs(cell, cell_path)
            if not direct:
                continue
            label, *cell_details = direct
            if (
                _is_short(label)
                and _tier(label.evidence) == tier
                and cell_details
                and all(_weaker(detail.evidence, tier) for detail in cell_details)
            ):
                labels.append(label)
                details.extend(cell_details)
        if len(labels) >= 2:
            qualifying.append((labels, details))
    if len(qualifying) != 1:
        return [], []
    return qualifying[0]


def _direct_nonempty_paragraphs(
    parent: StructureElement,
    parent_path: tuple[int, ...],
) -> list[_ParagraphRecord]:
    records: list[_ParagraphRecord] = []
    for index, child in enumerate(parent.children):
        if not isinstance(child, StructureElement) or not _is_leaf_paragraph(child):
            continue
        text = _normalized_text(child)
        if not text:
            continue
        evidence = typography_evidence(child)
        if evidence is None or evidence.font_size is None:
            return []
        records.append(_ParagraphRecord(child, (*parent_path, index), text, evidence))
    return records


def _descendants_with_role(
    root: StructureElement,
    root_path: tuple[int, ...],
    role: str,
) -> tuple[tuple[StructureElement, tuple[int, ...]], ...]:
    found: list[tuple[StructureElement, tuple[int, ...]]] = []
    stack = [(root, root_path)]
    while stack:
        parent, parent_path = stack.pop()
        for index in range(len(parent.children) - 1, -1, -1):
            child = parent.children[index]
            if not isinstance(child, StructureElement):
                continue
            path = (*parent_path, index)
            if child.semantic_role == role:
                found.append((child, path))
            stack.append((child, path))
    return tuple(sorted(found, key=lambda item: item[1]))


def _display_hint(
    record: _ParagraphRecord,
    role: str,
    body_weight: int,
    body_size: float,
    reason: str,
) -> TextDisplayHint:
    assert record.evidence.font_size is not None
    return TextDisplayHint(
        child_path=record.path,
        display_role=role,  # type: ignore[arg-type]
        font_weight=record.evidence.font_weight,
        font_size=record.evidence.font_size,
        comparison_body_font_weight=body_weight,
        comparison_body_font_size=body_size,
        reason=reason,
    )


def _is_leaf_paragraph(element: StructureElement) -> bool:
    if element.semantic_role != "paragraph":
        return False
    stack = list(element.children)
    while stack:
        child = stack.pop()
        if not isinstance(child, StructureElement):
            continue
        if child.semantic_role in _BLOCK_ROLES:
            return False
        stack.extend(child.children)
    return True


def _is_short(record: _ParagraphRecord) -> bool:
    return (
        1 <= len(record.text) <= _MAX_SHORT_TEXT_LENGTH
        and len(record.evidence.observed_lines) <= _MAX_SHORT_LINE_COUNT
    )


def _tier(evidence: TypographyEvidence) -> tuple[int, float] | None:
    if evidence.font_size is None:
        return None
    return evidence.font_weight, evidence.font_size


def _weaker(evidence: TypographyEvidence, tier: tuple[int, float]) -> bool:
    return (
        evidence.font_size is not None
        and evidence.font_weight < tier[0]
        and evidence.font_size < tier[1]
    )


def _heading_conflict(element: StructureElement) -> bool:
    return element.semantic_role == "heading" or is_heading_candidate(element.source_role)


def _paths_overlap(left: tuple[int, ...], right: tuple[int, ...]) -> bool:
    return left[: len(right)] == right or right[: len(left)] == left


def _normalized_text(element: StructureElement) -> str:
    parts: list[str] = []
    stack = list(reversed(element.children))
    while stack:
        child = stack.pop()
        if isinstance(child, ContentFragment):
            parts.extend(child.text_parts)
        else:
            stack.extend(reversed(child.children))
    return " ".join("".join(parts).split())


def detect_rf_line_break_hints(
    children: tuple[StructureElement | ContentFragment, ...],
) -> tuple[LineBreakHint, ...]:
    hints: list[LineBreakHint] = []

    def visit(
        siblings: tuple[StructureElement | ContentFragment, ...],
        parent_path: tuple[int, ...],
        inside_table_cell: bool,
    ) -> None:
        for index, child in enumerate(siblings):
            if not isinstance(child, StructureElement):
                continue
            child_path = (*parent_path, index)
            if child.semantic_role == "paragraph":
                if inside_table_cell:
                    hints.extend(_paragraph_hints(child, child_path))
                for nested_index, nested_child in enumerate(child.children):
                    if (
                        isinstance(nested_child, StructureElement)
                        and nested_child.semantic_role == "table"
                    ):
                        nested_path = (*child_path, nested_index)
                        visit(
                            nested_child.children,
                            nested_path,
                            inside_table_cell,
                        )
                continue
            visit(
                child.children,
                child_path,
                inside_table_cell or child.semantic_role == "table_cell",
            )

    visit(children, (), False)
    return tuple(hints)


def _paragraph_hints(
    paragraph: StructureElement,
    paragraph_path: tuple[int, ...],
) -> tuple[LineBreakHint, ...]:
    segments: list[tuple[tuple[int, ...], str, bool, int]] = []
    run_index = 0

    def collect_inline(
        siblings: tuple[StructureElement | ContentFragment, ...],
        parent_path: tuple[int, ...],
    ) -> None:
        nonlocal run_index
        for index, child in enumerate(siblings):
            child_path = (*parent_path, index)
            if isinstance(child, ContentFragment):
                segments.append((child_path, child.text, False, run_index))
            elif child.semantic_role in _INLINE_ROLES:
                if child.actual_text is not None:
                    segments.append(
                        (child_path, child.actual_text, True, run_index)
                    )
                else:
                    collect_inline(child.children, child_path)
            else:
                run_index += 1

    collect_inline(paragraph.children, paragraph_path)
    hints: list[LineBreakHint] = []
    for index, (child_path, text, is_actual_text, segment_run) in enumerate(segments):
        if not is_actual_text or text != "\n":
            continue
        if index == 0 or index == len(segments) - 1:
            continue
        previous = segments[index - 1]
        following = segments[index + 1]
        if previous[3] != segment_run or following[3] != segment_run:
            continue
        previous_text = previous[1]
        following_text = following[1]
        if not previous_text.strip() or not following_text.strip():
            continue
        if not previous_text.rstrip().endswith(","):
            continue
        hints.append(LineBreakHint(child_path=child_path))
    return tuple(hints)
