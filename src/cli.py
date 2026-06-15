from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from src.filename_parser import FilenameParseError
from src.pdf_analyzer import analyze_pdf_structure
from src.profile_lookup import ProfileLookupService
from src.profile_repository import PdfProfileNotFoundError, PdfProfileRepository
from src.structure_validator import validate_structure
from src.text_extractor import extract_review_text


DEFAULT_MAPPING_PATH = Path("metadata/pdf_profile_mapping/pdf_profile_mapping.json")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Look up a PDF profile from a manual filename.")
    parser.add_argument("pdf_path", help="Path to a manual PDF file")
    parser.add_argument(
        "--mapping",
        default=str(DEFAULT_MAPPING_PATH),
        help=f"Path to pdf_profile_mapping.json. Default: {DEFAULT_MAPPING_PATH}",
    )
    parser.add_argument(
        "--analyze-structure",
        action="store_true",
        help="Also analyze PDF page size, orientation, language pages, and grid cells.",
    )
    parser.add_argument(
        "--validate-structure",
        action="store_true",
        help="Compare pdf_profile_mapping values with the actual PDF structure.",
    )
    parser.add_argument(
        "--extract-text",
        action="store_true",
        help="Extract review text grouped by language, page, grid cell, and sentence.",
    )
    parser.add_argument(
        "--language",
        default="ENG",
        help="Language code to extract when --extract-text is used. Default: ENG",
    )
    parser.add_argument(
        "--output",
        help="Write --extract-text JSON to this path instead of stdout.",
    )
    return parser


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = build_parser()
    args = parser.parse_args()

    try:
        repository = PdfProfileRepository(args.mapping)
        result = ProfileLookupService(repository).lookup_for_file(args.pdf_path)
    except FilenameParseError as exc:
        print(f"Filename parse error: {exc}")
        return 2
    except PdfProfileNotFoundError as exc:
        print(f"No PDF profile found for source_token: {exc.args[0]}")
        return 3
    except FileNotFoundError as exc:
        print(f"File not found: {exc.filename}")
        return 4

    parsed = result.parsed_filename
    profile = result.profile
    print(f"file_name: {parsed.file_name}")
    print(f"manual_code: {parsed.manual_code}")
    print(f"manual_type: {parsed.manual_type}")
    print(f"product_info: {parsed.product_info}")
    print(f"buyer_region_token: {parsed.buyer_region_token}")
    print(f"language_token: {parsed.language_token}")
    print(f"source_token: {parsed.source_token}")
    print(f"date_code: {parsed.date_code}")
    print(f"region: {profile.region}")
    print(f"buyer_codes: {';'.join(profile.buyer_codes)}")
    print(f"languages: {';'.join(profile.languages)}")
    print(f"doc_type: {profile.doc_type}")
    print(f"language_count: {profile.language_count}")

    if args.analyze_structure or args.validate_structure or args.extract_text:
        structure = analyze_pdf_structure(args.pdf_path)
    else:
        structure = None

    if structure and args.analyze_structure:
        print("")
        print("PDF structure")
        print(f"page_count: {structure.page_count}")
        print(f"detected_doc_type: {structure.detected_doc_type}")
        if structure.language_sections:
            print("")
            print("Language sections")
            for section in structure.language_sections:
                print(
                    f"{section.reading_order}. language={section.language} "
                    f"title={section.title} "
                    f"pages={section.start_page}-{section.end_page} "
                    f"bookmark_page={section.bookmark_page} "
                    f"bookmark_level={section.bookmark_level} "
                    f"direction={section.reading_direction} "
                    f"page_numbers={','.join(str(page) for page in section.page_numbers)}"
                )
        for language_page in structure.language_pages:
            layout = language_page.layout
            print("")
            print(
                f"page {language_page.page_number}: "
                f"language={language_page.language} "
                f"direction={language_page.reading_direction} "
                f"role={language_page.page_role} "
                f"review_order={language_page.review_order}"
            )
            print(
                "layout: "
                f"{layout.page_size} {layout.orientation}, "
                f"{layout.rows}x{layout.columns}, "
                f"rule={layout.layout_rule}, "
                f"cover={layout.has_cover_area}"
            )
            for cell in language_page.grid_cells:
                text_preview = " ".join(cell.text.split())
                if len(text_preview) > 80:
                    text_preview = text_preview[:77] + "..."
                print(
                    f"  cell r{cell.row}c{cell.column} "
                    f"role={cell.role} "
                    f"order={cell.reading_order} "
                    f"direction={cell.reading_direction} "
                    f"chars={len(cell.text)} "
                    f"text={text_preview}"
                )

    if structure and args.validate_structure:
        validation = validate_structure(profile, structure)
        print("")
        print("Structure validation")
        print(f"status: {validation.status}")
        if validation.issues:
            for issue in validation.issues:
                print(
                    f"- {issue.field}: expected={issue.expected} "
                    f"actual={issue.actual} severity={issue.severity} "
                    f"message={issue.message}"
                )
        else:
            print("issues: none")

    if structure and args.extract_text:
        extracted = extract_review_text(parsed, profile, structure, language=args.language)
        payload = json.dumps(extracted, ensure_ascii=False, indent=2)
        if args.output:
            output_path = Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(payload + "\n", encoding="utf-8")
            print("")
            print(f"Extracted text written to: {output_path}")
        else:
            print("")
            print("Extracted text")
            print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
