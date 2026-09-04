import os
from pathlib import Path

import pytest

from tagged_pdf_extractor.application.evaluate_quality import QualityEvaluator
from tagged_pdf_extractor.infrastructure.pymupdf_baseline import (
    PyMuPdfBaselineReader,
)
from tagged_pdf_extractor.infrastructure.pypdf_reader import TaggedPdfReader


_SAMPLES = {
    "ZA": (
        "TAGGED_PDF_ZA_SAMPLE",
        Path("samples")
        / "SUG_RAW"
        / "0_TV_ZA"
        / "BN68-25099B-00_SUG_Y26 TV ALL_ZA_ENG_260126.0.pdf",
    ),
    "ZG": (
        "TAGGED_PDF_ZG_SAMPLE",
        Path("samples")
        / "SUG_RAW"
        / "1_TV_ZG"
        / "BN68-25448A-00_SUG_Y26 TV ALL_ZG XN ZT_L05_260204.0.pdf",
    ),
}
_README = Path(__file__).parents[1] / "README.md"


def _resolve_sample(
    sample: str,
    *,
    anchor: Path = Path(__file__),
    home: Path | None = None,
) -> Path | None:
    environment_name, relative_path = _SAMPLES[sample]
    candidates: list[Path] = []
    environment_path = os.environ.get(environment_name)
    if environment_path:
        candidates.append(Path(environment_path).expanduser())

    anchor = Path(anchor)
    start = anchor if anchor.is_dir() else anchor.parent
    candidates.extend(
        ancestor / relative_path for ancestor in (start, *start.parents)
    )
    candidates.append((home or Path.home()) / "image-extractor" / relative_path)

    seen: set[Path] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        if candidate.is_file():
            return candidate
    return None


def _extract_report(path: Path):
    document = TaggedPdfReader().read(path)
    baseline = PyMuPdfBaselineReader().read_text(path)
    report = QualityEvaluator().evaluate(
        document, baseline, xml_round_trip_ok=True
    )
    return document, report


def _assert_complete_page_quality(page_quality, expected_pages: set[str]) -> None:
    assert set(page_quality) == expected_pages
    for page_index in sorted(expected_pages, key=int):
        metric = page_quality[page_index]
        assert metric["fragment_count"] > 0
        assert metric["character_count"] > 0
        assert metric["forbidden_xml_control_count"] == 0


def _assert_common_layout_quality(document, report, expected_pages: set[str]) -> None:
    assert document.marked is True
    assert report.metrics["unresolved_mcid_count"] == 0
    assert report.metrics["forbidden_xml_control_count"] == 0
    assert report.metrics["element_count"] > 0
    assert report.metrics["body_count"] > 0
    _assert_complete_page_quality(
        report.metrics["text_quality_by_page"], expected_pages
    )


def test_page_quality_rejects_a_missing_expected_page() -> None:
    page_quality = {
        "0": {
            "fragment_count": 1,
            "character_count": 1,
            "forbidden_xml_control_count": 0,
        }
    }

    with pytest.raises(AssertionError):
        _assert_complete_page_quality(page_quality, {"0", "1"})


def test_readme_documents_sample_overrides_and_independent_skips() -> None:
    readme = _README.read_text(encoding="utf-8")

    assert "TAGGED_PDF_ZC_SAMPLE" in readme
    assert "TAGGED_PDF_ZA_SAMPLE" in readme
    assert "TAGGED_PDF_ZG_SAMPLE" in readme
    assert "그 샘플의 테스트만 독립적으로 건너뛰" in readme


def test_za_retains_complete_structure_and_clean_page_text() -> None:
    path = _resolve_sample("ZA")
    if path is None:
        pytest.skip("ZA tagged PDF sample is not available")

    document, report = _extract_report(path)
    _assert_common_layout_quality(document, report, {"0", "1"})


def test_zg_retains_all_pages_without_false_image_xobject_loss() -> None:
    path = _resolve_sample("ZG")
    if path is None:
        pytest.skip("ZG tagged PDF sample is not available")

    document, report = _extract_report(path)
    _assert_common_layout_quality(
        document, report, {str(page_index) for page_index in range(52)}
    )
    assert report.diagnostics == ()
    assert report.metrics["extraction_loss_diagnostic_total"] == 0
    assert report.hard_gates == {
        "is_marked": True,
        "has_structure": True,
        "has_body": True,
        "has_heading": False,
        "resolved_references": True,
        "resolved_references_reported": True,
        "xml_round_trip": True,
        "special_character_counts_preserved": True,
        "no_known_text_loss": True,
    }
    assert report.status == "fail"
