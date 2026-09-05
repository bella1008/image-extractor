import os
import re
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from tagged_pdf_extractor.application.evaluate_quality import QualityEvaluator
from tagged_pdf_extractor.application.extract_document import ExtractDocument
from tagged_pdf_extractor.infrastructure.output_bundle import OutputBundleWriter
from tagged_pdf_extractor.infrastructure.pymupdf_baseline import (
    PyMuPdfBaselineReader,
)
from tagged_pdf_extractor.infrastructure.pypdf_reader import TaggedPdfReader
from tagged_pdf_extractor.infrastructure.xml_writer import decode_data_element

from .acceptance_support import require_sample


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
_ZA_NUMBERED_HEADINGS = (
    ("01", "Initial Setup"),
    ("02", "Troubleshooting and Maintenance"),
    ("03", "Specifications and Other Information"),
)
_ZG_NUMBERED_HEADINGS = (
    ("01", "What's in the Box?"),
    ("02", "Connecting the TV to the One Connect Box"),
    ("03", "Initial Setup"),
    ("04", "Troubleshooting and Maintenance"),
    ("05", "Specifications and Other Information"),
    ("01", "Lieferumfang"),
    ("02", "Herstellen einer Verbindung zwischen Fernsehgerät und One Connect-Box"),
    ("03", "Anfangseinstellung"),
    ("04", "Fehlerbehebung und Wartung"),
    ("05", "Technische Daten und weitere Informationen"),
    ("01", "Contenu de la boîte"),
    ("02", "Connexion du téléviseur à la console One Connect"),
    ("03", "Configuration initiale"),
    ("04", "Résolution des problèmes et entretien"),
    ("05", "Spécifications et informations supplémentaires"),
    ("01", "Contenuto della confezione"),
    ("02", "Connessione del televisore a One Connect Box"),
    ("03", "Impostazione iniziale"),
    ("04", "Risoluzione dei problemi e manutenzione"),
    ("05", "Specifiche e altre informazioni"),
    ("01", "Inhoud van de verpakking"),
    ("02", "De tv aansluiten op de One Connect Box"),
    ("03", "Eerste instelling"),
    ("04", "Problemen oplossen en onderhoud"),
    ("05", "Technische gegevens en overige informatie"),
)


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


def _extract_report(path: Path, output: Path):
    return ExtractDocument(
        TaggedPdfReader(),
        PyMuPdfBaselineReader(),
        QualityEvaluator(),
        OutputBundleWriter(),
    ).run(path, output)


def _series_labels(report) -> list[tuple[str, ...]]:
    return [tuple(item["labels"]) for item in report.metrics["numbered_heading_series"]]


def _element_text(element: ET.Element) -> str:
    return re.sub(
        r"\s+",
        " ",
        "".join(decode_data_element(text) for text in element.iter("text")),
    ).strip()


def _assert_numbered_headings(
    report,
    semantic_xml: Path,
    semantic_markdown: Path,
    expected: tuple[tuple[str, str], ...],
    expected_series: list[tuple[str, ...]],
    *,
    heading_size: float,
    body_size: float,
) -> None:
    assert report.metrics["numbered_heading_promotion_count"] == len(expected)
    assert _series_labels(report) == expected_series
    assert report.hard_gates["has_heading"] is True
    assert report.hard_gates["numbered_heading_series_valid"] is True
    assert report.hard_gates["numbered_heading_series_counts_consistent"] is True
    assert report.hard_gates["numbered_heading_typography_valid"] is True
    assert report.status == "pass"

    evidence = [
        entry
        for entry in report.heading_hierarchy
        if entry["classification"] == "numbered_chapter_promotion"
    ]
    assert [(entry["label"], entry["title"]) for entry in evidence] == list(expected)
    for entry in evidence:
        assert entry["heading_font_size"] == heading_size
        assert entry["body_font_size"] == body_size
        assert entry["font_size_ratio"] == pytest.approx(heading_size / body_size)
        assert entry["series_index"] >= 0
        assert entry["promotion_reason"] == (
            "numbered_chapter_structure_sequence_typography"
        )

    root = ET.parse(semantic_xml).getroot()
    headings = [
        heading
        for heading in root.iter("heading")
        if heading.get("promotion-reason")
        == "numbered_chapter_structure_sequence_typography"
    ]
    assert [
        (_element_text(heading.find("label")), _element_text(heading.find("list_body")))
        for heading in headings
    ] == list(expected)

    markdown = semantic_markdown.read_text(encoding="utf-8")
    for label, title in expected:
        assert markdown.splitlines().count(f"## {label} {title}") == 1

    ordinary_labels = {
        _element_text(label)
        for item in root.iter("list_item")
        for label in item
        if label.tag == "label"
    }
    assert {"1.", "2."} <= ordinary_labels
    assert not re.search(r"(?m)^## [12]\.\s", markdown)


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


def _assert_separate_markdown_lines(
    markdown: str, values: tuple[str, ...]
) -> None:
    lines = [line.strip() for line in markdown.splitlines()]
    positions: list[int] = []
    for value in values:
        matching_lines = [
            index for index, line in enumerate(lines) if line.endswith(value)
        ]
        assert matching_lines, value
        positions.append(matching_lines[0])
    assert positions == sorted(positions)


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
    assert "TAGGED_PDF_REQUIRE_SAMPLES" in readme
    assert "그 샘플의 테스트만 독립적으로 건너뛰" in readme
    assert "Set-Location .\\samples\\tagged_pdf_xml_poc" in readme
    for variable in (
        "TAGGED_PDF_ZC_SAMPLE",
        "TAGGED_PDF_ZA_SAMPLE",
        "TAGGED_PDF_ZG_SAMPLE",
    ):
        assert f'$env:{variable} = (Resolve-Path `' in readme
    assert '"..\\SUG_RAW\\0_TV_ZC\\BN68-25100B-00_' in readme
    assert '"..\\SUG_RAW\\0_TV_ZA\\BN68-25099B-00_' in readme
    assert '"..\\SUG_RAW\\1_TV_ZG\\BN68-25448A-00_' in readme
    assert ".\\.venv\\Scripts\\python -m pytest tests -v" in readme
    assert "Set-Location C:\\Users\\bella" not in readme


def test_missing_sample_skips_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TAGGED_PDF_REQUIRE_SAMPLES", raising=False)

    with pytest.raises(pytest.skip.Exception, match="ZA tagged PDF"):
        require_sample(None, "ZA")


def test_missing_sample_fails_in_required_sample_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TAGGED_PDF_REQUIRE_SAMPLES", "1")

    with pytest.raises(pytest.fail.Exception, match="ZG tagged PDF"):
        require_sample(None, "ZG")


def test_available_sample_is_returned_in_required_sample_mode(tmp_path: Path) -> None:
    sample = tmp_path / "sample.pdf"
    sample.touch()

    assert require_sample(sample, "ZC", required=True) == sample


def test_za_retains_complete_structure_and_clean_page_text(tmp_path: Path) -> None:
    path = require_sample(_resolve_sample("ZA"), "ZA")

    document, report, artifacts = _extract_report(path, tmp_path / "za")
    _assert_common_layout_quality(document, report, {"0", "1"})
    _assert_numbered_headings(
        report,
        artifacts.semantic_xml,
        artifacts.semantic_markdown,
        _ZA_NUMBERED_HEADINGS,
        [("01", "02", "03")],
        heading_size=16.0,
        body_size=7.0,
    )


def test_zg_retains_all_pages_without_false_image_xobject_loss(tmp_path: Path) -> None:
    path = require_sample(_resolve_sample("ZG"), "ZG")

    document, report, artifacts = _extract_report(path, tmp_path / "zg")
    _assert_common_layout_quality(
        document, report, {str(page_index) for page_index in range(52)}
    )
    _assert_numbered_headings(
        report,
        artifacts.semantic_xml,
        artifacts.semantic_markdown,
        _ZG_NUMBERED_HEADINGS,
        [("01", "02", "03", "04", "05")] * 5,
        heading_size=12.0,
        body_size=6.5,
    )

    markdown = artifacts.semantic_markdown.read_text(encoding="utf-8")
    assert (
        "**Correct Disposal of This Product "
        "(Waste Electrical & Electronic Equipment)**"
    ) in markdown
    assert "**Correct disposal of batteries in this product**" in markdown
    assert markdown.count(
        "(Applicable in countries with separate collection systems)"
    ) == 2
    assert "## Correct Disposal" not in markdown

    class_one_lines = (
        "CLASS 1 LASER PRODUCT (The Frame (LS03HA) only)",
        "Caution - Invisible laser radiation when open. Do not stare into beam.",
        "Do not bend the One Connect Cable excessively. Do not cut the cable.",
        "Do not place heavy objects on the cable.",
        "Do not disassemble either of the cable connectors.",
        "Caution - Use of controls, adjustments, or the performance of procedures "
        "other than those specified herein may result in hazardous radiation exposure.",
    )
    _assert_separate_markdown_lines(markdown, class_one_lines)

    declaration_start = markdown.index("Declaration and applicable standards")
    declaration_end = markdown.index(
        "Signed for and on behalf of : Samsung", declaration_start
    )
    declaration = markdown[declaration_start:declaration_end]
    _assert_separate_markdown_lines(
        declaration,
        (
            "EMC",
            "EN 301 489-1 V2.2.3",
            "EN 301 489-17 V3.3.1",
            "Safety",
            "EN IEC 62368- 1:2020+A11:2020",
            "EN IEC 62368-3 :2020",
            "EN 62479:2010",
            "Radio",
            "EN 300 328 V2.2.2",
        ),
    )
