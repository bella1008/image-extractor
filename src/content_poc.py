from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import fitz
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

from src.cli import DEFAULT_MAPPING_PATH
from src.pdf_analyzer import analyze_pdf_structure
from src.profile_lookup import ProfileLookupService
from src.profile_repository import PdfProfileRepository
from src.text_extractor import (
    detect_block_type,
    extract_review_text,
    is_safety_symbol_table_text,
    parse_safety_symbol_rows,
    split_sentences,
)


EMBEDDED_HEADING_PATTERNS = [
    (
        "Providing proper ventilation for your TV",
        "Providing proper ventilation for your TV",
    ),
    ("Preventing the TV from falling", "Preventing the TV from falling"),
    (
        "Precautions when installing the TV with a",
        "Precautions when installing the TV with a stand",
    ),
    (
        "How to turn on and off the Microphone",
        "How to turn on and off the Microphone",
    ),
    ("The remote control does not work.", "The remote control does not work."),
]

SPEC_COMPOUND_HEADING_PREFIX = (
    "04 Specifications and Other Information Specifications Display Resolution"
)
MODEL_SPEC_FIELDS = {"Display Resolution", "Sound (Output)"}
COMMON_REQUIRED_SPEC_FIELDS = {
    "Operating Temperature",
    "Operating Humidity",
    "Storage Temperature",
    "Storage Humidity",
}


@dataclass(frozen=True)
class ContentPocPaths:
    root: Path
    json_path: Path
    markdown_path: Path
    xlsx_path: Path
    crop_dir: Path


def make_output_paths(
    output_dir: Path,
    manual_code: str,
    source_token: str,
    language: str,
    timestamp: str | None = None,
) -> ContentPocPaths:
    root = output_dir / manual_code / f"{source_token}_{language}"
    stamp = timestamp or datetime.now().strftime("%y%m%d_%H%M")
    return ContentPocPaths(
        root=root,
        json_path=root / "content_poc.json",
        markdown_path=root / "content_blocks.md",
        xlsx_path=root / f"{manual_code}_{source_token}_{language}_{stamp}_content_review.xlsx",
        crop_dir=root / "crops",
    )


def build_content_poc_payload(extracted: dict[str, Any]) -> dict[str, Any]:
    cells = collect_content_cells(extracted)
    blocks = build_content_blocks(cells)
    sections = build_content_sections(blocks)
    return {
        "file_name": extracted["file_name"],
        "source_token": extracted["source_token"],
        "region": extracted["region"],
        "buyer_codes": extracted["buyer_codes"],
        "language": extracted["language"],
        "doc_type": extracted["doc_type"],
        "detected_doc_type": extracted["detected_doc_type"],
        "summary": {
            "cell_count": len(cells),
            "block_count": len(blocks),
            "section_count": len(sections),
            "manual_review_block_count": sum(
                1 for block in blocks if block["manual_review_required"]
            ),
            "safety_table_count": sum(
                1 for block in blocks if block["block_type"] == "safety_symbol_table"
            ),
            "navigation_ui_count": sum(
                1 for block in blocks if block["block_type"] == "navigation_ui"
            ),
            "spec_table_count": sum(
                1 for block in blocks if block["block_type"] == "spec_table"
            ),
            "regulatory_note_count": sum(
                1 for block in blocks if block["block_type"] == "regulatory_note"
            ),
        },
        "sections": sections,
        "blocks": blocks,
    }


def collect_content_cells(extracted: dict[str, Any]) -> list[dict[str, Any]]:
    cells = []
    for page in extracted.get("pages", []):
        for cell in page.get("cells", []):
            if cell["role"] == "cover":
                continue
            cells.append(
                {
                    "page_number": page["page_number"],
                    "review_order": page["review_order"],
                    "page_role": page["page_role"],
                    "row": cell["row"],
                    "column": cell["column"],
                    "cell_role": cell["role"],
                    "cell_order": cell["reading_order"],
                    "reading_direction": cell["reading_direction"],
                    "review_items": cell.get("review_items", []),
                    "crop_path": None,
                }
            )
    return cells


def build_content_blocks(cells: list[dict[str, Any]]) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    current_section = "UNSECTIONED"
    section_order = 0
    for cell in cells:
        for item in expand_content_review_items(cell["review_items"]):
            for split_item in split_embedded_heading_items(item):
                for section_item in split_section_scoped_items(split_item, current_section):
                    if current_section == "Notes" and is_noise_note_fragment(section_item["text"]):
                        continue
                    block_type = detect_content_block_type(section_item, current_section)
                    if block_type == "heading":
                        section_order += 1
                        current_section = section_item["text"]
                    block = make_content_block(
                        section_item,
                        block_type,
                        cell,
                        block_order=len(blocks) + 1,
                        section_order=max(section_order, 1),
                        section_heading=current_section,
                    )
                    blocks.append(block)
    return blocks


def expand_content_review_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items = prepare_content_review_items(items)
    expanded: list[dict[str, Any]] = []
    index = 0
    while index < len(items):
        item = items[index]
        next_item = items[index + 1] if index + 1 < len(items) else None
        spec_items = split_specification_heading_item(item, next_item)
        if spec_items:
            expanded.extend(spec_items)
            index += 2 if next_item else 1
            continue
        if item["kind"] == "heading" and item["text"] == "Precautions when installing the TV with a":
            expanded.append(
                {
                    **item,
                    "text": "Precautions when installing the TV with a stand",
                }
            )
            index += 1
            continue
        if item["kind"] == "body" and normalize_joined_text(item["text"]) == "Notes":
            expanded.append({"kind": "heading", "text": "Notes", "sentences": []})
            index += 1
            continue
        regulatory_items, consumed = split_regulatory_note_items(items, index)
        if regulatory_items:
            expanded.extend(regulatory_items)
            index += consumed
            continue
        if item["kind"] == "heading" and item["text"] == "Display Resolution" and next_item:
            expanded.append(item)
            expanded.append(make_spec_table_item("Display Resolution", next_item["text"], "model_spec"))
            index += 2
            continue
        if item["kind"] == "heading" and item["text"] == "Sound (Output)":
            expanded.append(item)
            sound_values, index = collect_sound_output_values(items, index + 1)
            expanded.append(make_spec_table_item("Sound (Output)", " ".join(sound_values), "model_spec"))
            continue
        if item["kind"] == "heading" and item["text"].startswith("Sound (Output) "):
            expanded.append({**item, "text": "Sound (Output)"})
            initial_value = item["text"].removeprefix("Sound (Output)").strip()
            sound_values, index = collect_sound_output_values(items, index + 1)
            expanded.append(
                make_spec_table_item(
                    "Sound (Output)",
                    " ".join([initial_value, *sound_values]),
                    "model_spec",
                )
            )
            continue
        if item["kind"] == "heading" and item["text"] in COMMON_REQUIRED_SPEC_FIELDS and next_item:
            expanded.append(item)
            expanded.append(
                make_spec_table_item(item["text"], next_item["text"], "common_required_spec")
            )
            index += 2
            continue
        expanded.append(item)
        index += 1
    return expanded


def prepare_content_review_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    prepared = remove_stray_marker_items(items)
    prepared = merge_inline_caution_items(prepared)
    prepared = split_caution_warning_items(prepared)
    prepared = split_operation_body_list_items(prepared)
    prepared = split_safety_warning_precaution_items(prepared)
    prepared = merge_fragmented_falling_tv_procedure_items(prepared)
    prepared = split_condition_label_items(prepared)
    prepared = split_model_scoped_condition_label_items(prepared)
    prepared = merge_one_connect_action_label_items(prepared)
    prepared = merge_troubleshooting_reference_items(prepared)
    prepared = merge_fragmented_software_update_items(prepared)
    prepared = merge_software_update_sentence_items(prepared)
    prepared = merge_inline_ui_sentence_items(prepared)
    prepared = merge_remote_button_icon_items(prepared)
    prepared = merge_go_to_navigation_items(prepared)
    prepared = merge_model_specific_parenthetical_navigation_items(prepared)
    prepared = merge_parenthetical_navigation_items(prepared)
    prepared = merge_package_content_items(prepared)
    prepared = split_package_figure_notice_items(prepared)
    prepared = merge_tv_controller_figure_legend_items(prepared)
    prepared = merge_microphone_figure_items(prepared)
    return merge_model_condition_items(prepared)


def remove_stray_marker_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    marker_texts = {"– 2.", "– 3.", "–", "– stand properly."}
    cleaned: list[dict[str, Any]] = []
    for item in items:
        text = normalize_joined_text(item["text"])
        if text in marker_texts or text in {"( >", "1. 2. 3."}:
            continue
        if item["kind"] == "ui_label" and text == "Auto":
            continue
        if text.endswith(" 1."):
            text = text.removesuffix(" 1.").strip()
            if not text:
                continue
            item = {
                **item,
                "text": text,
                "sentences": split_sentences(text),
            }
        cleaned.append(item)
    return cleaned


def merge_inline_caution_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    index = 0
    while index < len(items):
        item = items[index]
        next_item = items[index + 1] if index + 1 < len(items) else None
        if (
            item["kind"] == "warning"
            and normalize_joined_text(item["text"]) == "CAUTION"
            and next_item
            and next_item["kind"] == "body"
            and normalize_joined_text(next_item["text"]).startswith(":")
        ):
            text = normalize_joined_text(f"CAUTION{normalize_joined_text(next_item['text'])}")
            merged.append(
                {
                    **item,
                    "text": text,
                    "sentences": split_sentences(text),
                }
            )
            index += 2
            continue
        merged.append(item)
        index += 1
    return merged


def split_caution_warning_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    split_items: list[dict[str, Any]] = []
    for item in items:
        text = normalize_joined_text(item["text"])
        warning_index = text.find("WARNING -")
        if item["kind"] != "warning" or not text.startswith("CAUTION:") or warning_index < 0:
            split_items.append(item)
            continue

        caution_text = normalize_joined_text(text[:warning_index])
        warning_text = normalize_joined_text(text[warning_index:])
        if caution_text:
            split_items.append(
                {
                    **item,
                    "kind": "bullet",
                    "text": caution_text,
                    "sentences": split_sentences(caution_text),
                }
            )
        if warning_text:
            split_items.append(
                {
                    **item,
                    "kind": "bullet",
                    "text": warning_text,
                    "sentences": split_sentences(warning_text),
                }
            )
    return split_items


def split_operation_body_list_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    split_items: list[dict[str, Any]] = []
    in_operation = False
    operation_starts = {
        "This apparatus uses batteries.",
        "In your community, there might be environmental regulations",
        "Please contact your local authorities",
        "Store the accessories",
        "Do not drop or strike the product.",
        "If the product is damaged,",
        "Do not dispose of remote control or batteries in a fire.",
        "Do not short-circuit, disassemble, or overheat the batteries.",
        "After removing the screen protective film,",
        "If the protective film removal label is not found,",
    }
    for item in items:
        if item["kind"] == "heading":
            in_operation = item["text"] == "Operation"
            split_items.append(item)
            continue
        text = normalize_joined_text(item["text"])
        if in_operation and item["kind"] == "body" and text.startswith("This apparatus uses batteries."):
            for line in split_sentences(text):
                kind = "bullet" if any(line.startswith(start) for start in operation_starts) else item["kind"]
                split_items.append({**item, "kind": kind, "text": line, "sentences": [line]})
            continue
        split_items.append(item)
    return split_items


def split_safety_warning_precaution_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    split_items: list[dict[str, Any]] = []
    for item in items:
        text = normalize_joined_text(item["text"])
        bullet_starts = [
            "Always use cabinets",
            "Always use furniture",
            "Always ensure",
            "Always educate",
            "Always route",
            "Never place",
            "If the existing",
            "When you have",
        ]
        has_marker = "Many injuries can be avoided by taking simple precautions such as:" in text
        starts_with_precaution = any(text.startswith(start) for start in bullet_starts)
        if item["kind"] != "body" or not (has_marker or starts_with_precaution):
            split_items.append(item)
            continue
        marker = "Many injuries can be avoided by taking simple precautions such as:"
        search_start = text.find(marker) + len(marker) if has_marker else 0
        list_text = text[search_start:]
        first_relative_start = min((list_text.find(start) for start in bullet_starts if list_text.find(start) >= 0), default=-1)
        if first_relative_start < 0:
            split_items.append(item)
            continue
        first_start = search_start + first_relative_start
        intro = normalize_joined_text(text[:first_start])
        if intro:
            split_items.append({**item, "text": intro, "sentences": split_sentences(intro)})
        for bullet_text in split_text_by_any_starts(text[first_start:], bullet_starts):
            split_items.append(
                {
                    **item,
                    "kind": "bullet",
                    "text": bullet_text,
                    "sentences": split_sentences(bullet_text),
                }
            )
    return split_items


def split_text_by_any_starts(text: str, starts: list[str]) -> list[str]:
    matches = sorted(
        (match.start(), match.group(0))
        for start in starts
        for match in re.finditer(re.escape(start), text)
    )
    if not matches:
        return [normalize_joined_text(text)]
    result = []
    for index, (position, _) in enumerate(matches):
        end = matches[index + 1][0] if index + 1 < len(matches) else len(text)
        result.append(normalize_joined_text(text[position:end]))
    return [item for item in result if item]


def merge_fragmented_falling_tv_procedure_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    index = 0
    while index < len(items):
        item = items[index]
        next_item = items[index + 1] if index + 1 < len(items) else None
        if (
            item["kind"] == "heading"
            and item["text"] == "Preventing the TV from falling"
            and next_item
            and next_item["kind"] == "body"
            and normalize_joined_text(next_item["text"]).startswith(": Wall-anchor (not supplied)")
        ):
            merged.append(item)
            source_item = next_item
            procedure_parts = []
            index += 1
            while index < len(items):
                current = items[index]
                current_text = normalize_joined_text(current["text"])
                if current["kind"] == "heading":
                    break
                if current["kind"] not in {"body", "bullet"}:
                    break
                if current_text in {"-", "–"}:
                    index += 1
                    continue
                if current["kind"] == "bullet" or current_text.startswith(": Wall-anchor"):
                    procedure_parts.append(strip_leading_list_marker(current_text))
                    index += 1
                    continue
                break
            text = normalize_joined_text(" ".join(procedure_parts))
            text = text.removesuffix(" stand properly.").strip()
            merged.append({**source_item, "text": text, "sentences": split_sentences(text)})
            continue
        merged.append(item)
        index += 1
    return merged


def strip_leading_list_marker(text: str) -> str:
    return normalize_joined_text(re.sub(r"^[\-–]\s*", "", text))


def split_condition_label_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    split_items: list[dict[str, Any]] = []
    for item in items:
        text = normalize_joined_text(item["text"])
        if item["kind"] == "body" and text.startswith("(The Frame only) "):
            body_text = text.removeprefix("(The Frame only) ").strip()
            split_items.append(
                {
                    **item,
                    "kind": "condition_label",
                    "text": "(The Frame only)",
                    "sentences": ["(The Frame only)"],
                }
            )
            if body_text:
                split_items.append({**item, "text": body_text, "sentences": split_sentences(body_text)})
            continue
        split_items.append(item)
    return split_items


def split_model_scoped_condition_label_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    split_items: list[dict[str, Any]] = []
    for item in items:
        if item["kind"] != "body":
            split_items.append(item)
            continue
        text = normalize_joined_text(item["text"])
        condition_split = split_model_scoped_condition_text(text)
        if not condition_split:
            split_items.append(item)
            continue
        for kind, part in condition_split:
            split_items.append(
                {
                    **item,
                    "kind": kind,
                    "text": part,
                    "sentences": split_sentences(part) if kind == "body" else [part],
                    "lines": [part],
                }
            )
    return split_items


def split_model_scoped_condition_text(text: str) -> list[tuple[str, str]] | None:
    if is_model_scoped_parenthetical(text):
        return [("condition_label", text)]

    parenthetical_prefix = extract_balanced_parenthetical_prefix(text)
    if parenthetical_prefix:
        condition, body = parenthetical_prefix
        return [
            ("condition_label", condition),
            ("body", body),
        ]

    laser_split = extract_laser_condition(text)
    if laser_split:
        before, condition, after = laser_split
        result: list[tuple[str, str]] = []
        if before:
            result.append(("body", before))
        result.append(("condition_label", condition))
        if after:
            result.append(("body", after))
        return result

    return None


def extract_balanced_parenthetical_prefix(text: str) -> tuple[str, str] | None:
    if not text.startswith("("):
        return None
    depth = 0
    for index, char in enumerate(text):
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                condition = text[: index + 1]
                body = text[index + 1 :].strip()
                if body and is_model_scoped_parenthetical(condition):
                    return condition, body
                return None
    return None


def extract_laser_condition(text: str) -> tuple[str, str, str] | None:
    laser_match = re.search(r"\bCLASS\s*1 LASER PRODUCT\s+\(", text)
    if not laser_match:
        return None
    open_index = text.find("(", laser_match.start())
    depth = 0
    for index in range(open_index, len(text)):
        char = text[index]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                before = text[: laser_match.start()].strip()
                condition = text[laser_match.start() : index + 1].strip()
                after = text[index + 1 :].strip()
                if contains_model_condition_token(condition):
                    return before, condition, after
                return None
    return None


def is_model_scoped_parenthetical(text: str) -> bool:
    return (
        text.startswith("(")
        and text.endswith(")")
        and contains_model_condition_token(text)
        and bool(re.search(r"\b(?:only|ONLY|except for|EXCEPT FOR)\b", text))
    )


def contains_model_condition_token(text: str) -> bool:
    return bool(
        re.search(r"\b[A-Z]{1,4}\d[\w*.-]*\b", text)
        or "The Frame" in text
        or "THE FRAME" in text
        or "Supported Model" in text
    )


def merge_one_connect_action_label_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    index = 0
    action_labels = {"Bending", "Twisting", "Pulling", "Pressing on", "Electric shock"}
    while index < len(items):
        item = items[index]
        text = normalize_joined_text(item["text"])
        if text.startswith("Take care not to subject the cable to any of the actions below"):
            merged.append(item)
            index += 1
            labels = []
            source_item = item
            while index < len(items):
                current = items[index]
                current_text = normalize_joined_text(current["text"])
                if current["kind"] != "body" or current_text not in action_labels:
                    break
                labels.append(current_text)
                source_item = current
                index += 1
            if labels:
                merged.append(
                    {
                        **source_item,
                        "kind": "figure_action_labels",
                        "text": "\n".join(labels),
                        "sentences": labels,
                        "lines": labels,
                        "labels": labels,
                    }
                )
            continue
        merged.append(item)
        index += 1
    return merged


def merge_troubleshooting_reference_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    index = 0
    while index < len(items):
        item = items[index]
        if (
            index + 2 < len(items)
            and item["kind"] == "body"
            and normalize_joined_text(item["text"]).endswith('refer to "')
            and items[index + 1]["kind"] == "ui_label"
            and items[index + 2]["kind"] == "body"
            and normalize_joined_text(items[index + 2]["text"]).lower().startswith('" in the user guide')
        ):
            text = normalize_joined_text(
                f'{item["text"]}{items[index + 1]["text"]}{items[index + 2]["text"]}'
            )
            merged.append({**item, "text": text, "sentences": split_sentences(text)})
            index += 3
            nav_parts = []
            while index < len(items):
                current = items[index]
                current_text = normalize_joined_text(current["text"])
                if current["kind"] == "body" and current_text == "Troubleshooting" and nav_parts:
                    nav_parts.append(current_text)
                    index += 1
                    continue
                if current["kind"] not in {"navigation", "ui_label"}:
                    break
                part = current_text
                if part != ")":
                    nav_parts.append(part)
                index += 1
                if part == ")":
                    break
            if nav_parts:
                nav_text = normalize_navigation_path(nav_parts)
                merged.append({"kind": "navigation", "text": nav_text, "sentences": [nav_text]})
            continue
        merged.append(item)
        index += 1
    return merged


def merge_fragmented_software_update_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    index = 0
    while index < len(items):
        item = items[index]
        if (
            index + 1 < len(items)
            and item["kind"] in {"bullet", "body"}
            and normalize_joined_text(item["text"]).endswith("upgrade to the latest")
            and items[index + 1]["kind"] == "body"
            and normalize_joined_text(items[index + 1]["text"]).startswith("software. Use the")
        ):
            merged_text = normalize_joined_text(f"{item['text']} {items[index + 1]['text']}")
            merged.append(
                {
                    **item,
                    "kind": "body",
                    "text": merged_text,
                    "sentences": split_sentences(merged_text),
                }
            )
            index += 2
            continue
        merged.append(item)
        index += 1
    return merged


def merge_inline_ui_sentence_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    index = 0
    inline_starts = ("You can turn on the TV with the", "Try pressing the")
    while index < len(items):
        item = items[index]
        text = normalize_joined_text(item["text"])
        if item["kind"] == "body" and text.startswith(inline_starts):
            parts = [text]
            index += 1
            while index < len(items):
                current = items[index]
                current_text = normalize_joined_text(current["text"])
                parts.append(current_text)
                index += 1
                if current_text.endswith("."):
                    break
            merged_text = cleanup_inline_sentence_text(" ".join(parts))
            merged.append({**item, "text": merged_text, "sentences": split_sentences(merged_text)})
            continue
        merged.append(item)
        index += 1
    return merged


def merge_remote_button_icon_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    index = 0
    while index < len(items):
        item = items[index]
        text = normalize_joined_text(item["text"])
        if (
            item["kind"] in {"body", "bullet"}
            and "press the button on the remote control" in text
            and "remote control sensor" in text
        ):
            tagged_text = text.replace(
                "press the button on the remote control",
                "press the {btn_power} button on the remote control",
            )
            merged.append({**item, "text": tagged_text, "sentences": split_sentences(tagged_text)})
            index += 1
            continue
        if (
            index + 2 < len(items)
            and item["kind"] in {"body", "bullet"}
            and text.endswith(". To pair")
            and items[index + 1]["kind"] == "body"
            and normalize_joined_text(items[index + 1]["text"]) == "a Samsung Smart Remote, press the"
            and items[index + 2]["kind"] == "body"
            and normalize_joined_text(items[index + 2]["text"])
            == "and buttons together for 3 seconds."
        ):
            tagged_text = normalize_joined_text(
                f"{text} a Samsung Smart Remote, press the "
                "{btn_return} and {btn_play_pause} buttons together for 3 seconds."
            )
            merged.append({**item, "text": tagged_text, "sentences": split_sentences(tagged_text)})
            index += 3
            continue
        merged.append(item)
        index += 1
    return merged


def merge_software_update_sentence_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    index = 0
    while index < len(items):
        item = items[index]
        if (
            index + 4 < len(items)
            and item["kind"] in {"body", "bullet"}
            and normalize_joined_text(item["text"]).endswith("Use the")
            and items[index + 1]["kind"] == "ui_label"
            and normalize_joined_text(items[index + 2]["text"]) == "or"
            and items[index + 3]["kind"] == "ui_label"
            and normalize_joined_text(items[index + 4]["text"]).endswith("menu (")
        ):
            menu_text = normalize_joined_text(items[index + 4]["text"]).removesuffix("(").strip()
            body_text = normalize_joined_text(
                f"{item['text']} {items[index + 1]['text']} or {items[index + 3]['text']} {menu_text}"
            )
            merged.append({**item, "text": body_text, "sentences": split_sentences(body_text)})
            index += 5
            nav_parts: list[str] = []
            while index < len(items):
                current = items[index]
                current_text = normalize_joined_text(current["text"])
                if current["kind"] == "body" and current_text.startswith(")"):
                    break
                nav_parts.append(current_text)
                index += 1
            if nav_parts:
                nav_text = normalize_navigation_path(nav_parts)
                merged.append({"kind": "navigation", "text": nav_text, "sentences": [nav_text]})
            if index < len(items):
                trailing = strip_closing_parenthetical_text(items[index]["text"])
                if trailing:
                    merged.append({**items[index], "text": trailing, "sentences": split_sentences(trailing)})
                index += 1
            continue
        merged.append(item)
        index += 1
    return merged


def cleanup_inline_sentence_text(text: str) -> str:
    cleaned = normalize_joined_text(text)
    cleaned = cleaned.replace(" . ", ". ")
    cleaned = cleaned.replace(" / ", " / ")
    return normalize_joined_text(cleaned)


def merge_go_to_navigation_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    index = 0
    while index < len(items):
        item = items[index]
        text = normalize_joined_text(item["text"])
        if item["kind"] == "body" and text.endswith("go to"):
            merged.append(item)
            index += 1
            nav_parts = []
            while index < len(items):
                current = items[index]
                current_text = normalize_joined_text(current["text"])
                if current_text == ".":
                    index += 1
                    break
                if current["kind"] not in {"navigation", "ui_label", "body"}:
                    break
                if current["kind"] == "body" and current_text not in {"General &", "Privacy"}:
                    break
                if current_text == "Privacy" and nav_parts and nav_parts[-1] == "General &":
                    nav_parts[-1] = "General & Privacy"
                else:
                    nav_parts.append(current_text)
                index += 1
            if nav_parts:
                nav_text = normalize_navigation_path(nav_parts)
                merged.append({"kind": "navigation", "text": nav_text, "sentences": [nav_text]})
            continue
        merged.append(item)
        index += 1
    return merged


def merge_model_specific_parenthetical_navigation_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    index = 0
    while index < len(items):
        item = items[index]
        text = normalize_joined_text(item["text"])
        if item["kind"] == "body" and text.startswith("(") and text.endswith(":"):
            parts = [text.removeprefix("(")]
            index += 1
            while index < len(items):
                current_text = normalize_joined_text(items[index]["text"])
                if current_text == ")":
                    index += 1
                    break
                parts.append(current_text)
                index += 1
            navigation_text = normalize_navigation_path(parts)
            merged.append(
                {
                    "kind": "navigation",
                    "text": navigation_text,
                    "sentences": [navigation_text],
                }
            )
            continue
        merged.append(item)
        index += 1
    return merged


def merge_parenthetical_navigation_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    index = 0
    while index < len(items):
        item = items[index]
        next_item = items[index + 1] if index + 1 < len(items) else None
        if (
            item["kind"] == "ui_label"
            and next_item
            and next_item["kind"] == "body"
            and normalize_joined_text(next_item["text"]).endswith("(")
            and merged
            and merged[-1]["kind"] in {"body", "bullet"}
        ):
            prefix = normalize_joined_text(next_item["text"]).removesuffix("(").strip()
            merged[-1] = append_text_to_item(merged[-1], f"{item['text']} {prefix}")
            nav_parts: list[str] = []
            index += 2
            while index < len(items):
                current = items[index]
                current_text = normalize_joined_text(current["text"])
                if current["kind"] == "body" and current_text.startswith(")"):
                    break
                nav_parts.append(current_text)
                index += 1
            if nav_parts:
                navigation_text = normalize_navigation_path(nav_parts)
                merged.append(
                    {
                        "kind": "navigation",
                        "text": navigation_text,
                        "sentences": [navigation_text],
                    }
                )
            if index < len(items):
                trailing = strip_closing_parenthetical_text(items[index]["text"])
                if trailing:
                    merged.append(
                        {
                            **items[index],
                            "text": trailing,
                            "sentences": split_sentences(trailing),
                        }
                    )
                index += 1
            continue
        merged.append(item)
        index += 1
    return merged


def append_text_to_item(item: dict[str, Any], text: str) -> dict[str, Any]:
    merged_text = normalize_joined_text(f"{item['text']} {text}")
    return {
        **item,
        "text": merged_text,
        "sentences": split_sentences(merged_text),
    }


def normalize_navigation_path(parts: list[str]) -> str:
    text = normalize_joined_text(" ".join(parts))
    text = re.sub(r"\s*>\s*", " > ", text)
    text = normalize_joined_text(text)
    text = re.sub(r"Software Update > Update$", "Software Update > Auto Update", text)
    return f"({text})"


def strip_closing_parenthetical_text(text: str) -> str:
    normalized = normalize_joined_text(text)
    return normalize_joined_text(re.sub(r"^\)\.?\s*", "", normalized))


def merge_package_content_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    in_package_content = False
    index = 0
    while index < len(items):
        item = items[index]
        if item["kind"] == "heading" and item["text"] == "01 Package Content":
            in_package_content = True
            merged.append(item)
            index += 1
            continue
        if in_package_content and is_package_item_candidate(item):
            package_items: list[str] = []
            note_text = ""
            while index < len(items) and is_package_item_candidate(items[index]):
                item_text, item_note = split_package_item_text(items[index]["text"])
                package_items.append(item_text)
                if item_note:
                    note_text = item_note
                index += 1
            item_list_text = "\n".join(package_items)
            merged.append(
                {
                    "kind": "item_list",
                    "text": item_list_text,
                    "sentences": package_items,
                    "lines": package_items,
                    "list_type": "package_contents",
                    "items": [
                        {"item_order": order, "text": text}
                        for order, text in enumerate(package_items, start=1)
                    ],
                }
            )
            if note_text:
                merged.append(
                    {
                        "kind": "item_list_note",
                        "text": note_text,
                        "sentences": split_sentences(note_text),
                    }
                )
            continue
        if in_package_content and is_package_note_item(item):
            note_text = normalize_joined_text(item["text"])
            index += 1
            while index < len(items) and is_package_note_continuation(items[index]):
                note_text = normalize_joined_text(f"{note_text} {items[index]['text']}")
                index += 1
            merged.append(
                {
                    "kind": "item_list_note",
                    "text": note_text,
                    "sentences": split_sentences(note_text),
                }
            )
            continue
        merged.append(item)
        index += 1
    return merged


def is_package_item_candidate(item: dict[str, Any]) -> bool:
    text = normalize_joined_text(item["text"])
    if is_package_note_item(item):
        return False
    if item["kind"] == "list_item" and text.startswith("*"):
        return True
    return item["kind"] == "bullet" and (
        text == "Simple User Guide"
        or text.startswith("Warranty Card / Regulatory Guide")
    )


def is_package_note_item(item: dict[str, Any]) -> bool:
    text = normalize_joined_text(item["text"])
    return item["kind"] == "list_item" and bool(re.match(r"^\*{1,2}:", text))


def is_package_note_continuation(item: dict[str, Any]) -> bool:
    text = normalize_joined_text(item["text"])
    return item["kind"] == "body" and bool(re.match(r"^(on|depending)\b", text))


def split_package_item_text(text: str) -> tuple[str, str]:
    normalized = normalize_joined_text(text)
    note = ""
    if " *:" in normalized:
        normalized, note_tail = normalized.split(" *:", 1)
        note = f"*: {note_tail.strip()}"
    return normalized.lstrip("*").strip(), note


def split_package_figure_notice_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    split_items: list[dict[str, Any]] = []
    for item in items:
        text = normalize_joined_text(item["text"])
        start = text.find("The screen can be damaged from direct pressure")
        if item["kind"] == "bullet" and start > 0:
            before = normalize_joined_text(text[:start])
            notice = normalize_joined_text(text[start:])
            split_items.append({**item, "text": before, "sentences": split_sentences(before)})
            split_items.append(
                {
                    **item,
                    "kind": "figure_notice",
                    "text": notice,
                    "sentences": split_sentences(notice),
                    "lines": split_sentences(notice),
                }
            )
            continue
        split_items.append(item)
    return split_items


def merge_tv_controller_figure_legend_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    index = 0
    while index < len(items):
        text = normalize_joined_text(items[index]["text"])
        if text == "Control menu TV Controller":
            consumed = collect_figure_legend_text(items, index)
            legend = make_tv_controller_figure_legend(consumed)
            merged.append(legend)
            index += len(consumed)
            continue
        merged.append(items[index])
        index += 1
    return merged


def collect_figure_legend_text(items: list[dict[str, Any]], index: int) -> list[str]:
    texts = []
    while index < len(items):
        item = items[index]
        text = normalize_joined_text(item["text"])
        if item["kind"] == "list_item" and text.startswith("*:"):
            break
        texts.append(text)
        index += 1
    return texts


def make_tv_controller_figure_legend(texts: list[str]) -> dict[str, Any]:
    combined = cleanup_figure_legend_text(" ".join(texts))
    items = [
        {"key": "A", "text": "Control menu"},
        {"key": "B", "text": "TV Controller button / Remote control sensor / Microphone switch"},
        {"key": "C", "text": "TV Controller button / Remote control sensor"},
        {"key": "D", "text": "Microphone switch"},
    ]
    return {
        "kind": "figure_legend",
        "text": combined,
        "sentences": [combined],
        "lines": [f"{item['key']}: {item['text']}" for item in items],
        "items": items,
    }


def cleanup_figure_legend_text(text: str) -> str:
    cleaned = normalize_joined_text(text)
    cleaned = cleaned.replace("/ * Motion Sensor", "/ Microphone switch Motion Sensor")
    return cleaned


def merge_microphone_figure_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    index = 0
    while index < len(items):
        if index + 3 < len(items):
            candidate_labels = [normalize_joined_text(items[index + offset]["text"]) for offset in range(4)]
        else:
            candidate_labels = []
        if candidate_labels[:3] == ["Type A", "Type B", "Type C"] and candidate_labels[3].startswith("Type D"):
            labels = ["Type A", "Type B", "Type C", "Type D"]
            text = "\n".join(labels)
            merged.append(
                {
                    "kind": "figure_variant_labels",
                    "text": text,
                    "sentences": labels,
                    "lines": labels,
                    "labels": labels,
                }
            )
            type_d_remainder = candidate_labels[3].removeprefix("Type D").strip()
            if type_d_remainder:
                type_d_remainder = type_d_remainder.lstrip(":").strip()
                if type_d_remainder.startswith("On/Off Switch "):
                    label = "On/Off Switch"
                    body_text = type_d_remainder.removeprefix(label).strip()
                    merged.append(
                        {
                            **items[index + 3],
                            "kind": "figure_callout_label",
                            "text": label,
                            "sentences": [label],
                            "lines": [label],
                        }
                    )
                    if body_text:
                        merged.append(
                            {
                                **items[index + 3],
                                "text": body_text,
                                "sentences": split_sentences(body_text),
                            }
                        )
                else:
                    merged.append(
                        {
                            **items[index + 3],
                            "text": type_d_remainder,
                            "sentences": split_sentences(type_d_remainder),
                        }
                    )
            index += 4
            continue
        merged.append(items[index])
        index += 1
    return merged


def merge_model_condition_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    index = 0
    while index < len(items):
        text = normalize_joined_text(items[index]["text"])
        if text.startswith("This function is supported only in "):
            model_parts = [text.removeprefix("This function is supported only in ")]
            start_item = items[index]
            index += 1
            while index < len(items):
                current_text = normalize_joined_text(items[index]["text"])
                if not looks_like_model_condition_continuation(current_text):
                    break
                model_parts.append(current_text)
                index += 1
                if current_text.endswith("."):
                    break
            model_text = normalize_model_condition_text("/".join(part.strip("/") for part in model_parts))
            text = f"This function is supported only in {model_text}."
            merged.append(
                {
                    **start_item,
                    "kind": "model_condition",
                    "text": text,
                    "sentences": [text],
                    "lines": [text],
                    "models": split_model_conditions(model_text),
                }
            )
            continue
        merged.append(items[index])
        index += 1
    return merged


def looks_like_model_condition_continuation(text: str) -> bool:
    return bool(
        re.fullmatch(r"[A-Za-z0-9*/._ -]+(?:/[A-Za-z0-9*/._ -]+)*\.?", text)
        or text in {"The", "Frame."}
    )


def normalize_model_condition_text(text: str) -> str:
    normalized = normalize_joined_text(text).rstrip(".")
    normalized = normalized.replace("/The/Frame", "/The Frame")
    return normalized


def split_model_conditions(text: str) -> list[str]:
    return [part for part in text.split("/") if part]


def split_regulatory_note_items(
    items: list[dict[str, Any]],
    index: int,
) -> tuple[list[dict[str, Any]], int]:
    item = items[index]
    text = normalize_joined_text(item["text"])
    next_item = items[index + 1] if index + 1 < len(items) else None

    if "This device is a Class B digital apparatus" in text:
        lan_extra = ""
        consumed = 1
        if next_item and normalize_joined_text(next_item["text"]) == "* Shielded Twisted Pair":
            lan_extra = " * Shielded Twisted Pair"
            consumed = 2
        return split_class_power_lan_notes(text, lan_extra), consumed

    if "Unpacking and Installation Guide may differ" in text:
        return split_wireless_notes(text), 1

    if text == "* Shielded Twisted Pair":
        return [], 1

    return [], 0


def split_class_power_lan_notes(text: str, lan_extra: str) -> list[dict[str, Any]]:
    return [
        make_regulatory_note_item(
            "REG_CLASS_B_DIGITAL",
            extract_note_segment(
                text,
                "This device is a Class B digital apparatus.",
                "For information about the power supply",
            ),
        ),
        make_regulatory_note_item(
            "REG_POWER_LABEL",
            extract_note_segment(
                text,
                "For information about the power supply",
                "To connect a LAN cable",
                include_start=True,
            ),
        ),
        make_regulatory_note_item(
            "REG_LAN_CABLE_STP",
            normalize_joined_text(
                extract_note_segment(
                    text,
                    "To connect a LAN cable",
                    None,
                    include_start=True,
                )
                + lan_extra
            ),
        ),
    ]


def split_wireless_notes(text: str) -> list[dict[str, Any]]:
    return [
        make_regulatory_note_item(
            "REG_UNPACKING_GUIDE_VARIANCE",
            extract_note_segment(
                text,
                "The images and specifications of the Unpacking and Installation Guide may differ from the actual product.",
                "Operation in the band 5150 - 5250 MHz",
            ),
        ),
        make_regulatory_note_item(
            "REG_5GHZ_INDOOR_USE",
            extract_note_segment(
                text,
                "Operation in the band 5150 - 5250 MHz",
                "[Operation in the band 5925 - 7125 MHz",
                include_start=True,
            ),
        ),
        make_regulatory_note_item(
            "REG_6GHZ_BAND_OPERATION",
            normalize_6ghz_note_text(
                extract_note_segment(
                    text,
                    "[Operation in the band 5925 - 7125 MHz",
                    None,
                    include_start=True,
                )
            ),
        ),
    ]


def make_regulatory_note_item(topic_id: str, text: str) -> dict[str, Any]:
    normalized = normalize_joined_text(text)
    return {
        "kind": "regulatory_note",
        "text": normalized,
        "sentences": [normalized],
        "lines": split_regulatory_note_lines(topic_id, normalized),
        "topic_id": topic_id,
    }


def split_regulatory_note_lines(topic_id: str, text: str) -> list[str]:
    if topic_id == "REG_POWER_LABEL":
        return split_power_label_note_lines(text)
    if topic_id == "REG_LAN_CABLE_STP":
        return split_lan_cable_note_lines(text)
    if topic_id == "REG_6GHZ_BAND_OPERATION":
        return split_6ghz_note_lines(text)
    return split_sentences(text)


def split_power_label_note_lines(text: str) -> list[str]:
    normalized = re.sub(
        r"\.\)\s+(On (?:Wireless )?One Connect Box models,)",
        r".)\n\1",
        text,
    )
    lines = []
    for part in normalized.splitlines():
        lines.extend(split_sentences(part))
    return lines


def split_lan_cable_note_lines(text: str) -> list[str]:
    lines = []
    main = text
    abbreviation = ""
    if " * Shielded Twisted Pair" in main:
        main, abbreviation = main.split(" * Shielded Twisted Pair", 1)
    speed = ""
    if " (100/10 Mbps)" in main:
        main = main.replace(" (100/10 Mbps)", "")
        speed = "(100/10 Mbps)"
    lines.extend(split_sentences(main))
    if speed:
        lines.append(speed)
    if abbreviation or "* Shielded Twisted Pair" in text:
        lines.append("* Shielded Twisted Pair")
    return lines


def split_6ghz_note_lines(text: str) -> list[str]:
    normalized = normalize_joined_text(text)
    lines = []
    heading_match = re.match(r"^(\[[^\]]+\])\s*(.*)$", normalized)
    if heading_match:
        lines.append(heading_match.group(1))
        normalized = heading_match.group(2)
    normalized = normalized.replace(
        "Operation of this product shall be limited to indoor use Operation of this product",
        "Operation of this product shall be limited to indoor use. Operation of this product",
    )
    lines.extend(split_sentences(normalized))
    return [line for line in lines if line]


def normalize_6ghz_note_text(text: str) -> str:
    normalized = normalize_joined_text(text)
    if normalized.endswith("(10,000"):
        return f"{normalized} ft)."
    return normalized


def extract_note_segment(
    text: str,
    start: str,
    end: str | None,
    include_start: bool = True,
) -> str:
    start_index = text.find(start)
    if start_index < 0:
        return ""
    end_index = text.find(end, start_index + len(start)) if end else -1
    segment_start = start_index if include_start else start_index + len(start)
    if end_index < 0:
        return text[segment_start:]
    return text[segment_start:end_index]


def collect_sound_output_values(items: list[dict[str, Any]], index: int) -> tuple[list[str], int]:
    values: list[str] = []
    while index < len(items):
        item = items[index]
        text = item["text"]
        if item["kind"] == "heading" and text in COMMON_REQUIRED_SPEC_FIELDS | {"Notes"}:
            break
        trailing = split_trailing_common_spec_heading(text)
        if trailing:
            model_value, common_heading = trailing
            if model_value:
                values.append(model_value)
            items[index] = {**item, "text": common_heading}
            break
        values.append(text)
        index += 1
    return values, index


def split_trailing_common_spec_heading(text: str) -> tuple[str, str] | None:
    for heading in COMMON_REQUIRED_SPEC_FIELDS:
        suffix = f" {heading}"
        if text.endswith(suffix):
            return text[: -len(suffix)].strip(), heading
    return None


def make_spec_table_item(field: str, value: str, category: str) -> dict[str, Any]:
    text = normalize_joined_text(f"{field} {value}")
    return {
        "kind": "spec_table",
        "text": text,
        "sentences": [text],
        "spec_field": field,
        "spec_category": category,
    }


def split_specification_heading_item(
    item: dict[str, Any], next_item: dict[str, Any] | None
) -> list[dict[str, Any]]:
    if item["kind"] != "heading" or item["text"] != SPEC_COMPOUND_HEADING_PREFIX:
        return []
    value = next_item["text"] if next_item and next_item["kind"] != "heading" else ""
    table_text = normalize_joined_text(f"Display Resolution {value}")
    return [
        {
            "kind": "heading",
            "text": "04 Specifications and Other Information",
            "sentences": [],
        },
        {"kind": "heading", "text": "Specifications", "sentences": []},
        {
            "kind": "spec_table",
            "text": table_text,
            "sentences": [table_text],
            "spec_field": "Display Resolution",
            "spec_category": "model_spec",
        },
    ]


def split_embedded_heading_items(item: dict[str, Any]) -> list[dict[str, Any]]:
    if item["kind"] in {"heading", "spec_table"}:
        return [item]
    remaining = [item]
    result: list[dict[str, Any]] = []
    while remaining:
        current = remaining.pop(0)
        if current["kind"] in {"heading", "spec_table"}:
            result.append(current)
            continue
        split_items = split_first_embedded_heading_item(current)
        if len(split_items) == 1 and split_items[0] is current:
            result.append(current)
        else:
            remaining = split_items + remaining
    return result


def split_first_embedded_heading_item(item: dict[str, Any]) -> list[dict[str, Any]]:
    text = item["text"]
    earliest: tuple[int, str, str] | None = None
    for trigger, heading in EMBEDDED_HEADING_PATTERNS:
        start = 0
        while True:
            index = text.find(trigger, start)
            if index < 0:
                break
            start = index + len(trigger)
            if is_inside_quote(text, index):
                continue
            if earliest is None or index < earliest[0]:
                earliest = (index, trigger, heading)
            break
    if earliest is None:
        return [item]

    index, trigger, heading = earliest
    before = text[:index].strip()
    after = text[index + len(trigger):].strip()
    split_items = []
    if before:
        split_items.append({**item, "text": before, "sentences": split_sentences(before)})
    split_items.append({"kind": "heading", "text": heading, "sentences": []})
    if after:
        split_items.append({**item, "text": after, "sentences": split_sentences(after)})
    return split_items


def split_section_scoped_items(item: dict[str, Any], section_heading: str) -> list[dict[str, Any]]:
    if section_heading != "Preventing the TV from falling":
        return [item]
    if item["kind"] != "body":
        return [item]
    text = normalize_joined_text(item["text"])
    if not text.startswith(": Wall-anchor (not supplied) "):
        return [item]
    return split_falling_tv_procedure_item(item)


def split_falling_tv_procedure_item(item: dict[str, Any]) -> list[dict[str, Any]]:
    text = normalize_joined_text(item["text"])
    note_text = "Wall-anchor (not supplied)"
    procedure_text = text.removeprefix(": Wall-anchor (not supplied)").strip()
    step_starts = [
        "Using the appropriate screws, firmly fasten a set of brackets to the wall.",
        "Using the appropriately sized screws, firmly fasten a set of brackets to the TV.",
        "Connect the brackets fixed to the TV and the brackets fixed to the wall",
    ]
    step_texts = split_text_by_step_starts(procedure_text, step_starts)
    if len(step_texts) != 3:
        return [item]
    result = [
        {
            **item,
            "kind": "procedure_note",
            "text": note_text,
            "sentences": [note_text],
        },
    ]
    for index, step_text in enumerate(step_texts, start=1):
        step_sentences = split_sentences(step_text)
        lines = (
            [f"{index}. {step_sentences[0]}", *step_sentences[1:]]
            if step_sentences
            else [f"{index}. {step_text}"]
        )
        result.append(
            {
                **item,
                "kind": "numbered_step",
                "text": f"{index}. {step_text}",
                "sentences": step_sentences,
                "lines": lines,
            }
        )
    return result


def split_text_by_step_starts(text: str, step_starts: list[str]) -> list[str]:
    positions = [text.find(step_start) for step_start in step_starts]
    if any(position < 0 for position in positions) or positions != sorted(positions):
        return []
    step_texts = []
    for index, position in enumerate(positions):
        end = positions[index + 1] if index + 1 < len(positions) else len(text)
        step_texts.append(normalize_joined_text(text[position:end]))
    return step_texts


def normalize_joined_text(text: str) -> str:
    return " ".join(text.split())


def is_noise_note_fragment(text: str) -> bool:
    return normalize_joined_text(text) in {"–", "-", "use.", "only.", "ft)."}


def is_inside_quote(text: str, index: int) -> bool:
    quote_count = text[:index].count('"')
    curly_open = text[:index].count("“")
    curly_close = text[:index].count("”")
    return quote_count % 2 == 1 or curly_open > curly_close


def detect_content_block_type(item: dict[str, Any], section_heading: str) -> str:
    if item["kind"] in {
        "procedure_note",
        "numbered_step",
        "item_list",
        "item_list_note",
        "condition_label",
        "figure_notice",
        "figure_legend",
        "figure_variant_labels",
        "figure_action_labels",
        "figure_callout_label",
        "model_condition",
    }:
        return item["kind"]
    if item["kind"] == "regulatory_note":
        return "regulatory_note"
    if item["kind"] == "spec_table":
        return "spec_table"
    if (
        item["kind"] == "warning"
        and section_heading == "Warning! Important Safety Instructions"
        and "CAUTION" in item["text"]
        and "RISK OF ELECTRIC SHOCK" in item["text"]
    ):
        return "safety_symbol_table"
    if (
        item["kind"] == "body"
        and section_heading == "Warning! Important Safety Instructions"
        and item["text"].startswith("Caution. Consult instructions for use:")
    ):
        return "safety_symbol_table"
    block_type = detect_block_type(item)
    if block_type == "body" and is_safety_symbol_table_text(item["text"]):
        return "safety_symbol_table"
    return block_type


def make_content_block(
    item: dict[str, Any],
    block_type: str,
    cell: dict[str, Any],
    block_order: int,
    section_order: int,
    section_heading: str,
) -> dict[str, Any]:
    risky = block_type in {
        "safety_symbol_table",
        "navigation_ui",
        "spec_table",
        "regulatory_note",
        "procedure_note",
        "numbered_step",
        "figure_notice",
        "figure_legend",
        "figure_variant_labels",
        "figure_action_labels",
        "figure_callout_label",
        "model_condition",
    }
    if item["text"].startswith(("CAUTION:", "WARNING -")):
        risky = True
    inline_tokens = extract_inline_tokens(item["text"])
    block = {
        "block_order": block_order,
        "section_order": section_order,
        "section_heading": section_heading,
        "block_type": block_type,
        "text": item["text"],
        "inline_tokens": inline_tokens,
        "lines": make_block_lines(item),
        "sentences": [
            {"sentence_order": index, "text": sentence}
            for index, sentence in enumerate(item.get("sentences", []), start=1)
        ],
        "manual_review_required": risky,
        "image_crop_required": risky,
        "ocr_recommended": risky,
        "crop_path": None,
        "source": {
            "page_number": cell["page_number"],
            "review_order": cell["review_order"],
            "page_role": cell["page_role"],
            "row": cell["row"],
            "column": cell["column"],
            "cell_role": cell["cell_role"],
            "cell_order": cell["cell_order"],
            "reading_direction": cell["reading_direction"],
        },
    }
    if block_type == "safety_symbol_table":
        block["table_type"] = "safety_symbol_table"
        rows = parse_safety_symbol_rows(item["text"])
        if not rows and "CAUTION" in item["text"]:
            rows = [
                {
                    "row_order": 0,
                    "symbol_key": "caution_warning",
                    "label": "CAUTION",
                    "lines": split_safety_warning_lines(item["text"]),
                    "symbol_image_crop": None,
                }
            ]
        block["rows"] = rows
    if block_type == "spec_table":
        block["table_type"] = "spec_table"
        block["spec_field"] = item.get("spec_field", "")
        block["spec_category"] = item.get("spec_category", "")
        block["rows"] = parse_spec_table_rows(
            block["spec_field"],
            item["text"],
            block["spec_category"],
        )
    if block_type == "regulatory_note":
        block["topic_id"] = item["topic_id"]
    if block_type == "item_list":
        block["list_type"] = item["list_type"]
        block["items"] = item["items"]
    if block_type in {"figure_legend"}:
        block["items"] = item["items"]
    if block_type in {"figure_variant_labels"}:
        block["labels"] = item["labels"]
    if block_type in {"figure_action_labels"}:
        block["labels"] = item["labels"]
    if block_type == "model_condition":
        block["models"] = item["models"]
    return block


def extract_inline_tokens(text: str) -> list[str]:
    tokens: list[str] = []
    for match in re.finditer(r"\{((?:btn|icn)_[a-z0-9_]+)\}", text):
        token = match.group(1)
        if token not in tokens:
            tokens.append(token)
    return tokens


def make_block_lines(item: dict[str, Any]) -> list[str]:
    if item.get("lines"):
        return list(item["lines"])
    text = normalize_joined_text(item["text"])
    if text.startswith("Caution. Consult instructions for use:"):
        return [
            "Caution.",
            text.removeprefix("Caution.").strip(),
        ]
    sentences = item.get("sentences", [])
    if sentences:
        return [normalize_joined_text(sentence) for sentence in sentences]
    return [normalize_joined_text(item["text"])]


def parse_spec_table_rows(
    field: str,
    text: str,
    category: str,
) -> list[dict[str, str | int]]:
    normalized = normalize_joined_text(text)
    value_text = normalized.removeprefix(field).strip() if field else normalized
    if category == "model_spec":
        rows = parse_model_spec_rows(field, value_text)
        if rows:
            return rows
    return [
        {
            "row_order": 1,
            "field": field,
            "model_pattern": "",
            "value": value_text,
            "unit": extract_spec_unit(value_text),
        }
    ]


def parse_model_spec_rows(field: str, text: str) -> list[dict[str, str | int]]:
    if field == "Display Resolution":
        display_matches = list(
            re.finditer(r"([^:]+):\s*(\d+\s*x\s*\d+)(?=\s+[^:]+:\s*|$)", text)
        )
        if display_matches:
            return [
                make_spec_row(
                    index,
                    field,
                    normalize_joined_text(match.group(1)),
                    match.group(2),
                )
                for index, match in enumerate(display_matches, start=1)
            ]
    value_pattern = r"(.+?\bW)" if field == "Sound (Output)" else r"([^:]+?)"
    matches = list(re.finditer(rf"([^:]+):\s*{value_pattern}(?=[,\s]+[^:]+:\s*|$)", text))
    rows: list[dict[str, str | int]] = []
    for match in matches:
        model_pattern = normalize_joined_text(match.group(1)).lstrip(", ")
        value = normalize_joined_text(match.group(2))
        if field == "Display Resolution" and "Other models" in value:
            first_value, other_value = value.split("Other models", 1)
            rows.append(make_spec_row(len(rows) + 1, field, model_pattern, first_value.strip()))
            rows.append(make_spec_row(len(rows) + 1, field, "Other models", other_value.strip()))
            continue
        rows.append(make_spec_row(len(rows) + 1, field, model_pattern, value))
    return rows


def make_spec_row(order: int, field: str, model_pattern: str, value: str) -> dict[str, str | int]:
    return {
        "row_order": order,
        "field": field,
        "model_pattern": model_pattern,
        "value": normalize_joined_text(value),
        "unit": extract_spec_unit(value),
    }


def extract_spec_unit(value: str) -> str:
    normalized = normalize_joined_text(value)
    if normalized.endswith("W"):
        return "W"
    if "°F" in normalized or "°C" in normalized:
        return "temperature_range"
    if "%" in normalized:
        return "%"
    return ""


def build_content_sections(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sections: dict[tuple[int, str], list[dict[str, Any]]] = {}
    for block in blocks:
        key = (block["section_order"], block["section_heading"])
        sections.setdefault(key, []).append(block)
    return [
        {
            "section_order": section_order,
            "heading": heading,
            "block_count": len(section_blocks),
            "manual_review_block_count": sum(
                1 for block in section_blocks if block["manual_review_required"]
            ),
        }
        for (section_order, heading), section_blocks in sections.items()
    ]


def build_content_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Content POC",
        "",
        f"- file_name: `{payload['file_name']}`",
        f"- source_token: `{payload['source_token']}`",
        f"- language: `{payload['language']}`",
        f"- doc_type: `{payload['doc_type']}`",
        f"- block_count: `{payload['summary']['block_count']}`",
        f"- manual_review_block_count: `{payload['summary']['manual_review_block_count']}`",
    ]
    current_section = None
    for block in payload["blocks"]:
        if current_section != block["section_heading"]:
            current_section = block["section_heading"]
            lines.extend(["", f"## {block['section_order']:02d}. {current_section}"])
        lines.extend(
            [
                "",
                f"### Block {block['block_order']:03d} - {block['block_type']}",
                "",
                f"- page: `{block['source']['page_number']}`",
                f"- cell_order: `{block['source']['cell_order']}`",
                f"- crop_path: `{block.get('crop_path') or ''}`",
                f"- manual_review_required: `{str(block['manual_review_required']).lower()}`",
                "",
                block["text"],
            ]
        )
    return "\n".join(lines) + "\n"


def write_content_poc_outputs(
    payload: dict[str, Any], paths: ContentPocPaths
) -> dict[str, Path]:
    paths.root.mkdir(parents=True, exist_ok=True)
    paths.crop_dir.mkdir(parents=True, exist_ok=True)
    paths.json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    paths.markdown_path.write_text(build_content_markdown(payload), encoding="utf-8")
    write_content_review_xlsx(payload, paths.xlsx_path)
    return {
        "json_path": paths.json_path,
        "markdown_path": paths.markdown_path,
        "xlsx_path": paths.xlsx_path,
    }


def write_content_review_xlsx(payload: dict[str, Any], output_path: Path) -> None:
    workbook = Workbook()
    summary = workbook.active
    summary.title = "Content Summary"
    write_summary_sheet(summary, payload)
    write_content_review_sheet(workbook.create_sheet("Content Review"), payload)
    write_safety_tables_sheet(workbook.create_sheet("Safety Tables"), payload)
    write_navigation_ui_sheet(workbook.create_sheet("Navigation UI"), payload)
    write_spec_tables_sheet(workbook.create_sheet("Spec Tables"), payload)
    write_regulatory_notes_sheet(workbook.create_sheet("Regulatory Notes"), payload)
    workbook.save(output_path)


def write_summary_sheet(sheet, payload: dict[str, Any]) -> None:
    sheet.append(["field", "value"])
    rows = [
        ("file_name", payload["file_name"]),
        ("language", payload["language"]),
        ("source_token", payload["source_token"]),
        ("doc_type", payload["doc_type"]),
        ("cell_count", payload["summary"]["cell_count"]),
        ("section_count", payload["summary"]["section_count"]),
        ("block_count", payload["summary"]["block_count"]),
        ("manual_review_block_count", payload["summary"]["manual_review_block_count"]),
        ("safety_table_count", payload["summary"]["safety_table_count"]),
        ("navigation_ui_count", payload["summary"]["navigation_ui_count"]),
        ("spec_table_count", payload["summary"]["spec_table_count"]),
        ("regulatory_note_count", payload["summary"]["regulatory_note_count"]),
    ]
    for row in rows:
        sheet.append(list(row))
    style_sheet(sheet, [28, 90])


def write_content_review_sheet(sheet, payload: dict[str, Any]) -> None:
    headers = [
        "block_order",
        "section_heading",
        "block_type",
        "manual_review_required",
        "lines_text",
        "sentence_count",
        "crop_path",
        "page",
        "cell_order",
    ]
    sheet.append(headers)
    for block in payload["blocks"]:
        sheet.append(
            [
                block["block_order"],
                block["section_heading"],
                block["block_type"],
                block["manual_review_required"],
                "\n".join(block.get("lines", [])),
                len(block["sentences"]),
                block.get("crop_path") or "",
                block["source"]["page_number"],
                block["source"]["cell_order"],
            ]
        )
    style_sheet(sheet, [12, 42, 22, 22, 120, 15, 80, 8, 12])


def split_safety_warning_lines(text: str) -> list[str]:
    normalized_text = normalize_joined_text(text)
    lines = []
    if normalized_text.startswith("CAUTION "):
        lines.append("CAUTION")
        normalized_text = normalized_text.removeprefix("CAUTION ").strip()
    for line in normalized_text.split("."):
        normalized = normalize_joined_text(line)
        if normalized:
            lines.append(f"{normalized}.")
    return lines


def write_safety_tables_sheet(sheet, payload: dict[str, Any]) -> None:
    headers = ["block_order", "section_heading", "row_order", "symbol_key", "label", "lines_text"]
    sheet.append(headers)
    for block in payload["blocks"]:
        if block["block_type"] != "safety_symbol_table":
            continue
        for row in block.get("rows", []):
            sheet.append(
                [
                    block["block_order"],
                    block["section_heading"],
                    row["row_order"],
                    row["symbol_key"],
                    row["label"],
                    "\n".join(row.get("lines", [])),
                ]
            )
    style_sheet(sheet, [12, 42, 10, 24, 42, 120])


def write_navigation_ui_sheet(sheet, payload: dict[str, Any]) -> None:
    headers = ["block_order", "section_heading", "text", "crop_path", "page", "cell_order"]
    sheet.append(headers)
    for block in payload["blocks"]:
        if block["block_type"] != "navigation_ui":
            continue
        sheet.append(
            [
                block["block_order"],
                block["section_heading"],
                block["text"],
                block.get("crop_path") or "",
                block["source"]["page_number"],
                block["source"]["cell_order"],
            ]
        )
    style_sheet(sheet, [12, 42, 120, 80, 8, 12])


def write_spec_tables_sheet(sheet, payload: dict[str, Any]) -> None:
    headers = [
        "block_order",
        "section_heading",
        "spec_category",
        "row_order",
        "field",
        "model_pattern",
        "value",
        "unit",
        "crop_path",
    ]
    sheet.append(headers)
    for block in payload["blocks"]:
        if block["block_type"] != "spec_table":
            continue
        for row in block.get("rows", []):
            sheet.append(
                [
                    block["block_order"],
                    block["section_heading"],
                    block.get("spec_category", ""),
                    row["row_order"],
                    row["field"],
                    row.get("model_pattern", ""),
                    row["value"],
                    row.get("unit", ""),
                    block.get("crop_path") or "",
                ]
            )
    style_sheet(sheet, [12, 42, 24, 10, 30, 42, 120, 16, 80])


def write_regulatory_notes_sheet(sheet, payload: dict[str, Any]) -> None:
    headers = ["block_order", "section_heading", "topic_id", "text", "crop_path"]
    sheet.append(headers)
    for block in payload["blocks"]:
        if block["block_type"] != "regulatory_note":
            continue
        sheet.append(
            [
                block["block_order"],
                block["section_heading"],
                block["topic_id"],
                block["text"],
                block.get("crop_path") or "",
            ]
        )
    style_sheet(sheet, [12, 42, 36, 140, 80])


def style_sheet(sheet, widths: list[int]) -> None:
    header_fill = PatternFill("solid", fgColor="1F4E78")
    header_font = Font(color="FFFFFF", bold=True)
    for cell in sheet[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")
    for row in sheet.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)
    for index, width in enumerate(widths, start=1):
        sheet.column_dimensions[chr(64 + index)].width = width
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions


def render_content_cell_crops(pdf_path: Path, payload: dict[str, Any], paths: ContentPocPaths) -> None:
    paths.crop_dir.mkdir(parents=True, exist_ok=True)
    zoom = 2
    matrix = fitz.Matrix(zoom, zoom)
    crop_cache: dict[tuple[int, int], str] = {}
    with fitz.open(pdf_path) as document:
        for block in payload["blocks"]:
            source = block["source"]
            key = (source["page_number"], source["cell_order"])
            if key not in crop_cache:
                page = document[source["page_number"] - 1]
                rect = cell_rect(page.rect, source["row"], source["column"], rows=2, columns=8)
                crop_path = paths.crop_dir / (
                    f"page_{source['page_number']:03d}_cell_{source['cell_order']:02d}.png"
                )
                page.get_pixmap(matrix=matrix, clip=rect, alpha=False).save(crop_path)
                crop_cache[key] = str(crop_path)
            if block["image_crop_required"]:
                block["crop_path"] = crop_cache[key]


def cell_rect(page_rect: fitz.Rect, row: int, column: int, rows: int, columns: int) -> fitz.Rect:
    cell_width = page_rect.width / columns
    cell_height = page_rect.height / rows
    return fitz.Rect(
        page_rect.x0 + (column - 1) * cell_width,
        page_rect.y0 + (row - 1) * cell_height,
        page_rect.x0 + column * cell_width,
        page_rect.y0 + row * cell_height,
    )


def run_content_poc(
    pdf_path: str | Path,
    output_dir: str | Path,
    language: str = "ENG",
    mapping_path: str | Path = DEFAULT_MAPPING_PATH,
) -> dict[str, Path]:
    pdf_path = Path(pdf_path)
    repository = PdfProfileRepository(mapping_path)
    lookup = ProfileLookupService(repository).lookup_for_file(str(pdf_path))
    structure = analyze_pdf_structure(str(pdf_path))
    extracted = extract_review_text(
        lookup.parsed_filename,
        lookup.profile,
        structure,
        language=language,
    )
    payload = build_content_poc_payload(extracted)
    paths = make_output_paths(
        Path(output_dir),
        lookup.parsed_filename.manual_code,
        extracted["source_token"],
        language,
    )
    render_content_cell_crops(pdf_path, payload, paths)
    return write_content_poc_outputs(payload, paths)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate a content-only POC review package.")
    parser.add_argument("pdf_path", help="Path to the source PDF.")
    parser.add_argument("--language", default="ENG", help="Language code to extract.")
    parser.add_argument(
        "--output-dir",
        default="outputs/content_poc",
        help="Root output directory. A source/language subfolder is created inside it.",
    )
    parser.add_argument(
        "--mapping",
        default=str(DEFAULT_MAPPING_PATH),
        help=f"Path to profile mapping JSON. Default: {DEFAULT_MAPPING_PATH}",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    written = run_content_poc(
        args.pdf_path,
        args.output_dir,
        language=args.language,
        mapping_path=args.mapping,
    )
    for label, path in written.items():
        print(f"{label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
