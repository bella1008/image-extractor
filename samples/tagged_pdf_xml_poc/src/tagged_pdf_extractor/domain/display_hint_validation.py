from __future__ import annotations

from dataclasses import dataclass
import math
from types import MappingProxyType
from typing import Mapping

from tagged_pdf_extractor.domain.models import (
    ContentFragment,
    LineBreakHint,
    StructureElement,
    TaggedDocument,
    TextDisplayHint,
)
from tagged_pdf_extractor.domain.review_formatting import detect_rf_line_break_hints
from tagged_pdf_extractor.domain.role_mapping import is_heading_candidate


_INLINE_ROLES = frozenset({"span", "link"})
_TEXT_DISPLAY_ROLES = frozenset({"section_heading", "strong_label"})


@dataclass(frozen=True)
class ValidatedReviewFormattingHints:
    line_break_by_path: Mapping[tuple[int, ...], LineBreakHint]
    text_display_by_path: Mapping[tuple[int, ...], TextDisplayHint]


def validate_review_formatting_hints(
    document: TaggedDocument,
) -> ValidatedReviewFormattingHints:
    line_break_by_path = _unique_hints(document.line_break_hints, "line break hint")
    text_display_by_path = _unique_hints(
        document.text_display_hints, "text display hint"
    )
    elements, ancestors = _index_document(document.children)

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
    subtitle_paths = tuple(item.child_path for item in document.subtitle_hints)
    text_paths = tuple(text_display_by_path)
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
        if not _is_nonempty_leaf_paragraph(target):
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
    )


def validate_display_hints(
    document: TaggedDocument,
) -> ValidatedReviewFormattingHints:
    """Compatibility name used by the semantic XML writer."""

    return validate_review_formatting_hints(document)


def _unique_hints(
    hints: tuple[LineBreakHint, ...] | tuple[TextDisplayHint, ...],
    name: str,
) -> dict[tuple[int, ...], LineBreakHint] | dict[tuple[int, ...], TextDisplayHint]:
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


def _is_nonempty_leaf_paragraph(element: StructureElement) -> bool:
    text_parts: list[str] = []
    stack = list(element.children)
    while stack:
        child = stack.pop()
        if isinstance(child, ContentFragment):
            text_parts.extend(child.text_parts)
            continue
        if child.semantic_role not in _INLINE_ROLES:
            return False
        if child.actual_text is not None:
            text_parts.append(child.actual_text)
        stack.extend(child.children)
    return bool("".join(text_parts).strip())


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


def _paths_overlap(left: tuple[int, ...], right: tuple[int, ...]) -> bool:
    return left[: len(right)] == right or right[: len(left)] == left
