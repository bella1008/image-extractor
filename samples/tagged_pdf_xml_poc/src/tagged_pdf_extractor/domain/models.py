from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal


@dataclass(frozen=True)
class Diagnostic:
    severity: Literal["warning", "error"]
    code: str
    message: str
    context: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TextStyle:
    font_name: str | None
    font_size: float | None


@dataclass(frozen=True)
class ContentFragment:
    page_index: int
    mcid: int | None
    text_parts: tuple[str, ...]
    object_ref: str | None = None
    text_styles: tuple[TextStyle, ...] = ()

    def __post_init__(self) -> None:
        if self.text_styles and len(self.text_parts) != len(self.text_styles):
            raise ValueError(
                f"ContentFragment has {len(self.text_parts)} text parts but "
                f"{len(self.text_styles)} text styles"
            )

    @property
    def text(self) -> str:
        return "".join(self.text_parts)


@dataclass(frozen=True)
class StructureElement:
    source_role: str
    semantic_role: str
    heading_level: int | None = None
    object_ref: str | None = None
    page_index: int | None = None
    title: str | None = None
    language: str | None = None
    alternate_text: str | None = None
    actual_text: str | None = None
    attributes: tuple[tuple[str, str], ...] = ()
    children: tuple[StructureElement | ContentFragment, ...] = ()


@dataclass(frozen=True)
class HeadingPromotion:
    child_path: tuple[int, ...]
    level: int
    label: str
    title: str
    series_index: int
    heading_font_size: float
    body_font_size: float
    font_size_ratio: float
    promotion_reason: str
    heading_font_names: tuple[str, ...] = ()
    body_font_names: tuple[str, ...] = ()


@dataclass(frozen=True)
class NumberedHeadingSeriesAudit:
    series_index: int
    labels: tuple[str, ...]
    valid_sequence: bool


@dataclass(frozen=True)
class SubtitleHint:
    child_path: tuple[int, ...]
    font_weight: int
    comparison_body_font_weight: int
    observed_line_count: int
    reason: str = "figure_table_title_stronger_than_following_body"


@dataclass(frozen=True)
class LineBreakHint:
    child_path: tuple[int, ...]
    reason: str = "source_actual_text_newline_after_comma_in_table_cell"


@dataclass(frozen=True)
class TextDisplayHint:
    child_path: tuple[int, ...]
    display_role: Literal["section_heading", "strong_label"]
    font_weight: int
    font_size: float
    comparison_body_font_weight: int
    comparison_body_font_size: float
    reason: str


@dataclass(frozen=True)
class SentenceBreakHint:
    child_path: tuple[int, ...]
    offsets: tuple[int, ...]
    reason: str = "conservative_sentence_terminal_in_review_container"


@dataclass(frozen=True)
class InlineIconHint:
    child_path: tuple[int, ...]
    page_index: int
    bbox: tuple[float, float, float, float]
    reference_font_size: float
    width_ratio: float
    height_ratio: float
    reason: str = "small_inline_figure_with_adjacent_text"


@dataclass(frozen=True)
class TaggedDocument:
    source_path: Path
    marked: bool
    language: str | None
    role_map: tuple[tuple[str, str], ...]
    children: tuple[StructureElement | ContentFragment, ...]
    diagnostics: tuple[Diagnostic, ...] = ()
    heading_promotions: tuple[HeadingPromotion, ...] = ()
    numbered_heading_series: tuple[NumberedHeadingSeriesAudit, ...] = ()
    numbered_heading_series_consistent: bool | None = None
    subtitle_hints: tuple[SubtitleHint, ...] = ()
    line_break_hints: tuple[LineBreakHint, ...] = ()
    text_display_hints: tuple[TextDisplayHint, ...] = ()
    sentence_break_hints: tuple[SentenceBreakHint, ...] = ()
    inline_icon_hints: tuple[InlineIconHint, ...] = ()


@dataclass(frozen=True)
class QualityReport:
    status: Literal["pass", "fail"]
    metrics: dict[str, Any]
    hard_gates: dict[str, bool]
    diagnostics: tuple[Diagnostic, ...]
    join_decisions: tuple[dict[str, Any], ...] = ()
    source_path: Path | None = None
    language: str | None = None
    marked: bool | None = None
    role_map: tuple[tuple[str, str], ...] = ()
    source_role_counts: dict[str, int] = field(default_factory=dict)
    heading_hierarchy: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class ExtractionArtifacts:
    raw_xml: Path
    semantic_xml: Path
    report_json: Path
    semantic_markdown: Path
