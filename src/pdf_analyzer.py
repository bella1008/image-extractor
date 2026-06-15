from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import re
from typing import Iterable

import fitz

from src.models import GridCell, LanguagePage, LanguageSection, PageLayout, PdfStructure, TextSpan


PAGE_SIZE_TOLERANCE = 8.0
KNOWN_PAGE_SIZES = {
    "A5": (466.5, 642.3),
    "A3": (888.9, 1237.6),
    "A2": (1730.8, 1237.6),
}
LANGUAGE_LABEL_PATTERN = re.compile(r"^[A-Z]+(?:-[A-Z]+)?$")
RTL_LANGUAGE_CODES = {"ARA", "HEB"}
BOOKMARK_LANGUAGE_CODES = {
    "English": "ENG",
    "Français": "FRA",
    "Español": "SPA",
    "Português": "POR",
    "العربية": "ARA",
    "Русский": "RUS",
    "Қазақ": "KAZ",
    "Монгол": "MON",
    "Кыргызча": "KYR",
    "Deutsch": "DEU",
    "Svenska": "SWE",
    "Dansk": "DAN",
    "Norsk": "NOR",
    "Suomi": "FIN",
    "Català": "CAT",
    "Galego": "GLG",
    "Euskara": "EUS",
    "Magyar": "HUN",
    "Polski": "POL",
    "Ελληνικά": "GRE",
    "Български": "BUL",
    "Hrvatski": "CRO",
    "Čeština": "CZE",
    "Slovenčina": "SLK",
    "Română": "ROM",
    "Srpski": "SER",
    "Shqip": "ALB",
    "Македонски": "MKD",
    "Slovenščina": "SLV",
    "Latviešu": "LAT",
    "Lietuvių kalba": "LTU",
    "Eesti": "EST",
    "Italiano": "ITA",
    "Nederlands": "DUT",
}


def analyze_pdf_structure(file_path: str | Path) -> PdfStructure:
    path = Path(file_path)
    with fitz.open(path) as document:
        detected_types = [detect_page_layout(page, page_index).page_size for page_index, page in enumerate(document, start=1)]
        detected_doc_type = detect_doc_type(detected_types)
        language_sections = ()
        section_by_page = {}
        review_order_by_page = {}
        if detected_doc_type == "BOOK":
            language_sections = tuple(extract_bookmark_language_sections(document))
            section_by_page = map_language_sections_by_page(language_sections)
            review_order_by_page = map_book_review_order_by_page(document.page_count, language_sections)

        language_pages = []
        for page_index, page in enumerate(document, start=1):
            layout = detect_page_layout(page, page_index)
            section = section_by_page.get(page_index)
            if section:
                language = section.language
                reading_direction = section.reading_direction
                page_role = detect_book_section_page_role(page_index, section)
            else:
                language = detect_corner_language_label(page) or f"PAGE-{page_index}"
                reading_direction = "rtl" if language in RTL_LANGUAGE_CODES else "ltr"
                page_role = (
                    detect_unassigned_book_page_role(page_index, language_sections)
                    if detected_doc_type == "BOOK"
                    else "content"
                )
            grid_cells = extract_grid_cells(page, layout, language, reading_direction, page_role)
            language_pages.append(
                LanguagePage(
                    page_number=page_index,
                    language=language,
                    layout=layout,
                    grid_cells=tuple(grid_cells),
                    reading_direction=reading_direction,
                    page_role=page_role,
                    review_order=review_order_by_page.get(page_index, page_index),
                )
            )

        return PdfStructure(
            file_name=path.name,
            page_count=document.page_count,
            detected_doc_type=detected_doc_type,
            language_pages=tuple(language_pages),
            language_sections=language_sections,
        )


def detect_page_layout(page: fitz.Page, page_number: int) -> PageLayout:
    width = round(page.rect.width, 1)
    height = round(page.rect.height, 1)
    page_size = detect_page_size(width, height)
    orientation = "landscape" if width > height else "portrait"

    rows = 1
    columns = 1
    layout_rule = f"{page_size}_{orientation}".upper()
    has_cover_area = False

    if page_size == "A2" and orientation == "landscape":
        rows = 2
        columns = 8
        layout_rule = "A2_LANDSCAPE_2X8"
        has_cover_area = True
    elif page_size == "A3" and orientation == "portrait":
        rows = 2
        columns = 4
        layout_rule = "A3_PORTRAIT_2X4"
        has_cover_area = page_number == 1
    elif page_size == "A5" and orientation == "portrait":
        rows = 1
        columns = 2
        layout_rule = "A5_BOOK_PORTRAIT_1X2"

    return PageLayout(
        page_number=page_number,
        width=width,
        height=height,
        page_size=page_size,
        orientation=orientation,
        rows=rows,
        columns=columns,
        layout_rule=layout_rule,
        has_cover_area=has_cover_area,
    )


def detect_page_size(width: float, height: float) -> str:
    for name, (known_width, known_height) in KNOWN_PAGE_SIZES.items():
        if close(width, known_width) and close(height, known_height):
            return name
        if close(width, known_height) and close(height, known_width):
            return name
    return "UNKNOWN"


def close(actual: float, expected: float) -> bool:
    return abs(actual - expected) <= PAGE_SIZE_TOLERANCE


def detect_doc_type(page_sizes: Iterable[str]) -> str:
    sizes = set(page_sizes)
    if sizes == {"A5"}:
        return "BOOK"
    if "A2" in sizes:
        return "A2"
    if "A3" in sizes:
        return "A3"
    return "UNKNOWN"


def detect_corner_language_label(page: fitz.Page) -> str | None:
    left_label = None
    right_label = None
    page_width = page.rect.width

    for span in iter_text_spans(page):
        x0, y0, _x1, _y1 = span["bbox"]
        text = span["text"].strip()
        if not text or y0 >= 50 or not is_language_label(text):
            continue
        if x0 < 80:
            left_label = text
        elif _x1 > page_width - 80:
            right_label = text

    return left_label or right_label


def is_language_label(text: str) -> bool:
    return bool(LANGUAGE_LABEL_PATTERN.fullmatch(text))


def extract_grid_cells(
    page: fitz.Page,
    layout: PageLayout,
    language: str,
    reading_direction: str = "ltr",
    page_role: str = "content",
) -> list[GridCell]:
    text_by_cell: dict[tuple[int, int], list[str]] = defaultdict(list)
    spans_by_cell: dict[tuple[int, int], list[TextSpan]] = defaultdict(list)
    cell_width = layout.width / layout.columns
    cell_height = layout.height / layout.rows

    for span in iter_text_spans(page):
        text = span["text"].strip()
        if not text:
            continue
        x0, y0, x1, y1 = span["bbox"]
        center_x = (x0 + x1) / 2
        center_y = (y0 + y1) / 2
        column = min(int(center_x // cell_width) + 1, layout.columns)
        row = min(int(center_y // cell_height) + 1, layout.rows)
        text_by_cell[(row, column)].append(text)
        spans_by_cell[(row, column)].append(
            TextSpan(
                text=text,
                bbox=tuple(round(value, 2) for value in span["bbox"]),
                font=span["font"],
                size=round(float(span["size"]), 2),
                flags=int(span["flags"]),
                bold_candidate=is_bold_candidate(span),
                italic_candidate=is_italic_candidate(span),
                underline_candidate=False,
            )
        )

    cells = []
    for row in range(1, layout.rows + 1):
        for column in range(1, layout.columns + 1):
            role = detect_cell_role(layout, row, column, page_role)
            text = "\n".join(text_by_cell.get((row, column), []))
            cells.append(
                GridCell(
                    page_number=layout.page_number,
                    language=language,
                    row=row,
                    column=column,
                    role=role,
                    text=text,
                    reading_order=detect_cell_reading_order(layout, row, column, reading_direction),
                    reading_direction=reading_direction,
                    styled_spans=tuple(spans_by_cell.get((row, column), [])),
                )
            )
    return cells


def detect_cell_role(layout: PageLayout, row: int, column: int, page_role: str = "content") -> str:
    if layout.layout_rule == "A5_BOOK_PORTRAIT_1X2":
        return page_role
    if layout.layout_rule == "A2_LANDSCAPE_2X8" and row == 1 and column <= 2:
        return "cover"
    if layout.layout_rule == "A3_PORTRAIT_2X4" and layout.page_number == 1 and row == 1 and column <= 2:
        return "cover"
    return "content"


def detect_cell_reading_order(
    layout: PageLayout, row: int, column: int, reading_direction: str
) -> int:
    if reading_direction == "rtl":
        return ((row - 1) * layout.columns) + (layout.columns - column + 1)
    return ((row - 1) * layout.columns) + column


def map_language_sections_by_page(sections: tuple[LanguageSection, ...]) -> dict[int, LanguageSection]:
    section_by_page = {}
    for section in sections:
        for page_number in section.page_numbers:
            section_by_page[page_number] = section
    return section_by_page


def detect_book_section_page_role(page_number: int, section: LanguageSection) -> str:
    if section.page_numbers and page_number == section.page_numbers[0]:
        return "section_front_cover"
    if section.page_numbers and page_number == section.page_numbers[-1]:
        return "section_back_cover"
    return "content"


def detect_unassigned_book_page_role(
    page_number: int, sections: tuple[LanguageSection, ...]
) -> str:
    return "book_unassigned"


def map_book_review_order_by_page(
    page_count: int, sections: tuple[LanguageSection, ...]
) -> dict[int, int]:
    section_pages = {page for section in sections for page in section.page_numbers}
    before_sections = [page for page in range(1, page_count + 1) if page not in section_pages]
    ordered_pages = []
    ordered_pages.extend(page for page in before_sections if page < min(section_pages, default=page_count + 1))
    for section in sections:
        ordered_pages.extend(section.page_numbers)
    ordered_pages.extend(page for page in before_sections if page > max(section_pages, default=0))
    ordered_pages.extend(page for page in before_sections if page not in ordered_pages)
    return {page: index for index, page in enumerate(ordered_pages, start=1)}


def extract_bookmark_language_sections(document: fitz.Document) -> list[LanguageSection]:
    toc = [
        (level, title.strip(), page_number, bookmark_title_to_language_code(title.strip()))
        for level, title, page_number in document.get_toc(simple=True)
        if title.strip() and page_number > 0
    ]
    rtl_physical_starts = detect_rtl_physical_starts(document, toc)

    sections = []
    for index, (level, title, bookmark_page, language) in enumerate(toc):
        start_page = rtl_physical_starts.get(index, bookmark_page)
        if index + 1 in rtl_physical_starts:
            next_start_page = rtl_physical_starts[index + 1]
        elif index + 1 < len(toc):
            next_start_page = toc[index + 1][2]
        else:
            next_start_page = document.page_count + 1
        end_page = max(start_page, next_start_page - 1)
        reading_direction = "rtl" if language in RTL_LANGUAGE_CODES else "ltr"
        page_numbers = tuple(range(start_page, end_page + 1))
        if reading_direction == "rtl":
            page_numbers = tuple(reversed(page_numbers))
        sections.append(
            LanguageSection(
                language=language,
                title=title,
                start_page=start_page,
                end_page=end_page,
                bookmark_page=bookmark_page,
                bookmark_level=level,
                reading_order=index + 1,
                reading_direction=reading_direction,
                page_numbers=page_numbers,
            )
        )
    return sections


def bookmark_title_to_language_code(title: str) -> str:
    return BOOKMARK_LANGUAGE_CODES.get(title, title)


def detect_rtl_physical_starts(
    document: fitz.Document, toc: list[tuple[int, str, int, str]]
) -> dict[int, int]:
    starts = {}
    for index, (_level, _title, bookmark_page, language) in enumerate(toc):
        if language not in RTL_LANGUAGE_CODES:
            continue
        search_start = toc[index - 1][2] + 1 if index > 0 else 1
        first_script_page = find_first_rtl_script_page(document, language, search_start, document.page_count)
        if first_script_page and first_script_page < bookmark_page:
            starts[index] = first_script_page
    return starts


def find_first_rtl_script_page(
    document: fitz.Document, language: str, start_page: int, end_page: int
) -> int | None:
    for page_number in range(start_page, end_page + 1):
        text = document[page_number - 1].get_text("text")
        if has_rtl_language_script(text, language):
            return page_number
    return None


def has_rtl_language_script(text: str, language: str) -> bool:
    if language == "ARA":
        return count_codepoints_in_ranges(text, ((0x0600, 0x06FF), (0x0750, 0x077F), (0x08A0, 0x08FF))) >= 10
    if language == "HEB":
        return count_codepoints_in_ranges(text, ((0x0590, 0x05FF),)) >= 10
    return False


def count_codepoints_in_ranges(text: str, ranges: tuple[tuple[int, int], ...]) -> int:
    count = 0
    for char in text:
        codepoint = ord(char)
        if any(start <= codepoint <= end for start, end in ranges):
            count += 1
    return count


def iter_text_spans(page: fitz.Page) -> Iterable[dict]:
    text_dict = page.get_text("dict")
    for block in text_dict["blocks"]:
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                text = span.get("text", "").strip()
                if not text:
                    continue
                yield {
                    "text": text,
                    "bbox": span.get("bbox", (0, 0, 0, 0)),
                    "font": span.get("font", ""),
                    "size": span.get("size", 0),
                    "flags": span.get("flags", 0),
                }


def is_bold_candidate(span: dict) -> bool:
    font = span.get("font", "").lower()
    if "bold" in font or "black" in font or "heavy" in font:
        return True
    match = re.search(r"[-_](\d{3})(?:\D|$)", font)
    return bool(match and int(match.group(1)) >= 600)


def is_italic_candidate(span: dict) -> bool:
    font = span.get("font", "").lower()
    return "italic" in font or "oblique" in font
