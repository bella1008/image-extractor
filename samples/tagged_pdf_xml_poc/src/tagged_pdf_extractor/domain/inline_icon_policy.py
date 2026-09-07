from __future__ import annotations

import ast
from collections.abc import Iterable
from dataclasses import dataclass
import math


GENERIC_INLINE_ICON_REASON = "small_inline_figure_with_adjacent_text"
NAVIGATION_ROUTE_INLINE_ICON_REASON = "navigation_route_inline_figure"
INLINE_ICON_REASON = GENERIC_INLINE_ICON_REASON
MAX_INLINE_ICON_WIDTH_FONT_RATIO = 3.0
MAX_INLINE_ICON_HEIGHT_FONT_RATIO = 2.0
MAX_NAVIGATION_ICON_WIDTH_FONT_RATIO = 5.0
MAX_NAVIGATION_ICON_HEIGHT_FONT_RATIO = 2.5
_ROUTE_SENTENCE_TERMINATORS = frozenset(".!?。！？؟।")
_ROUTE_CLOSING_CHARACTERS = frozenset(")]}'\"»”’")
_FIGURE_PLACEHOLDER = "\ufffc"


@dataclass(frozen=True)
class NavigationTextEvidence:
    separator_count: int
    parenthesized: bool
    text_item_indices: tuple[int, ...]


def inline_icon_ratio_limits(reason: str) -> tuple[float, float]:
    if reason == GENERIC_INLINE_ICON_REASON:
        return (
            MAX_INLINE_ICON_WIDTH_FONT_RATIO,
            MAX_INLINE_ICON_HEIGHT_FONT_RATIO,
        )
    if reason == NAVIGATION_ROUTE_INLINE_ICON_REASON:
        return (
            MAX_NAVIGATION_ICON_WIDTH_FONT_RATIO,
            MAX_NAVIGATION_ICON_HEIGHT_FONT_RATIO,
        )
    raise ValueError(f"unknown inline icon reason: {reason}")


def starts_with_balanced_parenthesized_label(value: str) -> bool:
    text = value.lstrip()
    if not text.startswith("("):
        return False

    depth = 0
    for index, character in enumerate(text):
        if character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
            if depth == 0:
                return bool(text[1:index].strip())
            if depth < 0:
                return False
    return False


def navigation_text_evidence(
    items: tuple[str | None, ...],
    candidate_index: int,
) -> NavigationTextEvidence | None:
    if (
        candidate_index < 0
        or candidate_index >= len(items)
        or items[candidate_index] is not None
    ):
        return None

    adjacent = tuple(
        text
        for text in (
            _adjacent_visible_text(items, candidate_index, -1),
            _adjacent_visible_text(items, candidate_index, 1),
        )
        if text is not None
    )
    separator_adjacent = any(
        _is_separator_adjacent(text) for text in adjacent
    )
    label_follows = _parenthesized_label_follows(items, candidate_index)
    if not separator_adjacent and not label_follows:
        return None

    flattened, spans, candidate_offset = _flatten_navigation_items(
        items,
        candidate_index,
    )
    start, end = _candidate_sentence_window(flattened, candidate_offset)
    local_text = flattened[start:end]
    separator_count = local_text.count(">")
    if separator_count < 2 or not any(
        character.isalnum() for character in local_text
    ):
        return None

    text_item_indices = tuple(
        index
        for index, (item_start, item_end) in enumerate(spans)
        if items[index] is not None
        and item_end > start
        and item_start < end
    )
    return NavigationTextEvidence(
        separator_count=separator_count,
        parenthesized=(
            _balanced_parentheses_enclose_candidate(
                local_text,
                candidate_offset - start,
            )
            or label_follows
        ),
        text_item_indices=text_item_indices,
    )


def _adjacent_visible_text(
    items: tuple[str | None, ...],
    candidate_index: int,
    direction: int,
) -> str | None:
    index = candidate_index + direction
    while 0 <= index < len(items):
        text = items[index]
        if text is None:
            return None
        if text.strip():
            return text
        index += direction
    return None


def _is_separator_adjacent(value: str) -> bool:
    text = value.strip()
    return text.startswith(">") or text.endswith(">")


def _parenthesized_label_follows(
    items: tuple[str | None, ...],
    candidate_index: int,
) -> bool:
    prefix_parts: list[str] = []
    for text in items[candidate_index + 1 :]:
        if text is None:
            break
        before_separator, separator, _ = text.partition(">")
        prefix_parts.append(before_separator)
        if separator:
            break
    return starts_with_balanced_parenthesized_label("".join(prefix_parts))


def _flatten_navigation_items(
    items: tuple[str | None, ...],
    candidate_index: int,
) -> tuple[str, tuple[tuple[int, int], ...], int]:
    parts: list[str] = []
    spans: list[tuple[int, int]] = []
    offset = 0
    candidate_offset = -1
    for index, item in enumerate(items):
        part = _FIGURE_PLACEHOLDER if item is None else item
        start = offset
        offset += len(part)
        spans.append((start, offset))
        parts.append(part)
        if index == candidate_index:
            candidate_offset = start
    return "".join(parts), tuple(spans), candidate_offset


def _candidate_sentence_window(text: str, candidate_offset: int) -> tuple[int, int]:
    boundaries = tuple(_route_sentence_boundaries(text))
    start = max(
        (boundary for boundary in boundaries if boundary <= candidate_offset),
        default=0,
    )
    end = min(
        (boundary for boundary in boundaries if boundary > candidate_offset),
        default=len(text),
    )
    return start, end


def _route_sentence_boundaries(text: str) -> Iterable[int]:
    for index, character in enumerate(text):
        if character not in _ROUTE_SENTENCE_TERMINATORS:
            continue
        next_index = index + 1
        while next_index < len(text) and (
            text[next_index].isspace()
            or text[next_index] in _ROUTE_CLOSING_CHARACTERS
        ):
            next_index += 1
        if next_index < len(text) and text[next_index] == ">":
            continue
        if (
            character == "."
            and next_index < len(text)
            and text[next_index].islower()
            and _has_short_abbreviation_before(text, index)
        ):
            continue
        yield index + 1


def _has_short_abbreviation_before(text: str, period_index: int) -> bool:
    start = period_index
    while start > 0 and text[start - 1].isalpha():
        start -= 1
    return 0 < period_index - start <= 3


def _balanced_parentheses_enclose_candidate(
    text: str,
    candidate_offset: int,
) -> bool:
    depth = 0
    candidate_depth = 0
    for index, character in enumerate(text):
        if index == candidate_offset:
            candidate_depth = depth
        if character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0 and candidate_depth > 0


def parse_unambiguous_bbox(
    attributes: Iterable[tuple[object, object]],
) -> tuple[float, float, float, float] | None:
    values = [
        value
        for name, value in attributes
        if isinstance(name, str) and name.casefold() in {"bbox", "/bbox"}
    ]
    if not values:
        return None
    parsed = tuple(_parse_bbox(value) for value in values)
    if any(value is None for value in parsed):
        return None
    bbox = parsed[0]
    if bbox is None or any(value != bbox for value in parsed[1:]):
        return None
    return bbox


def parse_positive_finite_number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return None
    try:
        number = float(value)
    except (OverflowError, TypeError, ValueError):
        return None
    if not math.isfinite(number) or number <= 0:
        return None
    return number


def _parse_bbox(value: object) -> tuple[float, float, float, float] | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = ast.literal_eval(value)
    except (SyntaxError, ValueError):
        return None
    if not isinstance(parsed, (list, tuple)) or len(parsed) != 4:
        return None
    if any(
        isinstance(coordinate, bool)
        or not isinstance(coordinate, (int, float))
        for coordinate in parsed
    ):
        return None
    try:
        bbox = tuple(float(coordinate) for coordinate in parsed)
    except (OverflowError, TypeError, ValueError):
        return None
    if (
        not all(math.isfinite(coordinate) for coordinate in bbox)
        or bbox[2] <= bbox[0]
        or bbox[3] <= bbox[1]
    ):
        return None
    return bbox
