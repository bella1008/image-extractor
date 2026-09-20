"""Seal the MENA readability rerun against the accepted source-reviewed bundle."""

import argparse
from collections import Counter
from hashlib import sha256
from html import escape
import json
from pathlib import Path
from xml.etree import ElementTree as E


CONTACT_TABLES = {"1056 0 R": "ENG", "647 0 R": "ARA"}
CONTACT_TITLES = {"1053 0 R": "ENG", "595 0 R": "ARA"}
MODEL_ROWS = {
    "1336 0 R": ("ENG", "1,2"),
    "1343 0 R": ("ENG", "1,2"),
    "331 0 R": ("ARA", "2,4"),
    "338 0 R": ("ARA", "2,4"),
}


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def dump(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def source_attributes(node: E.Element) -> dict[str, str]:
    return {
        attribute.get("name", ""): attribute.get("value", "")
        for attribute in node.findall("attributes/attribute")
    }


def source_structure_signature(root: E.Element) -> tuple:
    return tuple(
        (
            node.tag,
            node.get("object-ref"),
            node.get("page-index"),
            node.get("language"),
            node.get("mcid"),
        )
        for node in root.iter()
        if node.tag not in {"attributes", "attribute"}
    )


def source_text_inventory(root: E.Element) -> tuple:
    return tuple(
        (
            node.get("page-index"),
            node.get("mcid"),
            tuple(sorted(Counter(node.text or "").items())),
        )
        for node in root.iter("text")
    )


def table_signature(root: E.Element) -> tuple:
    return tuple(
        (
            table.get("object-ref"),
            tuple(
                tuple(
                    (
                        cell.tag,
                        source_attributes(cell).get("/RowSpan"),
                        source_attributes(cell).get("/ColSpan"),
                    )
                    for cell in row
                    if cell.tag in {"table_cell", "table_header"}
                )
                for row in table.findall("table_row")
            ),
        )
        for table in root.iter("table")
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("baseline", type=Path)
    args = parser.parse_args()
    folder = args.output.resolve() / "MENA_L02"
    baseline = args.baseline.resolve() / "MENA_L02"
    review = load(folder / "review_document.json")
    run = load(folder / "review_run.json")
    html_validation = load(folder / "html_validation.json")
    old_audit = load(baseline / "source_audit.json")
    if old_audit.get("final_source_review_complete") is not True:
        raise ValueError("baseline source review is not complete")
    if review["source"]["sha256"] != old_audit.get("source_sha256"):
        raise ValueError("baseline and rerun source revisions differ")
    if digest(Path(review["source"]["pdf"])) != review["source"]["sha256"]:
        raise ValueError("MENA PDF source changed")

    before = E.parse(baseline / "semantic_document.xml").getroot()
    after = E.parse(folder / "semantic_document.xml").getroot()
    if source_structure_signature(before) != source_structure_signature(after):
        raise ValueError("semantic source structure changed")
    if source_text_inventory(before) != source_text_inventory(after):
        raise ValueError("semantic source character inventory changed")
    if table_signature(before) != table_signature(after):
        raise ValueError("semantic table relationships changed")

    for reference, language in CONTACT_TABLES.items():
        table = next(node for node in after.iter("table") if node.get("object-ref") == reference)
        attributes = source_attributes(table)
        if (
            table.get("language") != language
            or attributes.get("review-table") != "source-spans"
            or attributes.get("review-table-kind") != "cover-contact"
        ):
            raise ValueError(f"contact table evidence missing: {reference}")
    for reference, language in CONTACT_TITLES.items():
        title = next(node for node in after.iter("paragraph") if node.get("object-ref") == reference)
        if (
            title.get("language") != language
            or title.get("display-role") != "strong-label"
            or title.get("font-weight") != "600"
            or title.get("comparison-body-font-weight") != "400"
        ):
            raise ValueError(f"contact title typography evidence missing: {reference}")
    for reference, expected in MODEL_ROWS.items():
        paragraph = next(
            node for node in after.iter("paragraph") if node.get("object-ref") == reference
        )
        attributes = source_attributes(paragraph)
        if (
            paragraph.get("language") != expected[0]
            or attributes.get("review-line-layout") != "model-code-rows"
            or attributes.get("review-line-break-before-child-indexes") != expected[1]
        ):
            raise ValueError(f"model row evidence missing: {reference}")
    dims = next(
        paragraph
        for paragraph in after.iter("paragraph")
        if "The Eco Sensor automatically adjusts" in "".join(paragraph.itertext())
    )
    if not any(text.get("sentence-break-offsets") for text in dims.iter("text")):
        raise ValueError("The screen dims paragraph sentence boundary is missing")
    spec_labels = [
        paragraph
        for paragraph in after.iter("paragraph")
        if paragraph.get("display-reason") == "repeated_table_label_value_typography"
    ]
    if Counter(paragraph.get("language") for paragraph in spec_labels) != Counter(
        {"ENG": 7, "ARA": 7}
    ):
        raise ValueError("MENA specification label coverage changed")

    markdown = (folder / "semantic_document.md").read_text(encoding="utf-8")
    required_markdown = (
        "**Contact Samsung world wide**",
        "Phone: 4873<br>WhatsApp +962-79-777-7421",
        "The Eco Sensor automatically adjusts the screen brightness based on the ambient light intensity.<br>",
        "QA100QN80HU QA85QN990HU QA55QN1EHAU<br>",
        "وجِّه دائمًا الأسلاك والكابلات المتصلة بالتلفزيون",
        "*: The Frame فقط",
        "**Display Resolution**",
        "**Model Name**",
        "**دقة العرض**",
        "**اسم الطراز**",
    )
    if any(value not in markdown for value in required_markdown):
        raise ValueError("required MENA Markdown readability output is missing")
    if (
        html_validation.get("xml_markdown_full_character_sequence") is not True
        or html_validation.get("unit_failures") != []
        or html_validation.get("md_preview_text_and_structure_equal") is not True
    ):
        raise ValueError("MENA Markdown/HTML validation failed")

    proof = {
        "source_sha256": review["source"]["sha256"],
        "baseline_source_audit": str((baseline / "source_audit.json").resolve()),
        "baseline_source_review_complete": True,
        "semantic_source_structure_equal": True,
        "semantic_source_character_inventory_equal": True,
        "table_relationships_equal": True,
        "contact_tables": CONTACT_TABLES,
        "contact_titles": CONTACT_TITLES,
        "model_rows": {key: {"language": value[0], "line_starts": value[1]} for key, value in MODEL_ROWS.items()},
        "screen_dims_sentence_break": True,
        "arabic_safety_sentence_order": True,
        "arabic_the_frame_marker_order": True,
        "specification_strong_labels": {"ENG": 7, "ARA": 7},
        "xml_markdown_character_sequence": True,
        "markdown_html_structure_equal": True,
        "final_semantic_sha256": digest(folder / "semantic_document.xml"),
        "final_source_review_complete": True,
    }
    dump(folder / "source_audit.json", proof)
    review["source_audit"] = proof
    review["hard_gates"].update(
        source_review_complete=True,
        targeted_readability_source_parity=True,
    )
    if any(value is not True for value in review["hard_gates"].values()):
        raise ValueError("MENA review still has unresolved hard gates")
    review["status"] = "extraction_review_pass_pending_human_review"
    review["human_approval"] = False
    dump(folder / "review_document.json", review)
    run.update(
        review_status=review["status"],
        hard_gate_failures=[],
        human_approval=False,
        validation_sha256=digest(folder / "html_validation.json"),
    )
    dump(folder / "review_run.json", run)

    rows = []
    for language, stats in review["language_stats"].items():
        rows.append(
            "<tr>"
            + "".join(
                f"<td>{escape(str(value))}</td>"
                for value in (
                    language,
                    stats["headings"],
                    stats["review_units"],
                    stats["blocks"].get("table", 0),
                    stats["blocks"].get("figure", 0),
                )
            )
            + '<td><a href="MENA_L02/semantic_document.preview.html">전체 HTML</a> · '
            '<a href="MENA_L02/semantic_document.md">MD</a> · '
            '<a href="MENA_L02/semantic_document.xml">XML</a></td></tr>'
        )
    body = (
        "<!doctype html><html lang=\"ko\"><meta charset=\"utf-8\"><style>"
        "body{font:18px Arial;max-width:1150px;margin:40px auto;line-height:1.7}"
        "table{border-collapse:collapse;width:100%}td,th{border:1px solid #aaa;padding:9px}"
        "th{background:#eef2f6}</style><body><h1>MENA 가독성 수정 검토</h1>"
        "<p>원문 구조·문자·표 관계는 승인된 MENA source audit과 동일합니다. 사용자 최종 컨펌 대기입니다.</p>"
        "<table><tr><th>언어</th><th>표시 제목</th><th>검토 단위</th><th>표</th><th>그림</th><th>검토 파일</th></tr>"
        + "".join(rows)
        + "</table><p>표시 제목은 표지 포함 검토 제목 수입니다. 그림은 semantic XML figure 노드 수입니다.</p>"
        "<h2>수정 확인</h2><ul><li>표지 Contact Samsung world wide 굵기</li>"
        "<li>연락처 표 셀의 원문 문단 줄바꿈</li><li>The screen dims. 하단 문장 줄바꿈</li>"
        "<li>사양표 모델 전용 물리행 줄바꿈</li>"
        "<li>Arabic 안전 문장의 동일 MCID 결합부호·단어 순서</li>"
        "<li>Arabic The Frame 각주의 원문 *: 순서</li>"
        "<li>Specifications 굵은 항목명 소제목 표시</li></ul>"
        '<p><a href="MENA_L02/source_audit.json">수정 근거</a> · '
        '<a href="ownership_findings.html">PDF/문장 연결 검토 자료</a></p></body></html>'
    )
    (args.output.resolve() / "review.html").write_text(body, encoding="utf-8")
    print(review["status"])


if __name__ == "__main__":
    main()
