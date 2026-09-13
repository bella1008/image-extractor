"""Real AFRICA source evidence; deliberately independent of legacy GridCell code."""
import os
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from tagged_pdf_extractor.cli import _build_use_case

NAME = "BN68-25031G-00_SUG_Y26 TV ALL_AFRICA_L05_251230.0.pdf"

@pytest.fixture(scope="module")
def africa(tmp_path_factory):
    source = Path(os.environ.get("TAGGED_PDF_AFRICA_SAMPLE", str(Path(__file__).resolve().parents[3] / "samples/SUG_RAW/TV_AFRICA" / NAME)))
    if not source.is_file():
        pytest.skip("AFRICA real PDF unavailable")
    output = tmp_path_factory.mktemp("africa")
    document, report, artifacts = _build_use_case().run(source, output)
    return document, report, artifacts

def test_arabic_chapter_numbers_use_pdf_actual_text(africa):
    document, report, artifacts = africa
    labels = [h.label for h in document.heading_promotions]
    assert labels == ["01", "02", "03", "04"] * 5

def test_semantic_arabic_pages_follow_rtl_book_order_and_raw_stays_original(africa):
    _, _, artifacts = africa
    raw = ET.parse(artifacts.raw_xml).getroot()
    semantic = ET.parse(artifacts.semantic_xml).getroot()
    def page_order(root, tag):
        return list(dict.fromkeys(int(e.get("page-index")) for e in root.iter(tag) if e.get("page-index") is not None and int(e.get("page-index")) >= 26))
    assert page_order(raw, "fragment") == list(range(26, 36))
    assert page_order(semantic, "text") == list(range(35, 25, -1))

def test_arabic_interval_does_not_leak_into_portuguese(africa):
    document, _, _ = africa
    signatures = document.multilingual_heading_audit.signatures
    by_lang = {s.language: s for s in signatures}
    assert by_lang["POR"].interval.end_page_index == 24
    assert by_lang["ARA"].interval.start_page_index == 26
    assert by_lang["ARA"].interval.end_page_index == 35


def test_markdown_displays_arabic_chapter_numbers_as_single_labels(africa):
    import re
    _, _, artifacts=africa
    md=artifacts.semantic_markdown.read_text(encoding="utf-8")
    assert len(re.findall(r"^## 0[1-4] ",md,re.M)) == 20
    assert not re.search(r"^## 0 [1-4] ",md,re.M)


def test_actual_text_and_reorder_keep_source_identity_and_glyph_evidence(africa):
    from collections import Counter
    _, report, artifacts=africa
    raw=ET.parse(artifacts.raw_xml).getroot();semantic=ET.parse(artifacts.semantic_xml).getroot()
    def identities(root,tag):
        return Counter((e.get("page-index"),e.get("mcid"),e.get("object-ref")) for e in root.iter(tag))
    assert identities(raw,"fragment") == identities(semantic,"text")
    target=raw.find(".//fragment[@page-index='29'][@mcid='870']")
    assert target is not None and target.get("bbox")
    diagnostics=[d for d in report.diagnostics if d.code=="pdf_actual_text_applied"]
    assert diagnostics and all("source_runs" in r for d in diagnostics for r in d.context["replacements"])


def test_rtl_glyph_heading_uses_observed_pdf_order_across_mcids(africa):
    _, _, artifacts = africa
    semantic = ET.parse(artifacts.semantic_xml).getroot()
    heading = semantic.find(".//*[@source-structure-path='0/17/1/0']")
    text = " ".join(" ".join(e.text or "" for e in heading.iter("text")).split())
    # Visually observed source wording; do not substitute grammatical guesses.
    assert text == "قبل قراءة الدليل البسيط للمستخدم هذا"
    assert [e.get("mcid") for e in heading.iter("text")] == ["72", "71", "70"]


def test_rtl_glyph_keeps_combining_glyph_with_its_word(africa):
    _, _, artifacts = africa
    semantic = ET.parse(artifacts.semantic_xml).getroot()
    text = semantic.find(".//text[@page-index='32'][@mcid='339']")
    assert text.text.strip() == "تجن\u0651\u064fب سقوط التلفزيون"


def test_rtl_glyph_combining_marks_with_source_sentence_period(africa):
    _, _, artifacts = africa
    semantic = ET.parse(artifacts.semantic_xml).getroot()
    text = semantic.find(".//text[@page-index='29'][@mcid='842']")
    assert text.text.strip() == "تعت\u0651م الشاشة."
