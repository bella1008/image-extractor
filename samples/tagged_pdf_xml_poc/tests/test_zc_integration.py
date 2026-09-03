import json
import os
import re
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from tagged_pdf_extractor.application.evaluate_quality import QualityEvaluator
from tagged_pdf_extractor.domain.models import ContentFragment, StructureElement
from tagged_pdf_extractor.infrastructure.output_bundle import OutputBundleWriter
from tagged_pdf_extractor.infrastructure.pymupdf_baseline import PyMuPdfBaselineReader
from tagged_pdf_extractor.infrastructure.pypdf_reader import TaggedPdfReader
from tagged_pdf_extractor.infrastructure.xml_writer import decode_data_element


_DEFAULT_PDF = Path(
    r"C:\Users\bella\image-extractor\samples\SUG_RAW\0_TV_ZC"
    r"\BN68-25100B-00_SUG_Y26 TV ALL_ZC_L02_260122.0.pdf"
)
PDF = Path(os.environ.get("TAGGED_PDF_ZC_SAMPLE", _DEFAULT_PDF))


def _walk(children, source_roles: Counter[str]) -> int:
    fragment_count = 0
    for child in children:
        if isinstance(child, ContentFragment):
            fragment_count += 1
        else:
            source_roles[child.source_role] += 1
            fragment_count += _walk(child.children, source_roles)
    return fragment_count


@pytest.mark.skipif(not PDF.is_file(), reason="ZC tagged PDF sample is not available")
def test_zc_pdf_has_recoverable_tagged_hierarchy_and_auditable_outputs(
    tmp_path: Path,
) -> None:
    reader = TaggedPdfReader()
    document = reader.read(PDF)
    source_roles: Counter[str] = Counter()
    fragment_count = _walk(document.children, source_roles)

    assert document.marked is True
    assert document.children
    assert fragment_count > 0
    assert not [d for d in document.diagnostics if d.code == "unresolved_mcid"]

    role_map = dict(document.role_map)
    expected_custom_headings = {
        "Heading2",
        "Heading3",
        "NoTOC-Heading1",
        "NoTOC-Heading2",
        "NoTOC-Heading3",
        "Cover_Title",
    }
    assert expected_custom_headings <= source_roles.keys()
    assert {role_map[name] for name in expected_custom_headings} == {"P"}

    baseline = PyMuPdfBaselineReader().read_text(PDF)
    validation = OutputBundleWriter().validate(document)
    report = QualityEvaluator().evaluate(document, baseline, xml_round_trip_ok=True)
    assert report.metrics["heading_count"] == 0
    assert report.hard_gates["has_heading"] is False
    assert report.status == "fail"
    assert validation.semantic_join_decisions == report.join_decisions

    output = tmp_path / "result"
    artifacts = OutputBundleWriter().write(document, report, output)
    raw_root = ET.parse(artifacts.raw_xml).getroot()
    semantic_root = ET.parse(artifacts.semantic_xml).getroot()
    report_data = json.loads(artifacts.report_json.read_text(encoding="utf-8"))

    raw_source_roles = {
        element.attrib["source-role"] for element in raw_root.iter("element")
    }
    assert expected_custom_headings <= raw_source_roles
    assert report_data["metrics"]["fragment_count"] > 0
    assert report_data["metrics"]["unresolved_mcid_count"] == 0
    assert report_data["join_decisions"] == list(report.join_decisions)

    normalized_paragraphs = {
        re.sub(
            r"\s+",
            " ",
            "".join(decode_data_element(text) for text in element.iter("text")),
        ).strip()
        for element in semantic_root.iter("paragraph")
    }
    assert (
        "( > left directional button > Settings > Support > Tips and User "
        "Guides > Open User Guide)"
    ) in normalized_paragraphs
