import re
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from tagged_pdf_extractor.domain.readability_formatting import (
    verified_subtitle_linked_body_paths,
)
from tagged_pdf_extractor.domain.text_joining import join_text_parts
from tagged_pdf_extractor.infrastructure.xml_writer import decode_data_element


READABILITY_DISPLAY_ATTRIBUTES = frozenset(
    {
        "display-role",
        "sentence-break-offsets",
        "sentence-break-reason",
        "icon-reason",
        "reference-font-size",
        "width-font-ratio",
        "height-font-ratio",
        "route-separator-count",
        "route-parenthesized",
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
            (
                int(element.attrib["route-separator-count"])
                if "route-separator-count" in element.attrib
                else None
            ),
            (
                element.attrib["route-parenthesized"] == "true"
                if "route-parenthesized" in element.attrib
                else None
            ),
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
            hint.route_separator_count,
            hint.route_parenthesized,
        )
        for hint in document.inline_icon_hints
    )
    assert len(observed) == len(expected)
    for actual, wanted in zip(observed, expected, strict=True):
        assert actual[0] == wanted[0]
        assert actual[1] == pytest.approx(wanted[1])
        assert actual[2] == wanted[2]
        assert actual[3:6] == pytest.approx(wanted[3:6], rel=1e-5, abs=1e-6)
        assert actual[6:] == wanted[6:]


def _normalized_display_text(value: str) -> str:
    return re.sub(
        r"\s+",
        " ",
        value.replace("<br>", " ")
        .replace(r"\>", ">")
        .replace(r"\[", "["),
    ).strip()


def _inline_navigation_flow(element: ET.Element) -> str | None:
    parts: list[str] = []

    def visit(parent: ET.Element) -> bool:
        for child in parent:
            if child.tag == "attributes":
                continue
            if child.tag == "text":
                parts.append(decode_data_element(child))
            elif (
                child.tag == "figure"
                and child.get("display-role") == "inline-icon"
            ):
                parts.append(" [아이콘] ")
            elif child.tag in {"span", "link"}:
                if (
                    child.get("display-role") == "preserved-line-break"
                    and child.get("actual-text") == "\n"
                ):
                    parts.append(" ")
                elif not visit(child):
                    return False
            else:
                return False
        return True

    if not visit(element):
        return None
    joined, _ = join_text_parts(tuple(parts))
    return _normalized_display_text(joined)


def assert_navigation_flows_preserved(
    semantic_root: ET.Element,
    markdown: str,
) -> None:
    flows: list[str] = []
    for element in semantic_root.iter():
        if element.tag not in {"paragraph", "list_body", "table_cell"}:
            continue
        flow = _inline_navigation_flow(element)
        if flow and ">" in flow:
            flows.append(flow)

    assert flows, "Semantic XML must contain an OSD/navigation flow"
    assert any(
        any(character in flow for character in "/[]()") for flow in flows
    ), "OSD/navigation flow must exercise source special characters"

    normalized_markdown = _normalized_display_text(markdown)
    for flow, expected_count in Counter(flows).items():
        assert (
            normalized_markdown.count(flow) >= expected_count
        ), f"Markdown navigation flow missing or reordered: {flow!r}"


def assert_generic_figure_fallback(semantic_root: ET.Element, markdown: str) -> None:
    generic_figures = [
        figure
        for figure in semantic_root.iter("figure")
        if figure.get("display-role") is None
    ]
    assert generic_figures
    empty_figures: list[ET.Element] = []
    textual_figures: list[str] = []
    for figure in generic_figures:
        text_nodes = list(figure.iter("text"))
        visible_texts = [
            decode_data_element(text).strip()
            for text in text_nodes
            if decode_data_element(text).strip()
        ]
        if visible_texts:
            textual_figures.append(
                _normalized_display_text(" ".join(visible_texts))
            )
        elif text_nodes:
            empty_figures.append(figure)

    assert empty_figures, "Semantic XML must contain an explicit empty figure"
    assert markdown.count("[그림: 텍스트 없음]") == len(empty_figures)

    normalized_markdown = _normalized_display_text(markdown)
    for text, expected_count in Counter(textual_figures).items():
        assert normalized_markdown.count(text) >= expected_count


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
    assert_navigation_flows_preserved(semantic_root, markdown)
    assert_generic_figure_fallback(semantic_root, markdown)
