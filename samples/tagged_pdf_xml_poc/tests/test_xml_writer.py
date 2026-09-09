import base64
from dataclasses import replace
import json
import math
from pathlib import Path
from types import MappingProxyType
from typing import cast
from xml.etree import ElementTree as ET

import pytest

from tagged_pdf_extractor.domain.models import (
    ContentFragment,
    ContinuationHint,
    ContinuationTypographyEvidence,
    Diagnostic,
    HeadingMismatchPosition,
    HeadingPromotion,
    HeadingSignatureEntry,
    InlineIconHint,
    LineBreakHint,
    LanguageHeadingSignature,
    LanguageIntervalEvidence,
    MultilingualHeadingAudit,
    QualityReport,
    SentenceBreakHint,
    StructureElement,
    SubtitleHint,
    TaggedDocument,
    TextDisplayHint,
    TextStyle,
)
from tagged_pdf_extractor.domain.display_hint_validation import (
    ValidatedReviewFormattingHints,
)
from tagged_pdf_extractor.domain.readability_formatting import (
    apply_readability_formatting,
)
from tagged_pdf_extractor.domain.subtitle_detection import detect_table_subtitles
from tagged_pdf_extractor.infrastructure import xml_writer as xml_writer_module
from tagged_pdf_extractor.infrastructure.markdown_writer import MarkdownDocumentWriter
from tagged_pdf_extractor.infrastructure.xml_writer import XmlDocumentWriter


def _xml_audit(
    state: str,
    mismatch_component: str = "level",
) -> MultilingualHeadingAudit:
    if state == "not_applicable":
        return MultilingualHeadingAudit(
            False, True, 1, 0, None, None, None, None, None
        )
    if state == "pending":
        return MultilingualHeadingAudit(
            True,
            False,
            2,
            2,
            True,
            None,
            None,
            None,
            None,
            diagnostics=(
                Diagnostic(
                    "error",
                    "multilingual_heading_interval_boundary_invalid",
                    "invalid boundary",
                    {"reason": "missing_start_path", "path": (1, 0)},
                ),
            ),
        )
    expected = (
        HeadingSignatureEntry(2, "promoted", "01")
        if mismatch_component in {"origin", "numbered_label"}
        else HeadingSignatureEntry(1, "source", None)
    )
    observed_entries = (expected,)
    if state == "failed":
        if mismatch_component == "count":
            observed_entries = ()
        elif mismatch_component in {"level", "origin"}:
            observed_entries = (HeadingSignatureEntry(2, "source", None),)
        else:
            observed_entries = (HeadingSignatureEntry(2, "promoted", "02"),)
    signatures = tuple(
        LanguageHeadingSignature(
            language,
            LanguageIntervalEvidence(
                language,
                ordinal - 1,
                ordinal - 1,
                (ordinal - 1,),
                (ordinal - 1,),
                "bookmark" if ordinal == 1 else "structural_language_section",
            ),
            entries,
        )
        for ordinal, (language, entries) in enumerate(
            (("ENG", (expected,)), ("C-FRA", observed_entries)), start=1
        )
    )
    observed = observed_entries[0] if observed_entries else None
    mismatch = (
        HeadingMismatchPosition(
            "C-FRA",
            0,
            mismatch_component,  # type: ignore[arg-type]
            expected,
            observed,
        ),
    ) if state == "failed" else ()
    component_states = {
        "count": True,
        "level": True,
        "origin": True,
        "numbered_label": True,
    }
    if state == "failed":
        component_states[mismatch_component] = False
    return MultilingualHeadingAudit(
        True,
        state == "passed",
        2,
        2,
        True,
        component_states["count"],
        component_states["level"],
        component_states["origin"],
        component_states["numbered_label"],
        signatures,
        mismatch,
    )


@pytest.mark.parametrize(
    ("audit", "status", "applicable", "passed"),
    (
        (None, "not_configured", None, None),
        (_xml_audit("not_applicable"), "not_applicable", False, True),
        (_xml_audit("pending"), "blocked_by_invalid_interval", True, False),
        (_xml_audit("failed"), "failed", True, False),
        (_xml_audit("passed"), "passed", True, True),
    ),
    ids=("no-audit", "not-applicable", "pending", "failed", "passed"),
)
def test_semantic_xml_contains_derived_multilingual_heading_audit_only(
    tmp_path: Path,
    audit: MultilingualHeadingAudit | None,
    status: str,
    applicable: bool | None,
    passed: bool | None,
) -> None:
    source_text = "Localized wording stays unchanged."
    document = TaggedDocument(
        Path("manual.pdf"),
        True,
        "ENG",
        (),
        (
            StructureElement(
                "P",
                "paragraph",
                children=(ContentFragment(0, 1, (source_text,)),),
            ),
        ),
        multilingual_heading_audit=audit,
    )
    raw_path = tmp_path / "raw.xml"
    semantic_path = tmp_path / "semantic.xml"

    writer = XmlDocumentWriter()
    writer.write_raw(document, raw_path)
    writer.write_semantic(document, semantic_path)

    raw_root = ET.parse(raw_path).getroot()
    semantic_root = ET.parse(semantic_path).getroot()
    assert raw_root.find("multilingual-heading-audit") is None
    node = semantic_root.find("multilingual-heading-audit")
    assert node is not None
    assert node.get("status") == status
    assert node.get("applicable") == (
        None if applicable is None else str(applicable).lower()
    )
    assert node.get("passed") == (None if passed is None else str(passed).lower())
    semantic_text = semantic_root.find("paragraph/text")
    assert semantic_text is not None
    assert xml_writer_module.decode_data_element(semantic_text) == source_text
    assert "Localized wording" not in ET.tostring(node, encoding="unicode")


def test_semantic_xml_serializes_exact_audit_evidence_in_stable_order(
    tmp_path: Path,
) -> None:
    audit = _xml_audit("failed")
    document = TaggedDocument(
        Path("manual.pdf"), True, "ENG", (), (), multilingual_heading_audit=audit
    )
    path = tmp_path / "semantic.xml"

    XmlDocumentWriter().write_semantic(document, path)

    node = ET.parse(path).getroot().find("multilingual-heading-audit")
    assert node is not None
    assert node.attrib == {
        "applicable": "true",
        "status": "failed",
        "passed": "false",
        "expected-interval-count": "2",
        "observed-interval-count": "2",
        "interval-count-matches": "true",
        "total-heading-count-matches": "true",
        "heading-level-sequence-matches": "false",
        "heading-origin-sequence-matches": "true",
        "numbered-label-sequence-matches": "true",
    }
    languages = node.findall("language")
    assert [item.attrib for item in languages] == [
        {
            "ordinal": "1",
            "code": "ENG",
            "start-page-index": "0",
            "end-page-index": "0",
            "start-path": "0",
            "end-path": "0",
            "evidence-origin": "bookmark",
            "heading-total": "1",
        },
        {
            "ordinal": "2",
            "code": "C-FRA",
            "start-page-index": "1",
            "end-page-index": "1",
            "start-path": "1",
            "end-path": "1",
            "evidence-origin": "structural_language_section",
            "heading-total": "1",
        },
    ]
    assert [entry.attrib for entry in languages[0].findall("heading")] == [
        {"position": "0", "level": "1", "origin": "source"}
    ]
    assert [entry.attrib for entry in languages[1].findall("heading")] == [
        {"position": "0", "level": "2", "origin": "source"}
    ]
    mismatch = node.find("mismatch")
    assert mismatch is not None
    assert mismatch.attrib == {
        "interval-ordinal": "2",
        "language": "C-FRA", "position": "0", "component": "level"
    }
    assert mismatch.find("expected").attrib == {
        "level": "1", "origin": "source"
    }
    assert mismatch.find("observed").attrib == {
        "level": "2", "origin": "source"
    }


@pytest.mark.parametrize(
    "component",
    ("count", "level", "origin", "numbered_label"),
)
def test_semantic_xml_mismatch_uses_ordered_signature_interval_ordinal(
    tmp_path: Path,
    component: str,
) -> None:
    audit = _xml_audit("failed", component)
    document = TaggedDocument(
        Path("manual.pdf"), True, "ENG", (), (), multilingual_heading_audit=audit
    )
    path = tmp_path / f"{component}.xml"

    XmlDocumentWriter().write_semantic(document, path)

    mismatch = ET.parse(path).getroot().find(
        "multilingual-heading-audit/mismatch"
    )
    assert mismatch is not None
    assert mismatch.get("interval-ordinal") == "2"
    assert mismatch.get("language") == "C-FRA"
    assert mismatch.get("component") == component


def test_pending_semantic_xml_serializes_diagnostic_context_stably(
    tmp_path: Path,
) -> None:
    document = TaggedDocument(
        Path("manual.pdf"),
        True,
        "ENG",
        (),
        (),
        multilingual_heading_audit=_xml_audit("pending"),
    )
    path = tmp_path / "semantic.xml"

    XmlDocumentWriter().write_semantic(document, path)

    diagnostic = ET.parse(path).getroot().find(
        "multilingual-heading-audit/diagnostic"
    )
    assert diagnostic is not None
    assert diagnostic.attrib == {
        "severity": "error",
        "code": "multilingual_heading_interval_boundary_invalid",
        "message": "invalid boundary",
        "context-json": '{"path":[1,0],"reason":"missing_start_path"}',
    }


def test_semantic_audit_diagnostic_attributes_round_trip_xml_controls(
    tmp_path: Path,
) -> None:
    audit = replace(
        _xml_audit("pending"),
        diagnostics=(
            Diagnostic(
                "error",
                "interval_failure",
                "bad\x01message",
                {
                    "nested": {"value": "bad\x02context"},
                    "sequence": ("safe", "bad\x03item"),
                },
            ),
        ),
    )
    document = TaggedDocument(
        Path("manual.pdf"), True, "ENG", (), (), multilingual_heading_audit=audit
    )
    path = tmp_path / "semantic.xml"

    XmlDocumentWriter().write_semantic(document, path)

    root = ET.parse(path).getroot()
    diagnostic = root.find("multilingual-heading-audit/diagnostic")
    assert diagnostic is not None
    decoded = dict(xml_writer_module._decoded_attributes(diagnostic))
    assert decoded["message"] == "bad\x01message"
    assert json.loads(decoded["context-json"]) == {
        "nested": {"value": "bad\x02context"},
        "sequence": ["safe", "bad\x03item"],
    }
    assert diagnostic.get("message-encoding") == "base64-utf8"
    assert "\x01" not in path.read_text(encoding="utf-8")


def test_semantic_xml_revalidates_approved_audit_model_before_serializing(
    tmp_path: Path,
) -> None:
    audit = _xml_audit("passed")
    object.__setattr__(audit, "passed", False)
    document = TaggedDocument(
        Path("manual.pdf"), True, "ENG", (), (), multilingual_heading_audit=audit
    )

    with pytest.raises(ValueError, match="passed contradicts"):
        XmlDocumentWriter().write_semantic(document, tmp_path / "semantic.xml")


def _promotion(
    child_path: tuple[int, ...], title: str = "Troubleshooting"
) -> HeadingPromotion:
    return HeadingPromotion(
        child_path=child_path,
        level=2,
        label="03",
        title=title,
        series_index=0,
        heading_font_size=16.0,
        body_font_size=7.0,
        font_size_ratio=16 / 7,
        promotion_reason="numbered_chapter_structure_sequence_typography",
        heading_font_names=("SamsungOne-600", "SamsungOne-Bold"),
        body_font_names=("SamsungOne-400",),
    )


def _list_item() -> StructureElement:
    return StructureElement(
        "LI",
        "list_item",
        children=(ContentFragment(0, 1, ("03 Troubleshooting",)),),
    )


def _subtitle_hint(child_path: tuple[int, ...]) -> SubtitleHint:
    return SubtitleHint(
        child_path=child_path,
        font_weight=600,
        comparison_body_font_weight=400,
        observed_line_count=2,
    )


def _text_display_hint(
    child_path: tuple[int, ...], display_role: str = "section_heading"
) -> TextDisplayHint:
    return TextDisplayHint(
        child_path=child_path,
        display_role=cast(object, display_role),
        font_weight=800,
        font_size=8.0,
        comparison_body_font_weight=400,
        comparison_body_font_size=6.5,
        reason="form_cluster_relative_typography",
    )


def _continuation_hint(child_path: tuple[int, ...]) -> ContinuationHint:
    return ContinuationHint(
        child_path=child_path,
        preceding_list_item_path=(0, 0, 0),
        preceding_list_body_path=(0, 0, 0, 1),
        page_index=0,
        paragraph_bbox=(100.0, 176.0, 180.0, 184.0),
        list_body_bbox=(100.0, 188.0, 180.0, 208.0),
        left_delta=0.0,
        vertical_gap=4.0,
        reference_font_size=8.0,
        source_role="LBody",
        typography_evidence=ContinuationTypographyEvidence(
            preceding_body_font_weight=400,
            preceding_body_font_size=8.0,
            preceding_body_observed_lines=((0, 11), (0, 12)),
            target_font_weight=400,
            target_font_size=8.0,
            target_observed_lines=((0, 20),),
        ),
    )


def test_semantic_writer_serializes_continuation_evidence_without_raw_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = StructureElement(
        "LBody",
        "paragraph",
        children=(ContentFragment(0, 20, ("Continuation text",)),),
    )
    hint = _continuation_hint((0,))
    document = TaggedDocument(
        Path("manual.pdf"), True, "en", (), (target,), continuation_hints=(hint,)
    )
    validated = ValidatedReviewFormattingHints(
        line_break_by_path=MappingProxyType({}),
        text_display_by_path=MappingProxyType({}),
        sentence_break_by_path=MappingProxyType({}),
        inline_icon_by_path=MappingProxyType({}),
        continuation_by_path=MappingProxyType({hint.child_path: hint}),
    )
    monkeypatch.setattr(xml_writer_module, "validate_display_hints", lambda actual: validated)
    raw_path = tmp_path / "raw.xml"
    raw_without_hint_path = tmp_path / "raw-without-hint.xml"
    semantic_path = tmp_path / "semantic.xml"

    writer = XmlDocumentWriter()
    writer.write_raw(document, raw_path)
    writer.write_raw(replace(document, continuation_hints=()), raw_without_hint_path)
    writer.write_semantic(document, semantic_path)

    assert raw_path.read_bytes() == raw_without_hint_path.read_bytes()
    paragraph = ET.parse(semantic_path).getroot().find("paragraph")
    assert paragraph is not None
    assert paragraph.attrib == {
        "page-index": "0",
        "display-role": "list-continuation",
        "continuation-reason": "sibling_list_paragraph_list_geometry_typography",
        "preceding-list-item-path": "0/0/0",
        "preceding-list-body-path": "0/0/0/1",
        "paragraph-bbox": "100,176,180,184",
        "list-body-bbox": "100,188,180,208",
        "left-delta": "0",
        "vertical-gap": "4",
        "reference-font-size": "8",
        "continuation-source-role": "LBody",
        "preceding-body-font-weight": "400",
        "preceding-body-font-size": "8",
        "preceding-body-observed-lines": "0:11,0:12",
        "target-font-weight": "400",
        "target-font-size": "8",
        "target-observed-lines": "0:20",
    }


def _continuation_publication_document(hint: ContinuationHint) -> TaggedDocument:
    def list_block(label_text: str, body_text: str, mcid: int) -> StructureElement:
        return StructureElement(
            "L",
            "list",
            children=(
                StructureElement(
                    "LI",
                    "list_item",
                    children=(
                        StructureElement(
                            "Lbl",
                            "label",
                            children=(ContentFragment(0, mcid, (label_text,)),),
                        ),
                        StructureElement(
                            "LBody",
                            "list_body",
                            children=(ContentFragment(0, mcid + 1, (body_text,)),),
                        ),
                    ),
                ),
            ),
        )

    target = StructureElement(
        "LBody",
        "paragraph",
        children=(ContentFragment(0, 20, ("Continuation text",)),),
    )
    return TaggedDocument(
        Path("manual.pdf"),
        True,
        "en",
        (),
        (list_block("10.", "Tenth item", 10), target, list_block("11.", "Eleventh item", 30)),
        continuation_hints=(hint,),
    )


@pytest.mark.parametrize(
    ("paragraph_bbox", "list_body_bbox", "left_delta", "vertical_gap", "attribute"),
    [
        (
            (0.0000045, 1.0, 20.0, 10.0),
            (0.0, 14.0, 20.0, 24.0),
            0.0000045,
            4.0,
            "left-delta",
        ),
        (
            (0.0, 1.0, 20.0, 10.0),
            (0.0, 10.0000045, 20.0, 24.0),
            0.0,
            0.0000045,
            "vertical-gap",
        ),
    ],
    ids=("left-delta-half-micro", "vertical-gap-half-micro"),
)
def test_continuation_half_micro_evidence_publishes_from_xml_to_markdown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    paragraph_bbox: tuple[float, float, float, float],
    list_body_bbox: tuple[float, float, float, float],
    left_delta: float,
    vertical_gap: float,
    attribute: str,
) -> None:
    hint = replace(
        _continuation_hint((1,)),
        preceding_list_item_path=(0, 0),
        preceding_list_body_path=(0, 0, 1),
        paragraph_bbox=paragraph_bbox,
        list_body_bbox=list_body_bbox,
        left_delta=left_delta,
        vertical_gap=vertical_gap,
    )
    document = _continuation_publication_document(hint)
    validated = ValidatedReviewFormattingHints(
        line_break_by_path=MappingProxyType({}),
        text_display_by_path=MappingProxyType({}),
        sentence_break_by_path=MappingProxyType({}),
        inline_icon_by_path=MappingProxyType({}),
        continuation_by_path=MappingProxyType({hint.child_path: hint}),
    )
    monkeypatch.setattr(
        xml_writer_module, "validate_display_hints", lambda actual: validated
    )
    semantic_path = tmp_path / "semantic.xml"
    markdown_path = tmp_path / "semantic.md"

    XmlDocumentWriter().write_semantic(document, semantic_path)
    paragraph = ET.parse(semantic_path).getroot().find("paragraph")
    assert paragraph is not None
    MarkdownDocumentWriter().write(
        semantic_path,
        QualityReport("pass", {}, {}, ()),
        markdown_path,
        source_name="manual.pdf",
    )

    assert paragraph.attrib[attribute] == repr(
        left_delta if attribute == "left-delta" else vertical_gap
    )
    assert "10. Tenth item\n\n    Continuation text\n\n11. Eleventh item" in markdown_path.read_text(
        encoding="utf-8"
    )


def test_tiny_positive_continuation_font_sizes_publish_from_xml_to_markdown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    font_size = 4e-7
    base_hint = _continuation_hint((1,))
    hint = replace(
        base_hint,
        preceding_list_item_path=(0, 0),
        preceding_list_body_path=(0, 0, 1),
        reference_font_size=font_size,
        typography_evidence=replace(
            base_hint.typography_evidence,
            preceding_body_font_size=font_size,
            target_font_size=font_size,
        ),
    )
    document = _continuation_publication_document(hint)
    validated = ValidatedReviewFormattingHints(
        line_break_by_path=MappingProxyType({}),
        text_display_by_path=MappingProxyType({}),
        sentence_break_by_path=MappingProxyType({}),
        inline_icon_by_path=MappingProxyType({}),
        continuation_by_path=MappingProxyType({hint.child_path: hint}),
    )
    monkeypatch.setattr(
        xml_writer_module, "validate_display_hints", lambda actual: validated
    )
    semantic_path = tmp_path / "semantic.xml"
    markdown_path = tmp_path / "semantic.md"

    XmlDocumentWriter().write_semantic(document, semantic_path)
    paragraph = ET.parse(semantic_path).getroot().find("paragraph")
    assert paragraph is not None
    MarkdownDocumentWriter().write(
        semantic_path,
        QualityReport("pass", {}, {}, ()),
        markdown_path,
        source_name="manual.pdf",
    )

    assert {
        name: paragraph.attrib[name]
        for name in (
            "reference-font-size",
            "preceding-body-font-size",
            "target-font-size",
        )
    } == {
        "reference-font-size": "4e-07",
        "preceding-body-font-size": "4e-07",
        "target-font-size": "4e-07",
    }
    assert "Continuation text" in markdown_path.read_text(encoding="utf-8")


def _review_formatting_document() -> TaggedDocument:
    heading = StructureElement(
        "P", "paragraph", children=(ContentFragment(0, 1, ("Form title",)),)
    )
    label = StructureElement(
        "P", "paragraph", children=(ContentFragment(0, 2, ("Field label",)),)
    )
    rf_paragraph = StructureElement(
        "P",
        "paragraph",
        children=(
            ContentFragment(0, 3, ("Band one,",)),
            StructureElement("Span", "span", actual_text="\n"),
            ContentFragment(0, 4, ("Band two",)),
        ),
    )
    wrapper = StructureElement(
        "P",
        "paragraph",
        children=(
            StructureElement(
                "Table",
                "table",
                children=(
                    StructureElement(
                        "TR",
                        "table_row",
                        children=(
                            StructureElement(
                                "TD", "table_cell", children=(rf_paragraph,)
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )
    return TaggedDocument(
        Path("manual.pdf"),
        True,
        "en",
        (),
        (StructureElement("Sect", "section", children=(heading, label, wrapper)),),
        line_break_hints=(LineBreakHint((0, 2, 0, 0, 0, 0, 1)),),
        text_display_hints=(
            _text_display_hint((0, 0)),
            replace(
                _text_display_hint((0, 1)),
                display_role="strong_label",
                font_weight=600,
                font_size=7.0,
            ),
        ),
    )


def _readability_evidence_document() -> tuple[
    TaggedDocument, SentenceBreakHint, InlineIconHint
]:
    sentence = ContentFragment(
        18,
        27,
        ("Deuxième phrase. Troisième phrase.",),
        object_ref="88 0 R",
    )
    before_icon = ContentFragment(
        18,
        28,
        ("Home",),
        object_ref="89 0 R",
        text_styles=(TextStyle("SamsungOne-400", 6.5),),
    )
    icon = StructureElement(
        "Figure",
        "figure",
        object_ref="123 0 R",
        page_index=18,
        alternate_text="Home",
        attributes=(("/BBox", "[100, 200, 109, 209]"),),
    )
    after_icon = ContentFragment(
        18,
        29,
        ("Settings",),
        object_ref="90 0 R",
        text_styles=(TextStyle("SamsungOne-400", 6.5),),
    )
    document = TaggedDocument(
        Path("manual.pdf"),
        True,
        "fr",
        (),
        (
            StructureElement("P", "paragraph", children=(sentence,)),
            StructureElement(
                "P",
                "paragraph",
                children=(before_icon, icon, after_icon),
            ),
        ),
    )
    sentence_hint = SentenceBreakHint(
        child_path=(0, 0),
        offsets=(0, 17),
        reason="conservative_sentence_terminal_in_review_container",
    )
    icon_hint = InlineIconHint(
        child_path=(1, 1),
        page_index=18,
        bbox=(100.0, 200.0, 109.0, 209.0),
        reference_font_size=6.5,
        width_ratio=9 / 6.5,
        height_ratio=9 / 6.5,
        reason="small_inline_figure_with_adjacent_text",
    )
    return (
        replace(
            document,
            sentence_break_hints=(sentence_hint,),
            inline_icon_hints=(icon_hint,),
        ),
        sentence_hint,
        icon_hint,
    )


def _validated_readability_hints(
    sentence_hint: SentenceBreakHint,
    icon_hint: InlineIconHint,
) -> ValidatedReviewFormattingHints:
    return ValidatedReviewFormattingHints(
        line_break_by_path=MappingProxyType({}),
        text_display_by_path=MappingProxyType({}),
        sentence_break_by_path=MappingProxyType(
            {sentence_hint.child_path: sentence_hint}
        ),
        inline_icon_by_path=MappingProxyType({icon_hint.child_path: icon_hint}),
    )


def test_semantic_writer_serializes_readability_evidence_without_raw_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document, sentence_hint, icon_hint = _readability_evidence_document()
    monkeypatch.setattr(
        xml_writer_module,
        "validate_display_hints",
        lambda actual: _validated_readability_hints(sentence_hint, icon_hint),
    )
    raw_path = tmp_path / "raw.xml"
    raw_without_hints_path = tmp_path / "raw-without-hints.xml"
    semantic_path = tmp_path / "semantic.xml"

    writer = XmlDocumentWriter()
    writer.write_raw(document, raw_path)
    writer.write_raw(
        replace(document, sentence_break_hints=(), inline_icon_hints=()),
        raw_without_hints_path,
    )
    writer.write_semantic(document, semantic_path)

    assert raw_path.read_bytes() == raw_without_hints_path.read_bytes()
    raw = raw_path.read_text(encoding="utf-8")
    for attribute_name in (
        "display-role",
        "sentence-break-offsets",
        "sentence-break-reason",
        "icon-reason",
        "reference-font-size",
        "width-font-ratio",
        "height-font-ratio",
    ):
        assert attribute_name not in raw
    raw_root = ET.parse(raw_path).getroot()
    raw_sentence = raw_root.find("./element/fragment")
    raw_figure = raw_root.find("./element[2]/element")
    assert raw_sentence is not None
    assert raw_sentence.attrib == {
        "page-index": "18",
        "mcid": "27",
        "object-ref": "88 0 R",
    }
    assert [part.text for part in raw_sentence.findall("part")] == [
        "Deuxième phrase. Troisième phrase.",
    ]
    assert raw_figure is not None
    assert raw_figure.attrib == {
        "source-role": "Figure",
        "semantic-role": "figure",
        "object-ref": "123 0 R",
        "page-index": "18",
        "alternate-text": "Home",
    }
    assert [item.attrib for item in raw_figure.findall("./attributes/attribute")] == [
        {"name": "/BBox", "value": "[100, 200, 109, 209]"}
    ]

    semantic_root = ET.parse(semantic_path).getroot()
    sentence = semantic_root.find("./paragraph[1]/text")
    figure = semantic_root.find("./paragraph[2]/figure")
    assert sentence is not None
    assert sentence.attrib == {
        "page-index": "18",
        "mcid": "27",
        "object-ref": "88 0 R",
        "display-role": "sentence-break-source",
        "sentence-break-offsets": "0,17",
        "sentence-break-reason": (
            "conservative_sentence_terminal_in_review_container"
        ),
    }
    assert sentence.text == "Deuxième phrase. Troisième phrase."
    assert figure is not None
    assert figure.attrib == {
        "object-ref": "123 0 R",
        "page-index": "18",
        "alternate-text": "Home",
        "display-role": "inline-icon",
        "icon-reason": "small_inline_figure_with_adjacent_text",
        "reference-font-size": "6.5",
        "width-font-ratio": "1.384615",
        "height-font-ratio": "1.384615",
    }
    assert [item.attrib for item in figure.findall("./attributes/attribute")] == [
        {"name": "/BBox", "value": "[100, 200, 109, 209]"}
    ]


def test_semantic_writer_serializes_navigation_route_icon_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document, sentence_hint, generic_hint = _readability_evidence_document()
    route_hint = replace(
        generic_hint,
        reason="navigation_route_inline_figure",
        route_separator_count=3,
        route_parenthesized=True,
    )
    document = replace(document, inline_icon_hints=(route_hint,))
    monkeypatch.setattr(
        xml_writer_module,
        "validate_display_hints",
        lambda actual: _validated_readability_hints(sentence_hint, route_hint),
    )
    semantic_path = tmp_path / "semantic.xml"

    XmlDocumentWriter().write_semantic(document, semantic_path)

    figure = ET.parse(semantic_path).getroot().find("./paragraph[2]/figure")
    assert figure is not None
    assert figure.attrib["icon-reason"] == "navigation_route_inline_figure"
    assert figure.attrib["route-separator-count"] == "3"
    assert figure.attrib["route-parenthesized"] == "true"
    assert figure.attrib["reference-font-size"] == "6.5"


def test_semantic_writer_rejects_generic_icon_with_route_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document, sentence_hint, generic_hint = _readability_evidence_document()
    invalid_hint = replace(
        generic_hint,
        route_separator_count=3,
        route_parenthesized=True,
    )
    document = replace(document, inline_icon_hints=(invalid_hint,))
    monkeypatch.setattr(
        xml_writer_module,
        "validate_display_hints",
        lambda actual: _validated_readability_hints(sentence_hint, invalid_hint),
    )

    with pytest.raises(ValueError, match="generic inline icon contains route evidence"):
        XmlDocumentWriter().write_semantic(document, tmp_path / "semantic.xml")


def test_semantic_writer_integrates_detector_validator_and_recursive_targets(
    tmp_path: Path,
) -> None:
    sentence_text = "First sentence. Next sentence."
    sentence_fragment = ContentFragment(3, 20, (sentence_text,))
    before_icon = ContentFragment(
        3,
        21,
        ("Before icon",),
        text_styles=(TextStyle("SamsungOne-400", 6.5),),
    )
    icon = StructureElement(
        "Figure",
        "figure",
        object_ref="123 0 R",
        page_index=3,
        attributes=(("/BBox", "[100, 200, 109, 209]"),),
    )
    after_icon = ContentFragment(
        3,
        22,
        ("After icon",),
        text_styles=(TextStyle("SamsungOne-400", 6.5),),
    )
    source_document = TaggedDocument(
        Path("detector-produced.pdf"),
        True,
        "en",
        (),
        (
            StructureElement(
                "L",
                "list",
                children=(
                    StructureElement(
                        "LI",
                        "list_item",
                        children=(
                            StructureElement(
                                "Lbl",
                                "label",
                                children=(ContentFragment(3, 19, ("1",)),),
                            ),
                            StructureElement(
                                "LBody",
                                "list_body",
                                children=(
                                    StructureElement(
                                        "P",
                                        "paragraph",
                                        children=(sentence_fragment,),
                                    ),
                                    StructureElement(
                                        "P",
                                        "paragraph",
                                        children=(before_icon, icon, after_icon),
                                    ),
                                ),
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )

    document = apply_readability_formatting(source_document)
    assert document.sentence_break_hints == (
        SentenceBreakHint((0, 0, 1, 0, 0), (sentence_text.index("Next"),)),
    )
    assert document.inline_icon_hints == (
        InlineIconHint(
            (0, 0, 1, 1, 1),
            page_index=3,
            bbox=(100.0, 200.0, 109.0, 209.0),
            reference_font_size=6.5,
            width_ratio=9 / 6.5,
            height_ratio=9 / 6.5,
        ),
    )
    semantic_path = tmp_path / "semantic.xml"

    XmlDocumentWriter().write_semantic(document, semantic_path)

    root = ET.parse(semantic_path).getroot()
    sentence = root.find("./list/list_item/list_body/paragraph[1]/text")
    inline_icon = root.find("./list/list_item/list_body/paragraph[2]/figure")
    assert sentence is not None
    assert sentence.attrib["display-role"] == "sentence-break-source"
    assert sentence.attrib["sentence-break-offsets"] == str(
        sentence_text.index("Next")
    )
    assert sentence.attrib["sentence-break-reason"] == (
        "conservative_sentence_terminal_in_review_container"
    )
    assert inline_icon is not None
    assert inline_icon.attrib["display-role"] == "inline-icon"
    assert inline_icon.attrib["icon-reason"] == (
        "small_inline_figure_with_adjacent_text"
    )
    assert inline_icon.attrib["reference-font-size"] == "6.5"
    assert inline_icon.attrib["width-font-ratio"] == "1.384615"
    assert inline_icon.attrib["height-font-ratio"] == "1.384615"
    assert inline_icon.attrib["page-index"] == "3"
    assert inline_icon.attrib["object-ref"] == "123 0 R"
    assert [item.attrib for item in inline_icon.findall("./attributes/attribute")] == [
        {"name": "/BBox", "value": "[100, 200, 109, 209]"}
    ]


@pytest.mark.parametrize(
    ("hint_kind", "error_pattern"),
    [
        ("sentence", r"unresolved sentence break hint path"),
        ("icon", r"unresolved inline icon hint path"),
    ],
)
def test_semantic_writer_rejects_unconsumed_readability_hint_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    hint_kind: str,
    error_pattern: str,
) -> None:
    document, sentence_hint, icon_hint = _readability_evidence_document()
    unresolved_sentence = replace(sentence_hint, child_path=(9, 9))
    unresolved_icon = replace(icon_hint, child_path=(9, 9))
    validated = ValidatedReviewFormattingHints(
        line_break_by_path=MappingProxyType({}),
        text_display_by_path=MappingProxyType({}),
        sentence_break_by_path=MappingProxyType(
            {unresolved_sentence.child_path: unresolved_sentence}
            if hint_kind == "sentence"
            else {}
        ),
        inline_icon_by_path=MappingProxyType(
            {unresolved_icon.child_path: unresolved_icon}
            if hint_kind == "icon"
            else {}
        ),
    )
    monkeypatch.setattr(
        xml_writer_module,
        "validate_display_hints",
        lambda actual: validated,
    )
    target = tmp_path / "semantic.xml"
    target.write_text("sentinel", encoding="utf-8")

    with pytest.raises(ValueError, match=error_pattern):
        XmlDocumentWriter().write_semantic(document, target)

    assert target.read_text(encoding="utf-8") == "sentinel"


def test_semantic_writer_serializes_validated_review_formatting_only_semantically(
    tmp_path: Path,
) -> None:
    document = _review_formatting_document()
    raw_path = tmp_path / "raw.xml"
    semantic_path = tmp_path / "semantic.xml"

    writer = XmlDocumentWriter()
    writer.write_raw(document, raw_path)
    writer.write_semantic(document, semantic_path)

    raw = raw_path.read_text(encoding="utf-8")
    assert "display-role" not in raw
    assert "display-level" not in raw
    assert "display-reason" not in raw
    assert "line-break-reason" not in raw

    root = ET.parse(semantic_path).getroot()
    heading = root.find("./section/paragraph[1]")
    label = root.find("./section/paragraph[2]")
    line_break = root.find(".//table_cell/paragraph/span")
    assert heading is not None
    assert heading.attrib == {
        "display-role": "section-heading",
        "display-level": "2",
        "display-reason": "form_cluster_relative_typography",
        "font-weight": "800",
        "font-size": "8",
        "comparison-body-font-weight": "400",
        "comparison-body-font-size": "6.5",
    }
    assert label is not None
    assert label.attrib == {
        "display-role": "strong-label",
        "display-reason": "form_cluster_relative_typography",
        "font-weight": "600",
        "font-size": "7",
        "comparison-body-font-weight": "400",
        "comparison-body-font-size": "6.5",
    }
    assert line_break is not None
    assert line_break.attrib == {
        "actual-text": "\n",
        "display-role": "preserved-line-break",
        "line-break-reason": "source_actual_text_newline_after_comma_in_table_cell",
    }


@pytest.mark.parametrize(
    "collection,invalid_path",
    (
        ("line_break_hints", ()),
        ("line_break_hints", (-1,)),
        ("line_break_hints", (True,)),
        ("line_break_hints", [0]),
        ("text_display_hints", ()),
        ("text_display_hints", (-1,)),
        ("text_display_hints", (False,)),
        ("text_display_hints", [0]),
    ),
)
def test_semantic_writer_rejects_invalid_review_hint_paths_before_writing(
    tmp_path: Path, collection: str, invalid_path: object
) -> None:
    document = _review_formatting_document()
    if collection == "line_break_hints":
        document = replace(
            document,
            line_break_hints=(LineBreakHint(cast(tuple[int, ...], invalid_path)),),
            text_display_hints=(),
        )
    else:
        document = replace(
            document,
            line_break_hints=(),
            text_display_hints=(
                _text_display_hint(cast(tuple[int, ...], invalid_path)),
            ),
        )
    target = tmp_path / "semantic.xml"
    target.write_text("sentinel", encoding="utf-8")

    with pytest.raises(ValueError, match="invalid .* hint path"):
        XmlDocumentWriter().write_semantic(document, target)

    assert target.read_text(encoding="utf-8") == "sentinel"


@pytest.mark.parametrize("collection", ("line_break_hints", "text_display_hints"))
def test_semantic_writer_rejects_duplicate_review_hint_paths(
    tmp_path: Path, collection: str
) -> None:
    document = _review_formatting_document()
    hints = getattr(document, collection)
    document = replace(document, **{collection: (hints[0], hints[0])})

    with pytest.raises(ValueError, match=f"duplicate {collection[:-1].replace('_', ' ')} path"):
        XmlDocumentWriter().write_semantic(document, tmp_path / "semantic.xml")


@pytest.mark.parametrize("collection", ("line_break_hints", "text_display_hints"))
def test_semantic_writer_rejects_unresolved_review_hint_paths(
    tmp_path: Path, collection: str
) -> None:
    document = _review_formatting_document()
    if collection == "line_break_hints":
        document = replace(
            document,
            line_break_hints=(LineBreakHint((9,)),),
            text_display_hints=(),
        )
    else:
        document = replace(
            document,
            line_break_hints=(),
            text_display_hints=(_text_display_hint((9,)),),
        )

    with pytest.raises(ValueError, match=f"unresolved {collection[:-1].replace('_', ' ')} path"):
        XmlDocumentWriter().write_semantic(document, tmp_path / "semantic.xml")


def test_semantic_writer_rejects_review_hint_targeting_content_fragment(
    tmp_path: Path,
) -> None:
    document = TaggedDocument(
        Path("manual.pdf"),
        True,
        None,
        (),
        (ContentFragment(0, 1, ("text",)),),
        text_display_hints=(_text_display_hint((0,)),),
    )

    with pytest.raises(ValueError, match="StructureElement"):
        XmlDocumentWriter().write_semantic(document, tmp_path / "semantic.xml")


@pytest.mark.parametrize(
    "mutator,error",
    (
        (
            lambda d: replace(
                d,
                children=(StructureElement("Span", "span"),),
                text_display_hints=(_text_display_hint((0,)),),
                line_break_hints=(),
            ),
            "paragraph",
        ),
        (
            lambda d: replace(
                d,
                text_display_hints=(
                    replace(d.text_display_hints[0], display_role=cast(object, "bold")),
                ),
                line_break_hints=(),
            ),
            "display role",
        ),
        (
            lambda d: replace(
                d,
                text_display_hints=(replace(d.text_display_hints[0], font_size=math.nan),),
                line_break_hints=(),
            ),
            "typography",
        ),
        (
            lambda d: replace(
                d,
                text_display_hints=(
                    replace(d.text_display_hints[0], comparison_body_font_size=0.0),
                ),
                line_break_hints=(),
            ),
            "typography",
        ),
    ),
)
def test_semantic_writer_rejects_invalid_text_display_hint_runtime_data(
    tmp_path: Path, mutator: object, error: str
) -> None:
    document = cast(object, mutator)(_review_formatting_document())

    with pytest.raises(ValueError, match=error):
        XmlDocumentWriter().write_semantic(document, tmp_path / "semantic.xml")


def test_semantic_writer_rejects_empty_or_block_bearing_text_display_paragraph(
    tmp_path: Path,
) -> None:
    for paragraph in (
        StructureElement("P", "paragraph"),
        StructureElement(
            "P",
            "paragraph",
            children=(
                ContentFragment(0, 1, ("title",)),
                StructureElement("Table", "table"),
            ),
        ),
    ):
        document = TaggedDocument(
            Path("manual.pdf"),
            True,
            None,
            (),
            (paragraph,),
            text_display_hints=(_text_display_hint((0,)),),
        )
        with pytest.raises(ValueError, match="nonempty leaf paragraph"):
            XmlDocumentWriter().write_semantic(document, tmp_path / "semantic.xml")


def test_semantic_writer_revalidates_manual_line_break_adjacency(
    tmp_path: Path,
) -> None:
    document = _review_formatting_document()
    section = cast(StructureElement, document.children[0])
    wrapper = cast(StructureElement, section.children[2])
    table = cast(StructureElement, wrapper.children[0])
    row = cast(StructureElement, table.children[0])
    cell = cast(StructureElement, row.children[0])
    paragraph = cast(StructureElement, cell.children[0])
    invalid_paragraph = replace(
        paragraph,
        children=(ContentFragment(0, 3, ("Band one",)), *paragraph.children[1:]),
    )
    invalid = replace(
        document,
        children=(
            replace(
                section,
                children=(
                    *section.children[:2],
                    replace(
                        wrapper,
                        children=(
                            replace(
                                table,
                                children=(
                                    replace(
                                        row,
                                        children=(replace(cell, children=(invalid_paragraph,)),),
                                    ),
                                ),
                            ),
                        ),
                    ),
                ),
            ),
        ),
        text_display_hints=(),
    )

    with pytest.raises(ValueError, match="line-break adjacency evidence"):
        XmlDocumentWriter().write_semantic(invalid, tmp_path / "semantic.xml")


def test_semantic_writer_rejects_text_display_conflicts(
    tmp_path: Path,
) -> None:
    base = _review_formatting_document()
    section = cast(StructureElement, base.children[0])
    heading = cast(StructureElement, section.children[0])
    cases = (
        replace(base, subtitle_hints=(_subtitle_hint((0, 0)),), line_break_hints=()),
        replace(
            base,
            children=(replace(section, children=(replace(heading, source_role="Heading2"), *section.children[1:])),),
            line_break_hints=(),
        ),
        replace(
            base,
            children=(StructureElement("LI", "list_item", children=(heading,)),),
            heading_promotions=(_promotion((0,)),),
            text_display_hints=(_text_display_hint((0, 0)),),
            line_break_hints=(),
        ),
        replace(
            base,
            text_display_hints=(_text_display_hint((0, 2)),),
        ),
    )
    for document in cases:
        with pytest.raises(ValueError, match="conflict|overlap"):
            XmlDocumentWriter().write_semantic(document, tmp_path / "semantic.xml")


def test_semantic_writer_serializes_subtitle_hint_on_exact_paragraph_path(
    tmp_path: Path,
) -> None:
    title = StructureElement(
        "P",
        "paragraph",
        children=(ContentFragment(0, 11, ("Generic title",)),),
    )
    qualifier = StructureElement(
        "P",
        "paragraph",
        children=(ContentFragment(0, 12, ("(Qualifier)",)),),
    )
    document = TaggedDocument(
        Path("manual.pdf"),
        True,
        "en",
        (),
        (
            StructureElement(
                "Sect",
                "section",
                children=(
                    StructureElement(
                        "Table",
                        "table",
                        children=(
                            StructureElement(
                                "TR",
                                "table_row",
                                children=(
                                    StructureElement(
                                        "TD",
                                        "table_cell",
                                        children=(title, qualifier),
                                    ),
                                ),
                            ),
                        ),
                    ),
                ),
            ),
        ),
        subtitle_hints=(_subtitle_hint((0, 0, 0, 0, 0)),),
    )
    semantic_path = tmp_path / "semantic.xml"

    XmlDocumentWriter().write_semantic(document, semantic_path)

    root = ET.parse(semantic_path).getroot()
    subtitle = root.find("./section/table/table_row/table_cell/paragraph")
    assert subtitle is not None
    assert subtitle.attrib == {
        "display-role": "subtitle",
        "subtitle-reason": "figure_table_title_stronger_than_following_body",
        "font-weight": "600",
        "comparison-body-font-weight": "400",
        "observed-line-count": "2",
    }
    assert "".join(subtitle.itertext()) == "Generic title"
    cell = root.find("./section/table/table_row/table_cell")
    assert cell is not None
    assert [child.tag for child in cell] == ["paragraph", "paragraph"]
    assert "".join(root.itertext()) == "Generic title(Qualifier)"


@pytest.mark.parametrize(
    ("title_parts", "expected_title"),
    (
        (("Arbitrary", "title"), "Arbitrary title"),
        (("正確", "處理"), "正確處理"),
        (("Cafe", "\u0301 title"), "Cafe\u0301 title"),
        (("Repeated  ", "  whitespace"), "Repeated whitespace"),
    ),
    ids=("english-space", "cjk-adjacent", "combining-mark", "repeated-space"),
)
def test_inline_subtitle_offsets_round_trip_through_xml_and_markdown(
    tmp_path: Path,
    title_parts: tuple[str, ...],
    expected_title: str,
) -> None:
    qualifier = "(Arbitrary qualifier)"
    subtitle = StructureElement(
        "P",
        "paragraph",
        children=(
            ContentFragment(
                0,
                11,
                title_parts,
                text_styles=tuple(
                    TextStyle("SamsungOne-600", 6.5) for _ in title_parts
                ),
            ),
            StructureElement("Span", "span", actual_text="\n"),
            ContentFragment(
                0,
                12,
                (qualifier,),
                text_styles=(TextStyle("SamsungOne-400", 6.5),),
            ),
        ),
    )
    figure_cell = StructureElement(
        "TD", "table_cell", children=(StructureElement("Figure", "figure"),)
    )
    text_cell = StructureElement("TD", "table_cell", children=(subtitle,))
    row = StructureElement("TR", "table_row", children=(figure_cell, text_cell))
    table = StructureElement("Table", "table", children=(row,))
    wrapper = StructureElement("P", "paragraph", children=(table,))
    body = StructureElement(
        "P",
        "paragraph",
        children=(
            ContentFragment(
                0,
                13,
                ("Following body",),
                text_styles=(TextStyle("SamsungOne-400", 6.5),),
            ),
        ),
    )
    section = StructureElement("Sect", "section", children=(wrapper, body))
    document = detect_table_subtitles(
        TaggedDocument(Path("manual.pdf"), True, "en", (), (section,))
    )
    raw_path = tmp_path / "raw.xml"
    semantic_path = tmp_path / "semantic.xml"
    markdown_path = tmp_path / "semantic.md"

    writer = XmlDocumentWriter()
    writer.write_raw(document, raw_path)
    writer.write_semantic(document, semantic_path)
    MarkdownDocumentWriter().write(
        semantic_path,
        QualityReport("pass", {}, {}, ()),
        markdown_path,
        source_name="manual.pdf",
    )

    raw = raw_path.read_text(encoding="utf-8")
    subtitle_xml = ET.parse(semantic_path).getroot().find(
        ".//*[@display-role='subtitle']"
    )
    assert subtitle_xml is not None
    assert subtitle_xml.get("title-end-offset") == str(len(expected_title))
    assert subtitle_xml.get("qualifier-start-offset") == str(
        len(expected_title + "\n")
    )
    assert subtitle_xml.get("observed-line-count") == "2"
    markdown = markdown_path.read_text(encoding="utf-8")
    markdown_lines = markdown.splitlines()
    title_line_index = next(
        index
        for index, line in enumerate(markdown_lines)
        if line.strip() == f"**{expected_title}**<br>"
    )
    assert markdown_lines[title_line_index + 1].strip() == qualifier
    assert "title-end-offset" not in raw
    assert "qualifier-start-offset" not in raw


@pytest.mark.parametrize(
    "block_role",
    (
        "list",
        "table",
        "figure",
        "heading",
        "paragraph",
        "caption",
        "section",
        "article",
        "division",
        "unknown",
    ),
)
def test_semantic_writer_rejects_subtitle_paragraph_with_block_descendant(
    tmp_path: Path, block_role: str
) -> None:
    paragraph = StructureElement(
        "P",
        "paragraph",
        children=(
            ContentFragment(0, 1, ("Title",)),
            StructureElement(block_role, block_role),
        ),
    )
    document = TaggedDocument(
        Path("manual.pdf"),
        True,
        "en",
        (),
        (paragraph,),
        subtitle_hints=(_subtitle_hint((0,)),),
    )

    with pytest.raises(ValueError, match="subtitle paragraph must not contain block"):
        XmlDocumentWriter().write_semantic(document, tmp_path / "semantic.xml")


def test_subtitle_display_metadata_never_enters_raw_xml(tmp_path: Path) -> None:
    paragraph = StructureElement(
        "P",
        "paragraph",
        children=(ContentFragment(0, 1, ("Title",)),),
    )
    document = TaggedDocument(
        Path("manual.pdf"),
        True,
        "en",
        (),
        (paragraph,),
        subtitle_hints=(_subtitle_hint((0,)),),
    )
    raw_path = tmp_path / "raw.xml"
    semantic_path = tmp_path / "semantic.xml"

    writer = XmlDocumentWriter()
    writer.write_raw(document, raw_path)
    writer.write_semantic(document, semantic_path)

    raw = raw_path.read_text(encoding="utf-8")
    semantic = semantic_path.read_text(encoding="utf-8")
    assert "display-role" not in raw
    assert "subtitle-reason" not in raw
    assert 'display-role="subtitle"' in semantic


def test_semantic_writer_rejects_duplicate_subtitle_hint_paths(tmp_path: Path) -> None:
    document = TaggedDocument(
        Path("manual.pdf"),
        True,
        "en",
        (),
        (StructureElement("P", "paragraph"),),
        subtitle_hints=(_subtitle_hint((0,)), _subtitle_hint((0,))),
    )

    with pytest.raises(ValueError, match="duplicate subtitle hint path"):
        XmlDocumentWriter().write_semantic(document, tmp_path / "semantic.xml")


def test_semantic_writer_rejects_unresolved_subtitle_hint_path(tmp_path: Path) -> None:
    document = TaggedDocument(
        Path("manual.pdf"),
        True,
        "en",
        (),
        (StructureElement("P", "paragraph"),),
        subtitle_hints=(_subtitle_hint((1,)),),
    )

    with pytest.raises(ValueError, match="unresolved subtitle hint path"):
        XmlDocumentWriter().write_semantic(document, tmp_path / "semantic.xml")


@pytest.mark.parametrize(
    "invalid_path",
    (
        (),
        (False,),
        ("0",),
        (0.0,),
        (-1,),
        [0],
    ),
    ids=("empty", "bool", "string", "float", "negative", "not-tuple"),
)
def test_semantic_writer_rejects_mistyped_subtitle_hint_path_before_writing(
    tmp_path: Path, invalid_path: object
) -> None:
    target = tmp_path / "semantic.xml"
    target.write_text("existing", encoding="utf-8")
    document = TaggedDocument(
        Path("manual.pdf"),
        True,
        "en",
        (),
        (StructureElement("P", "paragraph"),),
        subtitle_hints=(
            _subtitle_hint(cast(tuple[int, ...], invalid_path)),
        ),
    )

    with pytest.raises(ValueError, match="invalid subtitle hint path"):
        XmlDocumentWriter().write_semantic(document, target)

    assert target.read_text(encoding="utf-8") == "existing"
    assert list(tmp_path.glob(".semantic.xml.*.tmp")) == []


@pytest.mark.parametrize(
    "promoted", (False, True), ids=("non-paragraph", "heading")
)
def test_semantic_writer_rejects_invalid_subtitle_target(
    tmp_path: Path, promoted: bool
) -> None:
    target = _list_item() if promoted else StructureElement("Span", "span")
    document = TaggedDocument(
        Path("manual.pdf"),
        True,
        "en",
        (),
        (target,),
        heading_promotions=(_promotion((0,)),) if promoted else (),
        subtitle_hints=(_subtitle_hint((0,)),),
    )

    with pytest.raises(
        ValueError, match="subtitle hint must target an unpromoted paragraph"
    ):
        XmlDocumentWriter().write_semantic(document, tmp_path / "semantic.xml")


@pytest.mark.parametrize("source_role", ("Title", "Heading2"))
def test_semantic_writer_rejects_manual_subtitle_on_heading_candidate(
    tmp_path: Path, source_role: str
) -> None:
    target = tmp_path / "semantic.xml"
    target.write_text("existing", encoding="utf-8")
    document = TaggedDocument(
        Path("manual.pdf"),
        True,
        "en",
        (),
        (
            StructureElement(
                source_role,
                "paragraph",
                children=(ContentFragment(0, 1, ("Candidate",)),),
            ),
        ),
        subtitle_hints=(_subtitle_hint((0,)),),
    )

    with pytest.raises(ValueError, match="source-role heading candidate"):
        XmlDocumentWriter().write_semantic(document, target)

    assert target.read_text(encoding="utf-8") == "existing"
    assert list(tmp_path.glob(".semantic.xml.*.tmp")) == []


def test_semantic_writer_rejects_duplicate_promotion_paths(tmp_path: Path) -> None:
    document = TaggedDocument(
        Path("manual.pdf"),
        True,
        "en",
        (),
        (_list_item(),),
        heading_promotions=(_promotion((0,)), _promotion((0,))),
    )

    with pytest.raises(ValueError, match="duplicate heading promotion path"):
        XmlDocumentWriter().write_semantic(document, tmp_path / "semantic.xml")


def test_semantic_writer_rejects_unresolved_promotion_path(tmp_path: Path) -> None:
    document = TaggedDocument(
        Path("manual.pdf"),
        True,
        "en",
        (),
        (_list_item(),),
        heading_promotions=(_promotion((1,)),),
    )

    with pytest.raises(ValueError, match="unresolved heading promotion path"):
        XmlDocumentWriter().write_semantic(document, tmp_path / "semantic.xml")


@pytest.mark.parametrize(
    "target",
    (
        StructureElement("P", "paragraph"),
        ContentFragment(0, 1, ("not an element",)),
    ),
    ids=("wrong-semantic-role", "content-fragment"),
)
def test_semantic_writer_rejects_wrong_promotion_target(
    tmp_path: Path,
    target: StructureElement | ContentFragment,
) -> None:
    document = TaggedDocument(
        Path("manual.pdf"),
        True,
        "en",
        (),
        (target,),
        heading_promotions=(_promotion((0,)),),
    )

    with pytest.raises(ValueError, match="must target a list_item StructureElement"):
        XmlDocumentWriter().write_semantic(document, tmp_path / "semantic.xml")


def test_numbered_heading_promotion_changes_only_semantic_xml(
    tmp_path: Path,
) -> None:
    item = StructureElement(
        source_role="LI",
        semantic_role="list_item",
        children=(
            StructureElement(
                "Lbl",
                "label",
                children=(ContentFragment(0, 31, ("03",)),),
            ),
            StructureElement(
                "LBody",
                "list_body",
                children=(
                    ContentFragment(0, 32, ("Troubleshooting and Maintenance",)),
                ),
            ),
        ),
    )
    document = TaggedDocument(
        Path("manual.pdf"),
        True,
        "en",
        (),
        (StructureElement("L", "list", children=(item,)),),
        heading_promotions=(
            _promotion((0, 0), "Troubleshooting and Maintenance"),
        ),
    )
    raw_path = tmp_path / "raw.xml"
    semantic_path = tmp_path / "semantic.xml"

    writer = XmlDocumentWriter()
    writer.write_raw(document, raw_path)
    writer.write_semantic(document, semantic_path)

    raw_root = ET.parse(raw_path).getroot()
    semantic_root = ET.parse(semantic_path).getroot()
    raw_item = raw_root.find(".//element[@semantic-role='list_item']")
    semantic_heading = semantic_root.find(".//heading")

    assert raw_item is not None
    assert raw_item.attrib == {
        "source-role": "LI",
        "semantic-role": "list_item",
    }
    assert "promotion-reason" not in raw_item.attrib
    assert semantic_heading is not None
    assert semantic_heading.attrib == {
        "level": "2",
        "source-role": "LI",
        "promotion-reason": "numbered_chapter_structure_sequence_typography",
        "series-index": "0",
        "heading-font-size": "16",
        "body-font-size": "7",
        "font-size-ratio": "2.285714",
        "heading-font-names": '["SamsungOne-600","SamsungOne-Bold"]',
        "body-font-names": '["SamsungOne-400"]',
    }
    assert [child.tag for child in semantic_heading] == ["label", "list_body"]
    assert [text.attrib["mcid"] for text in semantic_heading.findall(".//text")] == [
        "31",
        "32",
    ]
    assert "".join(semantic_heading.itertext()) == (
        "03Troubleshooting and Maintenance"
    )


def test_semantic_heading_emits_empty_font_name_evidence(tmp_path: Path) -> None:
    document = TaggedDocument(
        Path("manual.pdf"),
        True,
        "en",
        (),
        (_list_item(),),
        heading_promotions=(
            HeadingPromotion(
                child_path=(0,),
                level=2,
                label="03",
                title="Troubleshooting",
                series_index=0,
                heading_font_size=16.0,
                body_font_size=7.0,
                font_size_ratio=16 / 7,
                promotion_reason="numbered_chapter_structure_sequence_typography",
            ),
        ),
    )
    semantic_path = tmp_path / "semantic.xml"

    XmlDocumentWriter().write_semantic(document, semantic_path)

    heading = ET.parse(semantic_path).getroot().find(".//heading")
    assert heading is not None
    assert heading.attrib["heading-font-names"] == "[]"
    assert heading.attrib["body-font-names"] == "[]"


def test_xml_round_trip_preserves_hierarchy_and_exact_unicode_osd_path(
    tmp_path: Path,
) -> None:
    fragment = ContentFragment(
        page_index=0,
        mcid=8,
        text_parts=("Settings > General", " → Accessibility & Help"),
    )
    heading = StructureElement(
        source_role="H2",
        semantic_role="heading",
        heading_level=2,
        children=(fragment,),
    )
    document = TaggedDocument(
        source_path=tmp_path / "sample.pdf",
        marked=True,
        language="en",
        role_map=(),
        children=(heading,),
    )
    raw_path = tmp_path / "nested" / "raw.xml"
    semantic_path = tmp_path / "nested" / "semantic.xml"

    writer = XmlDocumentWriter()
    writer.write_raw(document, raw_path)
    decisions = writer.write_semantic(document, semantic_path)

    raw = ET.parse(raw_path).getroot()
    assert "".join(raw.itertext()) == fragment.text
    assert [part.text for part in raw.findall("./element/fragment/part")] == list(
        fragment.text_parts
    )

    semantic = ET.parse(semantic_path).getroot()
    heading_xml = semantic.find("heading")
    assert heading_xml is not None
    assert heading_xml.attrib["level"] == "2"
    assert "".join(semantic.itertext()) == "Settings > General → Accessibility & Help"
    assert decisions == (
        {
            "page_index": 0,
            "mcid": 8,
            "element_path": "/heading[0]",
            "fragment_child_index": 0,
            "boundary": 0,
            "action": "trim_left",
        },
    )


def test_raw_and_semantic_fragments_serialize_resolved_union_bbox(
    tmp_path: Path,
) -> None:
    fragment = ContentFragment(
        page_index=2,
        mcid=7,
        text_parts=("First", "Second"),
        text_bboxes=(
            (10.0, 20.0, 20.0, 30.0),
            (15.0, 24.0, 30.0, 32.0),
        ),
    )
    document = TaggedDocument(Path("geometry.pdf"), True, "en", (), (fragment,))
    raw_path = tmp_path / "raw.xml"
    semantic_path = tmp_path / "semantic.xml"

    writer = XmlDocumentWriter()
    writer.write_raw(document, raw_path)
    writer.write_semantic(document, semantic_path)

    raw_fragment = ET.parse(raw_path).getroot().find("fragment")
    semantic_text = ET.parse(semantic_path).getroot().find("text")
    assert raw_fragment is not None
    assert semantic_text is not None
    assert raw_fragment.attrib["bbox"] == "10,20,30,32"
    assert semantic_text.attrib["bbox"] == "10,20,30,32"
    assert [part.text for part in raw_fragment.findall("part")] == ["First", "Second"]
    assert "".join(raw_fragment.itertext()) == fragment.text
    assert semantic_text.text == "First Second"


def test_fragment_bbox_serialization_preserves_tiny_positive_extent(
    tmp_path: Path,
) -> None:
    fragment = ContentFragment(
        page_index=2,
        mcid=7,
        text_parts=("Text",),
        text_bboxes=((10.0, 20.0, 10.0000001, 20.0000001),),
    )
    document = TaggedDocument(
        Path("tiny-geometry.pdf"), True, "en", (), (fragment,)
    )
    raw_path = tmp_path / "raw.xml"
    semantic_path = tmp_path / "semantic.xml"

    writer = XmlDocumentWriter()
    writer.write_raw(document, raw_path)
    writer.write_semantic(document, semantic_path)

    for element in (
        ET.parse(raw_path).getroot().find("fragment"),
        ET.parse(semantic_path).getroot().find("text"),
    ):
        assert element is not None
        assert element.attrib["bbox"] == "10,20,10.0000001,20.0000001"
        left, bottom, right, top = map(float, element.attrib["bbox"].split(","))
        assert right > left
        assert top > bottom


@pytest.mark.parametrize("write_method", ["write_raw", "write_semantic"])
def test_xml_writer_rejects_malformed_fragment_geometry_before_writing(
    tmp_path: Path,
    write_method: str,
) -> None:
    fragment = ContentFragment(
        page_index=2,
        mcid=7,
        text_parts=("Text",),
        text_bboxes=((10.0, 20.0, 10.0, 32.0),),
    )
    document = TaggedDocument(
        Path("invalid-geometry.pdf"), True, "en", (), (fragment,)
    )
    target = tmp_path / f"{write_method}.xml"
    target.write_text("sentinel", encoding="utf-8")

    with pytest.raises(ValueError, match=r"invalid fragment bbox at \(0,\)"):
        getattr(XmlDocumentWriter(), write_method)(document, target)

    assert target.read_text(encoding="utf-8") == "sentinel"


def test_fragment_without_geometry_omits_bbox_attribute(tmp_path: Path) -> None:
    fragment = ContentFragment(
        page_index=2,
        mcid=7,
        text_parts=("Text",),
        text_bboxes=(None,),
    )
    document = TaggedDocument(Path("no-geometry.pdf"), True, "en", (), (fragment,))
    raw_path = tmp_path / "raw.xml"
    semantic_path = tmp_path / "semantic.xml"

    writer = XmlDocumentWriter()
    writer.write_raw(document, raw_path)
    writer.write_semantic(document, semantic_path)

    raw_fragment = ET.parse(raw_path).getroot().find("fragment")
    semantic_text = ET.parse(semantic_path).getroot().find("text")
    assert raw_fragment is not None
    assert semantic_text is not None
    assert "bbox" not in raw_fragment.attrib
    assert "bbox" not in semantic_text.attrib


def test_geometry_does_not_change_complete_markdown_output(
    tmp_path: Path,
) -> None:
    source_text = "Settings > Support"
    fragment = ContentFragment(
        page_index=0,
        mcid=8,
        text_parts=(source_text,),
        text_bboxes=((10.0, 20.0, 30.0, 32.0),),
    )
    document = TaggedDocument(Path("geometry.pdf"), True, "en", (), (fragment,))
    document_without_geometry = replace(
        document,
        children=(replace(fragment, text_bboxes=()),),
    )
    semantic_path = tmp_path / "semantic-with-geometry.xml"
    semantic_without_geometry_path = tmp_path / "semantic-without-geometry.xml"
    markdown_path = tmp_path / "with-geometry.md"
    markdown_without_geometry_path = tmp_path / "without-geometry.md"

    writer = XmlDocumentWriter()
    writer.write_semantic(document, semantic_path)
    writer.write_semantic(document_without_geometry, semantic_without_geometry_path)
    semantic_text = ET.parse(semantic_path).getroot().find("text")
    assert semantic_text is not None
    assert semantic_text.attrib["bbox"] == "10,20,30,32"
    assert semantic_text.text == source_text

    report = QualityReport("pass", {}, {}, ())
    markdown_writer = MarkdownDocumentWriter()
    markdown_writer.write(
        semantic_path, report, markdown_path, source_name="geometry.pdf"
    )
    markdown_writer.write(
        semantic_without_geometry_path,
        report,
        markdown_without_geometry_path,
        source_name="geometry.pdf",
    )

    assert markdown_path.read_bytes() == markdown_without_geometry_path.read_bytes()


def test_populated_text_styles_are_not_serialized_to_xml_yet(tmp_path: Path) -> None:
    fragment = ContentFragment(
        page_index=3,
        mcid=7,
        text_parts=("03", "Title"),
        object_ref="12 0 R",
        text_styles=(
            TextStyle("SamsungOne-600", 16.0),
            TextStyle("SamsungOne-600", 16.0),
        ),
    )
    document = TaggedDocument(Path("styled.pdf"), True, "en", (), (fragment,))
    raw_path = tmp_path / "raw.xml"
    semantic_path = tmp_path / "semantic.xml"

    writer = XmlDocumentWriter()
    writer.write_raw(document, raw_path)
    writer.write_semantic(document, semantic_path)

    raw = ET.parse(raw_path).getroot()
    raw_fragment = raw.find("fragment")
    assert raw.attrib == {"source": "styled.pdf", "marked": "true", "language": "en"}
    assert raw_fragment is not None
    assert raw_fragment.attrib == {
        "page-index": "3",
        "mcid": "7",
        "object-ref": "12 0 R",
    }
    assert [child.tag for child in raw_fragment] == ["part", "part"]
    assert [child.text for child in raw_fragment] == ["03", "Title"]

    semantic = ET.parse(semantic_path).getroot()
    semantic_text = semantic.find("text")
    assert semantic.attrib == {}
    assert semantic_text is not None
    assert semantic_text.attrib == {
        "page-index": "3",
        "mcid": "7",
        "object-ref": "12 0 R",
    }
    assert list(semantic_text) == []
    assert semantic_text.text == "03 Title"


def test_preserves_mixed_interleaved_order_and_unknown_source_role(
    tmp_path: Path,
) -> None:
    first = ContentFragment(2, 3, ("before",), object_ref="10 0 R")
    nested_fragment = ContentFragment(2, 4, ("inside",), object_ref="11 0 R")
    unknown = StructureElement(
        source_role="Samsung:Box & Panel",
        semantic_role="unknown",
        object_ref="12 0 R",
        children=(nested_fragment,),
    )
    last = ContentFragment(2, 5, ("after",), object_ref="13 0 R")
    paragraph = StructureElement(
        source_role="P",
        semantic_role="paragraph",
        children=(first, unknown, last),
    )
    document = TaggedDocument(Path("manual.pdf"), True, None, (), (paragraph,))
    raw_path = tmp_path / "raw.xml"
    semantic_path = tmp_path / "semantic.xml"

    writer = XmlDocumentWriter()
    writer.write_raw(document, raw_path)
    writer.write_semantic(document, semantic_path)

    raw_paragraph = ET.parse(raw_path).getroot().find("element")
    assert raw_paragraph is not None
    assert [child.tag for child in raw_paragraph] == ["fragment", "element", "fragment"]
    assert raw_paragraph[0].attrib == {
        "page-index": "2",
        "mcid": "3",
        "object-ref": "10 0 R",
    }
    assert raw_paragraph[1].attrib["object-ref"] == "12 0 R"
    assert raw_paragraph[1][0].attrib["object-ref"] == "11 0 R"

    semantic_paragraph = ET.parse(semantic_path).getroot().find("paragraph")
    assert semantic_paragraph is not None
    assert [child.tag for child in semantic_paragraph] == ["text", "unknown", "text"]
    assert semantic_paragraph[1].attrib["source-role"] == "Samsung:Box & Panel"
    assert "".join(semantic_paragraph.itertext()) == "beforeinsideafter"


def test_raw_preserves_document_role_map_and_all_element_metadata(
    tmp_path: Path,
) -> None:
    element = StructureElement(
        source_role="Figure",
        semantic_role="figure",
        heading_level=4,
        object_ref="81 0 R",
        page_index=7,
        title="Controls <Overview>",
        language="ko-KR",
        alternate_text='Use "A&B"',
        actual_text="실제 → 텍스트",
        attributes=(("Placement", "Block"), ("Placement", "Inline & <safe>")),
    )
    document = TaggedDocument(
        source_path=Path("manual & <review>.pdf"),
        marked=False,
        language="en-US",
        role_map=(("Custom&H", "H2"), ("Box", "Div")),
        children=(element,),
    )
    raw_path = tmp_path / "raw.xml"

    XmlDocumentWriter().write_raw(document, raw_path)

    root = ET.parse(raw_path).getroot()
    assert root.attrib == {
        "source": "manual & <review>.pdf",
        "marked": "false",
        "language": "en-US",
    }
    assert [role.attrib for role in root.findall("./role-map/role")] == [
        {"source-role": "Custom&H", "mapped-role": "H2"},
        {"source-role": "Box", "mapped-role": "Div"},
    ]
    element_xml = root.find("element")
    assert element_xml is not None
    assert element_xml.attrib == {
        "source-role": "Figure",
        "semantic-role": "figure",
        "heading-level": "4",
        "object-ref": "81 0 R",
        "page-index": "7",
        "title": "Controls <Overview>",
        "language": "ko-KR",
        "alternate-text": 'Use "A&B"',
        "actual-text": "실제 → 텍스트",
    }
    assert [item.attrib for item in element_xml.findall("./attributes/attribute")] == [
        {"name": "Placement", "value": "Block"},
        {"name": "Placement", "value": "Inline & <safe>"},
    ]
    assert "".join(root.itertext()) == ""


def test_empty_fragment_and_null_identifiers_round_trip(tmp_path: Path) -> None:
    fragment = ContentFragment(page_index=9, mcid=None, text_parts=())
    document = TaggedDocument(Path("empty.pdf"), False, None, (), (fragment,))
    raw_path = tmp_path / "raw.xml"
    semantic_path = tmp_path / "semantic.xml"

    writer = XmlDocumentWriter()
    writer.write_raw(document, raw_path)
    assert writer.write_semantic(document, semantic_path) == ()

    raw_fragment = ET.parse(raw_path).getroot().find("fragment")
    semantic_text = ET.parse(semantic_path).getroot().find("text")
    assert raw_fragment is not None and raw_fragment.attrib == {"page-index": "9"}
    assert list(raw_fragment) == []
    assert semantic_text is not None and semantic_text.attrib == {"page-index": "9"}
    assert semantic_text.text is None


def test_xml_reserved_characters_round_trip_without_source_normalization(
    tmp_path: Path,
) -> None:
    parts = ("<&", " > © ‘설정’ \"도움말\"")
    fragment = ContentFragment(0, 1, parts, object_ref="7 & 0 <R>")
    document = TaggedDocument(Path("reserved.pdf"), True, None, (), (fragment,))
    raw_path = tmp_path / "raw.xml"
    semantic_path = tmp_path / "semantic.xml"

    writer = XmlDocumentWriter()
    writer.write_raw(document, raw_path)
    writer.write_semantic(document, semantic_path)

    raw_fragment = ET.parse(raw_path).getroot().find("fragment")
    semantic_text = ET.parse(semantic_path).getroot().find("text")
    assert raw_fragment is not None
    assert [part.text for part in raw_fragment.findall("part")] == list(parts)
    assert raw_fragment.attrib["object-ref"] == "7 & 0 <R>"
    assert "".join(raw_fragment.itertext()) == fragment.text
    assert semantic_text is not None
    assert semantic_text.text == "<& > © ‘설정’ \"도움말\""


def test_raw_preserves_whitespace_only_parts_exactly(tmp_path: Path) -> None:
    parts = (" ", "\n", "\t")
    fragment = ContentFragment(page_index=0, mcid=8, text_parts=parts)
    document = TaggedDocument(Path("whitespace.pdf"), True, None, (), (fragment,))
    raw_path = tmp_path / "raw.xml"

    XmlDocumentWriter().write_raw(document, raw_path)

    raw_fragment = ET.parse(raw_path).getroot().find("fragment")
    assert raw_fragment is not None
    assert [part.text for part in raw_fragment.findall("part")] == list(parts)
    assert "".join(raw_fragment.itertext()) == fragment.text


def test_semantic_structural_part_removes_indentation_from_itertext(
    tmp_path: Path,
) -> None:
    fragment = ContentFragment(page_index=1, mcid=4, text_parts=("Nested content",))
    structural_part = StructureElement(
        source_role="Part",
        semantic_role="part",
        children=(fragment,),
    )
    document = TaggedDocument(
        Path("semantic-part.pdf"), True, None, (), (structural_part,)
    )
    semantic_path = tmp_path / "semantic.xml"

    XmlDocumentWriter().write_semantic(document, semantic_path)

    semantic = ET.parse(semantic_path).getroot()
    assert semantic.find("part/text") is not None
    assert "".join(semantic.itertext()) == fragment.text


def test_raw_preserves_cr_crlf_and_literal_character_reference_text(
    tmp_path: Path,
) -> None:
    parts = ("\r", "\r\n", "literal &#13; remains text")
    fragment = ContentFragment(page_index=3, mcid=6, text_parts=parts)
    document = TaggedDocument(Path("carriage-return.pdf"), True, None, (), (fragment,))
    raw_path = tmp_path / "raw.xml"

    XmlDocumentWriter().write_raw(document, raw_path)

    raw_fragment = ET.parse(raw_path).getroot().find("fragment")
    assert raw_fragment is not None
    assert [part.text for part in raw_fragment.findall("part")] == list(parts)
    assert "".join(raw_fragment.itertext()) == fragment.text
    serialized = raw_path.read_bytes()
    assert b"&#13;" in serialized
    assert b"literal &amp;#13; remains text" in serialized


def test_semantic_preserves_carriage_returns_in_serialized_text(tmp_path: Path) -> None:
    source_text = "first\rsecond\r\nthird"
    fragment = ContentFragment(page_index=4, mcid=7, text_parts=(source_text,))
    document = TaggedDocument(Path("semantic-cr.pdf"), True, None, (), (fragment,))
    semantic_path = tmp_path / "semantic.xml"

    XmlDocumentWriter().write_semantic(document, semantic_path)

    semantic = ET.parse(semantic_path).getroot()
    semantic_text = semantic.find("text")
    assert semantic_text is not None
    assert semantic_text.text == source_text
    assert "".join(semantic.itertext()) == source_text


def test_control_nodes_preserve_forbidden_xml_characters_in_raw_and_semantic(
    tmp_path: Path,
) -> None:
    source_text = "A\x01B\x02C\x07D\x0eE\x00F"
    fragment = ContentFragment(page_index=5, mcid=9, text_parts=(source_text, "tail"))
    document = TaggedDocument(Path("controls.pdf"), True, None, (), (fragment,))
    raw_path = tmp_path / "raw.xml"
    semantic_path = tmp_path / "semantic.xml"

    writer = XmlDocumentWriter()
    writer.write_raw(document, raw_path)
    writer.write_semantic(document, semantic_path)

    raw_parts = ET.parse(raw_path).getroot().findall("fragment/part")
    semantic_text = ET.parse(semantic_path).getroot().find("text")
    assert len(raw_parts) == 2
    assert semantic_text is not None
    expected_codes = ["0001", "0002", "0007", "000E", "0000"]
    assert [node.attrib["code"] for node in raw_parts[0].findall("control")] == expected_codes
    assert [node.attrib["code"] for node in semantic_text.findall("control")] == expected_codes
    assert [xml_writer_module.decode_data_element(part) for part in raw_parts] == [
        source_text,
        "tail",
    ]
    assert xml_writer_module.decode_data_element(semantic_text) == f"{source_text} tail"


def test_invalid_metadata_and_source_attributes_use_reversible_base64(
    tmp_path: Path,
) -> None:
    source_role = "P\x01"
    title = "Title\x02"
    attribute_name = "Key\x07"
    attribute_value = "Value\x0e"
    element = StructureElement(
        source_role=source_role,
        semantic_role="paragraph",
        title=title,
        attributes=((attribute_name, attribute_value),),
    )
    document = TaggedDocument(
        Path("source.pdf"),
        True,
        "en\x00US",
        (("Role\x01", "P\x02"),),
        (element,),
    )
    raw_path = tmp_path / "raw.xml"
    semantic_path = tmp_path / "semantic.xml"

    writer = XmlDocumentWriter()
    writer.write_raw(document, raw_path)
    writer.write_semantic(document, semantic_path)

    raw = ET.parse(raw_path).getroot()
    assert raw.attrib["language-encoding"] == "base64-utf8"
    assert base64.b64decode(raw.attrib["language"]).decode("utf-8") == "en\x00US"
    raw_element = raw.find("element")
    assert raw_element is not None
    assert raw_element.attrib["source-role-encoding"] == "base64-utf8"
    assert base64.b64decode(raw_element.attrib["source-role"]).decode("utf-8") == source_role
    assert raw_element.attrib["title-encoding"] == "base64-utf8"
    assert base64.b64decode(raw_element.attrib["title"]).decode("utf-8") == title
    source_attribute = raw_element.find("attributes/attribute")
    assert source_attribute is not None
    assert source_attribute.attrib["name-encoding"] == "base64-utf8"
    assert source_attribute.attrib["value-encoding"] == "base64-utf8"
    assert base64.b64decode(source_attribute.attrib["name"]).decode("utf-8") == attribute_name
    assert base64.b64decode(source_attribute.attrib["value"]).decode("utf-8") == attribute_value


def test_failed_structural_validation_is_atomic_and_preserves_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fragment = ContentFragment(page_index=0, mcid=1, text_parts=("A", "B"))
    document = TaggedDocument(Path("boundaries.pdf"), True, None, (), (fragment,))
    raw_path = tmp_path / "raw.xml"
    raw_path.write_text("existing destination", encoding="utf-8")
    original_tostring = xml_writer_module.ET.tostring

    def collapse_part_boundary(*args: object, **kwargs: object) -> bytes:
        serialized = original_tostring(*args, **kwargs)
        return serialized.replace(b"<part>A</part><part>B</part>", b"<part>AB</part>")

    monkeypatch.setattr(xml_writer_module.ET, "tostring", collapse_part_boundary)

    with pytest.raises(ValueError, match="structural round trip mismatch"):
        XmlDocumentWriter().write_raw(document, raw_path)

    assert raw_path.read_text(encoding="utf-8") == "existing destination"
    assert list(tmp_path.glob(".raw.xml.*.tmp")) == []


def test_join_decisions_distinguish_sibling_fragments_with_null_mcids(
    tmp_path: Path,
) -> None:
    first = ContentFragment(0, None, ("first", "fragment"))
    second = ContentFragment(0, None, ("second", "fragment"))
    paragraph = StructureElement("P", "paragraph", children=(first, second))
    document = TaggedDocument(Path("decisions.pdf"), True, None, (), (paragraph,))

    decisions = XmlDocumentWriter().write_semantic(document, tmp_path / "semantic.xml")

    assert [decision["fragment_child_index"] for decision in decisions] == [0, 1]
    assert [decision["element_path"] for decision in decisions] == [
        "/paragraph[0]",
        "/paragraph[0]",
    ]
    assert [decision["mcid"] for decision in decisions] == [None, None]


def test_raw_preserves_whitespace_only_tail_after_control(tmp_path: Path) -> None:
    source_text = "A\x01 "
    fragment = ContentFragment(0, 1, (source_text,))
    document = TaggedDocument(Path("raw-tail.pdf"), True, None, (), (fragment,))
    raw_path = tmp_path / "raw.xml"

    XmlDocumentWriter().write_raw(document, raw_path)

    raw_part = ET.parse(raw_path).getroot().find("fragment/part")
    assert raw_part is not None
    assert xml_writer_module.decode_data_element(raw_part) == source_text
    control = raw_part.find("control")
    assert control is not None and control.tail == " "


def test_semantic_preserves_newline_tail_after_control(tmp_path: Path) -> None:
    source_text = "A\x01\n"
    fragment = ContentFragment(0, 2, (source_text,))
    document = TaggedDocument(
        Path("semantic-tail.pdf"), True, None, (), (fragment,)
    )
    semantic_path = tmp_path / "semantic.xml"

    XmlDocumentWriter().write_semantic(document, semantic_path)

    semantic_text = ET.parse(semantic_path).getroot().find("text")
    assert semantic_text is not None
    assert xml_writer_module.decode_data_element(semantic_text) == source_text
    control = semantic_text.find("control")
    assert control is not None and control.tail == "\n"


def test_lone_surrogate_metadata_round_trips_with_explicit_encoding(
    tmp_path: Path,
) -> None:
    title = "before\ud800after"
    element = StructureElement("P", "paragraph", title=title)
    document = TaggedDocument(Path("surrogate.pdf"), True, None, (), (element,))
    raw_path = tmp_path / "raw.xml"
    semantic_path = tmp_path / "semantic.xml"

    writer = XmlDocumentWriter()
    writer.write_raw(document, raw_path)
    writer.write_semantic(document, semantic_path)

    raw_element = ET.parse(raw_path).getroot().find("element")
    semantic_element = ET.parse(semantic_path).getroot().find("paragraph")
    assert raw_element is not None
    assert semantic_element is not None
    for serialized_element in (raw_element, semantic_element):
        assert (
            serialized_element.attrib["title-encoding"]
            == "base64-utf8-surrogatepass"
        )
        encoded = base64.b64decode(serialized_element.attrib["title"])
        assert encoded.decode("utf-8", errors="surrogatepass") == title


def test_partial_temporary_write_failure_removes_orphan_and_leaves_no_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destination = tmp_path / "raw.xml"
    partial_path = tmp_path / ".raw.xml.partial.tmp"
    fragment = ContentFragment(0, 1, ("content",))
    document = TaggedDocument(Path("write-failure.pdf"), True, None, (), (fragment,))

    class PartialTemporaryFile:
        def __init__(self) -> None:
            self.name = str(partial_path)
            self.handle = None

        def __enter__(self) -> "PartialTemporaryFile":
            self.handle = partial_path.open("wb")
            return self

        def write(self, data: bytes) -> None:
            assert self.handle is not None
            self.handle.write(data[:16])
            self.handle.flush()
            raise OSError("simulated temporary write failure")

        def __exit__(self, *args: object) -> None:
            assert self.handle is not None
            self.handle.close()

    monkeypatch.setattr(
        xml_writer_module.tempfile,
        "NamedTemporaryFile",
        lambda **kwargs: PartialTemporaryFile(),
    )

    with pytest.raises(OSError, match="simulated temporary write failure"):
        XmlDocumentWriter().write_raw(document, destination)

    assert not destination.exists()
    assert not partial_path.exists()
