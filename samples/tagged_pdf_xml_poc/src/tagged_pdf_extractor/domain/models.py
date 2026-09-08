from __future__ import annotations

from dataclasses import dataclass, field
import math
from pathlib import Path
from typing import Any, Literal

from tagged_pdf_extractor.domain.inline_icon_policy import INLINE_ICON_REASON


BBox = tuple[float, float, float, float]


@dataclass(frozen=True)
class PdfProfile:
    source_token: str
    doc_type: str
    languages: tuple[str, ...]
    language_count: int


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
    text_bboxes: tuple[BBox | None, ...] = ()

    def __post_init__(self) -> None:
        if self.text_styles and len(self.text_parts) != len(self.text_styles):
            raise ValueError(
                f"ContentFragment has {len(self.text_parts)} text parts but "
                f"{len(self.text_styles)} text styles"
            )
        if self.text_bboxes and len(self.text_parts) != len(self.text_bboxes):
            raise ValueError(
                f"ContentFragment has {len(self.text_parts)} text parts but "
                f"{len(self.text_bboxes)} text bboxes"
            )

    @property
    def text(self) -> str:
        return "".join(self.text_parts)

    @property
    def bbox(self) -> BBox | None:
        finite_boxes = tuple(
            bbox
            for bbox in self.text_bboxes
            if bbox is not None and all(math.isfinite(value) for value in bbox)
        )
        if not finite_boxes:
            return None
        return (
            min(bbox[0] for bbox in finite_boxes),
            min(bbox[1] for bbox in finite_boxes),
            max(bbox[2] for bbox in finite_boxes),
            max(bbox[3] for bbox in finite_boxes),
        )


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
    title_end_offset: int | None = None
    qualifier_start_offset: int | None = None


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
    reason: str = INLINE_ICON_REASON
    route_separator_count: int | None = None
    route_parenthesized: bool | None = None


@dataclass(frozen=True)
class ContinuationTypographyEvidence:
    preceding_body_font_weight: int
    preceding_body_font_size: float
    preceding_body_observed_lines: tuple[tuple[int, int], ...]
    target_font_weight: int
    target_font_size: float
    target_observed_lines: tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class ContinuationHint:
    child_path: tuple[int, ...]
    preceding_list_item_path: tuple[int, ...]
    preceding_list_body_path: tuple[int, ...]
    page_index: int
    paragraph_bbox: BBox
    list_body_bbox: BBox
    left_delta: float
    vertical_gap: float
    reference_font_size: float
    source_role: str
    typography_evidence: ContinuationTypographyEvidence
    reason: str = "sibling_list_paragraph_list_geometry_typography"


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
    continuation_hints: tuple[ContinuationHint, ...] = ()


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
