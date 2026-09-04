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
README = Path(__file__).parents[1] / "README.md"

_TEXT_TOKEN = re.compile(r"\[CONTROL U\+[0-9A-F]{4,6}\]|\w+|[^\w\s]")
_ORDERED_LIST_LABEL = re.compile(
    r"^(?:\(?\d+[.)]?|[A-Za-z][.)]|[ivxlcdmIVXLCDM]+[.)])$"
)
_HEADING_PREFIX = re.compile(r"^#{2,6}\s+")
_TABLE_SEPARATOR = re.compile(r"^\|(?:\s*:?-{3,}:?\s*\|)+$")
_FALLBACK_TABLE_ROW = re.compile(r"^-\s+행\s+\d+:\s*")


def _visible_source_text(value: str) -> str:
    return "".join(
        character
        if (
            ord(character) in {0x09, 0x0A, 0x0D}
            or 0x20 <= ord(character) <= 0xD7FF
            or 0xE000 <= ord(character) <= 0xFFFD
            or 0x10000 <= ord(character) <= 0x10FFFF
        )
        else f"[CONTROL U+{ord(character):04X}]"
        for character in value
    )


def _semantic_review_tokens(root: ET.Element) -> list[str]:
    suppressed_label_texts: set[ET.Element] = set()
    for item in root.iter("list_item"):
        direct_labels = [child for child in item if child.tag == "label"]
        for index, label in enumerate(direct_labels):
            label_text = re.sub(
                r"\s+",
                " ",
                "".join(
                    _visible_source_text(decode_data_element(text))
                    for text in label.iter("text")
                ),
            ).strip()
            if index > 0 or not _ORDERED_LIST_LABEL.fullmatch(label_text):
                suppressed_label_texts.update(label.iter("text"))

    return [
        token
        for element in root.iter("text")
        if element not in suppressed_label_texts
        for token in _TEXT_TOKEN.findall(
            _visible_source_text(decode_data_element(element))
        )
    ]


def _markdown_text_tokens(markdown: str) -> list[str]:
    _, _, body = markdown.partition("\n\n")
    _, separator, body = body.partition("\n\n")
    assert separator, "Markdown reviewer header must be separated from document text"

    source_lines: list[str] = []
    for line in body.splitlines():
        value = line.lstrip()
        if not value or value == "[그림: 텍스트 없음]":
            continue
        if _TABLE_SEPARATOR.fullmatch(value):
            continue
        if value.startswith("|") and value.endswith("|"):
            value = re.sub(r"(?<!\\)\|", " ", value[1:-1])
        value = value.replace(r"\|", "|").strip()
        value = _FALLBACK_TABLE_ROW.sub("", value)
        if value.startswith("- "):
            value = value[2:]
        value = _HEADING_PREFIX.sub("", value)
        if value.startswith("\\"):
            value = value[1:]
        source_lines.append(value)
    return _TEXT_TOKEN.findall("\n".join(source_lines))


def _candidate_heading_lines(markdown: str) -> Counter[tuple[str, str]]:
    return Counter(re.findall(r"(?m)^(#{2,6})\s+(.+?)\s*$", markdown))


def _assert_candidate_headings(
    markdown: str, expected: Counter[tuple[str, str]]
) -> Counter[tuple[str, str]]:
    actual = _candidate_heading_lines(markdown)
    assert actual == expected, "Markdown candidate headings must match the report"
    return actual


def _touch_sample(root: Path) -> Path:
    sample = root / _SAMPLE_RELATIVE_PATH
    sample.parent.mkdir(parents=True)
    sample.touch()
    return sample


def test_readme_prioritizes_markdown_and_explains_audit_artifacts() -> None:
    readme = README.read_text(encoding="utf-8")
    artifact_names = (
        "semantic_document.md",
        "semantic_document.xml",
        "raw_structure.xml",
        "extraction_report.json",
    )

    assert all(name in readme for name in artifact_names)
    assert [readme.index(name) for name in artifact_names] == sorted(
        readme.index(name) for name in artifact_names
    )
    assert "source-role heading 후보" in readme
    assert "검증된 표준 PDF heading이 아닙니다" in readme
    assert "눈에 보이는 원본 추출 결함" in readme
    assert "XML과 JSON은 감사 근거" in readme
    assert "--overwrite" in readme
    assert "동시 읽기는 지원하지 않습니다" in readme
    assert "추출 명령이 완전히 종료된 뒤" in readme
    assert "파일을 열기 직전과 읽은 직후" not in readme
    assert "수동 검토" in readme


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
    assert report.hard_gates["resolved_references"] is True
    assert report.hard_gates["no_known_text_loss"] is True
    assert report.hard_gates["special_character_counts_preserved"] is True
    assert report.status == "fail"
    assert validation.semantic_join_decisions == report.join_decisions

    output = tmp_path / "result"
    artifacts = OutputBundleWriter().write(document, report, output)
    raw_root = ET.parse(artifacts.raw_xml).getroot()
    semantic_root = ET.parse(artifacts.semantic_xml).getroot()
    report_data = json.loads(artifacts.report_json.read_text(encoding="utf-8"))
    assert artifacts.semantic_markdown.is_file()
    markdown = artifacts.semantic_markdown.read_text(encoding="utf-8")
    assert markdown.strip()

    raw_source_roles = {
        element.attrib["source-role"] for element in raw_root.iter("element")
    }
    assert expected_custom_headings <= raw_source_roles
    assert report_data["metrics"]["element_count"] == 1_842
    assert report_data["metrics"]["fragment_count"] == 1_938
    page_quality = report_data["metrics"]["text_quality_by_page"]
    assert list(page_quality) == ["0", "1"]
    # The known ZC source places ENG fragments on PDF page index 0.
    assert page_quality["0"] == {
        "fragment_count": 947,
        "character_count": 21_978,
        "forbidden_xml_control_count": 0,
    }
    # The known ZC source places C-FRA fragments on PDF page index 1.
    assert page_quality["1"]["fragment_count"] == 991
    assert page_quality["1"]["character_count"] > 0
    assert page_quality["1"]["forbidden_xml_control_count"] == 0
    assert report_data["metrics"]["heading_count"] == 0
    assert report_data["metrics"]["body_count"] == 1_410
    assert report_data["metrics"]["unknown_role_count"] == 0
    assert report_data["metrics"]["unresolved_mcid_count"] == 0
    assert report_data["metrics"]["unresolved_page_reference_count"] == 0
    assert report_data["metrics"]["unsupported_objr_count"] == 0
    assert report_data["metrics"]["unresolved_reference_count"] == 0
    assert report_data["metrics"]["extraction_loss_diagnostic_total"] == 0
    assert report_data["join_decisions"] == list(report.join_decisions)
    assert report_data["source_path"] == str(PDF)
    assert report_data["language"] == document.language == "ko"
    assert report_data["marked"] is True
    assert report_data["role_map"] == [list(item) for item in document.role_map]
    assert report_data["source_role_counts"] == dict(sorted(source_roles.items()))
    candidate_entries = [
        entry
        for entry in report_data["heading_hierarchy"]
        if entry["classification"] == "source_role_candidate"
    ]
    assert len(candidate_entries) == 38
    heading_candidates = {
        entry["source_role"]
        for entry in candidate_entries
    }
    assert expected_custom_headings <= heading_candidates
    assert len(report_data["heading_hierarchy"]) == 38
    candidate_texts = {
        entry["joined_text"].strip()
        for entry in report_data["heading_hierarchy"]
    }
    assert {
        "Troubleshooting",
        "Specifications",
        "Dépannage",
        "Spécifications",
    } <= candidate_texts
    assert all(
        entry["semantic_role"] == "paragraph"
        for entry in report_data["heading_hierarchy"]
    )
    expected_headings = Counter(
        (
            "#" * min(max(1, int(entry["level"] or 1)) + 1, 6),
            re.sub(r"\s+", " ", entry["joined_text"]).strip(),
        )
        for entry in candidate_entries
    )
    rendered_headings = _assert_candidate_headings(markdown, expected_headings)
    assert sum(rendered_headings.values()) == 38
    rendered_heading_texts = {text for _, text in rendered_headings}
    assert {
        "Before Reading This Simple User Guide",
        "Troubleshooting",
        "Specifications",
        "Dépannage",
        "Spécifications",
    } <= rendered_heading_texts
    cover_titles = [
        entry
        for entry in report_data["heading_hierarchy"]
        if entry["source_role"] == "Cover_Title"
    ]
    assert len(cover_titles) == 2
    for entry in cover_titles:
        cover_text = re.sub(r"\s+", " ", entry["joined_text"]).strip()
        assert rendered_headings[("##", cover_text)] == 1

    indented_heading = markdown.replace(
        "## Before Reading This Simple User Guide",
        "    ## Before Reading This Simple User Guide",
        1,
    )
    assert _markdown_text_tokens(indented_heading) == _semantic_review_tokens(
        semantic_root
    )
    with pytest.raises(
        AssertionError, match="candidate headings must match the report"
    ):
        _assert_candidate_headings(indented_heading, expected_headings)

    assert (
        "( > left directional button > Settings > Support > Tips and User "
        "Guides > Open User Guide)"
    ) in markdown
    assert report_data["metrics"]["forbidden_xml_control_count"] == 0
    assert report_data["metrics"]["forbidden_xml_control_field_count"] == 0
    assert "[CONTROL U+" not in markdown
    assert "\u0141" not in markdown
    assert "\u0152" not in markdown

    semantic_labels = {
        re.sub(
            r"\s+",
            " ",
            "".join(
                decode_data_element(text) for text in label.iter("text")
            ),
        ).strip()
        for item in semantic_root.iter("list_item")
        for label in item
        if label.tag == "label"
    }
    # After byte-safe Type0 decoding, this sample exposes the source list glyphs
    # as bullet and en dash. Markdown suppresses them by role; XML keeps them.
    assert {"\u2022", "\u2013"} <= semantic_labels

    normalized_markdown = re.sub(r"\s+", " ", markdown)
    assert "Produit de catégorie II" in normalized_markdown
    assert (
        "Communiquez avec un centre de service homologué" in normalized_markdown
    )
    assert (
        "Pour les modèles de 82 po, vous devrez être quatre" in normalized_markdown
    )
    assert (
        "Le fait de tirer, de pousser ou de monter sur le téléviseur"
        in normalized_markdown
    )
    assert (
        "Ne jamais placer un téléviseur dans une position instable"
        in normalized_markdown
    )
    assert "Wireless One Connect uniquement" in normalized_markdown
    assert _markdown_text_tokens(markdown) == _semantic_review_tokens(
        semantic_root
    )
    assert markdown.index("Before Reading This Simple User Guide") < markdown.index(
        "Dépannage"
    )
    assert (
        "CAUTION: TO REDUCE THE RISK OF ELECTRIC SHOCK, DO NOT REMOVE COVER "
        "(OR BACK)."
    ) in markdown
    assert (
        "Do not overload wall outlets, extension cords, or adapters beyond "
        "their voltage and capacity."
    ) in markdown
    special = report_data["metrics"]["special_characters"]
    assert special[">"] == {"tagged": 54, "baseline": 54, "count_preserved": True}
    assert special["/"] == {"tagged": 72, "baseline": 72, "count_preserved": True}
    assert special[":"] == {"tagged": 60, "baseline": 60, "count_preserved": True}
    assert special["["] == {"tagged": 2, "baseline": 2, "count_preserved": True}
    assert special["]"] == {"tagged": 2, "baseline": 2, "count_preserved": True}
    assert special["("] == {"tagged": 83, "baseline": 83, "count_preserved": True}
    assert special[")"] == {"tagged": 83, "baseline": 83, "count_preserved": True}

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
