from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
import math
import re
from statistics import median

from tagged_pdf_extractor.domain.models import (
    BBox,
    ContentFragment,
    ContinuationHint,
    ContinuationTypographyEvidence,
    StructureElement,
    TaggedDocument,
)
from tagged_pdf_extractor.domain.paragraph_eligibility import (
    is_nonempty_inline_paragraph,
)
from tagged_pdf_extractor.domain.typography import TypographyEvidence, typography_evidence


_VISIBLE_MARKER = re.compile(
    r"^\s*(?:[•◦▪▫‣⁃●○■□]|#{1,6}(?=\s)|\d{1,3}(?=\s)|"
    r"\(?\d{1,3}(?:[.)]|(?:\.\d+)+)(?=\s))"
)
_LIST_BODY_ROLE = "LBody"
_LEFT_TOLERANCE_FONT_RATIO = 0.25
_GAP_TOLERANCE_FONT_RATIO = 0.25
_GAP_TOLERANCE_LOCAL_RATIO = 0.5
_INDEPENDENT_BLOCK_GAP_FONT_RATIO = 1.0


@dataclass(frozen=True)
class _Geometry:
    page_index: int
    bbox: BBox
    line_bboxes: tuple[BBox, ...]


def detect_list_continuation_hints(
    document: TaggedDocument,
    *,
    heading_paths: Iterable[tuple[int, ...]] = (),
    promotion_paths: Iterable[tuple[int, ...]] = (),
    subtitle_paths: Iterable[tuple[int, ...]] = (),
    strong_label_paths: Iterable[tuple[int, ...]] = (),
    existing_continuation_paths: Iterable[tuple[int, ...]] = (),
) -> tuple[ContinuationHint, ...]:
    """Return conservative, evidence-only list continuation hints."""

    conflicts = tuple(
        path
        for paths in (
            heading_paths,
            promotion_paths,
            subtitle_paths,
            strong_label_paths,
            existing_continuation_paths,
        )
        for path in paths
    )
    role_map = dict(document.role_map)
    hints: list[ContinuationHint] = []

    def visit(
        siblings: tuple[StructureElement | ContentFragment, ...],
        parent_path: tuple[int, ...],
        inherited_language: str | None,
        section_path: tuple[int, ...] | None,
    ) -> None:
        for index, child in enumerate(siblings):
            if not isinstance(child, StructureElement):
                continue
            child_path = (*parent_path, index)
            language = child.language or inherited_language
            child_section_path = (
                child_path if child.semantic_role == "section" else section_path
            )
            if 0 < index < len(siblings) - 1:
                hint = _candidate_hint(
                    siblings[index - 1],
                    child,
                    siblings[index + 1],
                    target_path=child_path,
                    preceding_path=(*parent_path, index - 1),
                    inherited_language=inherited_language,
                    section_path=section_path,
                    conflicts=conflicts,
                    role_map=role_map,
                )
                if hint is not None:
                    hints.append(hint)
            visit(child.children, child_path, language, child_section_path)

    visit(document.children, (), document.language, None)
    return tuple(hints)


def _candidate_hint(
    preceding: StructureElement | ContentFragment,
    target: StructureElement,
    following: StructureElement | ContentFragment,
    *,
    target_path: tuple[int, ...],
    preceding_path: tuple[int, ...],
    inherited_language: str | None,
    section_path: tuple[int, ...] | None,
    conflicts: tuple[tuple[int, ...], ...],
    role_map: dict[str, str],
) -> ContinuationHint | None:
    if not (
        section_path is not None
        and isinstance(preceding, StructureElement)
        and preceding.semantic_role == "list"
        and target.semantic_role == "paragraph"
        and isinstance(following, StructureElement)
        and following.semantic_role == "list"
        and _resolves_to_list_body(target.source_role, role_map)
        and is_nonempty_inline_paragraph(target)
        and not _VISIBLE_MARKER.match(_normalized_text(target))
        and not any(_paths_overlap(target_path, path) for path in conflicts)
    ):
        return None

    languages = (
        _single_language(preceding, inherited_language),
        _single_language(target, inherited_language),
        _single_language(following, inherited_language),
    )
    if languages[0] is None or len(set(languages)) != 1:
        return None

    preceding_parts = _preceding_item_parts(preceding, preceding_path)
    if preceding_parts is None:
        return None
    item_path, marker, body, body_path = preceding_parts

    preceding_geometry = _complete_geometry(preceding)
    target_geometry = _complete_geometry(target)
    following_geometry = _complete_geometry(following)
    marker_geometry = _complete_geometry(marker)
    body_geometry = _complete_geometry(body)
    if any(
        geometry is None
        for geometry in (
            preceding_geometry,
            target_geometry,
            following_geometry,
            marker_geometry,
            body_geometry,
        )
    ):
        return None
    assert preceding_geometry is not None
    assert target_geometry is not None
    assert following_geometry is not None
    assert marker_geometry is not None
    assert body_geometry is not None
    pages = {
        preceding_geometry.page_index,
        target_geometry.page_index,
        following_geometry.page_index,
        marker_geometry.page_index,
        body_geometry.page_index,
    }
    if len(pages) != 1:
        return None

    body_type = _valid_typography(body)
    target_type = _valid_typography(target)
    if (
        body_type is None
        or target_type is None
        or body_type.font_weight != target_type.font_weight
        or body_type.font_size != target_type.font_size
    ):
        return None
    assert body_type.font_size is not None
    assert target_type.font_size is not None
    reference_font_size = body_type.font_size

    left_delta = target_geometry.bbox[0] - body_geometry.bbox[0]
    left_tolerance = reference_font_size * _LEFT_TOLERANCE_FONT_RATIO
    if (
        abs(left_delta) > left_tolerance
        or abs(target_geometry.bbox[0] - marker_geometry.bbox[0]) <= left_tolerance
    ):
        return None

    local_spacing = _local_line_spacing(body_geometry.line_bboxes)
    vertical_gap = body_geometry.bbox[1] - target_geometry.bbox[3]
    if local_spacing is None or vertical_gap < 0:
        return None
    gap_tolerance = max(
        reference_font_size * _GAP_TOLERANCE_FONT_RATIO,
        local_spacing * _GAP_TOLERANCE_LOCAL_RATIO,
    )
    if (
        abs(vertical_gap - local_spacing) > gap_tolerance
        or vertical_gap
        >= reference_font_size * _INDEPENDENT_BLOCK_GAP_FONT_RATIO
    ):
        return None

    return ContinuationHint(
        child_path=target_path,
        preceding_list_item_path=item_path,
        preceding_list_body_path=body_path,
        page_index=target_geometry.page_index,
        paragraph_bbox=target_geometry.bbox,
        list_body_bbox=body_geometry.bbox,
        left_delta=left_delta,
        vertical_gap=vertical_gap,
        reference_font_size=reference_font_size,
        source_role=target.source_role,
        typography_evidence=ContinuationTypographyEvidence(
            preceding_body_font_weight=body_type.font_weight,
            preceding_body_font_size=body_type.font_size,
            preceding_body_observed_lines=tuple(sorted(body_type.observed_lines)),
            target_font_weight=target_type.font_weight,
            target_font_size=target_type.font_size,
            target_observed_lines=tuple(sorted(target_type.observed_lines)),
        ),
    )


def _resolves_to_list_body(source_role: str, role_map: dict[str, str]) -> bool:
    seen: set[str] = set()
    role = source_role
    while role in role_map and role not in seen:
        seen.add(role)
        role = role_map[role]
    return role == _LIST_BODY_ROLE


def _single_language(
    element: StructureElement,
    inherited_language: str | None,
) -> str | None:
    languages: set[str] = set()
    valid = True

    def visit(current: StructureElement, language: str | None) -> None:
        nonlocal valid
        resolved = current.language or language
        if resolved is None:
            valid = False
            return
        languages.add(resolved)
        for child in current.children:
            if isinstance(child, StructureElement):
                visit(child, resolved)

    visit(element, inherited_language)
    return next(iter(languages)) if valid and len(languages) == 1 else None


def _preceding_item_parts(
    preceding: StructureElement,
    preceding_path: tuple[int, ...],
) -> tuple[
    tuple[int, ...],
    StructureElement,
    StructureElement,
    tuple[int, ...],
] | None:
    if not preceding.children:
        return None
    item_index = len(preceding.children) - 1
    item = preceding.children[item_index]
    if not isinstance(item, StructureElement) or item.semantic_role != "list_item":
        return None
    labels = tuple(
        (index, child)
        for index, child in enumerate(item.children)
        if isinstance(child, StructureElement) and child.semantic_role == "label"
    )
    bodies = tuple(
        (index, child)
        for index, child in enumerate(item.children)
        if isinstance(child, StructureElement) and child.semantic_role == "list_body"
    )
    if len(labels) != 1 or len(bodies) != 1:
        return None
    body_index, body = bodies[0]
    item_path = (*preceding_path, item_index)
    return item_path, labels[0][1], body, (*item_path, body_index)


def _complete_geometry(element: StructureElement) -> _Geometry | None:
    line_boxes: dict[tuple[int, int], list[BBox]] = {}
    page_claims: set[int] = set()
    valid = True

    def visit(current: StructureElement) -> None:
        nonlocal valid
        if current.page_index is not None:
            if (
                isinstance(current.page_index, bool)
                or not isinstance(current.page_index, int)
                or current.page_index < 0
            ):
                valid = False
            else:
                page_claims.add(current.page_index)
        if current.actual_text and current.actual_text.strip():
            valid = False
        for child in current.children:
            if isinstance(child, StructureElement):
                visit(child)
                continue
            if (
                isinstance(child.page_index, bool)
                or not isinstance(child.page_index, int)
                or child.page_index < 0
            ):
                valid = False
                continue
            page_claims.add(child.page_index)
            for index, text in enumerate(child.text_parts):
                if not text.strip():
                    continue
                if (
                    child.mcid is None
                    or not child.text_bboxes
                    or index >= len(child.text_bboxes)
                    or not _valid_bbox(child.text_bboxes[index])
                ):
                    valid = False
                    continue
                bbox = child.text_bboxes[index]
                assert bbox is not None
                line_boxes.setdefault((child.page_index, child.mcid), []).append(bbox)

    visit(element)
    if not valid or len(page_claims) != 1 or not line_boxes:
        return None
    page_index = next(iter(page_claims))
    if any(page != page_index for page, _ in line_boxes):
        return None
    normalized_lines = tuple(
        _union_bbox(boxes)
        for _, boxes in sorted(
            line_boxes.items(),
            key=lambda item: (-max(box[1] for box in item[1]), item[0][1]),
        )
    )
    return _Geometry(page_index, _union_bbox(normalized_lines), normalized_lines)


def _valid_typography(element: StructureElement) -> TypographyEvidence | None:
    evidence = typography_evidence(element)
    if (
        evidence is None
        or evidence.font_size is None
        or not math.isfinite(evidence.font_size)
        or evidence.font_size <= 0
    ):
        return None
    return evidence


def _local_line_spacing(line_bboxes: tuple[BBox, ...]) -> float | None:
    if len(line_bboxes) < 2:
        return None
    gaps = tuple(
        upper[1] - lower[3]
        for upper, lower in zip(line_bboxes, line_bboxes[1:])
    )
    if not gaps or any(not math.isfinite(gap) or gap < 0 for gap in gaps):
        return None
    return float(median(gaps))


def _valid_bbox(value: BBox | None) -> bool:
    return bool(
        value is not None
        and len(value) == 4
        and all(
            not isinstance(coordinate, bool)
            and isinstance(coordinate, (int, float))
            and math.isfinite(coordinate)
            for coordinate in value
        )
        and value[2] > value[0]
        and value[3] > value[1]
    )


def _union_bbox(boxes: Iterable[BBox]) -> BBox:
    values = tuple(boxes)
    return (
        min(box[0] for box in values),
        min(box[1] for box in values),
        max(box[2] for box in values),
        max(box[3] for box in values),
    )


def _normalized_text(element: StructureElement) -> str:
    parts: list[str] = []

    def visit(children: tuple[StructureElement | ContentFragment, ...]) -> None:
        for child in children:
            if isinstance(child, ContentFragment):
                parts.extend(child.text_parts)
            else:
                if child.actual_text:
                    parts.append(child.actual_text)
                visit(child.children)

    visit(element.children)
    return " ".join("".join(parts).split())


def _paths_overlap(left: tuple[int, ...], right: tuple[int, ...]) -> bool:
    return left[: len(right)] == right or right[: len(left)] == left
