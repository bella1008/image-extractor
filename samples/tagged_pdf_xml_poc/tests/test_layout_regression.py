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


@pytest.mark.parametrize("sample", ("ZA", "ZG"))
def test_tagged_layout_retains_structure_and_clean_page_text(sample: str) -> None:
    path = _resolve_sample(sample)
    if path is None:
        pytest.skip(f"{sample} tagged PDF sample is not available")

    document, report = _extract_report(path)

    assert document.marked is True
    assert report.metrics["unresolved_mcid_count"] == 0
    assert report.metrics["forbidden_xml_control_count"] == 0
    assert report.metrics["element_count"] > 0
    assert report.metrics["body_count"] > 0

    page_quality = report.metrics["text_quality_by_page"]
    assert page_quality
    assert all(
        metric["forbidden_xml_control_count"] == 0
        for metric in page_quality.values()
    )


def test_zg_keeps_form_xobject_text_loss_diagnostics_visible() -> None:
    path = _resolve_sample("ZG")
    if path is None:
        pytest.skip("ZG tagged PDF sample is not available")

    _, report = _extract_report(path)
    diagnostics = [
        diagnostic
        for diagnostic in report.diagnostics
        if diagnostic.code == "tagged_form_xobject_unsupported"
    ]

    assert len(diagnostics) == 10
    assert [diagnostic.context for diagnostic in diagnostics] == [
        {"page_index": page_index, "operand_repr": "'/Im0'"}
        for page_index in (8, 9, 18, 19, 28, 29, 38, 39, 48, 49)
    ]
    assert report.hard_gates["no_known_text_loss"] is False
    assert all("page_index" in diagnostic.context for diagnostic in diagnostics)
    assert all("operand_repr" in diagnostic.context for diagnostic in diagnostics)
