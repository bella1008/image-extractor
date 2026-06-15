from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ParsedManualFilename:
    file_path: Path
    file_name: str
    manual_code: str
    manual_type: str
    product_info: str
    buyer_region_token: str
    language_token: str
    source_token: str
    date_code: str


@dataclass(frozen=True)
class PdfProfile:
    source_token: str
    region: str
    buyer_codes: tuple[str, ...]
    languages: tuple[str, ...]
    doc_type: str
    language_count: int


@dataclass(frozen=True)
class ProfileLookupResult:
    parsed_filename: ParsedManualFilename
    profile: PdfProfile


@dataclass(frozen=True)
class TextSpan:
    text: str
    bbox: tuple[float, float, float, float]
    font: str
    size: float
    flags: int
    bold_candidate: bool
    italic_candidate: bool
    underline_candidate: bool


@dataclass(frozen=True)
class GridCell:
    page_number: int
    language: str
    row: int
    column: int
    role: str
    text: str
    reading_order: int = 0
    reading_direction: str = "ltr"
    styled_spans: tuple[TextSpan, ...] = ()


@dataclass(frozen=True)
class PageLayout:
    page_number: int
    width: float
    height: float
    page_size: str
    orientation: str
    rows: int
    columns: int
    layout_rule: str
    has_cover_area: bool


@dataclass(frozen=True)
class LanguagePage:
    page_number: int
    language: str
    layout: PageLayout
    grid_cells: tuple[GridCell, ...]
    reading_direction: str = "ltr"
    page_role: str = "content"
    review_order: int = 0


@dataclass(frozen=True)
class LanguageSection:
    language: str
    title: str
    start_page: int
    end_page: int
    bookmark_page: int
    bookmark_level: int
    reading_order: int
    reading_direction: str
    page_numbers: tuple[int, ...]


@dataclass(frozen=True)
class PdfStructure:
    file_name: str
    page_count: int
    detected_doc_type: str
    language_pages: tuple[LanguagePage, ...]
    language_sections: tuple[LanguageSection, ...] = ()


@dataclass(frozen=True)
class ValidationIssue:
    field: str
    expected: str
    actual: str
    severity: str
    message: str


@dataclass(frozen=True)
class StructureValidationResult:
    status: str
    issues: tuple[ValidationIssue, ...]
