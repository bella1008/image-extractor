from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from tagged_pdf_extractor.domain.readability_formatting import (
    verified_subtitle_linked_body_paths,
)


READABILITY_DISPLAY_ATTRIBUTES = frozenset(
    {
        "display-role",
        "sentence-break-offsets",
        "sentence-break-reason",
        "icon-reason",
        "reference-font-size",
        "width-font-ratio",
        "height-font-ratio",
        "subtitle-reason",
        "font-weight",
        "comparison-body-font-weight",
        "observed-line-count",
        "display-level",
    }
)


def assert_raw_has_no_readability_display_attributes(raw_xml: Path) -> None:
    root = ET.parse(raw_xml).getroot()
    for element in root.iter():
        assert READABILITY_DISPLAY_ATTRIBUTES.isdisjoint(element.attrib)


def _document_semantic_role_counts(document) -> Counter[str]:
    counts: Counter[str] = Counter()

    def visit(children) -> None:
        for child in children:
            semantic_role = getattr(child, "semantic_role", None)
            if semantic_role is None:
                continue
            counts[semantic_role] += 1
            visit(child.children)

    visit(document.children)
    return counts


def assert_sentence_breaks_do_not_create_source_units(
    document, report, semantic_root: ET.Element
) -> None:
    source_counts = _document_semantic_role_counts(document)
    promotion_count = report.metrics["numbered_heading_promotion_count"]
    assert len(list(semantic_root.iter("paragraph"))) == source_counts["paragraph"]
    assert len(list(semantic_root.iter("table_row"))) == source_counts["table_row"]
    assert len(list(semantic_root.iter("table_cell"))) == source_counts["table_cell"]
    assert (
        len(list(semantic_root.iter("list_item"))) + promotion_count
        == source_counts["list_item"]
    )
    for text in semantic_root.findall(
        ".//text[@display-role='sentence-break-source']"
    ):
        assert list(text) == []


def assert_sentence_evidence_matches_detector(
    document, semantic_root: ET.Element
) -> None:
    evidence = semantic_root.findall(
        ".//text[@display-role='sentence-break-source']"
    )
    assert len(evidence) == len(document.sentence_break_hints)
    for hint in document.sentence_break_hints:
        element = _resolve_semantic_path(semantic_root, hint.child_path)
        assert element.tag == "text"
        assert element.attrib["display-role"] == "sentence-break-source"
        assert tuple(
            int(value)
            for value in element.attrib["sentence-break-offsets"].split(",")
        ) == hint.offsets
        assert element.attrib["sentence-break-reason"] == hint.reason


def _resolve_semantic_path(
    root: ET.Element, child_path: tuple[int, ...]
) -> ET.Element:
    current = root
    for index in child_path:
        current = [child for child in current if child.tag != "attributes"][index]
    return current


def assert_inline_icon_evidence_matches_detector(
    document, semantic_root: ET.Element, markdown: str
) -> None:
    evidence = semantic_root.findall(".//figure[@display-role='inline-icon']")
    assert len(evidence) == len(document.inline_icon_hints)
    assert markdown.count("[아이콘]") == len(document.inline_icon_hints)
    for hint in document.inline_icon_hints:
        element = _resolve_semantic_path(semantic_root, hint.child_path)
        assert element.tag == "figure"
        assert element.attrib["display-role"] == "inline-icon"

    observed = sorted(
        (
            int(element.attrib["page-index"]),
            tuple(
                float(value)
                for value in next(
                    attribute.attrib["value"]
                    for attribute in element.findall("./attributes/attribute")
                    if attribute.attrib["name"] in {"BBox", "/BBox"}
                ).strip("[]").split(",")
            ),
            element.attrib["icon-reason"],
            float(element.attrib["reference-font-size"]),
            float(element.attrib["width-font-ratio"]),
            float(element.attrib["height-font-ratio"]),
        )
        for element in evidence
    )
    expected = sorted(
        (
            hint.page_index,
            hint.bbox,
            hint.reason,
            hint.reference_font_size,
            hint.width_ratio,
            hint.height_ratio,
        )
        for hint in document.inline_icon_hints
    )
    assert len(observed) == len(expected)
    for actual, wanted in zip(observed, expected, strict=True):
        assert actual[0] == wanted[0]
        assert actual[1] == pytest.approx(wanted[1])
        assert actual[2] == wanted[2]
        assert actual[3:] == pytest.approx(wanted[3:], rel=1e-5, abs=1e-6)


def assert_generic_figure_fallback(semantic_root: ET.Element, markdown: str) -> None:
    generic_figures = [
        figure
        for figure in semantic_root.iter("figure")
        if figure.get("display-role") is None
    ]
    assert generic_figures
    assert "[그림: 텍스트 없음]" in markdown


def assert_profile_readability_controls(document, report, artifacts) -> None:
    assert verified_subtitle_linked_body_paths(document) == ()
    assert_raw_has_no_readability_display_attributes(artifacts.raw_xml)
    semantic_root = ET.parse(artifacts.semantic_xml).getroot()
    markdown = artifacts.semantic_markdown.read_text(encoding="utf-8")
    assert_sentence_breaks_do_not_create_source_units(
        document, report, semantic_root
    )
    assert_sentence_evidence_matches_detector(document, semantic_root)
    assert_inline_icon_evidence_matches_detector(
        document, semantic_root, markdown
    )
    assert_generic_figure_fallback(semantic_root, markdown)
    assert all(
        character in markdown
        for character in (">", "/", "[", "]", "(", ")")
    )
