import json
import os
import re
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from tagged_pdf_extractor.application.evaluate_quality import QualityEvaluator
from tagged_pdf_extractor.application.extract_document import ExtractDocument
from tagged_pdf_extractor.domain.models import ContentFragment, StructureElement
from tagged_pdf_extractor.infrastructure.output_bundle import OutputBundleWriter
from tagged_pdf_extractor.infrastructure.pymupdf_baseline import PyMuPdfBaselineReader
from tagged_pdf_extractor.infrastructure.pypdf_reader import TaggedPdfReader
from tagged_pdf_extractor.infrastructure.xml_writer import decode_data_element

from .acceptance_support import require_sample
from .readability_assertions import assert_profile_readability_controls


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

_ZC_NUMBERED_HEADINGS = (
    ("01", "Package Content"),
    ("02", "Initial Setup"),
    ("03", "Troubleshooting and Maintenance"),
    ("04", "Specifications and Other Information"),
    ("01", "Contenu de la boîte"),
    ("02", "Configuration initiale"),
    ("03", "Dépannage et entretien"),
    ("04", "Spécifications et autres renseignements"),
)

_TEXT_TOKEN = re.compile(r"\[CONTROL U\+[0-9A-F]{4,6}\]|\w+|[^\w\s]")
_ZC_NONORDERED_LABEL_GLYPHS = frozenset({"\u2022", "\u2013"})
_HEADING_PREFIX = re.compile(r"^#{2,6}\s+")
_TABLE_SEPARATOR = re.compile(r"^\|(?:\s*:?-{3,}:?\s*\|)+$")
_COMPLEX_TABLE_MARKER = re.compile(r"^-\s+(?:행|열)\s+\d+:\s*$")
_EMPTY_TABLE_CELL_MARKER = "[빈 셀]"
_ESCAPED_DECIMAL_PREFIX = re.compile(r"^([0-9]{1,9})\\([.)])(?=\s)")
_BLOCK_PREFIX = re.compile(r"^(?:#{1,6}\s|>|[-+*]\s)")
_FENCE_PREFIX = re.compile(r"^(?:`{3,}|~{3,})")
_THEMATIC_BREAK = re.compile(r"^(?:(?:\*\s*){3,}|(?:-\s*){3,}|(?:_\s*){3,})$")
_RAW_HTML_PREFIX = re.compile(
    r"^<(?:!--|[!?]|/?[A-Za-z][A-Za-z0-9-]*(?=[\s/>]))"
)


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
    source_text = {
        element: _visible_source_text(decode_data_element(element))
        for element in root.iter("text")
    }
    for display_token in ("<br>", "[아이콘]"):
        assert all(
            display_token not in value for value in source_text.values()
        ), (
            "Semantic XML source text contains Markdown display token "
            f"{display_token!r}"
        )

    suppressed_label_texts: set[ET.Element] = set()
    for item in root.iter("list_item"):
        direct_labels = [child for child in item if child.tag == "label"]
        for label in direct_labels:
            label_text = re.sub(
                r"\s+",
                " ",
                "".join(
                    source_text[text]
                    for text in label.iter("text")
                ),
            ).strip()
            if label_text in _ZC_NONORDERED_LABEL_GLYPHS:
                suppressed_label_texts.update(label.iter("text"))

    return [
        token
        for element in root.iter("text")
        if element not in suppressed_label_texts
        for token in _TEXT_TOKEN.findall(
            source_text[element]
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
        if _COMPLEX_TABLE_MARKER.fullmatch(value):
            continue
        if value == _EMPTY_TABLE_CELL_MARKER:
            continue
        if _TABLE_SEPARATOR.fullmatch(value):
            continue
        if value.startswith("|") and value.endswith("|"):
            value = re.sub(r"(?<!\\)\|", " ", value[1:-1])
        value = value.replace(r"\|", "|").strip()
        value = (
            value.replace("<br>", " ")
            .replace(r"\[아이콘]", " ")
            .replace("[아이콘]", " ")
        )
        if value.startswith("- "):
            value = value[2:]
        value = _HEADING_PREFIX.sub("", value)
        value = _undo_writer_prefix_escape(value)
        source_lines.append(value)
    return _TEXT_TOKEN.findall("\n".join(source_lines))


def _undo_writer_prefix_escape(value: str) -> str:
    decimal = _ESCAPED_DECIMAL_PREFIX.match(value)
    if decimal is not None:
        return f"{decimal.group(1)}{decimal.group(2)}{value[decimal.end():]}"
    if not value.startswith("\\"):
        return value

    source = value[1:]
    if (
        _BLOCK_PREFIX.match(source)
        or _FENCE_PREFIX.match(source)
        or _THEMATIC_BREAK.fullmatch(source)
        or _RAW_HTML_PREFIX.match(source)
        or _starts_reference_definition(source)
    ):
        return source
    return value


def _starts_reference_definition(value: str) -> bool:
    if not value.startswith("["):
        return False
    index = 1
    while index < len(value):
        character = value[index]
        if character in "\r\n":
            return False
        if character == "\\":
            index += 2
            continue
        if character == "]":
            return index > 1 and value[index + 1 : index + 2] == ":"
        index += 1
    return False


def _candidate_heading_lines(markdown: str) -> Counter[tuple[str, str]]:
    return Counter(re.findall(r"(?m)^(#{2,6})\s+(.+?)\s*$", markdown))


def test_markdown_token_oracle_reverses_only_writer_prefix_escapes() -> None:
    markdown = (
        "# Header\n\n- metadata\n\n"
        "\\literal\n"
        "1\\. decimal\n"
        "\\* source asterisk\n"
    )

    assert _markdown_text_tokens(markdown) == [
        "\\",
        "literal",
        "1",
        ".",
        "decimal",
        "*",
        "source",
        "asterisk",
    ]


def test_markdown_token_oracle_ignores_only_display_break_and_icon_tokens() -> None:
    markdown = (
        "# Header\n\n- metadata\n\n"
        "First sentence.<br>\n"
        "Second \\[아이콘]: sentence.\n"
        "※ Source note\n"
    )

    assert _markdown_text_tokens(markdown) == [
        "First",
        "sentence",
        ".",
        "Second",
        ":",
        "sentence",
        ".",
        "※",
        "Source",
        "note",
    ]


@pytest.mark.parametrize("display_token", ["<br>", "[아이콘]"])
def test_semantic_token_oracle_rejects_literal_markdown_display_tokens(
    display_token: str,
) -> None:
    root = ET.fromstring(
        "<document><paragraph><text>Literal "
        + display_token.replace("<", "&lt;").replace(">", "&gt;")
        + " source</text></paragraph></document>"
    )

    with pytest.raises(AssertionError, match="display token"):
        _semantic_review_tokens(root)


def test_semantic_token_oracle_never_removes_note_marker() -> None:
    root = ET.fromstring(
        "<document><paragraph><text>※ Source note</text></paragraph></document>"
    )

    assert _semantic_review_tokens(root) == ["※", "Source", "note"]


def test_markdown_token_oracle_excludes_only_complex_table_structure_markers() -> None:
    markdown = (
        "# Header\n\n- metadata\n\n"
        "- 행 1:\n"
        "  - 열 1:\n"
        "    Source cell text\n"
        "  - 열 2:\n"
        "    [빈 셀]\n"
    )

    assert _markdown_text_tokens(markdown) == ["Source", "cell", "text"]


def test_markdown_token_oracle_preserves_source_text_similar_to_table_markers() -> None:
    markdown = (
        "# Header\n\n- metadata\n\n"
        "열 1: is source text\n"
        "행 2: is also source text\n"
        "[빈 셀] is a literal source phrase\n"
    )

    assert _markdown_text_tokens(markdown) == [
        "열",
        "1",
        ":",
        "is",
        "source",
        "text",
        "행",
        "2",
        ":",
        "is",
        "also",
        "source",
        "text",
        "[",
        "빈",
        "셀",
        "]",
        "is",
        "a",
        "literal",
        "source",
        "phrase",
    ]


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


def _decoded_text(element: ET.Element, tag: str) -> str:
    return re.sub(
        r"\s+",
        " ",
        "".join(decode_data_element(item) for item in element.iter(tag)),
    ).strip()


def _assert_raw_numbered_heading_sources(
    raw_root: ET.Element, expected: tuple[tuple[str, str], ...]
) -> None:
    observed: Counter[tuple[str, str]] = Counter()
    for item in raw_root.iter("element"):
        if item.get("source-role") != "LI":
            continue
        direct = [child for child in item if child.tag == "element"]
        labels = [child for child in direct if child.get("source-role") == "Lbl"]
        bodies = [child for child in direct if child.get("source-role") == "LBody"]
        if len(labels) == len(bodies) == 1:
            observed[(_decoded_text(labels[0], "part"), _decoded_text(bodies[0], "part"))] += 1

    assert all(observed[item] == 1 for item in expected)


def test_zc_pdf_has_recoverable_tagged_hierarchy_and_auditable_outputs(
    tmp_path: Path,
) -> None:
    pdf = require_sample(PDF, "ZC")
    output = tmp_path / "result"
    document, report, artifacts = ExtractDocument(
        TaggedPdfReader(),
        PyMuPdfBaselineReader(),
        QualityEvaluator(),
        OutputBundleWriter(),
    ).run(pdf, output)
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

    validation = OutputBundleWriter().validate(document)
    assert document.line_break_hints == ()
    assert document.text_display_hints == ()
    assert report.metrics["numbered_heading_promotion_count"] == 8
    assert [item["labels"] for item in report.metrics["numbered_heading_series"]] == [
        ["01", "02", "03", "04"],
        ["01", "02", "03", "04"],
    ]
    assert report.hard_gates["has_heading"] is True
    assert report.hard_gates["numbered_heading_series_valid"] is True
    assert report.hard_gates["numbered_heading_series_counts_consistent"] is True
    assert report.hard_gates["numbered_heading_typography_valid"] is True
    assert report.status == "pass"
    assert validation.semantic_join_decisions == report.join_decisions

    raw_root = ET.parse(artifacts.raw_xml).getroot()
    semantic_root = ET.parse(artifacts.semantic_xml).getroot()
    for display_role in (
        "section-heading",
        "strong-label",
        "preserved-line-break",
    ):
        assert semantic_root.find(
            f".//*[@display-role='{display_role}']"
        ) is None
    report_data = json.loads(artifacts.report_json.read_text(encoding="utf-8"))
    assert artifacts.semantic_markdown.is_file()
    markdown = artifacts.semantic_markdown.read_text(encoding="utf-8")
    assert markdown.strip()
    assert_profile_readability_controls(document, report, artifacts)

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
    assert page_quality["1"] == {
        "fragment_count": 991,
        "character_count": 26_976,
        "forbidden_xml_control_count": 0,
    }
    assert report_data["metrics"]["heading_count"] == 8
    assert report_data["metrics"]["body_count"] == 1_410
    assert report_data["metrics"]["unknown_role_count"] == 0
    assert report_data["metrics"]["unresolved_mcid_count"] == 0
    assert report_data["metrics"]["unresolved_page_reference_count"] == 0
    assert report_data["metrics"]["unsupported_objr_count"] == 0
    assert report_data["metrics"]["unresolved_reference_count"] == 0
    assert report_data["metrics"]["extraction_loss_diagnostic_total"] == 0
    assert report_data["join_decisions"] == list(report.join_decisions)
    assert report_data["source_path"] == str(pdf)
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
    promotion_entries = [
        entry
        for entry in report_data["heading_hierarchy"]
        if entry["classification"] == "numbered_chapter_promotion"
    ]
    assert len(promotion_entries) == 8
    assert [(entry["label"], entry["title"]) for entry in promotion_entries] == list(
        _ZC_NUMBERED_HEADINGS
    )
    for entry in promotion_entries:
        assert entry["level"] == 2
        assert entry["heading_font_size"] == 16.0
        assert entry["body_font_size"] == 7.0
        assert entry["font_size_ratio"] == pytest.approx(16 / 7)
        assert entry["series_index"] in {0, 1}
        assert entry["promotion_reason"] == (
            "numbered_chapter_structure_sequence_typography"
        )
    assert len(report_data["heading_hierarchy"]) == 46
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
        for entry in candidate_entries
    )
    expected_headings = Counter(
        (
            "#" * min(max(1, int(entry["level"] or 1)) + 1, 6),
            re.sub(r"\s+", " ", entry["joined_text"]).strip(),
        )
        for entry in candidate_entries
    )
    expected_headings.update(
        ("##", f"{label} {title}") for label, title in _ZC_NUMBERED_HEADINGS
    )
    rendered_headings = _assert_candidate_headings(markdown, expected_headings)
    assert sum(rendered_headings.values()) == 46
    for label, title in _ZC_NUMBERED_HEADINGS:
        assert rendered_headings[("##", f"{label} {title}")] == 1

    semantic_headings = [
        heading
        for heading in semantic_root.iter("heading")
        if heading.get("promotion-reason")
        == "numbered_chapter_structure_sequence_typography"
    ]
    assert [
        (_decoded_text(heading.find("label"), "text"), _decoded_text(heading.find("list_body"), "text"))
        for heading in semantic_headings
    ] == list(_ZC_NUMBERED_HEADINGS)
    assert all(heading.get("level") == "2" for heading in semantic_headings)
    _assert_raw_numbered_heading_sources(raw_root, _ZC_NUMBERED_HEADINGS)
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

    semantic_label_counts = Counter(
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
    )
    # After byte-safe Type0 decoding, this sample exposes the source list glyphs
    # as bullet and en dash. Markdown suppresses them by role; XML keeps them.
    assert semantic_label_counts["\u2022"] == 184
    assert semantic_label_counts["\u2013"] == 38
    assert not re.search(
        r"(?m)^\s*(?:-|[0-9]{1,9}[.)])\s+[\u2022\u2013](?:\s|$)",
        markdown,
    )

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

    package_start = markdown.index("## 01 Package Content")
    package_end = markdown.index("## 02 Initial Setup", package_start)
    package = markdown[package_start:package_end]
    package_items = (
        "Simple User Guide",
        "Warranty Card / Regulatory Guide (Not available in some locations)",
        "*Samsung Smart Remote",
        "*Remote Control",
        "*Standard Remote Control",
        "*Batteries",
        "*TV Power Cord",
        "*Wall Mount Adapter x 2",
        "*Slim Power Cord",
        "*Power Box",
        "*Power Box Cable x 2",
        "*C-type Power Adapter",
        "*C to C Cable",
        "*Wireless One Connect Box",
    )
    package_lines = [line.strip() for line in package.splitlines()]
    for item in package_items:
        assert f"- {item}" in package_lines
    assert [package.index(item) for item in package_items] == sorted(
        package.index(item) for item in package_items
    )

    microphone_body = (
        "You can turn on or off the microphone by using the switch at the bottom "
        "or rear bottom of the TV. If microphone is turned off, All voice and sound "
        "features using microphone are not available."
    )
    microphone_items = (
        "This function is supported only in R9*H/R8*H/QN1EH/ QN7*H/QN8*H/"
        "QN9**H/S8*H/S9*H/M9*H/M8*H/ U9***H/LS03H*.",
        "The position and shape of the microphone switch may differ depending "
        "on the model.",
        "During analysis using data from the microphone, the data is not saved.",
    )
    microphone_start = markdown.index(microphone_body)
    microphone_end = markdown.index(
        "## 03 Troubleshooting and Maintenance", microphone_start
    )
    microphone = markdown[microphone_start:microphone_end]
    microphone_lines = [line.strip() for line in microphone.splitlines()]
    assert microphone_lines[0] == microphone_body
    for item in microphone_items:
        assert f"- {item}" in microphone_lines
    assert [microphone.index(item) for item in microphone_items] == sorted(
        microphone.index(item) for item in microphone_items
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
