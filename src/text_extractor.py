from __future__ import annotations

import re
from dataclasses import asdict
from typing import Any

from src.models import ParsedManualFilename, PdfProfile, PdfStructure


BULLET = chr(0x2022)
EN_DASH = chr(0x2013)
SENTENCE_END_PATTERN = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(\[])")
ABBREVIATION_PLACEHOLDERS = {
    "e.g.": "e__g__",
    "i.e.": "i__e__",
    "etc.": "etc__",
    "No.": "No__",
    "Fig.": "Fig__",
    "Mr.": "Mr__",
    "Ms.": "Ms__",
    "Dr.": "Dr__",
}
NON_HEADING_TEXTS = {
    "on",
    "or",
    "Yes",
    "Simple User Guide",
    "Do Not Touch This Screen!",
    "Do Not Touch",
    "This Screen!",
    "(The Frame only)",
}


def extract_review_text(
    parsed_filename: ParsedManualFilename,
    profile: PdfProfile,
    structure: PdfStructure,
    language: str = "ENG",
) -> dict[str, Any]:
    pages = [
        page
        for page in sorted(structure.language_pages, key=lambda item: item.review_order)
        if page.language == language
    ]

    extracted_pages = []
    flat_cells = []
    total_chars = 0
    total_sentences = 0
    empty_cells = 0
    total_cells = 0

    for page in pages:
        cells = []
        for cell in sorted(page.grid_cells, key=lambda item: item.reading_order):
            review_items = build_review_items(cell.text, language=language)
            normalized_text = build_normalized_text(review_items)
            normalized_sentences = split_sentences(normalized_text, language=language)
            sentences = [
                sentence
                for item in review_items
                if item["kind"] != "heading"
                for sentence in item["sentences"]
            ]
            total_chars += len(cell.text)
            total_sentences += len(sentences)
            total_cells += 1
            if not cell.text.strip():
                empty_cells += 1

            cells.append(
                {
                    "row": cell.row,
                    "column": cell.column,
                    "role": cell.role,
                    "reading_order": cell.reading_order,
                    "reading_direction": cell.reading_direction,
                    "char_count": len(cell.text),
                    "text": cell.text,
                    "style_spans": [asdict(span) for span in cell.styled_spans],
                    "style_summary": summarize_cell_style(cell.styled_spans),
                    "normalized_text": normalized_text,
                    "normalized_sentences": [
                        {"sentence_order": index, "text": sentence}
                        for index, sentence in enumerate(normalized_sentences, start=1)
                    ],
                    "review_items": review_items,
                    "sentences": [
                        {"sentence_order": index, "text": sentence}
                        for index, sentence in enumerate(sentences, start=1)
                    ],
                }
            )
            flat_cells.append(
                {
                    "page_number": page.page_number,
                    "review_order": page.review_order,
                    "page_role": page.page_role,
                    "row": cell.row,
                    "column": cell.column,
                    "cell_role": cell.role,
                    "cell_order": cell.reading_order,
                    "reading_direction": cell.reading_direction,
                    "text": cell.text,
                    "review_items": review_items,
                    "style_spans": [asdict(span) for span in cell.styled_spans],
                }
            )

        extracted_pages.append(
            {
                "page_number": page.page_number,
                "review_order": page.review_order,
                "language": page.language,
                "page_role": page.page_role,
                "reading_direction": page.reading_direction,
                "layout": asdict(page.layout),
                "cells": cells,
            }
        )

    return {
        "file_name": parsed_filename.file_name,
        "source_token": parsed_filename.source_token,
        "region": profile.region,
        "buyer_codes": list(profile.buyer_codes),
        "profile_languages": list(profile.languages),
        "language": language,
        "language_variant": None,
        "doc_type": profile.doc_type,
        "detected_doc_type": structure.detected_doc_type,
        "page_count": structure.page_count,
        "extraction": {
            "method": "pymupdf_text",
            "unit": "grid_cell_sentence",
            "ocr_applied": False,
            "ocr_recommended": should_recommend_ocr(total_chars, total_cells, empty_cells),
            "total_chars": total_chars,
            "total_sentences": total_sentences,
            "total_cells": total_cells,
            "empty_cells": empty_cells,
        },
        "sections": build_sections(flat_cells, language=language),
        "cover_pages": build_cover_pages(flat_cells),
        "pages": extracted_pages,
    }


def summarize_cell_style(spans: tuple[Any, ...]) -> dict[str, Any]:
    if not spans:
        return {
            "span_count": 0,
            "max_font_size": 0,
            "bold_span_count": 0,
            "italic_span_count": 0,
            "underline_span_count": 0,
        }
    return {
        "span_count": len(spans),
        "max_font_size": max(span.size for span in spans),
        "bold_span_count": sum(1 for span in spans if span.bold_candidate),
        "italic_span_count": sum(1 for span in spans if span.italic_candidate),
        "underline_span_count": sum(1 for span in spans if span.underline_candidate),
    }


def build_cover_pages(cells: list[dict[str, Any]]) -> list[dict[str, Any]]:
    pages: dict[int, list[dict[str, Any]]] = {}
    for cell in cells:
        if cell["cell_role"] == "cover":
            pages.setdefault(cell["page_number"], []).append(cell)

    cover_pages = []
    for page_number, cover_cells in sorted(pages.items()):
        ordered_cells = sorted(cover_cells, key=lambda cell: cell["cell_order"])
        regions = []
        for cell in ordered_cells:
            regions.extend(build_cover_regions(cell))
        regions = post_process_cover_regions(regions)
        cover_pages.append(
            {
                "page_number": page_number,
                "page_role": "cover",
                "schema": detect_cover_schema(ordered_cells),
                "schema_validation": validate_cover_schema(
                    detect_cover_schema(ordered_cells), regions
                ),
                "regions": regions,
                "markdown": build_cover_markdown(regions),
            }
        )
    return cover_pages


def detect_cover_schema(cells: list[dict[str, Any]]) -> dict[str, Any]:
    # First explicit schema: Canadian ZC A2 cover, shared by ENG and C-FRA.
    text = " ".join(cell["text"] for cell in cells)
    if (
        "1-800-SAMSUNG" in text
        and (
            "Contact Samsung world wide" in text
            or "Samsung Service Center" in text
            or "Comment contacter Samsung" in text
        )
    ):
        return {
            "schema_id": "ZC_A2_COVER",
            "schema_version": 1,
            "required_regions": [
                "language_label",
                "title",
                "model_serial_fields",
                "support_note",
                "disclaimer",
                "contact_heading",
                "contact_table",
                "copyright",
                "document_code",
            ],
            "optional_regions": ["contact_note", "address"],
        }
    return {
        "schema_id": "generic_cover",
        "schema_version": 1,
        "required_regions": [],
        "optional_regions": [],
    }


def validate_cover_schema(schema: dict[str, Any], regions: list[dict[str, Any]]) -> dict[str, Any]:
    present = {region["region_type"] for region in regions}
    required = set(schema.get("required_regions", []))
    missing = sorted(required - present)
    return {
        "status": "PASS" if not missing else "REVIEW_REQUIRED",
        "present_regions": sorted(present),
        "missing_required_regions": missing,
    }


def build_cover_regions(cell: dict[str, Any]) -> list[dict[str, Any]]:
    spans = sorted(cell["style_spans"], key=lambda span: (span["bbox"][1], span["bbox"][0]))
    regions: list[dict[str, Any]] = []
    index = 0
    while index < len(spans):
        span = spans[index]
        text = span["text"]
        region_type = detect_cover_region_type(text, span)

        if region_type in {"copyright", "document_code", "language_label"}:
            regions.append(make_cover_region(region_type, [span], cell))
            index += 1
            continue

        region_spans = [span]
        index += 1
        while index < len(spans) and should_merge_cover_span(region_type, spans[index]):
            region_spans.append(spans[index])
            index += 1
        regions.append(make_cover_region(region_type, region_spans, cell))

    return merge_cover_regions(regions)


def detect_cover_region_type(text: str, span: dict[str, Any]) -> str:
    normalized = normalize_sentence(text)
    if normalized in {"ENG", "KOR", "ARA", "INS", "TPE", "C-FRA"}:
        return "language_label"
    if "All rights reserved" in normalized:
        return "copyright"
    if normalized == "-00" or re.fullmatch(r"BN\d{2}-\d{5}[A-Z]-\d{2}", normalized):
        return "document_code"
    if span["size"] >= 20:
        return "title"
    if "Contact Samsung" in normalized:
        return "contact_heading"
    if normalized in {"Samsung Service Center", "Website", "Address"}:
        return "table_heading"
    if normalized.startswith("www."):
        return "website"
    if "If you have any questions, please call" in normalized:
        return "support_note"
    if "1-800" in normalized:
        return "contact_value"
    if "Model" in normalized and "Serial" in normalized:
        return "model_serial_fields"
    if "Figures and illustrations" in normalized:
        return "disclaimer"
    if "Product design and specifications may change" in normalized:
        return "product_note"
    if "questions or comments" in normalized:
        return "contact_note"
    return "body"


def should_merge_cover_span(region_type: str, span: dict[str, Any]) -> bool:
    next_type = detect_cover_region_type(span["text"], span)
    if region_type == "body":
        return next_type == "body"
    if region_type == "disclaimer":
        return next_type == "disclaimer"
    if region_type == "contact_note":
        return next_type == "contact_note"
    if region_type == "website":
        return next_type == "website"
    return False


def make_cover_region(
    region_type: str, spans: list[dict[str, Any]], cell: dict[str, Any]
) -> dict[str, Any]:
    text = normalize_sentence(" ".join(span["text"] for span in spans))
    return {
        "region_order": 0,
        "region_type": region_type,
        "heading": cover_region_heading(region_type, text),
        "text": text,
        "bbox": union_bbox([span["bbox"] for span in spans]),
        "source": make_source(cell),
        "style_summary": summarize_cover_spans(spans),
        "markdown": cover_region_to_markdown(region_type, text),
    }


def merge_cover_regions(regions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    for region in regions:
        if (
            merged
            and region["region_type"] in {"website"}
            and merged[-1]["region_type"] == region["region_type"]
        ):
            merged[-1]["text"] = normalize_sentence(f"{merged[-1]['text']} {region['text']}")
            merged[-1]["bbox"] = union_bbox([merged[-1]["bbox"], region["bbox"]])
            merged[-1]["markdown"] = cover_region_to_markdown(merged[-1]["region_type"], merged[-1]["text"])
        else:
            merged.append(region)
    return merged


def post_process_cover_regions(regions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    regions = merge_disclaimer_regions(regions)
    regions = merge_contact_table_regions(regions)
    return sort_and_number_cover_regions(regions)


def merge_disclaimer_regions(regions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    disclaimer = next((region for region in regions if region["region_type"] == "disclaimer"), None)
    product_note = next((region for region in regions if region["region_type"] == "product_note"), None)
    if not disclaimer or not product_note:
        return regions

    disclaimer["text"] = normalize_sentence(f"{disclaimer['text']} {product_note['text']}")
    disclaimer["bbox"] = union_bbox([disclaimer["bbox"], product_note["bbox"]])
    disclaimer["markdown"] = disclaimer["text"]
    return [region for region in regions if region is not product_note]


def merge_contact_table_regions(regions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    table_regions = [
        region
        for region in regions
        if is_contact_table_region(region)
    ]
    if not table_regions:
        return regions

    rows = build_contact_table_rows(table_regions)
    if not rows:
        return regions

    table_region = {
        "region_order": 0,
        "region_type": "contact_table",
        "heading": "Contact table",
        "text": contact_rows_to_text(rows),
        "bbox": union_bbox([region["bbox"] for region in table_regions]),
        "source": table_regions[0]["source"],
        "style_summary": {},
        "table": {
            "table_type": "cover_contact_table",
            "columns": list(rows[0].keys()),
            "rows": rows,
        },
        "normalized_fields": normalize_contact_table_fields(rows),
        "markdown": build_contact_table_markdown(rows),
    }

    consumed = {id(region) for region in table_regions}
    kept = [region for region in regions if id(region) not in consumed]
    kept.append(table_region)
    return kept


def is_contact_table_region(region: dict[str, Any]) -> bool:
    if region["region_type"] in {"table_heading", "contact_value", "website"}:
        return True
    if region["region_type"] == "body":
        text = region["text"]
        return (
            "Samsung Electronics Canada Inc." in text
            or "Derry Road" in text
            or "Mississauga" in text
            or text == "Canada"
        )
    return False


def build_contact_table_rows(table_regions: list[dict[str, Any]]) -> list[dict[str, str]]:
    service_center = ""
    websites: list[str] = []
    address_parts: list[str] = []
    has_address_heading = False

    for region in table_regions:
        text = region["text"]
        if region["region_type"] == "contact_value":
            service_center = text
        elif region["region_type"] == "website":
            websites.extend(split_cover_values(text, prefix="www."))
        elif region["region_type"] == "table_heading" and text == "Address":
            has_address_heading = True
        elif region["region_type"] == "body" and (
            has_address_heading
            or "Samsung Electronics Canada Inc." in text
            or "Derry Road" in text
            or "Mississauga" in text
            or text == "Canada"
        ):
            address_parts.append(text)

    row = {
        "Samsung Service Center": service_center,
        "Website": "\n".join(dedupe_preserve_order(websites)),
    }
    if has_address_heading or address_parts:
        row["Address"] = "\n".join(address_parts)
    return [row] if any(row.values()) else []


def contact_rows_to_text(rows: list[dict[str, str]]) -> str:
    parts = []
    for row in rows:
        parts.extend(f"{key}: {value}" for key, value in row.items() if value)
    return normalize_sentence(" ".join(parts))


def build_contact_table_markdown(rows: list[dict[str, str]]) -> str:
    columns = list(rows[0].keys())
    header = "| " + " | ".join(columns) + " |"
    separator = "| " + " | ".join("---" for _ in columns) + " |"
    body_rows = []
    for row in rows:
        values = [row.get(column, "").replace("\n", "<br>") for column in columns]
        body_rows.append("| " + " | ".join(values) + " |")
    return "\n".join([header, separator, *body_rows])


def normalize_contact_table_fields(rows: list[dict[str, str]]) -> dict[str, Any]:
    service_center: list[str] = []
    phone_numbers: list[str] = []
    websites: list[dict[str, str]] = []
    address: list[str] = []

    for row in rows:
        service_value = normalize_sentence(row.get("Samsung Service Center", ""))
        if service_value:
            service_center.append(service_value)
            phone_numbers.extend(extract_service_phone_tokens(service_value))

        for website in split_multiline_values(row.get("Website", "")):
            websites.append(normalize_website_value(website))

        address.extend(split_multiline_values(row.get("Address", "")))

    return {
        "field_schema": "cover_contact_table.v1",
        "service_center": dedupe_preserve_order(service_center),
        "service_phone_numbers": dedupe_preserve_order(phone_numbers),
        "websites": dedupe_websites(websites),
        "address": dedupe_preserve_order(address),
    }


def extract_service_phone_tokens(text: str) -> list[str]:
    tokens = re.findall(r"1-\d{3}-[A-Z]+|\d{3}-\d{4}", text)
    return [token.upper() for token in tokens]


def split_multiline_values(text: str) -> list[str]:
    return [
        normalize_sentence(value)
        for value in text.splitlines()
        if normalize_sentence(value)
    ]


def normalize_website_value(text: str) -> dict[str, str]:
    match = re.match(r"^(www\.[^\s()]+)(?:\s*\(([^)]+)\))?$", normalize_sentence(text))
    if not match:
        return {"url": normalize_sentence(text), "label": ""}
    return {
        "url": match.group(1),
        "label": match.group(2) or "",
    }


def dedupe_websites(values: list[dict[str, str]]) -> list[dict[str, str]]:
    seen = set()
    result = []
    for value in values:
        key = (value["url"], value["label"])
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def dedupe_preserve_order(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def sort_and_number_cover_regions(regions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    footer_types = {"copyright", "document_code"}
    body_regions = [region for region in regions if region["region_type"] not in footer_types]
    footer_regions = [region for region in regions if region["region_type"] in footer_types]
    ordered = sorted(body_regions, key=lambda region: (region["bbox"][1], region["bbox"][0]))
    ordered.extend(sorted(footer_regions, key=lambda region: region["bbox"][0]))
    for index, region in enumerate(ordered, start=1):
        region["region_order"] = index
    return ordered


def cover_region_heading(region_type: str, text: str) -> str | None:
    if region_type in {"title", "contact_heading", "table_heading"}:
        return text
    if region_type == "language_label":
        return "Language"
    if region_type == "model_serial_fields":
        return "Model / Serial"
    if region_type == "support_note":
        return "Support Note"
    if region_type == "website":
        return "Website"
    if region_type == "contact_value":
        return "Samsung Service Center"
    if region_type == "contact_table":
        return "Contact table"
    return None


def cover_region_to_markdown(region_type: str, text: str) -> str:
    if region_type == "title":
        return f"# {text}"
    if region_type in {"contact_heading", "table_heading"}:
        return f"## {text}"
    if region_type == "language_label":
        return f"**Language:** {text}"
    if region_type == "model_serial_fields":
        return f"| Field | Value |\n|---|---|\n| Model |  |\n| Serial No. |  |"
    if region_type == "support_note":
        return text
    if region_type == "website":
        values = split_cover_values(text, prefix="www.")
        rows = "\n".join(f"| Website | {value} |" for value in values)
        return f"| Type | Value |\n|---|---|\n{rows}"
    if region_type == "contact_value":
        return f"| Service Center | {text} |"
    if region_type == "contact_table":
        return text
    if region_type == "document_code":
        return f"**Document code:** {text}"
    return text


def build_cover_markdown(regions: list[dict[str, Any]]) -> str:
    return "\n\n".join(region["markdown"] for region in regions if region["markdown"])


def split_cover_values(text: str, prefix: str) -> list[str]:
    parts = []
    for piece in text.split(prefix):
        piece = piece.strip()
        if not piece:
            continue
        parts.append(prefix + piece)
    return parts or [text]


def union_bbox(boxes: list[list[float] | tuple[float, float, float, float]]) -> list[float]:
    return [
        round(min(box[0] for box in boxes), 2),
        round(min(box[1] for box in boxes), 2),
        round(max(box[2] for box in boxes), 2),
        round(max(box[3] for box in boxes), 2),
    ]


def summarize_cover_spans(spans: list[dict[str, Any]]) -> dict[str, Any]:
    if not spans:
        return {}
    return {
        "span_count": len(spans),
        "max_font_size": max(span["size"] for span in spans),
        "bold_candidate": any(span["bold_candidate"] for span in spans),
        "italic_candidate": any(span["italic_candidate"] for span in spans),
        "underline_candidate": any(span["underline_candidate"] for span in spans),
    }


def should_recommend_ocr(total_chars: int, total_cells: int, empty_cells: int) -> bool:
    if total_chars < 200:
        return True
    if total_cells and empty_cells / total_cells > 0.8:
        return True
    return False


def build_sections(cells: list[dict[str, Any]], language: str) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    current_section: dict[str, Any] | None = None

    for cell in cells:
        for item in cell["review_items"]:
            if item["kind"] == "heading":
                current_section = make_section(item, cell, len(sections) + 1)
                sections.append(current_section)
                continue

            if current_section is None:
                current_section = make_unsectioned_section(cell, len(sections) + 1)
                sections.append(current_section)

            block = make_block(item, cell, len(current_section["blocks"]) + 1, language)
            current_section["blocks"].append(block)

    return sections


def make_section(item: dict[str, Any], cell: dict[str, Any], section_order: int) -> dict[str, Any]:
    return {
        "section_order": section_order,
        "heading": item["text"],
        "heading_kind": "heading",
        "source": make_source(cell),
        "style_summary": summarize_item_style(item["text"], cell["style_spans"]),
        "blocks": [],
    }


def make_unsectioned_section(cell: dict[str, Any], section_order: int) -> dict[str, Any]:
    return {
        "section_order": section_order,
        "heading": "UNSECTIONED",
        "heading_kind": "synthetic",
        "source": make_source(cell),
        "style_summary": {},
        "blocks": [],
    }


def make_block(
    item: dict[str, Any], cell: dict[str, Any], block_order: int, language: str
) -> dict[str, Any]:
    block_type = detect_block_type(item)
    block = {
        "block_order": block_order,
        "block_type": block_type,
        "text": item["text"],
        "sentences": [
            {"sentence_order": index, "text": sentence}
            for index, sentence in enumerate(item["sentences"], start=1)
        ],
        "source": make_source(cell),
        "style_summary": summarize_item_style(item["text"], cell["style_spans"]),
    }
    if block_type == "safety_symbol_table":
        rows = parse_safety_symbol_rows(item["text"])
        block["table_type"] = "safety_symbol_table"
        block["rows"] = rows
        block["manual_review_required"] = True
        block["image_crop_required"] = True
        block["ocr_recommended"] = True
        block["sentences"] = [
            {"sentence_order": index, "text": row["description"]}
            for index, row in enumerate(rows, start=1)
        ]
    return block


def detect_block_type(item: dict[str, Any]) -> str:
    text = item["text"]
    if is_safety_symbol_table_text(text):
        return "safety_symbol_table"
    if item["kind"] in {"navigation", "ui_label"}:
        return "navigation_ui"
    return item["kind"]


def make_source(cell: dict[str, Any]) -> dict[str, Any]:
    return {
        "page_number": cell["page_number"],
        "review_order": cell["review_order"],
        "page_role": cell["page_role"],
        "row": cell["row"],
        "column": cell["column"],
        "cell_role": cell["cell_role"],
        "cell_order": cell["cell_order"],
        "reading_direction": cell["reading_direction"],
    }


def summarize_item_style(text: str, spans: list[dict[str, Any]]) -> dict[str, Any]:
    item_spans = [span for span in spans if span["text"] and span["text"] in text]
    if not item_spans:
        item_spans = spans
    if not item_spans:
        return {
            "span_count": 0,
            "max_font_size": 0,
            "bold_candidate": False,
            "italic_candidate": False,
            "underline_candidate": False,
        }
    return {
        "span_count": len(item_spans),
        "max_font_size": max(span["size"] for span in item_spans),
        "bold_candidate": any(span["bold_candidate"] for span in item_spans),
        "italic_candidate": any(span["italic_candidate"] for span in item_spans),
        "underline_candidate": any(span["underline_candidate"] for span in item_spans),
    }


def is_safety_symbol_table_text(text: str) -> bool:
    markers = [
        "This symbol indicates",
        "Class II product",
        "AC voltage",
        "DC voltage",
        "Consult instructions for use",
    ]
    return sum(1 for marker in markers if marker in text) >= 3


def parse_safety_symbol_rows(text: str) -> list[dict[str, Any]]:
    patterns = [
        ("high_voltage", "This symbol indicates that high voltage", "This symbol indicates that this product"),
        ("important_literature", "This symbol indicates that this product", "Class II product:"),
        ("class_ii", "Class II product:", "AC voltage:"),
        ("ac_voltage", "AC voltage:", "DC voltage:"),
        ("dc_voltage", "DC voltage:", "Caution. Consult instructions for use:"),
        ("consult_instructions", "Caution. Consult instructions for use:", None),
    ]
    rows = []
    for order, (label, start, end) in enumerate(patterns, start=1):
        description = extract_between(text, start, end)
        if not description:
            continue
        rows.append(
            {
                "row_order": order,
                "symbol_key": label,
                "label": start.rstrip(":"),
                "description": description,
                "symbol_image_crop": None,
            }
        )
    return rows


def extract_between(text: str, start: str, end: str | None) -> str:
    start_index = text.find(start)
    if start_index < 0:
        return ""
    end_index = text.find(end, start_index + len(start)) if end else -1
    if end_index < 0:
        return normalize_sentence(text[start_index:])
    return normalize_sentence(text[start_index:end_index])


def build_review_items(text: str, language: str = "ENG") -> list[dict[str, Any]]:
    if not text.strip():
        return []
    if language != "ENG":
        return [make_item("body", normalize_sentence(text), language)]

    items: list[dict[str, Any]] = []
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    index = 0
    while index < len(lines):
        line = lines[index]

        if is_standalone_bullet(line):
            index += 1
            bullet_lines = []
            while index < len(lines) and should_continue_run(lines[index]):
                bullet_lines.append(lines[index])
                index += 1
            add_review_item(items, "bullet", " ".join(bullet_lines), language)
            continue

        if is_navigation_fragment(line):
            index = consume_run(lines, index, items, "navigation", language, is_navigation_fragment)
            continue

        if is_ui_label_line(line):
            index = consume_run(lines, index, items, "ui_label", language, is_ui_label_line)
            continue

        if is_warning_line(line):
            index = consume_run(lines, index, items, "warning", language, is_warning_line)
            continue

        if is_list_item_line(line):
            list_lines = [line]
            index += 1
            while index < len(lines) and is_list_item_continuation(list_lines[-1], lines[index]):
                list_lines.append(lines[index])
                index += 1
            add_review_item(items, "list_item", " ".join(list_lines), language)
            continue

        if starts_new_bullet(line):
            index = consume_bullet(lines, index, items, language)
            continue

        if is_heading_line(line):
            heading_lines = [line]
            index += 1
            while index < len(lines) and is_heading_continuation(heading_lines[-1], lines[index]):
                heading_lines.append(lines[index])
                index += 1
            add_review_item(items, "heading", " ".join(heading_lines), language)
            continue

        body_lines = [line]
        index += 1
        while index < len(lines) and should_continue_run(lines[index]):
            body_lines.append(lines[index])
            index += 1
        add_review_item(items, "body", " ".join(body_lines), language)

    return [{**item, "item_order": index} for index, item in enumerate(items, start=1)]


def build_normalized_text(items: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for item in items:
        text = item["text"]
        kind = item["kind"]
        if kind in {"navigation"}:
            continue
        if kind == "heading":
            parts.append(ensure_terminal_punctuation(text))
        elif kind == "ui_label":
            append_inline(parts, text)
        elif is_fragment_text(text):
            append_inline(parts, text)
        else:
            parts.append(text)
    return cleanup_joined_text(" ".join(parts))


def append_inline(parts: list[str], text: str) -> None:
    if parts:
        parts[-1] = f"{parts[-1]} {text}"
    else:
        parts.append(text)


def is_fragment_text(text: str) -> bool:
    normalized = normalize_sentence(text)
    if not normalized:
        return False
    if normalized in {"or", "/", "button /", ")", "("}:
        return True
    if normalized[0] in {".", ",", ":", ";", "/", ")"}:
        return True
    if normalized[-1] in {"(", "/", "\""}:
        return True
    return len(normalized.split()) <= 3 and not normalized.endswith((".", "!", "?"))


def cleanup_joined_text(text: str) -> str:
    replacements = {
        " .": ".",
        " ,": ",",
        " :": ":",
        " ;": ";",
        "( ": "(",
        " )": ")",
        " / ": " / ",
        "\" ": "\"",
        " \"": " \"",
    }
    cleaned = normalize_sentence(text)
    for old, new in replacements.items():
        cleaned = cleaned.replace(old, new)
    cleaned = cleaned.replace("\"in", "\" in")
    cleaned = cleaned.replace("\"and", "\" and")
    cleaned = cleaned.replace("www. samsung.com", "www.samsung.com")
    return normalize_sentence(cleaned)


def ensure_terminal_punctuation(text: str) -> str:
    normalized = normalize_sentence(text)
    if not normalized:
        return normalized
    if normalized.endswith((".", "!", "?")):
        return normalized
    return f"{normalized}."


def consume_run(
    lines: list[str],
    index: int,
    items: list[dict[str, Any]],
    kind: str,
    language: str,
    predicate,
) -> int:
    run = [lines[index]]
    index += 1
    while index < len(lines) and predicate(lines[index]):
        run.append(lines[index])
        index += 1
    add_review_item(items, kind, " ".join(run), language)
    return index


def consume_bullet(lines: list[str], index: int, items: list[dict[str, Any]], language: str) -> int:
    bullet_lines = [lines[index]]
    index += 1
    while index < len(lines) and should_continue_run(lines[index]):
        bullet_lines.append(lines[index])
        index += 1
    add_review_item(items, "bullet", " ".join(bullet_lines), language)
    return index


def should_continue_run(line: str) -> bool:
    return not (
        is_standalone_bullet(line)
        or starts_new_bullet(line)
        or is_navigation_fragment(line)
        or is_ui_label_line(line)
        or is_warning_line(line)
        or is_list_item_line(line)
        or is_heading_line(line)
    )


def add_review_item(items: list[dict[str, Any]], kind: str, text: str, language: str) -> None:
    normalized = normalize_sentence(text)
    if normalized:
        items.append(make_item(kind, normalized, language))


def make_item(kind: str, text: str, language: str) -> dict[str, Any]:
    return {
        "kind": kind,
        "text": text,
        "sentences": [] if kind == "heading" else split_sentences(text, language=language),
    }


def split_sentences(text: str, language: str = "ENG") -> list[str]:
    if not text.strip():
        return []
    if language != "ENG":
        return [normalize_sentence(text)]

    chunks: list[str] = []
    for paragraph in split_paragraphs(text):
        prepared = protect_abbreviations(paragraph)
        for sentence in SENTENCE_END_PATTERN.split(prepared):
            normalized = restore_abbreviations(normalize_sentence(sentence))
            if normalized:
                chunks.append(normalized)
    return chunks


def split_paragraphs(text: str) -> list[str]:
    paragraphs = []
    current: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            if current:
                paragraphs.append(" ".join(current))
                current = []
            continue
        if starts_new_bullet(line) and current:
            paragraphs.append(" ".join(current))
            current = [line]
        else:
            current.append(line)
    if current:
        paragraphs.append(" ".join(current))
    return paragraphs


def is_heading_continuation(previous_line: str, line: str) -> bool:
    if not is_heading_line(line):
        return False
    return len(previous_line) + len(line) <= 80


def is_heading_line(line: str) -> bool:
    normalized = normalize_sentence(line)
    if not normalized or is_standalone_bullet(normalized):
        return False
    if normalized in NON_HEADING_TEXTS:
        return False
    if normalized in {"ENG", "Website", "-00"}:
        return False
    if normalized == "Caution":
        return False
    if normalized[0] in {".", ",", ":", ";", "/"}:
        return False
    if (
        is_navigation_fragment(normalized)
        or is_ui_label_line(normalized)
        or is_list_item_line(normalized)
        or is_warning_line(normalized)
    ):
        return False
    if "www." in normalized or "@" in normalized:
        return False
    if len(normalized) > 55:
        return False
    if normalized.endswith("."):
        return False
    if re.match(r"^\d{2}\s+[A-Z]", normalized):
        return True
    if normalized.endswith(("!", "?")) and len(normalized.split()) <= 4:
        return True

    words = [word for word in re.split(r"\s+", normalized) if word]
    if not words or len(words) > 8:
        return False
    heading_stopwords = {"a", "an", "and", "for", "in", "of", "on", "or", "the", "to", "with"}
    title_like_words = 0
    for word in words:
        cleaned = word.strip("\"'()[]:;,-")
        if cleaned.lower() in heading_stopwords:
            title_like_words += 1
        elif cleaned and (cleaned[0].isupper() or cleaned.isupper()):
            title_like_words += 1
    return title_like_words >= max(1, len(words) - 1)


def is_standalone_bullet(line: str) -> bool:
    return normalize_sentence(line) == BULLET


def starts_new_bullet(line: str) -> bool:
    normalized = normalize_sentence(line)
    return normalized.startswith((BULLET, "-", EN_DASH)) or bool(re.match(r"^\d+[.)]\s+", normalized))


def is_navigation_fragment(line: str) -> bool:
    normalized = normalize_sentence(line)
    if normalized in {">", "(", ")"}:
        return True
    if normalized in {"Settings", "Support", "Tips", "and User Guides", "Open User Guide"}:
        return True
    if normalized.startswith(">") or normalized.endswith(">"):
        return True
    return normalized in {
        "left directional button",
        "> left directional button >",
    }


def is_ui_label_line(line: str) -> bool:
    normalized = normalize_sentence(line)
    if not normalized:
        return False
    ui_labels = {
        "TV Controller",
        "Control menu",
        "Control menu . The Control menu",
        "Remote control sensor",
        "Remote Control Sensor",
        "Microphone switch",
        "Motion Sensor",
        "Update Now",
        "Auto Update",
        "Auto",
        "Update",
        "Software Update",
        "Troubleshooting",
        "button / Remote control sensor /",
        "button / Remote Control Sensor /",
        "button / Remote control sensor",
        "button / Remote Control Sensor",
    }
    if normalized in ui_labels:
        return True
    if normalized.endswith("button") and len(normalized.split()) <= 5:
        return True
    if normalized.endswith("sensor") and len(normalized.split()) <= 5:
        return True
    return False


def is_list_item_line(line: str) -> bool:
    normalized = normalize_sentence(line)
    if normalized.startswith("*"):
        return True
    if re.match(r"^x\s*\d+$", normalized, flags=re.IGNORECASE):
        return True
    return normalized in {
        "Warranty Card / Regulatory Guide (Not available in some locations)",
        "User Manual",
        "Power Cord",
    }


def is_list_item_continuation(previous_line: str, line: str) -> bool:
    previous = normalize_sentence(previous_line)
    current = normalize_sentence(line)
    if previous.startswith("*:"):
        return should_continue_run(current)
    if previous.startswith("*Wireless One Connect Box") and current.startswith("*:"):
        return True
    return False


def is_warning_line(line: str) -> bool:
    normalized = normalize_sentence(line)
    if not normalized:
        return False
    warning_terms = {
        "CAUTION",
        "RISK OF ELECTRIC SHOCK",
        "DO NOT OPEN",
        "DO NOT REMOVE COVER",
        "NO USER SERVICEABLE PARTS",
        "SERVICING TO QUALIFIED PERSONNEL",
    }
    if any(term in normalized for term in warning_terms):
        return True
    letters = [char for char in normalized if char.isalpha()]
    if not letters:
        return False
    uppercase_ratio = sum(1 for char in letters if char.isupper()) / len(letters)
    return uppercase_ratio > 0.85 and len(normalized) > 20


def protect_abbreviations(text: str) -> str:
    for abbreviation, placeholder in ABBREVIATION_PLACEHOLDERS.items():
        text = text.replace(abbreviation, placeholder)
    return text


def restore_abbreviations(text: str) -> str:
    for abbreviation, placeholder in ABBREVIATION_PLACEHOLDERS.items():
        text = text.replace(placeholder, abbreviation)
    return text


def normalize_sentence(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()
