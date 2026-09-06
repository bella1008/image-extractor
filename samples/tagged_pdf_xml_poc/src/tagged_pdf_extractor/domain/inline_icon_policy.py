from __future__ import annotations

import ast
from collections.abc import Iterable
import math


INLINE_ICON_REASON = "small_inline_figure_with_adjacent_text"
MAX_INLINE_ICON_WIDTH_FONT_RATIO = 3.0
MAX_INLINE_ICON_HEIGHT_FONT_RATIO = 2.0


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
