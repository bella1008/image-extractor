from __future__ import annotations

from dataclasses import dataclass
import re
from typing import TypeVar

from tagged_pdf_extractor.domain.models import ContentFragment, StructureElement


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
_WeightedValue = TypeVar("_WeightedValue", int, float)


@dataclass(frozen=True)
class TypographyEvidence:
    font_weight: int
    font_size: float
    observed_lines: frozenset[tuple[int, int]]


def normalize_font_weight(font_name: str | None) -> int | None:
    if not font_name:
        return None
    normalized = font_name.rsplit("+", 1)[-1].strip().lower()
    numeric = _TRAILING_WEIGHT.search(normalized)
    if numeric:
        return int(numeric.group(1))
    for keyword, weight in _KEYWORD_WEIGHTS:
        if re.search(rf"(?:^|[-_\s]){re.escape(keyword)}$", normalized):
            return weight
    return None


def typography_evidence(
    element: StructureElement,
) -> TypographyEvidence | None:
    weight_samples: list[tuple[int, int]] = []
    size_samples: list[tuple[float, int]] = []
    observed_lines: set[tuple[int, int]] = set()
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
                style = child.text_styles[part_index]
                weight = normalize_font_weight(style.font_name)
                if weight is None or style.font_size is None or style.font_size <= 0:
                    valid = False
                    continue
                weight_samples.append((weight, visible_count))
                size_samples.append((style.font_size, visible_count))
                observed_lines.add((child.page_index, child.mcid))

    visit(element.children)
    if not valid or not weight_samples or not size_samples or not observed_lines:
        return None
    return TypographyEvidence(
        font_weight=_weighted_median(weight_samples),
        font_size=_weighted_median(size_samples),
        observed_lines=frozenset(observed_lines),
    )


def _weighted_median(
    samples: list[tuple[_WeightedValue, int]],
) -> _WeightedValue:
    ordered = sorted(samples)
    total = sum(count for _, count in ordered)
    threshold = (total + 1) // 2
    cumulative = 0
    for value, count in ordered:
        cumulative += count
        if cumulative >= threshold:
            return value
    raise AssertionError("weighted median requires at least one sample")
