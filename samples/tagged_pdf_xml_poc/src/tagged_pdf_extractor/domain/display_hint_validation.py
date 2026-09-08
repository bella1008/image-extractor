from __future__ import annotations

from dataclasses import dataclass, field
import math
from types import MappingProxyType
from typing import Mapping, TypeVar

from tagged_pdf_extractor.domain.models import (
    ContentFragment,
    ContinuationHint,
    ContinuationTypographyEvidence,
    InlineIconHint,
    LineBreakHint,
    SentenceBreakHint,
    StructureElement,
    SubtitleHint,
    TaggedDocument,
    TextDisplayHint,
)
from tagged_pdf_extractor.domain.list_continuation_detection import (
    detect_list_continuation_hints,
)
from tagged_pdf_extractor.domain.inline_icon_policy import (
    GENERIC_INLINE_ICON_REASON,
    NAVIGATION_ROUTE_INLINE_ICON_REASON,
    inline_icon_ratio_limits,
)
from tagged_pdf_extractor.domain.paragraph_eligibility import (
    is_nonempty_inline_paragraph,
)
from tagged_pdf_extractor.domain.review_formatting import detect_rf_line_break_hints
from tagged_pdf_extractor.domain.readability_formatting import (
    detect_inline_icon_hints,
    detect_sentence_break_hints,
)
from tagged_pdf_extractor.domain.role_mapping import is_heading_candidate
from tagged_pdf_extractor.domain.subtitle_detection import inline_subtitle_offsets
from tagged_pdf_extractor.domain.text_joining import join_text_parts


_INLINE_ROLES = frozenset({"span", "link"})
_TEXT_DISPLAY_ROLES = frozenset({"section_heading", "strong_label"})


@dataclass(frozen=True)
class ValidatedReviewFormattingHints:
    line_break_by_path: Mapping[tuple[int, ...], LineBreakHint]
    text_display_by_path: Mapping[tuple[int, ...], TextDisplayHint]
    sentence_break_by_path: Mapping[tuple[int, ...], SentenceBreakHint]
    inline_icon_by_path: Mapping[tuple[int, ...], InlineIconHint]
    continuation_by_path: Mapping[tuple[int, ...], ContinuationHint] = field(
        default_factory=lambda: MappingProxyType({})
    )


def validate_review_formatting_hints(
    document: TaggedDocument,
) -> ValidatedReviewFormattingHints:
    subtitle_by_path = _unique_hints(document.subtitle_hints, "subtitle hint")
    line_break_by_path = _unique_hints(document.line_break_hints, "line break hint")
    text_display_by_path = _unique_hints(
        document.text_display_hints, "text display hint"
    )
    sentence_break_by_path = _unique_hints(
        document.sentence_break_hints, "sentence break hint"
    )
    inline_icon_by_path = _unique_hints(
        document.inline_icon_hints, "inline icon hint"
    )
    continuation_by_path = _unique_hints(
        document.continuation_hints, "continuation hint"
    )
    elements, ancestors = _index_document(document.children)
    for path, target in elements.items():
        if not isinstance(target, ContentFragment):
            continue
        for bbox in target.text_bboxes:
            if bbox is not None and not _valid_bbox(bbox):
                raise ValueError(f"invalid fragment bbox at {path}")
    for path, hint in subtitle_by_path.items():
        target = _resolved_structure_element(elements, path, "subtitle hint")
        title_end = hint.title_end_offset
        qualifier_start = hint.qualifier_start_offset
        if title_end is None and qualifier_start is None:
            continue
        if type(title_end) is not int or type(qualifier_start) is not int:
            raise ValueError(f"invalid inline subtitle offsets at {path}")
        detected_offsets = inline_subtitle_offsets(target)
        if detected_offsets is None:
            raise ValueError(f"inline subtitle source boundary is invalid at {path}")
        if (title_end, qualifier_start) != detected_offsets:
            raise ValueError(f"invalid inline subtitle offsets at {path}")

    detected_line_paths = {
        hint.child_path for hint in detect_rf_line_break_hints(document.children)
    }
    for path in line_break_by_path:
        target = _resolved_structure_element(elements, path, "line break hint")
        if target.semantic_role not in _INLINE_ROLES or target.actual_text != "\n":
            raise ValueError(
                "line break hint must target a span/link with exact newline "
                f"actual_text at {path}"
            )
        ancestor_roles = tuple(element.semantic_role for element in ancestors[path])
        if "table_cell" not in ancestor_roles or "paragraph" not in ancestor_roles:
            raise ValueError(
                "line break hint must target an inline element in a table_cell "
                f"paragraph at {path}"
            )
        if path not in detected_line_paths:
            raise ValueError(f"line-break adjacency evidence is invalid at {path}")

    source_heading_paths = {
        path
        for path, target in elements.items()
        if isinstance(target, StructureElement)
        and (
            target.semantic_role == "heading"
            or is_heading_candidate(target.source_role)
        )
    }
    promotion_paths = tuple(item.child_path for item in document.heading_promotions)
    subtitle_paths = tuple(subtitle_by_path)
    text_paths = tuple(text_display_by_path)
    sentence_paths = tuple(sentence_break_by_path)
    icon_paths = tuple(inline_icon_by_path)
    continuation_paths = tuple(continuation_by_path)

    strong_label_paths = tuple(
        path
        for path, hint in text_display_by_path.items()
        if hint.display_role == "strong_label"
    )
    heading_paths = tuple(
        sorted(
            {
                *source_heading_paths,
                *(
                    path
                    for path, hint in text_display_by_path.items()
                    if hint.display_role == "section_heading"
                ),
            }
        )
    )
    for index, path in enumerate(continuation_paths):
        target = _resolved_structure_element(elements, path, "continuation hint")
        hint = continuation_by_path[path]
        if target.semantic_role != "paragraph":
            raise ValueError(f"continuation hint must target a paragraph at {path}")
        predecessor = _resolved_structure_element(
            elements, hint.preceding_list_item_path, "continuation predecessor"
        )
        if predecessor.semantic_role != "list_item":
            raise ValueError(
                f"continuation predecessor must resolve to list_item at {path}"
            )
        predecessor_body = _resolved_structure_element(
            elements, hint.preceding_list_body_path, "continuation predecessor body"
        )
        if predecessor_body.semantic_role != "list_body":
            raise ValueError(
                f"continuation predecessor body must resolve to list_body at {path}"
            )
        if (
            hint.preceding_list_body_path[: len(hint.preceding_list_item_path)]
            != hint.preceding_list_item_path
        ):
            raise ValueError(
                f"continuation predecessor body is outside list_item at {path}"
            )
        _validate_continuation_evidence(hint, target, predecessor, predecessor_body)
        for other_path in continuation_paths[index + 1 :]:
            _reject_hint_path_conflict(
                path, (other_path,), "other continuation", "continuation"
            )
        for candidates, name in (
            (heading_paths, "heading"),
            (promotion_paths, "promotion"),
            (subtitle_paths, "subtitle"),
            (strong_label_paths, "strong label"),
            (sentence_paths, "sentence break"),
        ):
            _reject_hint_path_conflict(path, candidates, name, "continuation")

    if continuation_by_path:
        try:
            detected_continuation_by_path = {
                hint.child_path: hint
                for hint in detect_list_continuation_hints(
                    document,
                    heading_paths=heading_paths,
                    promotion_paths=promotion_paths,
                    subtitle_paths=subtitle_paths,
                    strong_label_paths=strong_label_paths,
                )
            }
        except (OverflowError, TypeError, ValueError) as exc:
            raise ValueError("continuation hint redetection failed") from exc
        for path, hint in continuation_by_path.items():
            if detected_continuation_by_path.get(path) != hint:
                raise ValueError(f"continuation hint detector mismatch at {path}")
        if continuation_by_path != detected_continuation_by_path:
            raise ValueError("continuation hint mapping mismatch")

    for sentence_path in sentence_paths:
        _reject_hint_path_conflict(
            sentence_path,
            source_heading_paths,
            "source heading",
            "sentence break",
        )
        _reject_hint_path_conflict(
            sentence_path, promotion_paths, "promotion", "sentence break"
        )
        _reject_hint_path_conflict(
            sentence_path, subtitle_paths, "subtitle", "sentence break"
        )
        _reject_hint_path_conflict(
            sentence_path, text_paths, "text display", "sentence break"
        )
        _reject_hint_path_conflict(
            sentence_path,
            tuple(line_break_by_path),
            "line break",
            "sentence break",
        )

    detected_sentence_by_path = _detected_sentence_hints(document)
    for path, hint in sentence_break_by_path.items():
        target = _resolved_content_fragment(elements, path, "sentence break hint")
        offsets = hint.offsets
        if (
            type(offsets) is not tuple
            or not offsets
            or any(type(offset) is not int or offset < 0 for offset in offsets)
            or offsets != tuple(sorted(offsets))
            or len(offsets) != len(set(offsets))
        ):
            raise ValueError(f"invalid sentence break offsets at {path}")
        try:
            text = join_text_parts(target.text_parts)[0]
        except (OverflowError, TypeError, ValueError) as exc:
            raise ValueError(f"invalid sentence break target text at {path}") from exc
        if not text:
            raise ValueError(f"sentence break hint has empty target at {path}")
        if any(offset >= len(text) for offset in offsets):
            raise ValueError(
                f"sentence break offset is outside target text at {path}"
            )
        if detected_sentence_by_path.get(path) != hint:
            raise ValueError(f"sentence break detector mismatch at {path}")
    if sentence_break_by_path != detected_sentence_by_path:
        raise ValueError("sentence break hint mapping mismatch")

    detected_icon_by_path = _detected_inline_icon_hints(document)
    for path, hint in inline_icon_by_path.items():
        target = _resolved_structure_element(elements, path, "inline icon hint")
        if target.semantic_role != "figure":
            raise ValueError(f"inline icon hint must target a figure at {path}")
        if type(hint.page_index) is not int or hint.page_index < 0:
            raise ValueError(f"invalid inline icon page_index at {path}")
        if not _valid_bbox(hint.bbox):
            raise ValueError(f"invalid inline icon bbox at {path}")
        if not all(
            _is_finite_number(value, positive=True)
            for value in (
                hint.reference_font_size,
                hint.width_ratio,
                hint.height_ratio,
            )
        ):
            raise ValueError(f"invalid inline icon size or ratio at {path}")
        if not isinstance(hint.reason, str) or not hint.reason:
            raise ValueError(f"invalid inline icon reason at {path}")
        try:
            max_width_ratio, max_height_ratio = inline_icon_ratio_limits(
                hint.reason
            )
        except ValueError as exc:
            raise ValueError(f"invalid inline icon reason at {path}") from exc
        if (
            hint.width_ratio > max_width_ratio
            or hint.height_ratio > max_height_ratio
        ):
            raise ValueError(f"inline icon ratio exceeds policy at {path}")
        if hint.reason == NAVIGATION_ROUTE_INLINE_ICON_REASON:
            if (
                type(hint.route_separator_count) is not int
                or hint.route_separator_count < 2
                or type(hint.route_parenthesized) is not bool
            ):
                raise ValueError(
                    f"invalid navigation route icon evidence at {path}"
                )
        elif hint.reason == GENERIC_INLINE_ICON_REASON and (
            hint.route_separator_count is not None
            or hint.route_parenthesized is not None
        ):
            raise ValueError(f"generic inline icon has route evidence at {path}")
        if detected_icon_by_path.get(path) != hint:
            raise ValueError(f"inline icon detector mismatch at {path}")
    if inline_icon_by_path != detected_icon_by_path:
        raise ValueError("inline icon hint mapping mismatch")

    for line_path in line_break_by_path:
        _reject_line_path_conflict(
            line_path, source_heading_paths, "heading candidate"
        )
        _reject_line_path_conflict(
            line_path, promotion_paths, "heading promotion"
        )
        _reject_line_path_conflict(line_path, subtitle_paths, "subtitle")
        for text_path in text_display_by_path:
            if _paths_overlap(line_path, text_path):
                raise ValueError(
                    "line break and text display hint paths overlap at "
                    f"{line_path} and {text_path}"
                )
    for icon_path in icon_paths:
        _reject_hint_path_conflict(
            icon_path, source_heading_paths, "source heading", "inline icon"
        )
        _reject_hint_path_conflict(
            icon_path, promotion_paths, "promotion", "inline icon"
        )
        _reject_hint_path_conflict(
            icon_path, subtitle_paths, "subtitle", "inline icon"
        )
        _reject_hint_path_conflict(
            icon_path, text_paths, "text display", "inline icon"
        )
        _reject_hint_path_conflict(
            icon_path,
            tuple(line_break_by_path),
            "line break",
            "inline icon",
        )
        _reject_hint_path_conflict(
            icon_path, sentence_paths, "sentence break", "inline icon"
        )
    for index, path in enumerate(text_paths):
        for other_path in text_paths[index + 1 :]:
            if _paths_overlap(path, other_path):
                raise ValueError(
                    "overlapping text display hint paths "
                    f"{path} and {other_path}"
                )
    for path in text_paths:
        target = _resolved_structure_element(elements, path, "text display hint")
        hint = text_display_by_path[path]
        if hint.display_role not in _TEXT_DISPLAY_ROLES:
            raise ValueError(f"invalid text display role at {path}")
        if target.semantic_role != "paragraph":
            raise ValueError(f"text display hint must target a paragraph at {path}")
        if not is_nonempty_inline_paragraph(target):
            raise ValueError(
                "text display hint must target a nonempty paragraph; target must "
                "be a nonempty leaf paragraph without block descendants "
                f"at {path}"
            )
        if not _valid_typography(hint):
            raise ValueError(f"invalid text display typography at {path}")
        if not (
            hint.font_weight > hint.comparison_body_font_weight
            and hint.font_size > hint.comparison_body_font_size
        ):
            raise ValueError(
                "text display typography must be strictly stronger than body "
                f"typography at {path}"
            )
        _reject_path_conflict(path, promotion_paths, "heading promotion")
        _reject_path_conflict(path, subtitle_paths, "subtitle")
        _reject_path_conflict(path, source_heading_paths, "heading candidate")

    return ValidatedReviewFormattingHints(
        line_break_by_path=MappingProxyType(line_break_by_path),
        text_display_by_path=MappingProxyType(text_display_by_path),
        sentence_break_by_path=MappingProxyType(sentence_break_by_path),
        inline_icon_by_path=MappingProxyType(inline_icon_by_path),
        continuation_by_path=MappingProxyType(continuation_by_path),
    )


def validate_display_hints(
    document: TaggedDocument,
) -> ValidatedReviewFormattingHints:
    """Compatibility name used by the semantic XML writer."""

    return validate_review_formatting_hints(document)


_Hint = TypeVar(
    "_Hint",
    SubtitleHint,
    LineBreakHint,
    TextDisplayHint,
    SentenceBreakHint,
    InlineIconHint,
    ContinuationHint,
)


def _unique_hints(
    hints: tuple[_Hint, ...],
    name: str,
) -> dict[tuple[int, ...], _Hint]:
    result = {}
    for hint in hints:
        path = hint.child_path
        if (
            type(path) is not tuple
            or not path
            or any(type(component) is not int or component < 0 for component in path)
        ):
            raise ValueError(
                f"invalid {name} path {path!r}: expected a nonempty tuple of "
                "nonnegative exact integers"
            )
        if path in result:
            raise ValueError(f"duplicate {name} path {path}")
        result[path] = hint
    return result


def _index_document(
    children: tuple[StructureElement | ContentFragment, ...],
) -> tuple[
    dict[tuple[int, ...], StructureElement | ContentFragment],
    dict[tuple[int, ...], tuple[StructureElement, ...]],
]:
    elements: dict[tuple[int, ...], StructureElement | ContentFragment] = {}
    ancestors: dict[tuple[int, ...], tuple[StructureElement, ...]] = {}
    stack = [(children, (), ())]
    while stack:
        siblings, parent_path, parent_elements = stack.pop()
        for index in range(len(siblings) - 1, -1, -1):
            child = siblings[index]
            path = (*parent_path, index)
            elements[path] = child
            ancestors[path] = parent_elements
            if isinstance(child, StructureElement):
                stack.append((child.children, path, (*parent_elements, child)))
    return elements, ancestors


def _resolved_structure_element(
    elements: Mapping[tuple[int, ...], StructureElement | ContentFragment],
    path: tuple[int, ...],
    name: str,
) -> StructureElement:
    if path not in elements:
        raise ValueError(f"unresolved {name} path {path}")
    target = elements[path]
    if not isinstance(target, StructureElement):
        raise ValueError(f"{name} must target a StructureElement at {path}")
    return target


def _resolved_content_fragment(
    elements: Mapping[tuple[int, ...], StructureElement | ContentFragment],
    path: tuple[int, ...],
    name: str,
) -> ContentFragment:
    if path not in elements:
        raise ValueError(f"unresolved {name} path {path}")
    target = elements[path]
    if not isinstance(target, ContentFragment):
        raise ValueError(f"{name} must target a ContentFragment at {path}")
    return target


def _detected_sentence_hints(
    document: TaggedDocument,
) -> dict[tuple[int, ...], SentenceBreakHint]:
    try:
        continuation_paths = tuple(
            hint.child_path for hint in document.continuation_hints
        )
        return {
            hint.child_path: hint
            for hint in detect_sentence_break_hints(document)
            if not any(
                _paths_overlap(hint.child_path, path)
                for path in continuation_paths
            )
        }
    except (OverflowError, TypeError, ValueError) as exc:
        raise ValueError("sentence break hint redetection failed") from exc


def _detected_inline_icon_hints(
    document: TaggedDocument,
) -> dict[tuple[int, ...], InlineIconHint]:
    try:
        return {hint.child_path: hint for hint in detect_inline_icon_hints(document)}
    except (OverflowError, TypeError, ValueError) as exc:
        raise ValueError("inline icon hint redetection failed") from exc


def _is_finite_number(value: object, *, positive: bool = False) -> bool:
    if type(value) not in {int, float}:
        return False
    try:
        finite = math.isfinite(value)
    except (OverflowError, TypeError, ValueError):
        return False
    return finite and (not positive or value > 0)


def _valid_bbox(value: object) -> bool:
    if type(value) is not tuple or len(value) != 4:
        return False
    if not all(_is_finite_number(coordinate) for coordinate in value):
        return False
    return value[2] > value[0] and value[3] > value[1]


def _validate_continuation_evidence(
    hint: ContinuationHint,
    target: StructureElement,
    predecessor: StructureElement,
    predecessor_body: StructureElement,
) -> None:
    path = hint.child_path
    if (
        type(hint.page_index) is not int
        or hint.page_index < 0
        or not _valid_bbox(hint.paragraph_bbox)
        or not _valid_bbox(hint.list_body_bbox)
        or not _is_finite_number(hint.left_delta)
        or not _is_finite_number(hint.vertical_gap)
        or hint.vertical_gap < 0
        or not _is_finite_number(hint.reference_font_size, positive=True)
        or not isinstance(hint.source_role, str)
        or not hint.source_role
        or hint.source_role != target.source_role
        or hint.reason != "sibling_list_paragraph_list_geometry_typography"
    ):
        raise ValueError(f"invalid continuation evidence at {path}")
    evidence = hint.typography_evidence
    if not isinstance(evidence, ContinuationTypographyEvidence):
        raise ValueError(f"invalid continuation typography evidence at {path}")
    weights = (
        evidence.preceding_body_font_weight,
        evidence.target_font_weight,
    )
    sizes = (
        evidence.preceding_body_font_size,
        evidence.target_font_size,
    )
    observed = (
        evidence.preceding_body_observed_lines,
        evidence.target_observed_lines,
    )
    if (
        any(type(value) is not int or value <= 0 for value in weights)
        or any(not _is_finite_number(value, positive=True) for value in sizes)
        or any(
            type(lines) is not tuple
            or not lines
            or any(
                type(line) is not tuple
                or len(line) != 2
                or any(type(value) is not int or value < 0 for value in line)
                or line[0] != hint.page_index
                for line in lines
            )
            for lines in observed
        )
    ):
        raise ValueError(f"invalid continuation typography evidence at {path}")
    pages = (
        _structure_page_indices(target),
        _structure_page_indices(predecessor),
        _structure_page_indices(predecessor_body),
    )
    if any(page_indices != {hint.page_index} for page_indices in pages):
        raise ValueError(f"cross-page continuation evidence at {path}")


def _structure_page_indices(element: StructureElement) -> set[int]:
    pages: set[int] = set()
    stack = [element]
    while stack:
        current = stack.pop()
        if current.page_index is not None:
            if type(current.page_index) is not int or current.page_index < 0:
                return set()
            pages.add(current.page_index)
        for child in current.children:
            if isinstance(child, StructureElement):
                stack.append(child)
            else:
                if type(child.page_index) is not int or child.page_index < 0:
                    return set()
                pages.add(child.page_index)
    return pages


def _valid_typography(hint: TextDisplayHint) -> bool:
    weights = (hint.font_weight, hint.comparison_body_font_weight)
    sizes = (hint.font_size, hint.comparison_body_font_size)
    return (
        all(type(value) is int and value > 0 for value in weights)
        and all(
            type(value) in {int, float}
            and not isinstance(value, bool)
            and math.isfinite(value)
            and value > 0
            for value in sizes
        )
    )


def _reject_path_conflict(
    path: tuple[int, ...],
    candidates: tuple[tuple[int, ...], ...] | set[tuple[int, ...]],
    name: str,
) -> None:
    if any(_paths_overlap(path, candidate) for candidate in candidates):
        raise ValueError(f"{name} conflict for text display hint at {path}")


def _reject_line_path_conflict(
    path: tuple[int, ...],
    candidates: tuple[tuple[int, ...], ...] | set[tuple[int, ...]],
    name: str,
) -> None:
    if any(_paths_overlap(path, candidate) for candidate in candidates):
        raise ValueError(f"{name} conflict for line break hint at {path}")


def _reject_hint_path_conflict(
    path: tuple[int, ...],
    candidates: tuple[tuple[int, ...], ...] | set[tuple[int, ...]],
    candidate_name: str,
    hint_name: str,
) -> None:
    if any(_paths_overlap(path, candidate) for candidate in candidates):
        raise ValueError(f"{candidate_name} conflict for {hint_name} hint at {path}")


def _paths_overlap(left: tuple[int, ...], right: tuple[int, ...]) -> bool:
    return left[: len(right)] == right or right[: len(left)] == left
