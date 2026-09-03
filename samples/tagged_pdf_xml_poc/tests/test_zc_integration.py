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


_SAMPLE_RELATIVE_PATH = (
    Path("samples")
    / "SUG_RAW"
    / "0_TV_ZC"
    / "BN68-25100B-00_SUG_Y26 TV ALL_ZC_L02_260122.0.pdf"
)
def _resolve_zc_pdf(
    *, anchor: Path = Path(__file__), home: Path | None = None
) -> Path | None:
    candidates: list[Path] = []
    environment_path = os.environ.get("TAGGED_PDF_ZC_SAMPLE")
    if environment_path:
        candidates.append(Path(environment_path).expanduser())

    anchor = Path(anchor)
    start = anchor if anchor.is_dir() else anchor.parent
    candidates.extend(
        ancestor / _SAMPLE_RELATIVE_PATH
        for ancestor in (start, *start.parents)
    )
    candidates.append((home or Path.home()) / "image-extractor" / _SAMPLE_RELATIVE_PATH)

    seen: set[Path] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        if candidate.is_file():
            return candidate
    return None


PDF = _resolve_zc_pdf()


def _touch_sample(root: Path) -> Path:
    sample = root / _SAMPLE_RELATIVE_PATH
    sample.parent.mkdir(parents=True)
    sample.touch()
    return sample


def test_sample_resolver_prefers_available_environment_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    environment_sample = tmp_path / "external" / "sample.pdf"
    environment_sample.parent.mkdir()
    environment_sample.touch()
    repository_root = tmp_path / "repository"
    _touch_sample(repository_root)
    monkeypatch.setenv("TAGGED_PDF_ZC_SAMPLE", str(environment_sample))

    assert _resolve_zc_pdf(
        anchor=repository_root / "samples/tagged_pdf_xml_poc/tests/test.py",
        home=tmp_path / "home",
    ) == environment_sample


def test_sample_resolver_prefers_repository_relative_sample_before_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("TAGGED_PDF_ZC_SAMPLE", raising=False)
    repository_root = tmp_path / "repository"
    repository_sample = _touch_sample(repository_root)
    home = tmp_path / "home"
    _touch_sample(home / "image-extractor")

    assert _resolve_zc_pdf(
        anchor=repository_root / "samples/tagged_pdf_xml_poc/tests/test.py",
        home=home,
    ) == repository_sample


def test_sample_resolver_uses_home_development_fallback_and_then_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("TAGGED_PDF_ZC_SAMPLE", raising=False)
    home = tmp_path / "home"
    home_sample = _touch_sample(home / "image-extractor")
    unrelated_anchor = tmp_path / "elsewhere/tests/test.py"

    assert _resolve_zc_pdf(anchor=unrelated_anchor, home=home) == home_sample
    assert _resolve_zc_pdf(
        anchor=unrelated_anchor, home=tmp_path / "empty-home"
    ) is None


def _walk(children, source_roles: Counter[str]) -> int:
    fragment_count = 0
    for child in children:
        if isinstance(child, ContentFragment):
            fragment_count += 1
        else:
            source_roles[child.source_role] += 1
            fragment_count += _walk(child.children, source_roles)
    return fragment_count


@pytest.mark.skipif(PDF is None, reason="ZC tagged PDF sample is not available")
def test_zc_pdf_has_recoverable_tagged_hierarchy_and_auditable_outputs(
    tmp_path: Path,
) -> None:
    assert PDF is not None
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
