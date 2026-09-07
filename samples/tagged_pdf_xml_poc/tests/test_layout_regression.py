import os
import re
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from tagged_pdf_extractor.application.evaluate_quality import QualityEvaluator
from tagged_pdf_extractor.application.extract_document import ExtractDocument
from tagged_pdf_extractor.domain.readability_formatting import (
    verified_subtitle_linked_body_paths,
)
from tagged_pdf_extractor.infrastructure.output_bundle import OutputBundleWriter
from tagged_pdf_extractor.infrastructure.pymupdf_baseline import (
    PyMuPdfBaselineReader,
)
from tagged_pdf_extractor.infrastructure.pypdf_reader import TaggedPdfReader
from tagged_pdf_extractor.infrastructure.xml_writer import decode_data_element

from .acceptance_support import require_sample
from .readability_assertions import (
    assert_inline_icon_evidence_matches_detector as _assert_inline_icon_evidence_matches_detector,
    assert_profile_readability_controls as _assert_profile_readability_controls,
    assert_raw_has_no_readability_display_attributes as _assert_raw_has_no_readability_display_attributes,
    assert_sentence_breaks_do_not_create_source_units as _assert_sentence_breaks_do_not_create_source_units,
)


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
    "XY": (
        "TAGGED_PDF_XY_SAMPLE",
        Path("samples")
        / "SUG_RAW"
        / "TV_XY"
        / "BN68-25031B-00_SUG_Y26 TV ALL_XY_ENG_251229.0.pdf",
    ),
    "KR": (
        "TAGGED_PDF_KR_SAMPLE",
        Path("samples")
        / "SUG_RAW"
        / "TV_KR"
        / "BN68-25108A-00_SUG_Y26 TV ALL_KR_KOR_251218.0.pdf",
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
_XY_NUMBERED_HEADINGS = (
    ("01", "What's in the Box?"),
    ("02", "Initial Setup"),
    ("03", "Troubleshooting and Maintenance"),
    ("04", "Specifications and Other Information"),
)
_KR_NUMBERED_HEADINGS = (
    ("01", "구성품 확인하기"),
    ("02", "초기 설정하기"),
    ("03", "문제해결 및 관리하기"),
    ("04", "사양 및 정보"),
)
_ZG_FORM_HEADINGS = (
    "Declaration of Conformity",
    "Konformitätserklärung",
    "Déclaration de conformité",
    "Dichiarazione di Conformità",
    "Verklaring van overeenstemming",
)
_ZG_FORM_LABEL_GROUPS = (
    (
        "Manufacturer",
        "Product Details",
        "Declaration and applicable standards",
        "EMC",
        "Safety",
        "Radio",
        "Signed for and on behalf of : Samsung",
    ),
    (
        "Hersteller",
        "Produktdetails",
        "Erklärung und gültige Normen",
        "EMV",
        "Sicherheit",
        "Funk",
        "Unterzeichnet für und im Namen von: Samsung",
    ),
    (
        "Fabricant",
        "Détails du produit",
        "Déclaration et normes applicables",
        "CEM",
        "Sécurité",
        "Radio",
        "Signé en nom et pour le compte de: Samsung",
    ),
    (
        "Produttore",
        "Dettagli prodotto",
        "Dichiarazione e Standard applicabili",
        "EMC",
        "Sicurezza",
        "Radio",
        "Firmato a nome e per conto di: Samsung",
    ),
    (
        "Fabrikant",
        "Productgegevens",
        "Verklaring en toepasselijke normen",
        "EMC",
        "VEILIGHEID",
        "Radio",
        "Ondertekend voor en namens: Samsung",
    ),
)
_ZG_SUBTITLE_COUNTS = Counter(
    {
        "Correct Disposal of This Product "
        "(Waste Electrical & Electronic Equipment)": 1,
        "Correct disposal of batteries in this product": 1,
        "Ordnungsgemäße Entsorgung der Batterien in diesem Gerät": 1,
        "Elimination des batteries de ce produit": 1,
        "Corretto smaltimento delle batterie del prodotto": 1,
        "Correcte verwijdering van dit product "
        "(elektrische & elektronische afvalapparatuur)": 1,
        "Correcte behandeling van een gebruikte accu uit dit product": 1,
    }
)
_ZG_SUBTITLE_LINKED_BODY_PATHS = {
    (0, 0, 6, 1),
    (0, 0, 6, 5),
    (0, 0, 12, 7),
    (0, 0, 18, 5),
    (0, 0, 24, 7),
    (0, 0, 30, 1),
    (0, 0, 30, 5),
}
_FRA_POWER_SENTENCES = (
    "Veillez à brancher correctement et complètement le cordon d'alimentation.",
    "Lorsque vous débranchez le cordon d'alimentation d'une prise murale, "
    "tirez toujours sur la fiche du cordon d'alimentation.",
    "Ne le débranchez jamais en tirant sur le cordon d'alimentation.",
    "Ne touchez pas le cordon d'alimentation si vous avez les mains mouillées.",
)
_DEU_BATTERY_SENTENCES = (
    "Diese Kennzeichnung auf der Batterie, dem Handbuch oder der Verpackung "
    "bedeutet, dass die Batterien am Ende ihrer Lebensdauer nicht im normalen "
    "Hausmüll entsorgt werden dürfen.",
    "Die Kennzeichnung mit den chemischen Symbolen „Hg“, „Cd“ oder „Pb“ "
    "bedeutet, dass die Batterie Quecksilber, Cadmium oder Blei in Mengen "
    "enthält, die die Grenzwerte der EU-Direktive 2006/66 übersteigen.",
    "Wenn Batterien nicht ordnungsgemäß entsorgt werden, können diese "
    "Substanzen die Gesundheit von Menschen oder die Umwelt gefährden.",
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


@pytest.fixture(scope="module")
def za_bundle(tmp_path_factory: pytest.TempPathFactory):
    path = require_sample(_resolve_sample("ZA"), "ZA")
    return _extract_report(path, tmp_path_factory.mktemp("layout-za") / "bundle")


@pytest.fixture(scope="module")
def zg_bundle(tmp_path_factory: pytest.TempPathFactory):
    path = require_sample(_resolve_sample("ZG"), "ZG")
    return _extract_report(path, tmp_path_factory.mktemp("layout-zg") / "bundle")


@pytest.fixture(scope="module")
def xy_bundle(tmp_path_factory: pytest.TempPathFactory):
    path = require_sample(_resolve_sample("XY"), "XY")
    return _extract_report(path, tmp_path_factory.mktemp("layout-xy") / "bundle")


@pytest.fixture(scope="module")
def kr_bundle(tmp_path_factory: pytest.TempPathFactory):
    path = require_sample(_resolve_sample("KR"), "KR")
    return _extract_report(path, tmp_path_factory.mktemp("layout-kr") / "bundle")


def _series_labels(report) -> list[tuple[str, ...]]:
    return [tuple(item["labels"]) for item in report.metrics["numbered_heading_series"]]


def _element_text(element: ET.Element) -> str:
    return re.sub(
        r"\s+",
        " ",
        "".join(decode_data_element(text) for text in element.iter("text")),
    ).strip()


def _elements_starting_with(
    root: ET.Element, tag: str, prefix: str
) -> list[ET.Element]:
    return [
        element
        for element in root.iter(tag)
        if _element_text(element).startswith(prefix)
    ]


def _normalized_markdown_line(line: str) -> str:
    return re.sub(r"\s+", " ", line.strip().removesuffix("<br>")).strip()


def _flow_text_with_inline_icons(element: ET.Element) -> str:
    parts: list[str] = []

    def visit(node: ET.Element) -> None:
        if node.tag == "figure" and node.get("display-role") == "inline-icon":
            parts.append("[아이콘]")
            return
        if node.tag == "text":
            parts.append(decode_data_element(node))
            return
        for child in node:
            visit(child)

    visit(element)
    return re.sub(r"\s+", " ", " ".join(parts)).strip()


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
    lines = [_normalized_markdown_line(line) for line in markdown.splitlines()]
    positions: list[int] = []
    for value in values:
        matching_lines = [
            index for index, line in enumerate(lines) if line.endswith(value)
        ]
        assert matching_lines, value
        positions.append(matching_lines[0])
    assert positions == sorted(positions)


def _assert_no_zg_profile_display_evidence(document, semantic_xml: Path) -> None:
    assert document.line_break_hints == ()
    assert document.text_display_hints == ()
    root = ET.parse(semantic_xml).getroot()
    for role in ("section-heading", "strong-label", "preserved-line-break"):
        assert root.find(f".//*[@display-role='{role}']") is None


def _assert_zg_sentence_readability(
    root: ET.Element, markdown: str
) -> None:
    fra_bodies = _elements_starting_with(
        root, "list_body", _FRA_POWER_SENTENCES[0]
    )
    assert len(fra_bodies) == 1
    parent_by_child = {
        child: parent for parent in root.iter() for child in parent
    }
    assert parent_by_child[fra_bodies[0]].tag == "list_item"
    fra_breaks = fra_bodies[0].findall(
        ".//text[@display-role='sentence-break-source']"
    )
    assert sum(
        len(text.attrib["sentence-break-offsets"].split(","))
        for text in fra_breaks
    ) == 3

    markdown_lines = markdown.splitlines()
    fra_start = next(
        index
        for index, line in enumerate(markdown_lines)
        if _normalized_markdown_line(line).startswith("- " + _FRA_POWER_SENTENCES[0])
    )
    fra_visual_lines = [
        _normalized_markdown_line(line).removeprefix("- ")
        for line in markdown_lines[fra_start : fra_start + 4]
    ]
    assert tuple(fra_visual_lines) == _FRA_POWER_SENTENCES

    deu_paragraphs = _elements_starting_with(
        root, "paragraph", _DEU_BATTERY_SENTENCES[0]
    )
    assert len(deu_paragraphs) == 1
    deu_breaks = deu_paragraphs[0].findall(
        ".//text[@display-role='sentence-break-source']"
    )
    assert sum(
        len(text.attrib["sentence-break-offsets"].split(","))
        for text in deu_breaks
    ) == 2
    deu_start = next(
        index
        for index, line in enumerate(markdown_lines)
        if _normalized_markdown_line(line).startswith(
            _DEU_BATTERY_SENTENCES[0]
        )
    )
    deu_lines = markdown_lines[deu_start : deu_start + 3]
    assert deu_lines[0].endswith("<br>")
    assert deu_lines[1].endswith("<br>")
    deu_visual_lines = tuple(_normalized_markdown_line(line) for line in deu_lines)
    assert deu_visual_lines == _DEU_BATTERY_SENTENCES


def _assert_zg_inline_osd_icons(root: ET.Element, markdown: str) -> None:
    osd_flows = [
        element
        for element in root.iter("paragraph")
        if _element_text(element).startswith(">")
        and _element_text(element).count(">") == 6
        and len(
            element.findall(".//figure[@display-role='inline-icon']")
        ) == 2
    ]
    assert len(osd_flows) == 5
    assert sum(
        len(flow.findall(".//figure[@display-role='inline-icon']"))
        for flow in osd_flows
    ) == 10

    normalized_markdown = re.sub(r"\s+", " ", markdown)
    for flow in osd_flows:
        expected = _flow_text_with_inline_icons(flow)
        assert expected.count("[아이콘]") == 2
        assert expected in normalized_markdown


def _assert_zg_note_markers_and_plain_model_labels(
    root: ET.Element, markdown: str
) -> None:
    fra_note_items = _elements_starting_with(
        root, "list_item", "※ Cette adresse"
    )
    assert len(fra_note_items) == 2
    for item in fra_note_items:
        direct_labels = [child for child in item if child.tag == "label"]
        direct_bodies = [child for child in item if child.tag == "list_body"]
        assert len(direct_labels) == len(direct_bodies) == 1
        assert _element_text(direct_labels[0]) == "※"
        assert _element_text(direct_bodies[0]).startswith("Cette adresse")
    fra_note_lines = [
        line.strip()
        for line in markdown.splitlines()
        if line.strip().startswith("※ Cette adresse")
    ]
    assert len(fra_note_lines) == len(fra_note_items)
    assert all(line.count("※") == 1 for line in fra_note_lines)
    assert "- ※ Cette adresse" not in markdown
    assert "UK ※ 2025-10-31" in re.sub(r"\s+", " ", markdown)

    bracketed_model_labels = (
        "[QN990H]",
        "[R9*H/R8*H/S9*H/S8*H/QN8*H]",
        "[QN7*H/QN1EH/M9*H/M8*H/M7*H/M1EH/U9***H/U8***H/ U7***H]",
        "[The Frame (LS03HA, LS03HE)]",
        "[The Frame (LS03HW)]",
    )
    semantic_text = _element_text(root)
    markdown_lines = [line.strip() for line in markdown.splitlines()]
    for label in bracketed_model_labels:
        assert label in semantic_text
        assert label in markdown_lines
        assert f"\\{label[0]}{label[1:-1]}\\{label[-1]}" not in markdown
        assert f"**{label}**" not in markdown


def _assert_zg_subtitles(root: ET.Element, markdown: str) -> None:
    semantic_subtitles = Counter(
        _element_text(element)
        for element in root.findall(".//*[@display-role='subtitle']")
    )
    assert semantic_subtitles == _ZG_SUBTITLE_COUNTS, (
        "semantic subtitle evidence must preserve all seven reviewed ZG subtitles"
    )

    markdown_subtitles = Counter(
        line.strip()[2:-2]
        for line in markdown.splitlines()
        if line.strip().startswith("**")
        and line.strip().endswith("**")
        and line.strip()[2:-2] in _ZG_SUBTITLE_COUNTS
    )
    assert markdown_subtitles == _ZG_SUBTITLE_COUNTS, (
        "Markdown must render every reviewed ZG subtitle exactly once"
    )


def _preserved_line_break_pairs(root: ET.Element) -> list[tuple[str, str]]:
    parent_by_child = {
        child: parent for parent in root.iter() for child in parent
    }
    pairs: list[tuple[str, str]] = []
    for boundary in root.findall(".//*[@display-role='preserved-line-break']"):
        paragraph = parent_by_child.get(boundary)
        while paragraph is not None and paragraph.tag != "paragraph":
            paragraph = parent_by_child.get(paragraph)
        assert paragraph is not None
        descendants = list(paragraph.iter())
        boundary_index = descendants.index(boundary)
        before = [
            _element_text(item)
            for item in descendants[:boundary_index]
            if item.tag == "text" and _element_text(item)
        ]
        after = [
            _element_text(item)
            for item in descendants[boundary_index + 1 :]
            if item.tag == "text" and _element_text(item)
        ]
        assert before and after
        pairs.append((before[-1], after[0]))
    return pairs


def _assert_preserved_breaks_are_physical_markdown_lines(
    root: ET.Element, markdown: str
) -> None:
    pairs = _preserved_line_break_pairs(root)
    assert len(pairs) == 90
    lines = [re.sub(r"\s+", " ", line.strip()) for line in markdown.splitlines()]
    cursor = 0
    observed_before: list[str] = []
    for before, after in pairs:
        matching_index = next(
            (
                index
                for index in range(cursor, len(lines))
                if lines[index] == before
            ),
            None,
        )
        assert matching_index is not None, before
        next_nonempty = next(
            (
                line
                for line in lines[matching_index + 1 :]
                if line
            ),
            None,
        )
        assert next_nonempty == after
        observed_before.append(lines[matching_index])
        cursor = matching_index + 1

    assert observed_before == [before for before, _ in pairs]
    assert all(before.endswith(",") for before in observed_before)


def _assert_form_labels_and_details_remain_separate(
    root: ET.Element, markdown: str
) -> None:
    elements = list(root.iter())
    element_index = {element: index for index, element in enumerate(elements)}
    pairs: list[tuple[str, str]] = []
    for label in root.findall(".//*[@display-role='strong-label']"):
        following_paragraph = next(
            (
                candidate
                for candidate in elements[element_index[label] + 1 :]
                if candidate.tag == "paragraph"
                and _element_text(candidate)
            ),
            None,
        )
        assert following_paragraph is not None
        assert following_paragraph.get("display-role") is None
        pairs.append((_element_text(label), _element_text(following_paragraph)))

    lines = [line.strip() for line in markdown.splitlines()]
    cursor = 0
    for label, detail in pairs:
        label_index = next(
            index
            for index in range(cursor, len(lines))
            if lines[index] == f"**{label}**"
        )
        detail_index = next(
            index
            for index in range(label_index + 1, len(lines))
            if re.sub(r"\s+", "", lines[index]) == re.sub(r"\s+", "", detail)
        )
        assert detail_index > label_index
        cursor = detail_index + 1


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


def test_zg_subtitle_gate_rejects_a_missing_localized_subtitle() -> None:
    root = ET.Element("document")
    for subtitle in _ZG_SUBTITLE_COUNTS:
        paragraph = ET.SubElement(root, "paragraph", {"display-role": "subtitle"})
        ET.SubElement(paragraph, "text").text = subtitle
    localized = next(
        paragraph
        for paragraph in root.findall(".//*[@display-role='subtitle']")
        if _element_text(paragraph).startswith("Ordnungsgemäße")
    )
    root.remove(localized)
    markdown = "\n".join(f"**{subtitle}**" for subtitle in _ZG_SUBTITLE_COUNTS)

    with pytest.raises(AssertionError, match="semantic subtitle evidence"):
        _assert_zg_subtitles(root, markdown)


def test_readme_documents_sample_overrides_and_independent_skips() -> None:
    readme = _README.read_text(encoding="utf-8")

    assert "TAGGED_PDF_ZC_SAMPLE" in readme
    assert "TAGGED_PDF_ZA_SAMPLE" in readme
    assert "TAGGED_PDF_ZG_SAMPLE" in readme
    assert "TAGGED_PDF_XY_SAMPLE" in readme
    assert "TAGGED_PDF_KR_SAMPLE" in readme
    assert "TAGGED_PDF_REQUIRE_SAMPLES" in readme
    assert "그 샘플의 테스트만 독립적으로 건너뛰" in readme
    assert "Set-Location .\\samples\\tagged_pdf_xml_poc" in readme
    required_command = readme.split(
        "# Current mandatory gate: ZC, ZG, and KR only.", 1
    )[1].split("```", 1)[0]
    for variable in (
        "TAGGED_PDF_ZC_SAMPLE",
        "TAGGED_PDF_ZG_SAMPLE",
        "TAGGED_PDF_KR_SAMPLE",
    ):
        assert f'$env:{variable} = (Resolve-Path `' in required_command
    assert "TAGGED_PDF_ZA_SAMPLE" not in required_command
    assert "TAGGED_PDF_XY_SAMPLE" not in required_command
    assert '"..\\SUG_RAW\\0_TV_ZC\\BN68-25100B-00_' in readme
    assert '"..\\SUG_RAW\\1_TV_ZG\\BN68-25448A-00_' in readme
    assert '"..\\SUG_RAW\\1_TV_KR\\BN68-25108A-00_' in readme
    assert (
        "--deselect tests/test_layout_regression.py::"
        "test_za_retains_complete_structure_and_clean_page_text"
    ) in required_command
    assert (
        "--deselect tests/test_layout_regression.py::"
        "test_xy_retains_structure_without_zg_display_rules"
    ) in required_command
    assert "ZA/XY" in readme and "optional" in readme
    assert "Set-Location C:\\Users\\bella" not in readme


def test_readme_documents_semantic_markdown_readability_contract() -> None:
    readme = _README.read_text(encoding="utf-8")

    assert "같은 원본 구조 단위 안의 표시용 문장 경계" in readme
    assert "이름을 판별한 결과가 아닙니다" in readme
    assert "주변 문장, 페이지, BBox, 상대 크기" in readme
    assert "standalone, 큰 그림 또는 판별이 불확실한 figure" in readme
    assert "`※`는 PDF에 실제로 존재하는 의미 있는 source label" in readme
    assert "`Ł`, `Œ`" in readme
    assert "편집기의 구문 강조 색상" in readme
    assert "PDF 원본의 글자색이나 스타일을 뜻하지 않습니다" in readme


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


@pytest.mark.parametrize(
    ("sample", "environment_name", "relative_path"),
    (
        (
            "XY",
            "TAGGED_PDF_XY_SAMPLE",
            Path("samples")
            / "SUG_RAW"
            / "TV_XY"
            / "BN68-25031B-00_SUG_Y26 TV ALL_XY_ENG_251229.0.pdf",
        ),
        (
            "KR",
            "TAGGED_PDF_KR_SAMPLE",
            Path("samples")
            / "SUG_RAW"
            / "TV_KR"
            / "BN68-25108A-00_SUG_Y26 TV ALL_KR_KOR_251218.0.pdf",
        ),
    ),
)
def test_xy_and_kr_sample_resolver_searches_repository_and_environment(
    sample: str,
    environment_name: str,
    relative_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(environment_name, raising=False)
    repository = tmp_path / "repository"
    repository_sample = repository / relative_path
    repository_sample.parent.mkdir(parents=True)
    repository_sample.touch()

    assert _resolve_sample(
        sample,
        anchor=repository / "samples/tagged_pdf_xml_poc/tests/test.py",
        home=tmp_path / "empty-home",
    ) == repository_sample

    environment_sample = tmp_path / "external" / f"{sample}.pdf"
    environment_sample.parent.mkdir()
    environment_sample.touch()
    monkeypatch.setenv(environment_name, str(environment_sample))

    assert _resolve_sample(
        sample,
        anchor=repository / "samples/tagged_pdf_xml_poc/tests/test.py",
        home=tmp_path / "empty-home",
    ) == environment_sample

    monkeypatch.delenv(environment_name)
    home = tmp_path / "home"
    home_sample = home / "image-extractor" / relative_path
    home_sample.parent.mkdir(parents=True)
    home_sample.touch()
    assert _resolve_sample(
        sample,
        anchor=tmp_path / "elsewhere/tests/test.py",
        home=home,
    ) == home_sample


@pytest.mark.parametrize("sample", ("XY", "KR"))
def test_xy_and_kr_missing_samples_fail_in_required_mode(
    sample: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TAGGED_PDF_REQUIRE_SAMPLES", "1")
    monkeypatch.delenv(f"TAGGED_PDF_{sample}_SAMPLE", raising=False)

    with pytest.raises(pytest.fail.Exception, match=rf"{sample} tagged PDF"):
        require_sample(
            _resolve_sample(
                sample,
                anchor=tmp_path / "repository/tests/test.py",
                home=tmp_path / "empty-home",
            ),
            sample,
        )


def test_za_retains_complete_structure_and_clean_page_text(za_bundle) -> None:
    document, report, artifacts = za_bundle
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
    _assert_no_zg_profile_display_evidence(document, artifacts.semantic_xml)
    _assert_profile_readability_controls(document, report, artifacts)


def test_zg_retains_all_pages_without_false_image_xobject_loss(zg_bundle) -> None:
    document, report, artifacts = zg_bundle
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

    assert len(document.line_break_hints) == 90
    assert Counter(
        hint.display_role for hint in document.text_display_hints
    ) == {"section_heading": 10, "strong_label": 70}
    subtitle_body_paths = verified_subtitle_linked_body_paths(document)
    assert set(subtitle_body_paths) == _ZG_SUBTITLE_LINKED_BODY_PATHS
    subtitle_body_hints = {
        body_path: tuple(
            hint
            for hint in document.sentence_break_hints
            if hint.child_path[: len(body_path)] == body_path
        )
        for body_path in subtitle_body_paths
    }
    assert all(subtitle_body_hints.values())
    assert sum(
        len(hint.offsets)
        for hints in subtitle_body_hints.values()
        for hint in hints
    ) == 11
    semantic_root = ET.parse(artifacts.semantic_xml).getroot()
    assert len(
        semantic_root.findall(".//*[@display-role='preserved-line-break']")
    ) == 90
    assert len(semantic_root.findall(".//*[@display-role='section-heading']")) == 10
    assert len(semantic_root.findall(".//*[@display-role='strong-label']")) == 70

    markdown = artifacts.semantic_markdown.read_text(encoding="utf-8")
    _assert_raw_has_no_readability_display_attributes(artifacts.raw_xml)
    _assert_sentence_breaks_do_not_create_source_units(
        document, report, semantic_root
    )
    _assert_inline_icon_evidence_matches_detector(
        document, semantic_root, markdown
    )
    _assert_zg_sentence_readability(semantic_root, markdown)
    _assert_zg_inline_osd_icons(semantic_root, markdown)
    _assert_zg_note_markers_and_plain_model_labels(semantic_root, markdown)
    _assert_preserved_breaks_are_physical_markdown_lines(semantic_root, markdown)
    _assert_zg_subtitles(semantic_root, markdown)

    expected_form_headings = Counter(
        heading for heading in _ZG_FORM_HEADINGS for _ in range(2)
    )
    semantic_form_headings = Counter(
        _element_text(element)
        for element in semantic_root.findall(
            ".//*[@display-role='section-heading']"
        )
    )
    markdown_form_headings = Counter(
        line.removeprefix("## ")
        for line in markdown.splitlines()
        if line.startswith("## ") and line.removeprefix("## ") in _ZG_FORM_HEADINGS
    )
    assert semantic_form_headings == expected_form_headings
    assert markdown_form_headings == expected_form_headings

    expected_form_labels = Counter(
        label
        for labels in _ZG_FORM_LABEL_GROUPS
        for label in labels
        for _ in range(2)
    )
    semantic_form_labels = Counter(
        _element_text(element)
        for element in semantic_root.findall(".//*[@display-role='strong-label']")
    )
    markdown_strong_only_lines = Counter(
        line.strip()[2:-2]
        for line in markdown.splitlines()
        if line.strip().startswith("**") and line.strip().endswith("**")
    )
    assert semantic_form_labels == expected_form_labels
    assert Counter(
        {
            label: markdown_strong_only_lines[label]
            for label in expected_form_labels
        }
    ) == expected_form_labels
    _assert_form_labels_and_details_remain_separate(semantic_root, markdown)

    assert markdown.count(
        "(Applicable in countries with separate collection systems)"
    ) == 2
    assert "## Correct Disposal" not in markdown

    class_one_lines = (
        "CLASS 1 LASER PRODUCT (The Frame (LS03HA) only)",
        "Caution - Invisible laser radiation when open.",
        "Do not stare into beam.",
        "Do not bend the One Connect Cable excessively.",
        "Do not cut the cable.",
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
            "**EMC**",
            "EN 301 489-1 V2.2.3",
            "EN 301 489-17 V3.3.1",
            "**Safety**",
            "EN IEC 62368- 1:2020+A11:2020",
            "EN IEC 62368-3 :2020",
            "EN 62479:2010",
            "**Radio**",
            "EN 300 328 V2.2.2",
        ),
    )


def _assert_non_zg_profile_bundle(
    bundle,
    expected_headings: tuple[tuple[str, str], ...],
) -> None:
    document, report, artifacts = bundle
    _assert_common_layout_quality(document, report, {"0", "1"})
    _assert_numbered_headings(
        report,
        artifacts.semantic_xml,
        artifacts.semantic_markdown,
        expected_headings,
        [("01", "02", "03", "04")],
        heading_size=16.0,
        body_size=7.0,
    )
    _assert_no_zg_profile_display_evidence(document, artifacts.semantic_xml)
    assert report.status == "pass"
    assert artifacts.raw_xml.is_file()
    assert artifacts.semantic_xml.is_file()
    assert artifacts.report_json.is_file()
    assert artifacts.semantic_markdown.is_file()
    assert artifacts.semantic_markdown.read_text(encoding="utf-8").strip()


def test_xy_retains_structure_without_zg_display_rules(xy_bundle) -> None:
    _assert_non_zg_profile_bundle(xy_bundle, _XY_NUMBERED_HEADINGS)
    document, report, artifacts = xy_bundle
    _assert_profile_readability_controls(document, report, artifacts)


def test_kr_retains_structure_without_zg_display_rules(kr_bundle) -> None:
    _assert_non_zg_profile_bundle(kr_bundle, _KR_NUMBERED_HEADINGS)
    document, report, artifacts = kr_bundle
    _assert_profile_readability_controls(document, report, artifacts)


def test_form_detection_runtime_has_no_title_or_model_dictionary() -> None:
    domain = (
        Path(__file__).parents[1]
        / "src"
        / "tagged_pdf_extractor"
        / "domain"
    )
    runtime = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(domain.glob("*.py"))
    )

    forbidden_literals = (
        *_ZG_FORM_HEADINGS,
        *(label for labels in _ZG_FORM_LABEL_GROUPS for label in labels),
        "QN990H",
        "LS03HA",
    )
    assert not [literal for literal in forbidden_literals if literal in runtime]
