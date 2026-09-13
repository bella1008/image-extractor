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


def test_rtl_inline_navigation_reads_each_source_line_from_the_right(africa):
    _, _, artifacts = africa
    semantic = ET.parse(artifacts.semantic_xml).getroot()
    route = semantic.find(".//*[@source-structure-path='0/17/1/2']")
    assert [int(t.get("mcid")) for t in route.iter("text")] == [
        88, 87, 86, 85, 84, 83, 82, 81, 80, 79, 92, 91, 90, 89]
    md = artifacts.semantic_markdown.read_text(encoding="utf-8")
    assert "( [아이콘] > زر الاتجاه الأيسر > [아이콘] الإعدادات > الدعم > التلميحات وأدلة المستخدم > فتح دليل المستخدم )" in md


def test_rtl_controller_heading_matches_source_title_order(africa):
    _, _, artifacts = africa
    semantic = ET.parse(artifacts.semantic_xml).getroot()
    title = semantic.find(".//*[@source-structure-path='0/13/0/3']")
    assert [int(t.get("mcid")) for t in title.iter("text")] == [568, 567]
    assert "استخدام وحدة التحكم في التلفزيون" in artifacts.semantic_markdown.read_text(encoding="utf-8")


def test_rtl_mixed_eco_line_restores_local_word_and_inline_route_order(africa):
    _, _, artifacts = africa
    semantic = ET.parse(artifacts.semantic_xml).getroot()
    paragraph = semantic.find(".//*[@source-structure-path='0/12/0/3']")
    ids = [int(t.get("mcid")) for t in paragraph.iter("text")]
    assert ids[:4] == [846,845,844,843]
    assert ids.index(852) < ids.index(851) < ids.index(850) < ids.index(849)
    assert ids.index(862) < ids.index(860) < ids.index(858) < ids.index(856) < ids.index(864)
    md = artifacts.semantic_markdown.read_text(encoding="utf-8")
    assert "يقوم مستشعر Eco بضبط درجة سطوع الشاشة تلقائيًا بناءً على شدة" in md


def test_rtl_list_body_update_route_follows_source_inline_order(africa):
    _, _, artifacts = africa
    semantic = ET.parse(artifacts.semantic_xml).getroot()
    route = semantic.find(".//*[@source-structure-path='0/13/0/21/1/1']")
    ids = [int(t.get("mcid")) for t in route.iter("text")]
    assert ids.index(748) < ids.index(747) < ids.index(746) < ids.index(744)
    assert ids.index(744) < ids.index(757) < ids.index(755) < ids.index(753)


def test_verified_jordan_source_difference_preserves_observed_heading_counts(africa):
    document, report, artifacts = africa
    audit = document.multilingual_heading_audit
    assert [len(s.entries) for s in audit.signatures] == [22,21,21,21,22]
    assert audit.total_heading_count_matches is False
    assert report.hard_gates["multilingual_heading_count_parity"] is True
    data = report.metrics["multilingual_heading_audit"]
    assert data["status"] == "passed_with_source_exception"
    assert [(m["language"],m["position"]) for m in data["mismatch_positions"]] == [("FRA",21),("SPA",21),("POR",21)]
    assert data["source_count_exception"]["code"] == "africa_observed_jordan_only"
    assert ET.parse(artifacts.semantic_xml).find(".//multilingual-heading-audit/source-count-exception") is not None


@pytest.mark.parametrize("mutation", ["hash", "profile", "headings", "table", "heading_text", "heading_level", "extra_mismatch"])
def test_jordan_exception_fails_closed_on_changed_source_evidence(africa, mutation):
    from dataclasses import replace
    from tagged_pdf_extractor.domain.africa_heading_evidence import verified_jordan_difference
    from tagged_pdf_extractor.domain.models import ContentFragment, PdfProfile
    document, _, _ = africa
    profile = PdfProfile("AFRICA_L05","BOOK",("ENG","FRA","SPA","POR","ARA"),5)
    audit = document.multilingual_heading_audit
    signatures, mismatches = audit.signatures, audit.mismatch_positions
    if mutation == "hash":
        document = replace(document, source_sha256="0"*64)
    elif mutation == "profile":
        profile = replace(profile, source_token="AFRICA MENA_L05")
    elif mutation == "headings":
        signatures = (replace(signatures[0],entries=signatures[0].entries[1:]),*signatures[1:])
    elif mutation == "extra_mismatch":
        mismatches = (*mismatches, replace(mismatches[0],position=20))
    else:
        def damage(node):
            if isinstance(node,ContentFragment):
                return node
            if node.source_structure_path == (0,2,0,15,0):
                if mutation == "table":
                    return replace(node,children=node.children[:1])
            if node.source_structure_path == (0,2,0,14):
                if mutation == "heading_text":
                    return replace(node,children=(ContentFragment(6,1,("Changed source",)),))
                if mutation == "heading_level":
                    return replace(node,source_role="Heading2")
            return replace(node,children=tuple(damage(c) for c in node.children))
        document = replace(document,children=tuple(damage(c) for c in document.children))
    assert verified_jordan_difference(profile, document, signatures, mismatches) is None


def test_arabic_jordan_url_preserves_source_ltr_island(africa):
    _, _, artifacts = africa
    semantic = ET.parse(artifacts.semantic_xml).getroot()
    paragraph = semantic.find(".//*[@source-structure-path='0/12/0/15/0/1/0/1']")
    ids = [int(t.get("mcid")) for t in paragraph.iter("text")]
    assert ids.index(823) < ids.index(824)
    assert "http://www.samsung.com" in artifacts.semantic_markdown.read_text(encoding="utf-8")


def test_arabic_actual_text_decimal_digits_stay_one_source_number(africa):
    _, _, artifacts = africa
    semantic = ET.parse(artifacts.semantic_xml).getroot()
    for mcid, number in ((802,"6.425"),(804,"7.125"),(806,"5.925")):
        assert semantic.find(f".//text[@page-index='29'][@mcid='{mcid}']").text.strip() == number


def test_source_count_exception_never_overrides_an_unrelated_hard_failure(africa):
    from dataclasses import replace
    from tagged_pdf_extractor.application.evaluate_quality import QualityEvaluator
    document, _, _ = africa
    report = QualityEvaluator().evaluate(replace(document, marked=False), "", True)
    assert report.hard_gates["multilingual_heading_count_parity"]
    assert not report.hard_gates["is_marked"]
    assert report.status == "fail"


def test_rtl_model_range_and_wifi_ranges_preserve_source_associations(africa):
    _, _, artifacts = africa
    semantic = ET.parse(artifacts.semantic_xml).getroot()
    paragraph = semantic.find(".//*[@source-structure-path='0/12/0/7/0/1/0/4']")
    ids = [int(t.get("mcid")) for t in paragraph.iter("text")]
    assert ids.index(934) < ids.index(932) < ids.index(930) < ids.index(928)
    assert ids.index(926) < ids.index(924) < ids.index(922) < ids.index(920) < ids.index(918)
    wifi = semantic.find(".//*[@source-structure-path='0/12/0/12']")
    ids = [int(t.get("mcid")) for t in wifi.iter("text")]
    assert ids.index(806) < ids.index(805) < ids.index(804) < ids.index(803) < ids.index(802) < ids.index(801)


def test_rtl_model_list_keeps_slash_at_wrapped_line_boundary(africa):
    _, _, artifacts = africa
    semantic = ET.parse(artifacts.semantic_xml).getroot()
    paragraph = semantic.find(".//*[@source-structure-path='0/12/0/7/0/1/0/1']")
    ids = [int(t.get("mcid")) for t in paragraph.iter("text")]
    assert ids[:14] == list(range(896,882,-1))
    assert ids.index(883) < ids.index(903) < ids.index(902) < ids.index(901) < ids.index(899)


@pytest.mark.parametrize("page,mcid,token", [(6,743,"7.125"),(12,1599,"7,125"),(18,2437,"7,125"),(24,3276,"7,125")])
def test_ltr_wifi_decimal_keeps_source_token_and_no_sentence_break(africa,page,mcid,token):
    _, _, artifacts = africa
    semantic = ET.parse(artifacts.semantic_xml).getroot()
    fragment = semantic.find(f".//text[@page-index='{page}'][@mcid='{mcid}']")
    assert token in fragment.text
    assert fragment.get("sentence-break-offsets") is None
    md = artifacts.semantic_markdown.read_text(encoding="utf-8")
    assert "7 .<br>" not in md and "7 ,125" not in md


@pytest.mark.parametrize("suffix", [4,6,7])
def test_arabic_inch_conditions_restore_neutral_order_and_rtl_display(africa,suffix):
    _, _, artifacts=africa
    root=ET.parse(artifacts.semantic_xml).getroot()
    paragraph=root.find(f".//*[@source-structure-path='0/12/0/7/0/1/0/{suffix}']")
    assert paragraph.get("display-direction") == "rtl"
    assert len(root.findall(".//*[@display-direction='rtl']")) == 4
    clean=lambda s: ''.join(c for c in s if not c.isspace() and c not in '\u200e\u200f')
    text=clean(''.join(t.text or '' for t in paragraph.iter('text')))
    expected={4:'S90H("42):20واط,S90H("48-"83):40واط',
              6:'LS03HE("43-"85):20واط',7:'LS03HE("98)/LS03HW:40واط'}
    assert text==expected[suffix]
    md=artifacts.semantic_markdown.read_text(encoding="utf-8")
    assert md.count('<span dir="rtl">')==4



def test_arabic_wifi_brackets_enclose_the_complete_source_precaution(africa):
    _, _, artifacts=africa
    root=ET.parse(artifacts.semantic_xml).getroot()
    paragraph=root.find(".//*[@source-structure-path='0/12/0/12']")
    assert paragraph.get('display-direction')=='rtl'
    texts=list(paragraph.iter('text'))
    assert texts[0].text.strip().startswith('[')
    assert texts[-1].text.strip().endswith(']')
    assert '7.125' in ''.join(t.text or '' for t in texts)
