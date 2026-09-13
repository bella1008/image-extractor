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

    def __post_init__(self) -> None:
        if not isinstance(self.source_token, str) or not self.source_token.strip():
            raise ValueError("source_token must be a non-empty string")
        if self.doc_type not in {"A2", "A3", "BOOK"}:
            raise ValueError("doc_type must be A2, A3, or BOOK")
        if not isinstance(self.languages, tuple) or not self.languages:
            raise ValueError("languages must be a non-empty tuple")
        for language in self.languages:
            _validate_language_code(language)
        if len(set(self.languages)) != len(self.languages):
            raise ValueError("languages must not contain duplicates")
        if (
            not isinstance(self.language_count, int)
            or isinstance(self.language_count, bool)
            or self.language_count <= 0
            or self.language_count != len(self.languages)
        ):
            raise ValueError("language_count must equal the number of languages")


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
    source_structure_path: tuple[int, ...] | None = None
    display_direction: Literal["rtl"] | None = None


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


HeadingOrigin = Literal["source", "promoted"]
IntervalEvidenceOrigin = Literal["bookmark", "structural_language_section"]
HeadingMismatchComponent = Literal["count", "level", "origin", "numbered_label"]


@dataclass(frozen=True)
class LanguageIntervalEvidence:
    language: str
    start_page_index: int
    end_page_index: int
    start_path: tuple[int, ...]
    end_path: tuple[int, ...]
    evidence_origin: IntervalEvidenceOrigin

    def __post_init__(self) -> None:
        _validate_language_code(self.language)
        if not isinstance(self.start_page_index, int) or isinstance(
            self.start_page_index, bool
        ):
            raise ValueError("start_page_index must be an integer")
        if not isinstance(self.end_page_index, int) or isinstance(
            self.end_page_index, bool
        ):
            raise ValueError("end_page_index must be an integer")
        if self.start_page_index < 0 or self.end_page_index < self.start_page_index:
            raise ValueError("page bounds must be non-negative and ordered")
        _validate_child_path(self.start_path, "start_path")
        _validate_child_path(self.end_path, "end_path")
        if self.end_path < self.start_path:
            raise ValueError("path bounds must be ordered")
        if self.evidence_origin not in {"bookmark", "structural_language_section"}:
            raise ValueError("evidence_origin is not supported")


@dataclass(frozen=True)
class HeadingSignatureEntry:
    heading_level: int
    heading_origin: HeadingOrigin
    numbered_label: str | None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.heading_level, int)
            or isinstance(self.heading_level, bool)
            or self.heading_level <= 0
        ):
            raise ValueError("heading_level must be a positive integer")
        if self.heading_origin not in {"source", "promoted"}:
            raise ValueError("heading_origin must be source or promoted")
        if self.heading_origin == "source" and self.numbered_label is not None:
            raise ValueError("numbered_label must be None for a source heading")
        if self.heading_origin == "promoted" and (
            not isinstance(self.numbered_label, str)
            or len(self.numbered_label) != 2
            or self.numbered_label == "00"
            or any(character not in "0123456789" for character in self.numbered_label)
        ):
            raise ValueError("numbered_label must be an ASCII label from 01 through 99")


@dataclass(frozen=True)
class LanguageHeadingSignature:
    language: str
    interval: LanguageIntervalEvidence
    entries: tuple[HeadingSignatureEntry, ...]

    def __post_init__(self) -> None:
        if self.language != self.interval.language:
            raise ValueError("signature language must match interval language")
        if not isinstance(self.entries, tuple) or not all(
            isinstance(entry, HeadingSignatureEntry) for entry in self.entries
        ):
            raise ValueError("entries must be a tuple of HeadingSignatureEntry values")


@dataclass(frozen=True)
class HeadingMismatchPosition:
    language: str
    position: int
    component: HeadingMismatchComponent
    expected: HeadingSignatureEntry | None
    observed: HeadingSignatureEntry | None

    def __post_init__(self) -> None:
        if not self.language:
            raise ValueError("language is required")
        if (
            not isinstance(self.position, int)
            or isinstance(self.position, bool)
            or self.position < 0
        ):
            raise ValueError("position must be a non-negative integer")
        if self.component not in {"count", "level", "origin", "numbered_label"}:
            raise ValueError("component is not supported")
        if self.component == "count" and (self.expected is None) == (
            self.observed is None
        ):
            raise ValueError("count mismatch must identify one missing signature entry")
        if self.component != "count" and (
            self.expected is None or self.observed is None
        ):
            raise ValueError("component mismatch requires expected and observed entries")
        if self.component == "level" and (
            self.expected is not None
            and self.observed is not None
            and self.expected.heading_level == self.observed.heading_level
        ):
            raise ValueError("level mismatch entries must differ")
        if self.component == "origin" and (
            self.expected is not None
            and self.observed is not None
            and self.expected.heading_origin == self.observed.heading_origin
        ):
            raise ValueError("origin mismatch entries must differ")
        if self.component == "numbered_label" and (
            self.expected is not None
            and self.observed is not None
            and self.expected.numbered_label == self.observed.numbered_label
        ):
            raise ValueError("numbered_label mismatch entries must differ")


@dataclass(frozen=True)
class HeadingCountSourceException:
    code: str
    source_sha256: str
    # Observed source headings, not runtime translations or stable checklist keys.
    source_headings: tuple[tuple[str, tuple[int, ...], str], ...]
    covered_mismatches: tuple[HeadingMismatchPosition, ...]

    def __post_init__(self) -> None:
        if not self.code or len(self.source_sha256) != 64 or any(c not in "0123456789abcdef" for c in self.source_sha256):
            raise ValueError("source count exception requires a code and SHA-256")
        if not isinstance(self.source_headings, tuple) or not self.source_headings:
            raise ValueError("source count exception requires observed headings")
        for language, path, text in self.source_headings:
            _validate_language_code(language)
            _validate_child_path(path, "source heading path")
            if not isinstance(text, str) or not text.strip():
                raise ValueError("source heading text must be observed")
        if (not isinstance(self.covered_mismatches, tuple) or not self.covered_mismatches
                or any(not isinstance(m, HeadingMismatchPosition) or m.component != "count"
                       for m in self.covered_mismatches)):
            raise ValueError("source exception may cover count mismatches only")


@dataclass(frozen=True)
class MultilingualHeadingAudit:
    applicable: bool
    passed: bool
    expected_interval_count: int
    observed_interval_count: int
    interval_count_matches: bool | None
    total_heading_count_matches: bool | None
    heading_level_sequence_matches: bool | None
    heading_origin_sequence_matches: bool | None
    numbered_label_sequence_matches: bool | None
    signatures: tuple[LanguageHeadingSignature, ...] = ()
    mismatch_positions: tuple[HeadingMismatchPosition, ...] = ()
    diagnostics: tuple[Diagnostic, ...] = ()
    source_count_exception: HeadingCountSourceException | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.applicable, bool) or not isinstance(self.passed, bool):
            raise ValueError("applicable and passed must be booleans")
        for name, value in (
            ("expected_interval_count", self.expected_interval_count),
            ("observed_interval_count", self.observed_interval_count),
        ):
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        component_states = (
            self.total_heading_count_matches,
            self.heading_level_sequence_matches,
            self.heading_origin_sequence_matches,
            self.numbered_label_sequence_matches,
        )
        for state in (self.interval_count_matches, *component_states):
            if state is not None and not isinstance(state, bool):
                raise ValueError("audit component states must be booleans or None")
        for name, values, member_type in (
            ("signatures", self.signatures, LanguageHeadingSignature),
            ("mismatch_positions", self.mismatch_positions, HeadingMismatchPosition),
            ("diagnostics", self.diagnostics, Diagnostic),
        ):
            if not isinstance(values, tuple):
                raise ValueError(f"{name} must be a tuple")
            if not all(isinstance(value, member_type) for value in values):
                raise ValueError(f"{name} contains an invalid member")

        if not self.applicable:
            if not self.passed:
                raise ValueError("a not-applicable audit must pass")
            if self.interval_count_matches is not None or any(
                state is not None for state in component_states
            ):
                raise ValueError("a not-applicable audit cannot have component results")
            if self.signatures or self.mismatch_positions or self.diagnostics or self.source_count_exception:
                raise ValueError("a not-applicable audit cannot have evidence")
            return

        if self.interval_count_matches is None:
            raise ValueError("an applicable audit requires an interval count result")
        counts_are_equal = (
            self.expected_interval_count == self.observed_interval_count
        )
        if self.interval_count_matches != counts_are_equal:
            raise ValueError("interval count result contradicts the interval counts")

        all_pending = all(state is None for state in component_states)
        all_evaluated = all(isinstance(state, bool) for state in component_states)
        if not all_pending and not all_evaluated:
            raise ValueError("signature component states must be all pending or evaluated")
        if all_pending:
            if self.passed or self.signatures or self.mismatch_positions or self.source_count_exception:
                raise ValueError("a pending applicable audit must fail closed")
            if not self.diagnostics:
                raise ValueError("a pending applicable audit requires a diagnostic")
            return

        if not self.interval_count_matches:
            raise ValueError("signature components cannot be evaluated for invalid intervals")
        if len(self.signatures) != self.observed_interval_count:
            raise ValueError("signature count must match observed interval count")
        if self.diagnostics:
            raise ValueError("an evaluated audit cannot contain failure diagnostics")
        exception = self.source_count_exception
        if exception is not None:
            if not isinstance(exception, HeadingCountSourceException):
                raise ValueError("invalid source count exception")
            if (self.total_heading_count_matches or not all(component_states[1:])
                    or exception.covered_mismatches != self.mismatch_positions):
                raise ValueError("source exception must cover all and only count mismatches")
        expected_passed = all(component_states) or exception is not None
        if self.passed != expected_passed:
            raise ValueError("passed contradicts the evaluated component results")
        mismatch_components = {
            mismatch.component for mismatch in self.mismatch_positions
        }
        for state, component in (
            (self.total_heading_count_matches, "count"),
            (self.heading_level_sequence_matches, "level"),
            (self.heading_origin_sequence_matches, "origin"),
            (self.numbered_label_sequence_matches, "numbered_label"),
        ):
            if state == (component in mismatch_components):
                raise ValueError(
                    f"{component} component result contradicts mismatch positions"
                )
        if self.passed and self.mismatch_positions and exception is None:
            raise ValueError("a passed audit cannot contain mismatch positions")
        if not self.passed and not self.mismatch_positions:
            raise ValueError("a failed evaluated audit requires mismatch positions")


def _validate_child_path(path: tuple[int, ...], name: str) -> None:
    if not isinstance(path, tuple) or not path:
        raise ValueError(f"{name} must be a non-empty tuple")
    if any(
        not isinstance(index, int) or isinstance(index, bool) or index < 0
        for index in path
    ):
        raise ValueError(f"{name} must contain non-negative integer indices")


def _validate_language_code(language: object) -> None:
    if (
        not isinstance(language, str)
        or not language
        or language != language.upper()
        or language.startswith("-")
        or language.endswith("-")
        or "--" in language
        or any(
            character not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ-" for character in language
        )
    ):
        raise ValueError("language must be a canonical uppercase ASCII code")


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
class BookmarkPageBounds:
    ordinal: int
    start_page_index: int
    end_page_index: int
    source_title: str | None = None

    def __post_init__(self) -> None:
        for name, value in (
            ("ordinal", self.ordinal),
            ("start_page_index", self.start_page_index),
            ("end_page_index", self.end_page_index),
        ):
            if not isinstance(value, int) or isinstance(value, bool):
                raise ValueError(f"{name} must be an integer")
        if self.ordinal <= 0:
            raise ValueError("ordinal must be positive")
        if self.start_page_index < 0:
            raise ValueError("start_page_index must be non-negative")
        if self.end_page_index < self.start_page_index:
            raise ValueError("page bounds must be ordered")
        if self.source_title is not None and not isinstance(self.source_title, str):
            raise ValueError("source_title must be a string or None")


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
    multilingual_heading_audit: MultilingualHeadingAudit | None = None
    bookmark_page_bounds: tuple[BookmarkPageBounds, ...] = ()
    raw_children: tuple[StructureElement | ContentFragment, ...] | None = None
    source_sha256: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.bookmark_page_bounds, tuple):
            raise ValueError("bookmark_page_bounds must be a tuple")
        if not all(
            isinstance(bounds, BookmarkPageBounds)
            for bounds in self.bookmark_page_bounds
        ):
            raise ValueError(
                "bookmark_page_bounds must contain BookmarkPageBounds values"
            )


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
