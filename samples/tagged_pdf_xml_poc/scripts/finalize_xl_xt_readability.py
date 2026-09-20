"""Seal the XL/XT readability rerun against the accepted source audits."""

import argparse
from collections import Counter
from hashlib import sha256
from html import escape
import json
from pathlib import Path
from xml.etree import ElementTree as E

from review_tk_xml import code_hashes, dump


POC = Path(__file__).resolve().parents[1]
BASELINE = POC / "outputs" / "xml_review_mena_xl_xt_20260917_ready"


def digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def source_signature(root: E.Element) -> tuple:
    return tuple(
        (
            node.tag,
            node.get("source-structure-path"),
            node.get("object-ref"),
            node.get("page-index"),
            node.get("language"),
            node.get("mcid"),
            node.text if node.tag == "text" else None,
        )
        for node in root.iter()
        if node.tag not in {"attributes", "attribute"}
    )


def table_signature(root: E.Element) -> tuple:
    return tuple(
        (
            table.get("source-structure-path"),
            tuple(
                tuple(
                    (
                        cell.tag,
                        cell.get("source-structure-path"),
                        tuple(
                            sorted(
                                (item.get("name"), item.get("value"))
                                for item in cell.findall("attributes/attribute")
                                if item.get("name") in {"/RowSpan", "/ColSpan"}
                            )
                        ),
                    )
                    for cell in row
                    if cell.tag in {"table_cell", "table_header"}
                )
                for row in table
                if row.tag == "table_row"
            ),
        )
        for table in root.iter("table")
    )


def _validate_common(folder: Path, baseline: Path) -> tuple[dict, E.Element]:
    review = json.loads((folder / "review_document.json").read_text(encoding="utf-8"))
    run = json.loads((folder / "review_run.json").read_text(encoding="utf-8"))
    html = json.loads((folder / "html_validation.json").read_text(encoding="utf-8"))
    old_root = E.parse(baseline / "semantic_document.xml").getroot()
    new_root = E.parse(folder / "semantic_document.xml").getroot()
    old_audit = json.loads((baseline / "source_audit.json").read_text(encoding="utf-8"))

    if old_audit.get("final_source_review_complete") is not True:
        raise ValueError("accepted source audit is incomplete")
    if review["source"]["sha256"] != old_audit.get(
        "sha256", old_audit.get("source_sha256")
    ):
        raise ValueError("source revision changed")
    if run["runtime_code_sha256"] != code_hashes():
        raise ValueError("runtime changed after extraction")
    if source_signature(old_root) != source_signature(new_root):
        raise ValueError("source text or structure changed")
    if table_signature(old_root) != table_signature(new_root):
        raise ValueError("table row/cell/span relationships changed")
    if not (
        html.get("xml_markdown_full_character_sequence") is True
        and html.get("md_preview_text_and_structure_equal") is True
        and html.get("unit_failures") == []
    ):
        raise ValueError("Markdown/HTML validation failed")
    if any(
        value is not True
        for key, value in review["hard_gates"].items()
        if key != "source_review_complete"
    ):
        raise ValueError("automatic hard gate remains")
    return review, new_root


def _validate_xl(folder: Path, root: E.Element) -> dict:
    markdown = (folder / "semantic_document.md").read_text(encoding="utf-8")
    required = (
        "**Contact Samsung world wide**",
        "<td>1800-88-9999<br>+603-7713 7420 (Overseas contact)</td>",
        "<td>Mobile to Landline:<br>02 8422-2111<br>Landline to Landline:<br>8422-2111</td>",
        "The Eco Sensor automatically adjusts the screen brightness based on the ambient light intensity.<br>\nIf the screen is too dark",
    )
    if any(value not in markdown for value in required):
        raise ValueError("XL required readability output is missing")
    labels = [
        node
        for node in root.iter("paragraph")
        if node.get("display-reason") == "repeated_table_label_value_typography"
    ]
    if len(labels) != 33 or Counter(node.get("language") for node in labels) != {"ENG": 33}:
        raise ValueError("XL specification label coverage changed")
    return {
        "cover_contact_title": True,
        "cover_contact_source_paragraph_breaks": True,
        "screen_dims_sentence_break": True,
        "specification_strong_labels": {"ENG": 33},
        "market_context": "India; retained source headings include For India only",
    }


def _validate_xt(folder: Path, root: E.Element) -> dict:
    markdown = (folder / "semantic_document.md").read_text(encoding="utf-8")
    required = (
        "**Contact Samsung world wide**",
        "<td>Hotline no : 1282<br>1800-29-3232 (Toll free for all product)</td>",
        "The Eco Sensor automatically adjusts the screen brightness based on the ambient light intensity.<br>\nIf the screen is too dark",
        "**Display Resolution**",
        "**ความละเอียดการแสดงผล**",
    )
    if any(value not in markdown for value in required):
        raise ValueError("XT required readability output is missing")
    labels = [
        node
        for node in root.iter("paragraph")
        if node.get("display-reason") == "repeated_table_label_value_typography"
    ]
    if Counter(node.get("language") for node in labels) != {"ENG": 7, "THA": 7}:
        raise ValueError("XT specification label coverage changed")
    return {
        "cover_contact_title": True,
        "cover_contact_source_paragraph_breaks": {"ENG": True, "THA": True},
        "screen_dims_sentence_break": True,
        "specification_strong_labels": {"ENG": 7, "THA": 7},
    }


def _seal(folder: Path, baseline: Path, buyer: str) -> dict:
    review, root = _validate_common(folder, baseline)
    findings = _validate_xl(folder, root) if buyer == "XL_ENG" else _validate_xt(folder, root)
    old_audit = json.loads((baseline / "source_audit.json").read_text(encoding="utf-8"))
    audit = {
        **old_audit,
        "baseline_source_audit": str((baseline / "source_audit.json").resolve()),
        "semantic_source_text_and_structure_equal": True,
        "table_relationships_equal": True,
        **findings,
        "xml_markdown_character_sequence": True,
        "markdown_html_structure_equal": True,
        "final_semantic_sha256": digest(folder / "semantic_document.xml"),
        "final_markdown_sha256": digest(folder / "semantic_document.md"),
        "final_source_review_complete": True,
    }
    dump(folder / "source_audit.json", audit)
    review["source_audit"] = audit
    review["hard_gates"]["source_review_complete"] = True
    review["status"] = "extraction_review_pass_pending_human_review"
    review["human_approval"] = False
    dump(folder / "review_document.json", review)
    run = json.loads((folder / "review_run.json").read_text(encoding="utf-8"))
    run.update(
        review_status=review["status"],
        hard_gate_failures=[],
        human_approval=False,
        validation_sha256=digest(folder / "html_validation.json"),
    )
    dump(folder / "review_run.json", run)
    return review


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    reviews = [
        _seal(output / buyer, BASELINE / buyer, buyer)
        for buyer in ("XL_ENG", "XT_L02")
    ]

    body = (
        "<h1>XL · XT 추출 검토</h1>"
        "<p>2026-09-20 표시 개선 재추출입니다. 원문 텍스트·구조·표 관계는 승인된 2026-09-17 원문 감사와 동일합니다. "
        "추출 Hard gate는 0이며 사용자 최종 컨펌은 대기 상태입니다.</p>"
        "<table><tr><th>바이어</th><th>언어</th><th>제목</th><th>검토 단위</th><th>표</th><th>그림</th><th>파일</th></tr>"
    )
    for review in reviews:
        buyer = review["source"]["buyer"]
        for language, stats in review["language_stats"].items():
            body += (
                f"<tr><td>{escape(buyer)}</td><td>{escape(language)}</td>"
                f"<td>{stats['headings']}</td><td>{stats['review_units']}</td>"
                f"<td>{stats['blocks'].get('table', 0)}</td><td>{stats['blocks'].get('figure', 0)}</td>"
                f'<td><a href="{buyer}/semantic_document.preview.html">전체 HTML</a> · '
                f'<a href="{buyer}/semantic_document.md">MD</a> · '
                f'<a href="{buyer}/semantic_document.xml">XML</a></td></tr>'
            )
    body += (
        "</table><h2>이번 확인 항목</h2><ul>"
        "<li>XL/XT 표지 연락처 제목 굵기와 서로 다른 원문 문단의 셀 내부 줄바꿈</li>"
        "<li>The screen dims. 하단 문장 경계</li>"
        "<li>XL 4열 사양표 첫 열의 굵은 항목 33개</li>"
        "<li>XT 사양표 ENG 7개·THA 7개 굵은 항목</li>"
        "</ul><p>XL은 인도향 문서이며 실제 원문의 For India only 구간을 그대로 유지했습니다.</p>"
    )
    (output / "review.html").write_text(
        "<!doctype html><html lang=\"ko\"><meta charset=\"utf-8\"><style>"
        "body{font:18px Arial,sans-serif;max-width:1150px;margin:36px auto;line-height:1.7}"
        "table{border-collapse:collapse;width:100%}th,td{border:1px solid #aaa;padding:9px}"
        "th{background:#eef2f6}</style><body>" + body + "</body></html>",
        encoding="utf-8",
    )
    dump(
        output / "final_summary.json",
        [
            {
                "buyer": review["source"]["buyer"],
                "status": review["status"],
                "stats": review["language_stats"],
                "hard_gate_failures": [],
            }
            for review in reviews
        ],
    )
    print("XL/XT readability reviews sealed; human approval remains pending.")


if __name__ == "__main__":
    main()
