from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import MappingProxyType
from typing import Any, cast

import pytest

from tagged_pdf_extractor.domain.display_hint_validation import (
    validate_review_formatting_hints,
)
from tagged_pdf_extractor.domain.models import (
    ContentFragment,
    ContinuationHint,
    ContinuationTypographyEvidence,
    HeadingPromotion,
    InlineIconHint,
    LineBreakHint,
    SentenceBreakHint,
    StructureElement,
    SubtitleHint,
    TaggedDocument,
    TextDisplayHint,
    TextStyle,
)
from tagged_pdf_extractor.domain.list_continuation_detection import (
    detect_list_continuation_hints,
)
from tagged_pdf_extractor.domain.readability_formatting import (
    detect_inline_icon_hints,
    detect_sentence_break_hints,
)
from tagged_pdf_extractor.domain.subtitle_detection import detect_subtitle_hints
from tagged_pdf_extractor.domain import display_hint_validation as validation_module


def _element(
    semantic_role: str,
    *children: StructureElement | ContentFragment,
    source_role: str = "P",
    actual_text: str | None = None,
) -> StructureElement:
    return StructureElement(
        source_role=source_role,
        semantic_role=semantic_role,
        actual_text=actual_text,
        children=children,
    )


def _fragment(text: str) -> ContentFragment:
    return ContentFragment(page_index=0, mcid=1, text_parts=(text,))


def _continuation_document() -> TaggedDocument:
    def styled(text: str, mcid: int, bbox: tuple[float, float, float, float]) -> ContentFragment:
        return ContentFragment(
            0,
            mcid,
            (text,),
            text_styles=(TextStyle("Body-Regular", 8.0),),
            text_bboxes=(bbox,),
        )

    def list_element(marker_mcid: int, body_mcid: int, top: float) -> StructureElement:
        label = _element(
            "label",
            styled("bullet", marker_mcid, (88.0, top, 96.0, top + 8.0)),
            source_role="Lbl",
        )
        body = _element(
            "list_body",
            styled("Body one", body_mcid, (100.0, top, 180.0, top + 8.0)),
            styled("Body two", body_mcid + 1, (100.0, top - 12.0, 180.0, top - 4.0)),
            source_role="LBody",
        )
        return _element(
            "list",
            _element("list_item", label, body, source_role="LI"),
            source_role="L",
        )

    section = _element(
        "section",
        list_element(10, 11, 200.0),
        _element(
            "paragraph",
            styled("Continuation text", 20, (100.0, 176.0, 180.0, 184.0)),
            source_role="LBody",
        ),
        list_element(30, 31, 164.0),
        source_role="Sect",
    )
    source = TaggedDocument(Path("manual.pdf"), True, "en", (), (section,))
    return replace(source, continuation_hints=detect_list_continuation_hints(source))


def test_continuation_hints_are_redetected_and_exposed_as_immutable_mapping() -> None:
    document = _continuation_document()

    validated = validate_review_formatting_hints(document)

    hint = document.continuation_hints[0]
    assert validated.continuation_by_path == {hint.child_path: hint}
    with pytest.raises(TypeError):
        validated.continuation_by_path[hint.child_path] = hint  # type: ignore[index]


def test_continuation_hint_tampering_is_rejected() -> None:
    document = _continuation_document()
    hint = replace(document.continuation_hints[0], vertical_gap=3.0)

    with pytest.raises(ValueError, match="continuation hint detector mismatch"):
        validate_review_formatting_hints(
            replace(document, continuation_hints=(hint,))
        )


def test_duplicate_continuation_targets_are_rejected() -> None:
    document = _continuation_document()
    hint = document.continuation_hints[0]

    with pytest.raises(ValueError, match="duplicate continuation hint path"):
        validate_review_formatting_hints(
            replace(document, continuation_hints=(hint, hint))
        )


@pytest.mark.parametrize(
    ("child_path", "message"),
    [
        ((9,), "unresolved continuation hint path"),
        ((0, 1, 0), "continuation hint must target a StructureElement"),
    ],
)
def test_continuation_target_path_must_resolve_to_element(
    child_path: tuple[int, ...], message: str
) -> None:
    document = _continuation_document()
    hint = replace(document.continuation_hints[0], child_path=child_path)

    with pytest.raises(ValueError, match=message):
        validate_review_formatting_hints(replace(document, continuation_hints=(hint,)))


@pytest.mark.parametrize(
    ("field_name", "path", "message"),
    [
        ("preceding_list_item_path", (0, 0), "predecessor must resolve to list_item"),
        ("preceding_list_body_path", (0, 0, 0, 0), "predecessor body must resolve to list_body"),
        ("preceding_list_body_path", (9,), "unresolved continuation predecessor body path"),
    ],
)
def test_continuation_predecessor_paths_must_resolve_to_expected_roles(
    field_name: str, path: tuple[int, ...], message: str
) -> None:
    document = _continuation_document()
    hint = replace(document.continuation_hints[0], **{field_name: path})

    with pytest.raises(ValueError, match=message):
        validate_review_formatting_hints(replace(document, continuation_hints=(hint,)))


def test_continuation_cross_page_evidence_is_rejected() -> None:
    document = _continuation_document()
    section = document.children[0]
    assert isinstance(section, StructureElement)
    preceding = section.children[0]
    assert isinstance(preceding, StructureElement)
    item = preceding.children[0]
    assert isinstance(item, StructureElement)
    body = item.children[1]
    assert isinstance(body, StructureElement)
    changed_body = replace(
        body,
        children=tuple(
            replace(child, page_index=1)
            if isinstance(child, ContentFragment)
            else child
            for child in body.children
        ),
    )
    changed = replace(
        document,
        children=(
            replace(
                section,
                children=(
                    replace(preceding, children=(replace(item, children=(item.children[0], changed_body)),)),
                    section.children[1],
                    section.children[2],
                ),
            ),
        ),
    )

    with pytest.raises(ValueError, match="cross-page continuation evidence"):
        validate_review_formatting_hints(changed)


def test_continuation_malformed_typography_evidence_is_rejected() -> None:
    document = _continuation_document()
    hint = document.continuation_hints[0]
    malformed = replace(
        hint,
        typography_evidence=replace(
            hint.typography_evidence,
            target_observed_lines=((True, 20),),
        ),
    )

    with pytest.raises(ValueError, match="invalid continuation typography evidence"):
        validate_review_formatting_hints(
            replace(document, continuation_hints=(malformed,))
        )


@pytest.mark.parametrize(
    "conflict",
    ["heading", "promotion", "subtitle", "strong_label", "sentence_break"],
)
def test_continuation_conflicts_with_other_display_hints_are_rejected(
    conflict: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = _continuation_document()
    target_path = document.continuation_hints[0].child_path
    if conflict == "heading":
        section = document.children[0]
        assert isinstance(section, StructureElement)
        target = section.children[1]
        assert isinstance(target, StructureElement)
        changed_target = replace(target, source_role="Heading2")
        document = replace(
            document,
            children=(
                replace(
                    section,
                    children=(section.children[0], changed_target, section.children[2]),
                ),
            ),
            continuation_hints=(
                replace(document.continuation_hints[0], source_role="Heading2"),
            ),
        )
    elif conflict == "promotion":
        document = replace(
            document,
            heading_promotions=(
                HeadingPromotion(
                    target_path,
                    2,
                    "01",
                    "Title",
                    0,
                    9.0,
                    8.0,
                    1.125,
                    "numbered_chapter_structure_sequence_typography",
                ),
            ),
        )
    elif conflict == "subtitle":
        document = replace(document, subtitle_hints=(SubtitleHint(target_path, 600, 400, 1),))
    elif conflict == "strong_label":
        document = replace(
            document,
            text_display_hints=(
                TextDisplayHint(target_path, "strong_label", 600, 9.0, 400, 8.0, "test"),
            ),
        )
    else:
        fragment_path = (*target_path, 0)
        sentence = SentenceBreakHint(fragment_path, (0,))
        document = replace(document, sentence_break_hints=(sentence,))
        monkeypatch.setattr(
            validation_module,
            "detect_sentence_break_hints",
            lambda actual: (sentence,),
        )

    with pytest.raises(ValueError, match=f"{conflict.replace('_', ' ')} conflict for continuation hint"):
        validate_review_formatting_hints(document)


@pytest.mark.parametrize(
    "bbox",
    [
        (0.0, 0.0, float("nan"), 1.0),
        (0.0, 0.0, float("inf"), 1.0),
        (2.0, 0.0, 1.0, 1.0),
        (0.0, 2.0, 1.0, 1.0),
        (0.0, 0.0, 0.0, 1.0),
        (0.0, 0.0, 1.0, 0.0),
    ],
)
def test_fragment_geometry_validation_rejects_malformed_box(
    bbox: tuple[float, float, float, float],
) -> None:
    fragment = ContentFragment(
        page_index=0,
        mcid=1,
        text_parts=("Text",),
        text_bboxes=(bbox,),
    )

    with pytest.raises(ValueError, match=r"invalid fragment bbox at \(0,\)"):
        validate_review_formatting_hints(_document(fragment))


@pytest.mark.parametrize("text_bboxes", [(), (None,)])
def test_fragment_geometry_validation_accepts_absent_box(
    text_bboxes: tuple[None, ...],
) -> None:
    fragment = ContentFragment(
        page_index=0,
        mcid=1,
        text_parts=("Text",),
        text_bboxes=text_bboxes,
    )

    validate_review_formatting_hints(_document(fragment))


def _styled_fragment(text: str, *, mcid: int = 1) -> ContentFragment:
    return ContentFragment(
        page_index=3,
        mcid=mcid,
        text_parts=(text,),
        text_styles=(TextStyle("Synthetic", 6.5),),
    )


def _figure() -> StructureElement:
    return StructureElement(
        source_role="Figure",
        semantic_role="figure",
        page_index=3,
        alternate_text="Smart Hub",
        attributes=(("/BBox", "[100.0, 200.0, 109.0, 209.0]"),),
    )


def _document(*children: StructureElement | ContentFragment) -> TaggedDocument:
    return TaggedDocument(
        source_path=Path("sample.pdf"),
        marked=True,
        language="ENG",
        role_map=(),
        children=children,
    )


def _resolve_path(
    document: TaggedDocument, path: tuple[int, ...]
) -> StructureElement | ContentFragment:
    siblings = document.children
    for depth, component in enumerate(path):
        target = siblings[component]
        if depth < len(path) - 1:
            assert isinstance(target, StructureElement)
            siblings = target.children
    return target


def _replace_path(
    document: TaggedDocument,
    path: tuple[int, ...],
    replacement: StructureElement | ContentFragment,
) -> TaggedDocument:
    def replace_child(
        siblings: tuple[StructureElement | ContentFragment, ...],
        remaining: tuple[int, ...],
    ) -> tuple[StructureElement | ContentFragment, ...]:
        index = remaining[0]
        changed = list(siblings)
        if len(remaining) == 1:
            changed[index] = replacement
        else:
            parent = changed[index]
            assert isinstance(parent, StructureElement)
            changed[index] = replace(
                parent,
                children=replace_child(parent.children, remaining[1:]),
            )
        return tuple(changed)

    return replace(document, children=replace_child(document.children, path))


def _line_document() -> tuple[TaggedDocument, tuple[int, ...]]:
    newline = _element("span", source_role="Span", actual_text="\n")
    paragraph = _element(
        "paragraph",
        _fragment("first,"),
        newline,
        _fragment("second"),
    )
    document = _document(
        _element(
            "table",
            _element("table_row", _element("table_cell", paragraph)),
            source_role="Table",
        )
    )
    return replace(document, line_break_hints=(LineBreakHint((0, 0, 0, 0, 1)),)), (
        0,
        0,
        0,
        0,
        1,
    )


def _inline_subtitle_document() -> TaggedDocument:
    title = ContentFragment(
        0,
        11,
        ("Arbitrary title",),
        text_styles=(TextStyle("Synthetic-600", 6.5),),
    )
    qualifier = ContentFragment(
        0,
        12,
        ("(Arbitrary qualifier)",),
        text_styles=(TextStyle("Synthetic-400", 6.5),),
    )
    body = ContentFragment(
        0,
        13,
        ("Following body",),
        text_styles=(TextStyle("Synthetic-400", 6.5),),
    )
    paragraph = _element(
        "paragraph",
        title,
        _element("span", source_role="Span", actual_text="\n"),
        qualifier,
    )
    document = _document(
        _element(
            "section",
            _element(
                "paragraph",
                _element(
                    "table",
                    _element(
                        "table_row",
                        _element("table_cell", _element("figure")),
                        _element("table_cell", paragraph),
                    ),
                    source_role="Table",
                ),
            ),
            _element("paragraph", body),
            source_role="Sect",
        )
    )
    return replace(document, subtitle_hints=detect_subtitle_hints(document.children))


def test_inline_subtitle_offsets_are_validated_from_source_boundary() -> None:
    document = _inline_subtitle_document()

    assert document.subtitle_hints[0].observed_line_count == 2
    validate_review_formatting_hints(document)


def test_omitted_detectable_inline_subtitle_hint_is_rejected() -> None:
    document = replace(_inline_subtitle_document(), subtitle_hints=())

    with pytest.raises(ValueError, match="inline subtitle detector mismatch"):
        validate_review_formatting_hints(document)


def test_inline_subtitle_requires_exact_detector_match() -> None:
    paragraph = _element(
        "paragraph",
        ContentFragment(
            0,
            11,
            ("Arbitrary title",),
            text_styles=(TextStyle("Synthetic-600", 6.5),),
        ),
        _element("span", source_role="Span", actual_text="\n"),
        ContentFragment(
            0,
            12,
            ("(Arbitrary qualifier)",),
            text_styles=(TextStyle("Synthetic-400", 6.5),),
        ),
    )
    document = replace(
        _document(paragraph),
        subtitle_hints=(SubtitleHint((0,), 600, 400, 1, title_end_offset=15, qualifier_start_offset=16),),
    )

    with pytest.raises(ValueError, match="inline subtitle detector mismatch"):
        validate_review_formatting_hints(document)


def test_forged_inline_subtitle_without_following_body_is_rejected() -> None:
    document = _inline_subtitle_document()
    section = document.children[0]
    assert isinstance(section, StructureElement)
    forged = replace(
        document,
        children=(replace(section, children=section.children[:1]),),
    )

    with pytest.raises(ValueError, match="inline subtitle detector mismatch"):
        validate_review_formatting_hints(forged)


def test_forged_inline_subtitle_without_relative_typography_is_rejected() -> None:
    document = _inline_subtitle_document()
    title_path = (0, 0, 0, 0, 1, 0, 0)
    title = _resolve_path(document, title_path)
    assert isinstance(title, ContentFragment)
    forged = _replace_path(
        document,
        title_path,
        replace(title, text_styles=(TextStyle("Synthetic-400", 6.5),)),
    )

    with pytest.raises(ValueError, match="inline subtitle detector mismatch"):
        validate_review_formatting_hints(forged)


@pytest.mark.parametrize(
    "changes",
    (
        {"font_weight": 700},
        {"comparison_body_font_weight": 300},
        {"observed_line_count": 1},
        {"reason": "manual"},
    ),
)
def test_inline_subtitle_rejects_tampered_detector_evidence(
    changes: dict[str, object],
) -> None:
    document = _inline_subtitle_document()
    hint = replace(document.subtitle_hints[0], **changes)

    with pytest.raises(ValueError, match="inline subtitle detector mismatch"):
        validate_review_formatting_hints(replace(document, subtitle_hints=(hint,)))


@pytest.mark.parametrize(
    "changes",
    [
        {"title_end_offset": None},
        {"qualifier_start_offset": None},
        {"title_end_offset": True},
        {"qualifier_start_offset": 999},
        {"title_end_offset": 1},
    ],
)
def test_inline_subtitle_rejects_malformed_or_tampered_offsets(
    changes: dict[str, object],
) -> None:
    document = _inline_subtitle_document()
    hint = replace(document.subtitle_hints[0], **changes)

    with pytest.raises(ValueError, match="invalid inline subtitle offsets"):
        validate_review_formatting_hints(replace(document, subtitle_hints=(hint,)))


def test_inline_subtitle_rejects_tampered_source_boundary() -> None:
    document = _inline_subtitle_document()
    paragraph_path = document.subtitle_hints[0].child_path
    paragraph = cast(StructureElement, _resolve_path(document, paragraph_path))
    newline = cast(StructureElement, paragraph.children[1])
    changed = _replace_path(
        document,
        paragraph_path,
        replace(
            paragraph,
            children=(
                paragraph.children[0],
                replace(newline, actual_text=None),
                paragraph.children[2],
            ),
        ),
    )

    with pytest.raises(ValueError, match="inline subtitle source boundary"):
        validate_review_formatting_hints(changed)


def _text_hint(
    path: tuple[int, ...] = (0,),
    *,
    display_role: Any = "section_heading",
    font_weight: Any = 800,
    font_size: Any = 8.0,
    comparison_body_font_weight: Any = 400,
    comparison_body_font_size: Any = 6.5,
) -> TextDisplayHint:
    return TextDisplayHint(
        child_path=path,
        display_role=cast(Any, display_role),
        font_weight=cast(Any, font_weight),
        font_size=cast(Any, font_size),
        comparison_body_font_weight=cast(Any, comparison_body_font_weight),
        comparison_body_font_size=cast(Any, comparison_body_font_size),
        reason="verified structural typography cluster",
    )


def _text_document(
    *,
    target: StructureElement | ContentFragment | None = None,
    hints: tuple[TextDisplayHint, ...] | None = None,
) -> TaggedDocument:
    if target is None:
        target = _element("paragraph", _fragment("Visible title"))
    if hints is None:
        hints = (_text_hint(),)
    return replace(_document(target), text_display_hints=hints)


def _promotion(path: tuple[int, ...]) -> HeadingPromotion:
    return HeadingPromotion(
        child_path=path,
        level=2,
        label="01",
        title="Title",
        series_index=0,
        heading_font_size=10.0,
        body_font_size=6.0,
        font_size_ratio=1.5,
        promotion_reason="test",
    )


def _subtitle(path: tuple[int, ...]) -> SubtitleHint:
    return SubtitleHint(
        child_path=path,
        font_weight=700,
        comparison_body_font_weight=400,
        observed_line_count=1,
    )


def _sentence_document(
    *,
    text: str = "First sentence. Next sentence.",
    paragraph_source_role: str = "P",
    paragraph_semantic_role: str = "paragraph",
) -> tuple[TaggedDocument, tuple[int, ...]]:
    fragment = _styled_fragment(text)
    paragraph = _element(
        paragraph_semantic_role,
        fragment,
        source_role=paragraph_source_role,
    )
    document = _document(
        _element(
            "list",
            _element(
                "list_item",
                _element("label", _fragment("1")),
                _element("list_body", paragraph),
            ),
        )
    )
    detected = detect_sentence_break_hints(document)
    return replace(document, sentence_break_hints=detected), (0, 0, 1, 0, 0)


def _readability_document() -> tuple[
    TaggedDocument, tuple[int, ...], tuple[int, ...]
]:
    sentence_paragraph = _element(
        "paragraph",
        _styled_fragment("First sentence. Next sentence.", mcid=10),
    )
    icon_paragraph = _element(
        "paragraph",
        _styled_fragment("Before icon", mcid=11),
        _figure(),
        _styled_fragment("After icon", mcid=12),
    )
    document = _document(
        _element(
            "list",
            _element(
                "list_item",
                _element("label", _fragment("1")),
                _element("list_body", sentence_paragraph, icon_paragraph),
            ),
        )
    )
    sentence_hints = detect_sentence_break_hints(document)
    icon_hints = detect_inline_icon_hints(document)
    return (
        replace(
            document,
            sentence_break_hints=sentence_hints,
            inline_icon_hints=icon_hints,
        ),
        (0, 0, 1, 0, 0),
        (0, 0, 1, 1, 1),
    )


def _multiple_readability_document() -> TaggedDocument:
    body_children = (
        _element(
            "paragraph",
            _styled_fragment("First sentence. Next sentence.", mcid=20),
        ),
        _element(
            "paragraph",
            _styled_fragment("Another sentence. Final sentence.", mcid=21),
        ),
        _element(
            "paragraph",
            _styled_fragment("Before first icon", mcid=22),
            _figure(),
            _styled_fragment("After first icon", mcid=23),
        ),
        _element(
            "paragraph",
            _styled_fragment("Before second icon", mcid=24),
            _figure(),
            _styled_fragment("After second icon", mcid=25),
        ),
    )
    document = _document(
        _element(
            "list",
            _element(
                "list_item",
                _element("label", _fragment("1")),
                _element("list_body", *body_children),
            ),
        )
    )
    return replace(
        document,
        sentence_break_hints=detect_sentence_break_hints(document),
        inline_icon_hints=detect_inline_icon_hints(document),
    )


def test_returns_read_only_path_lookups_for_valid_hints() -> None:
    line_document, line_path = _line_document()
    title = _element("paragraph", _fragment("Visible title"))
    document = replace(
        line_document,
        children=(*line_document.children, title),
        text_display_hints=(_text_hint((1,)),),
    )

    validated = validate_review_formatting_hints(document)

    assert validated.line_break_by_path[line_path] == document.line_break_hints[0]
    assert validated.text_display_by_path[(1,)] == document.text_display_hints[0]
    with pytest.raises(TypeError):
        validated.line_break_by_path[line_path] = document.line_break_hints[0]  # type: ignore[index]
    with pytest.raises(TypeError):
        validated.text_display_by_path[(1,)] = document.text_display_hints[0]  # type: ignore[index]


@pytest.mark.parametrize(
    "path",
    [(), [0], (True,), (-1,), (0, 1.0), ("0",)],
)
def test_rejects_invalid_exact_tuple_paths(path: Any) -> None:
    document = _text_document(hints=(_text_hint(cast(Any, path)),))

    with pytest.raises(ValueError, match=r"text display hint.*path"):
        validate_review_formatting_hints(document)


@pytest.mark.parametrize("kind", ["line", "text"])
def test_rejects_duplicate_paths_per_hint_kind(kind: str) -> None:
    if kind == "line":
        document, _ = _line_document()
        document = replace(
            document, line_break_hints=document.line_break_hints * 2
        )
    else:
        document = _text_document(hints=(_text_hint(), _text_hint()))

    with pytest.raises(ValueError, match=rf"duplicate {kind}.*path.*\(0"):
        validate_review_formatting_hints(document)


@pytest.mark.parametrize("kind", ["line", "text"])
def test_rejects_unresolved_paths(kind: str) -> None:
    if kind == "line":
        document, _ = _line_document()
        document = replace(document, line_break_hints=(LineBreakHint((9,)),))
    else:
        document = _text_document(hints=(_text_hint((9,)),))

    with pytest.raises(ValueError, match=rf"unresolved {kind}.*path.*\(9,"):
        validate_review_formatting_hints(document)


@pytest.mark.parametrize("kind", ["line", "text"])
def test_rejects_content_fragment_targets(kind: str) -> None:
    if kind == "line":
        document = replace(
            _document(_fragment("text")),
            line_break_hints=(LineBreakHint((0,)),),
        )
    else:
        document = _text_document(
            target=_fragment("text"), hints=(_text_hint((0,)),)
        )

    with pytest.raises(ValueError, match=rf"{kind}.*StructureElement.*\(0,"):
        validate_review_formatting_hints(document)


@pytest.mark.parametrize(
    ("role", "actual_text"),
    [("paragraph", "\n"), ("span", "\r"), ("span", "\r\n"), ("link", None)],
)
def test_line_hint_requires_inline_target_with_exact_newline(
    role: str, actual_text: str | None
) -> None:
    target = _element(role, source_role="Span", actual_text=actual_text)
    paragraph = _element("paragraph", _fragment("first,"), target, _fragment("next"))
    document = replace(
        _document(
            _element("table", _element("table_cell", paragraph), source_role="Table")
        ),
        line_break_hints=(LineBreakHint((0, 0, 0, 1)),),
    )

    with pytest.raises(ValueError, match=r"line break hint.*span/link.*\(0, 0, 0, 1\)"):
        validate_review_formatting_hints(document)


def test_line_hint_requires_paragraph_inside_table_cell() -> None:
    newline = _element("span", source_role="Span", actual_text="\n")
    paragraph = _element("paragraph", _fragment("first,"), newline, _fragment("next"))
    document = replace(
        _document(paragraph), line_break_hints=(LineBreakHint((0, 1)),)
    )

    with pytest.raises(ValueError, match=r"table_cell paragraph.*\(0, 1\)"):
        validate_review_formatting_hints(document)


def test_line_hint_recomputes_detector_evidence_to_block_manual_adjacency_bypass() -> None:
    newline = _element("span", source_role="Span", actual_text="\n")
    paragraph = _element("paragraph", _fragment("missing comma"), newline, _fragment("next"))
    document = replace(
        _document(
            _element("table", _element("table_cell", paragraph), source_role="Table")
        ),
        line_break_hints=(LineBreakHint((0, 0, 0, 1)),),
    )

    with pytest.raises(ValueError, match=r"adjacency evidence.*\(0, 0, 0, 1\)"):
        validate_review_formatting_hints(document)


def test_rejects_line_break_inside_source_role_heading_candidate() -> None:
    document, _ = _line_document()
    table = cast(StructureElement, document.children[0])
    row = cast(StructureElement, table.children[0])
    cell = cast(StructureElement, row.children[0])
    paragraph = replace(
        cast(StructureElement, cell.children[0]),
        source_role="Heading2",
    )
    document = replace(
        document,
        children=(
            replace(
                table,
                children=(
                    replace(
                        row,
                        children=(replace(cell, children=(paragraph,)),),
                    ),
                ),
            ),
        ),
    )

    with pytest.raises(
        ValueError,
        match=r"heading candidate.*conflict.*line break hint.*\(0, 0, 0, 0, 1\)",
    ):
        validate_review_formatting_hints(document)


def test_rejects_line_break_inside_heading_promotion_target_subtree() -> None:
    document, _ = _line_document()
    document = replace(
        document,
        heading_promotions=(_promotion((0, 0, 0, 0)),),
    )

    with pytest.raises(
        ValueError,
        match=r"heading promotion.*conflict.*line break hint.*\(0, 0, 0, 0, 1\)",
    ):
        validate_review_formatting_hints(document)


def test_rejects_line_break_inside_subtitle_paragraph() -> None:
    document, _ = _line_document()
    document = replace(
        document,
        subtitle_hints=(_subtitle((0, 0, 0, 0)),),
    )

    with pytest.raises(
        ValueError,
        match=r"subtitle.*conflict.*line break hint.*\(0, 0, 0, 0, 1\)",
    ):
        validate_review_formatting_hints(document)


@pytest.mark.parametrize("role", ["section_heading", "strong_label"])
def test_accepts_each_runtime_text_display_role(role: str) -> None:
    document = _text_document(hints=(_text_hint(display_role=role),))

    validated = validate_review_formatting_hints(document)

    assert validated.text_display_by_path[(0,)].display_role == role


@pytest.mark.parametrize("role", ["heading", "SECTION_HEADING", "", 1, None])
def test_rejects_non_runtime_text_display_roles(role: Any) -> None:
    document = _text_document(hints=(_text_hint(display_role=role),))

    with pytest.raises(ValueError, match=r"text display role.*\(0,"):
        validate_review_formatting_hints(document)


def test_text_display_hint_requires_nonempty_paragraph() -> None:
    document = _text_document(target=_element("paragraph", _fragment("  \n  ")))

    with pytest.raises(ValueError, match=r"nonempty paragraph.*\(0,"):
        validate_review_formatting_hints(document)


def test_text_display_hint_rejects_non_paragraph_target() -> None:
    document = _text_document(target=_element("list_item", _fragment("Visible")))

    with pytest.raises(ValueError, match=r"must target a paragraph.*\(0,"):
        validate_review_formatting_hints(document)


@pytest.mark.parametrize(
    "descendant_role",
    [
        "figure",
        "caption",
        "article",
        "division",
        "paragraph",
        "table",
        "list",
        "section",
    ],
)
def test_text_display_leaf_paragraph_rejects_every_non_inline_descendant(
    descendant_role: str,
) -> None:
    target = _element(
        "paragraph",
        _element(descendant_role, _fragment("Nested visible text")),
    )
    document = _text_document(target=target)

    with pytest.raises(ValueError, match=r"nonempty leaf paragraph.*\(0,"):
        validate_review_formatting_hints(document)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("font_weight", True),
        ("font_weight", 0),
        ("font_size", -1.0),
        ("font_size", float("nan")),
        ("comparison_body_font_weight", float("inf")),
        ("comparison_body_font_size", "6.5"),
    ],
)
def test_rejects_invalid_typography_numbers(field: str, value: Any) -> None:
    hint = replace(_text_hint(), **{field: value})
    document = _text_document(hints=(hint,))

    with pytest.raises(ValueError, match=r"typography.*\(0,"):
        validate_review_formatting_hints(document)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("font_weight", 400),
        ("font_weight", 399),
        ("font_size", 6.5),
        ("font_size", 6.4),
    ],
)
def test_text_display_typography_must_be_strictly_stronger_than_body(
    field: str,
    value: int | float,
) -> None:
    hint = replace(_text_hint(), **{field: value})
    document = _text_document(hints=(hint,))

    with pytest.raises(ValueError, match=r"strictly stronger.*\(0,"):
        validate_review_formatting_hints(document)


def test_rejects_overlapping_text_display_paths() -> None:
    nested = _element("paragraph", _fragment("Nested"))
    outer = _element("paragraph", nested)
    document = _text_document(
        target=outer,
        hints=(_text_hint((0,), display_role="section_heading"), _text_hint((0, 0), display_role="strong_label")),
    )

    with pytest.raises(ValueError, match=r"overlapping text display hint paths.*\(0,\).+\(0, 0\)"):
        validate_review_formatting_hints(document)


@pytest.mark.parametrize(
    ("conflict_kind", "conflict_path"),
    [
        ("promotion", (0,)),
        ("promotion", (0, 0)),
        ("promotion", ()),
        ("subtitle", (0,)),
        ("subtitle", (0, 0)),
    ],
)
def test_rejects_equal_ancestor_or_descendant_existing_hint_conflicts(
    conflict_kind: str, conflict_path: tuple[int, ...]
) -> None:
    target = _element("paragraph", _element("span", _fragment("Visible")))
    document = _text_document(target=target)
    if conflict_kind == "promotion":
        document = replace(document, heading_promotions=(_promotion(conflict_path),))
    else:
        document = replace(document, subtitle_hints=(_subtitle(conflict_path),))

    with pytest.raises(ValueError, match=rf"{conflict_kind}.*conflict.*\(0,"):
        validate_review_formatting_hints(document)


@pytest.mark.parametrize("candidate_path", [(0,), (0, 0), ()])
def test_rejects_equal_ancestor_or_descendant_source_heading_candidate_conflicts(
    candidate_path: tuple[int, ...]
) -> None:
    target = _element("paragraph", _element("span", _fragment("Visible")))
    if candidate_path == (0,):
        target = replace(target, source_role="Heading2")
        document = _text_document(target=target)
    elif candidate_path == (0, 0):
        child = replace(cast(StructureElement, target.children[0]), source_role="my-title")
        document = _text_document(target=replace(target, children=(child,)))
    else:
        wrapper = _element("section", target, source_role="Heading")
        document = replace(_document(wrapper), text_display_hints=(_text_hint((0, 0)),))

    with pytest.raises(ValueError, match=r"heading candidate.*conflict"):
        validate_review_formatting_hints(document)


def test_rejects_overlapping_line_and_text_targets() -> None:
    line_document, line_path = _line_document()
    document = replace(
        line_document,
        text_display_hints=(_text_hint(line_path[:-1]),),
    )

    with pytest.raises(ValueError, match=r"line break.*text display.*overlap"):
        validate_review_formatting_hints(document)


def test_returns_read_only_sentence_and_inline_icon_lookups_together() -> None:
    document, sentence_path, icon_path = _readability_document()

    validated = validate_review_formatting_hints(document)

    assert type(validated.sentence_break_by_path) is MappingProxyType
    assert type(validated.inline_icon_by_path) is MappingProxyType
    assert (
        validated.sentence_break_by_path[sentence_path]
        == document.sentence_break_hints[0]
    )
    assert validated.inline_icon_by_path[icon_path] == document.inline_icon_hints[0]
    with pytest.raises(TypeError):
        validated.sentence_break_by_path[sentence_path] = document.sentence_break_hints[0]  # type: ignore[index]
    with pytest.raises(TypeError):
        validated.inline_icon_by_path[icon_path] = document.inline_icon_hints[0]  # type: ignore[index]


@pytest.mark.parametrize(
    ("field", "name"),
    [
        ("sentence_break_hints", "sentence break"),
        ("inline_icon_hints", "inline icon"),
    ],
)
def test_rejects_total_detector_hint_omission(field: str, name: str) -> None:
    document, _, _ = _readability_document()
    document = replace(document, **{field: ()})

    with pytest.raises(ValueError, match=rf"{name} hint mapping mismatch"):
        validate_review_formatting_hints(document)


@pytest.mark.parametrize(
    ("field", "name"),
    [
        ("sentence_break_hints", "sentence break"),
        ("inline_icon_hints", "inline icon"),
    ],
)
def test_rejects_partial_detector_hint_omission(field: str, name: str) -> None:
    document = _multiple_readability_document()
    detected = getattr(document, field)
    assert len(detected) == 2
    document = replace(document, **{field: detected[:1]})

    with pytest.raises(ValueError, match=rf"{name} hint mapping mismatch"):
        validate_review_formatting_hints(document)


def test_sibling_sentence_text_and_inline_figure_paths_do_not_overlap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    text = "First sentence. Next sentence."
    paragraph = _element(
        "paragraph",
        _styled_fragment(text),
        _figure(),
        _styled_fragment("After icon", mcid=2),
    )
    document = _document(
        _element(
            "list",
            _element(
                "list_item",
                _element("label", _fragment("1")),
                _element("list_body", paragraph),
            ),
        )
    )
    sentence_hint = SentenceBreakHint(
        (0, 0, 1, 0, 0),
        (text.index("Next"),),
    )
    icon_hint = InlineIconHint(
        child_path=(0, 0, 1, 0, 1),
        page_index=3,
        bbox=(100.0, 200.0, 109.0, 209.0),
        reference_font_size=6.5,
        width_ratio=9.0 / 6.5,
        height_ratio=9.0 / 6.5,
    )
    document = replace(
        document,
        sentence_break_hints=(sentence_hint,),
        inline_icon_hints=(icon_hint,),
    )
    monkeypatch.setattr(
        validation_module,
        "detect_sentence_break_hints",
        lambda actual: (sentence_hint,),
        raising=False,
    )
    monkeypatch.setattr(
        validation_module,
        "detect_inline_icon_hints",
        lambda actual: (icon_hint,),
        raising=False,
    )

    validated = validate_review_formatting_hints(document)

    assert sentence_hint.child_path in validated.sentence_break_by_path
    assert icon_hint.child_path in validated.inline_icon_by_path


@pytest.mark.parametrize("kind", ["sentence break", "inline icon"])
@pytest.mark.parametrize(
    "path",
    [(), [0], (True,), (-1,), (0, 1.0), ("0",)],
)
def test_readability_hints_reject_invalid_exact_tuple_paths(
    kind: str, path: Any
) -> None:
    document, _, _ = _readability_document()
    if kind == "sentence break":
        hint = replace(document.sentence_break_hints[0], child_path=cast(Any, path))
        document = replace(document, sentence_break_hints=(hint,))
    else:
        hint = replace(document.inline_icon_hints[0], child_path=cast(Any, path))
        document = replace(document, inline_icon_hints=(hint,))

    with pytest.raises(ValueError, match=rf"invalid {kind} hint path"):
        validate_review_formatting_hints(document)


@pytest.mark.parametrize("kind", ["sentence break", "inline icon"])
def test_readability_hints_reject_duplicate_paths(kind: str) -> None:
    document, _, _ = _readability_document()
    if kind == "sentence break":
        document = replace(
            document, sentence_break_hints=document.sentence_break_hints * 2
        )
    else:
        document = replace(document, inline_icon_hints=document.inline_icon_hints * 2)

    with pytest.raises(ValueError, match=rf"duplicate {kind} hint path"):
        validate_review_formatting_hints(document)


@pytest.mark.parametrize("kind", ["sentence break", "inline icon"])
def test_readability_hints_reject_unresolved_paths(kind: str) -> None:
    document, _, _ = _readability_document()
    if kind == "sentence break":
        hint = replace(document.sentence_break_hints[0], child_path=(9,))
        document = replace(document, sentence_break_hints=(hint,))
    else:
        hint = replace(document.inline_icon_hints[0], child_path=(9,))
        document = replace(document, inline_icon_hints=(hint,))

    with pytest.raises(ValueError, match=rf"unresolved {kind} hint path.*\(9,"):
        validate_review_formatting_hints(document)


@pytest.mark.parametrize(
    "path",
    [(), [0], (False,), (True,), (-1,), (0, 1.0), ("0",)],
    ids=(
        "empty",
        "not-tuple",
        "false-bool",
        "true-bool",
        "negative",
        "float",
        "string",
    ),
)
def test_subtitle_hints_reject_invalid_exact_tuple_paths_before_redetection(
    monkeypatch: pytest.MonkeyPatch,
    path: Any,
) -> None:
    document = replace(
        _document(_element("paragraph", _fragment("Subtitle"))),
        subtitle_hints=(_subtitle(cast(Any, path)),),
    )

    def unexpected_redetection(_actual: TaggedDocument) -> None:
        pytest.fail("readability detector ran before subtitle path validation")

    monkeypatch.setattr(
        validation_module,
        "detect_sentence_break_hints",
        unexpected_redetection,
    )

    with pytest.raises(ValueError, match="invalid subtitle hint path"):
        validate_review_formatting_hints(document)


def test_subtitle_hints_reject_duplicates_before_redetection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hint = _subtitle((0,))
    document = replace(
        _document(_element("paragraph", _fragment("Subtitle"))),
        subtitle_hints=(hint, hint),
    )
    monkeypatch.setattr(
        validation_module,
        "detect_sentence_break_hints",
        lambda actual: pytest.fail(
            "readability detector ran before subtitle duplicate validation"
        ),
    )

    with pytest.raises(ValueError, match="duplicate subtitle hint path"):
        validate_review_formatting_hints(document)


def test_subtitle_hints_reject_unresolved_paths_before_redetection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = replace(
        _document(_element("paragraph", _fragment("Subtitle"))),
        subtitle_hints=(_subtitle((9,)),),
    )
    monkeypatch.setattr(
        validation_module,
        "detect_sentence_break_hints",
        lambda actual: pytest.fail(
            "readability detector ran before subtitle resolution"
        ),
    )

    with pytest.raises(ValueError, match=r"unresolved subtitle hint path.*\(9,"):
        validate_review_formatting_hints(document)


def test_subtitle_hint_path_must_resolve_to_structure_before_redetection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = replace(
        _document(_fragment("Not a structure element")),
        subtitle_hints=(_subtitle((0,)),),
    )
    monkeypatch.setattr(
        validation_module,
        "detect_sentence_break_hints",
        lambda actual: pytest.fail(
            "readability detector ran before subtitle target resolution"
        ),
    )

    with pytest.raises(ValueError, match="subtitle hint must target a StructureElement"):
        validate_review_formatting_hints(document)


def test_sentence_hint_requires_content_fragment_target() -> None:
    document, _, _ = _readability_document()
    hint = replace(document.sentence_break_hints[0], child_path=(0, 0, 1, 0))
    document = replace(document, sentence_break_hints=(hint,))

    with pytest.raises(ValueError, match=r"sentence break hint.*ContentFragment"):
        validate_review_formatting_hints(document)


def test_inline_icon_hint_requires_figure_structure_target() -> None:
    document, sentence_path, _ = _readability_document()
    hint = replace(document.inline_icon_hints[0], child_path=sentence_path)
    document = replace(document, inline_icon_hints=(hint,))

    with pytest.raises(ValueError, match=r"inline icon hint.*StructureElement"):
        validate_review_formatting_hints(document)


def test_inline_icon_hint_requires_figure_semantic_role() -> None:
    document, _, icon_path = _readability_document()
    figure = cast(StructureElement, _resolve_path(document, icon_path))
    changed = _replace_path(
        document,
        icon_path,
        replace(figure, semantic_role="span"),
    )

    with pytest.raises(ValueError, match=rf"inline icon hint.*figure.*{icon_path}"):
        validate_review_formatting_hints(changed)


@pytest.mark.parametrize(
    "offsets",
    [
        (),
        [16],
        (True,),
        (-1,),
        (16, 15),
        (16, 16),
        ("16",),
        (16.0,),
    ],
)
def test_sentence_hint_rejects_malformed_offsets(offsets: Any) -> None:
    document, _, _ = _readability_document()
    hint = replace(document.sentence_break_hints[0], offsets=cast(Any, offsets))
    document = replace(document, sentence_break_hints=(hint,))

    with pytest.raises(ValueError, match=r"invalid sentence break offsets"):
        validate_review_formatting_hints(document)


@pytest.mark.parametrize("offset_delta", [0, 1])
def test_sentence_hint_rejects_offset_at_or_beyond_fragment_length(
    offset_delta: int,
) -> None:
    document, sentence_path, _ = _readability_document()
    target = cast(ContentFragment, _resolve_path(document, sentence_path))
    length = len("".join(target.text_parts))
    hint = replace(document.sentence_break_hints[0], offsets=(length + offset_delta,))
    document = replace(document, sentence_break_hints=(hint,))

    with pytest.raises(ValueError, match=r"sentence break offset.*outside target text"):
        validate_review_formatting_hints(document)


def test_sentence_hint_rejects_empty_fragment_target() -> None:
    fragment = _styled_fragment("")
    paragraph = _element("paragraph", fragment)
    document = _document(
        _element(
            "list",
            _element(
                "list_item",
                _element("label", _fragment("1")),
                _element("list_body", paragraph),
            ),
        )
    )
    document = replace(
        document,
        sentence_break_hints=(SentenceBreakHint((0, 0, 1, 0, 0), (0,)),),
    )

    with pytest.raises(ValueError, match=r"sentence break hint.*empty target"):
        validate_review_formatting_hints(document)


def test_sentence_hint_accepts_zero_offset_at_new_source_fragment() -> None:
    first = _styled_fragment("First sentence.", mcid=20)
    second = _styled_fragment("Next sentence.", mcid=21)
    paragraph = _element("paragraph", first, second)
    document = _document(
        _element(
            "list",
            _element(
                "list_item",
                _element("label", _fragment("1")),
                _element("list_body", paragraph),
            ),
        )
    )
    document = replace(
        document, sentence_break_hints=detect_sentence_break_hints(document)
    )

    validated = validate_review_formatting_hints(document)

    assert validated.sentence_break_by_path[(0, 0, 1, 0, 1)].offsets == (0,)


@pytest.mark.parametrize(
    "offset",
    [3, 15],
    ids=["mid-sentence", "whitespace"],
)
def test_sentence_hint_rejects_non_detected_in_range_offset(offset: int) -> None:
    document, _, _ = _readability_document()
    hint = replace(document.sentence_break_hints[0], offsets=(offset,))
    document = replace(document, sentence_break_hints=(hint,))

    with pytest.raises(ValueError, match=r"sentence break detector mismatch"):
        validate_review_formatting_hints(document)


def test_sentence_hint_rejects_offset_inside_protected_token() -> None:
    text = "Visit https://www.samsung.com/support. Next step."
    document, path = _sentence_document(text=text)
    protected_offset = text.index("samsung")
    hint = replace(document.sentence_break_hints[0], offsets=(protected_offset,))
    document = replace(document, sentence_break_hints=(hint,))

    with pytest.raises(ValueError, match=rf"sentence break detector mismatch.*{path}"):
        validate_review_formatting_hints(document)


def test_sentence_hint_accepts_ordinary_top_level_leaf_body() -> None:
    text = "First sentence. Next sentence."
    fragment = _styled_fragment(text)
    document = _document(_element("paragraph", fragment))
    document = replace(
        document, sentence_break_hints=detect_sentence_break_hints(document)
    )
    validated = validate_review_formatting_hints(document)

    assert validated.sentence_break_by_path[(0, 0)].offsets == (
        text.index("Next"),
    )


def test_sentence_hint_rejects_manually_altered_reason() -> None:
    document, _, _ = _readability_document()
    hint = replace(document.sentence_break_hints[0], reason="manual override")
    document = replace(document, sentence_break_hints=(hint,))

    with pytest.raises(ValueError, match=r"sentence break detector mismatch"):
        validate_review_formatting_hints(document)


def test_sentence_hint_rejects_manually_altered_resolved_path() -> None:
    document, _, _ = _readability_document()
    hint = replace(document.sentence_break_hints[0], child_path=(0, 0, 1, 1, 2), offsets=(0,))
    document = replace(document, sentence_break_hints=(hint,))

    with pytest.raises(ValueError, match=r"sentence break detector mismatch"):
        validate_review_formatting_hints(document)


def test_unrelated_sentence_and_source_rf_line_break_hints_are_preserved() -> None:
    line_document, line_path = _line_document()
    sentence_document, _ = _sentence_document()
    document = replace(
        line_document,
        children=(*line_document.children, *sentence_document.children),
    )
    document = replace(
        document,
        sentence_break_hints=detect_sentence_break_hints(document),
    )

    validated = validate_review_formatting_hints(document)

    assert line_path in validated.line_break_by_path
    assert validated.sentence_break_by_path


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("page_index", True),
        ("page_index", -1),
        ("page_index", 3.0),
        ("bbox", [100.0, 200.0, 109.0, 209.0]),
        ("bbox", (100.0, 200.0, 109.0)),
        ("bbox", (True, 200.0, 109.0, 209.0)),
        ("bbox", (100.0, 200.0, float("nan"), 209.0)),
        ("bbox", (100.0, 200.0, float("inf"), 209.0)),
        ("bbox", (100.0, 200.0, 100.0, 209.0)),
        ("bbox", (100.0, 200.0, 99.0, 209.0)),
        ("bbox", (100.0, 200.0, 109.0, 200.0)),
        ("bbox", (100.0, 200.0, 109.0, 199.0)),
        ("bbox", ("100", 200.0, 109.0, 209.0)),
        ("reference_font_size", True),
        ("reference_font_size", 0),
        ("reference_font_size", -1.0),
        ("reference_font_size", float("nan")),
        ("reference_font_size", float("inf")),
        ("reference_font_size", "6.5"),
        ("width_ratio", True),
        ("width_ratio", 0),
        ("width_ratio", -1.0),
        ("width_ratio", float("nan")),
        ("width_ratio", float("inf")),
        ("width_ratio", "1.0"),
        ("height_ratio", True),
        ("height_ratio", 0),
        ("height_ratio", -1.0),
        ("height_ratio", float("nan")),
        ("height_ratio", float("inf")),
        ("height_ratio", "1.0"),
        ("reason", ""),
        ("reason", 1),
    ],
)
def test_inline_icon_hint_rejects_invalid_value(field: str, value: Any) -> None:
    document, _, _ = _readability_document()
    hint = replace(document.inline_icon_hints[0], **{field: value})
    document = replace(document, inline_icon_hints=(hint,))

    with pytest.raises(ValueError, match=r"invalid inline icon"):
        validate_review_formatting_hints(document)


@pytest.mark.parametrize(
    "changes",
    [
        {"page_index": 4},
        {"bbox": (100.0, 200.0, 110.0, 209.0)},
        {"reference_font_size": 7.0},
        {"width_ratio": 1.0},
        {"height_ratio": 1.0},
    ],
)
def test_inline_icon_hint_rejects_detector_evidence_tampering(
    changes: dict[str, Any],
) -> None:
    document, _, _ = _readability_document()
    hint = replace(document.inline_icon_hints[0], **changes)
    document = replace(document, inline_icon_hints=(hint,))

    with pytest.raises(ValueError, match=r"inline icon detector mismatch"):
        validate_review_formatting_hints(document)


def test_inline_icon_hint_rejects_manually_altered_resolved_path() -> None:
    document, _, _ = _readability_document()
    standalone = _figure()
    hint = replace(document.inline_icon_hints[0], child_path=(1,))
    document = replace(
        document,
        children=(*document.children, standalone),
        inline_icon_hints=(hint,),
    )

    with pytest.raises(ValueError, match=r"inline icon detector mismatch"):
        validate_review_formatting_hints(document)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("page_index", 10**400),
        ("bbox", (0, 0, 10**400, 1)),
        ("reference_font_size", 10**400),
        ("width_ratio", 10**400),
        ("height_ratio", 10**400),
        ("bbox", (0, 0, object(), 1)),
    ],
)
def test_malformed_inline_icon_values_raise_clear_value_error(
    field: str, value: Any
) -> None:
    document, _, _ = _readability_document()
    hint = replace(document.inline_icon_hints[0], **{field: value})
    document = replace(document, inline_icon_hints=(hint,))

    with pytest.raises(ValueError, match=r"inline icon"):
        validate_review_formatting_hints(document)


@pytest.mark.parametrize("conflict_kind", ["source heading", "promotion", "subtitle", "text display"])
def test_sentence_hint_rejects_existing_target_subtree_conflicts(
    conflict_kind: str,
) -> None:
    document, _ = _sentence_document()
    paragraph_path = (0, 0, 1, 0)
    if conflict_kind == "source heading":
        paragraph = cast(StructureElement, _resolve_path(document, paragraph_path))
        document = _replace_path(
            document, paragraph_path, replace(paragraph, source_role="Heading2")
        )
    elif conflict_kind == "promotion":
        document = replace(document, heading_promotions=(_promotion(paragraph_path),))
    elif conflict_kind == "subtitle":
        document = replace(document, subtitle_hints=(_subtitle(paragraph_path),))
    elif conflict_kind == "text display":
        document = replace(
            document, text_display_hints=(_text_hint(paragraph_path),)
        )

    with pytest.raises(ValueError, match=rf"{conflict_kind}.*sentence break"):
        validate_review_formatting_hints(document)


def test_sentence_hint_rejects_semantic_heading_conflict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    text = "First sentence. Next sentence."
    document, path = _sentence_document(
        text=text,
        paragraph_semantic_role="heading",
    )
    hint = SentenceBreakHint(path, (text.index("Next"),))
    document = replace(document, sentence_break_hints=(hint,))
    monkeypatch.setattr(
        validation_module,
        "detect_sentence_break_hints",
        lambda actual: (hint,),
        raising=False,
    )

    with pytest.raises(ValueError, match=r"source heading.*sentence break"):
        validate_review_formatting_hints(document)


def test_sentence_hint_rejects_overlapping_line_break_subtree(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document, line_path = _line_document()
    text = "First sentence. Next sentence."
    target = cast(StructureElement, _resolve_path(document, line_path))
    document = _replace_path(
        document,
        line_path,
        replace(target, children=(_styled_fragment(text),)),
    )
    hint = SentenceBreakHint((*line_path, 0), (text.index("Next"),))
    document = replace(document, sentence_break_hints=(hint,))
    monkeypatch.setattr(
        validation_module,
        "detect_sentence_break_hints",
        lambda actual: (hint,),
        raising=False,
    )

    with pytest.raises(ValueError, match=r"line break.*sentence break"):
        validate_review_formatting_hints(document)


@pytest.mark.parametrize("conflict_kind", ["source heading", "promotion", "subtitle"])
def test_inline_icon_hint_rejects_existing_target_subtree_conflicts(
    conflict_kind: str,
) -> None:
    document, _, icon_path = _readability_document()
    paragraph_path = icon_path[:-1]
    if conflict_kind == "source heading":
        paragraph = cast(StructureElement, _resolve_path(document, paragraph_path))
        document = _replace_path(
            document,
            paragraph_path,
            replace(paragraph, source_role="Heading2"),
        )
    elif conflict_kind == "promotion":
        document = replace(document, heading_promotions=(_promotion(paragraph_path),))
    else:
        document = replace(document, subtitle_hints=(_subtitle(paragraph_path),))

    with pytest.raises(ValueError, match=rf"{conflict_kind}.*inline icon"):
        validate_review_formatting_hints(document)


def test_inline_icon_hint_rejects_semantic_heading_conflict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document, _, icon_path = _readability_document()
    paragraph_path = icon_path[:-1]
    paragraph = cast(StructureElement, _resolve_path(document, paragraph_path))
    document = _replace_path(
        document,
        paragraph_path,
        replace(paragraph, semantic_role="heading"),
    )
    hint = document.inline_icon_hints[0]
    monkeypatch.setattr(
        validation_module,
        "detect_inline_icon_hints",
        lambda actual: (hint,),
        raising=False,
    )

    with pytest.raises(ValueError, match=r"source heading.*inline icon"):
        validate_review_formatting_hints(document)


def test_inline_icon_hint_rejects_text_display_target_subtree() -> None:
    document, _, icon_path = _readability_document()
    paragraph_path = icon_path[:-1]
    document = replace(
        document,
        text_display_hints=(_text_hint(paragraph_path),),
    )

    with pytest.raises(ValueError, match=r"text display.*inline icon"):
        validate_review_formatting_hints(document)


def test_inline_icon_hint_rejects_overlapping_line_break_subtree(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document, line_path = _line_document()
    target = cast(StructureElement, _resolve_path(document, line_path))
    document = _replace_path(
        document,
        line_path,
        replace(target, children=(_figure(),)),
    )
    valid_document, _, _ = _readability_document()
    hint = replace(valid_document.inline_icon_hints[0], child_path=(*line_path, 0))
    document = replace(document, inline_icon_hints=(hint,))
    monkeypatch.setattr(
        validation_module,
        "detect_inline_icon_hints",
        lambda actual: (hint,),
        raising=False,
    )

    with pytest.raises(ValueError, match=r"line break.*inline icon"):
        validate_review_formatting_hints(document)


def test_inline_icon_hint_rejects_overlapping_sentence_break_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    text = "First sentence. Next sentence."
    fragment = _styled_fragment(text)
    figure = replace(_figure(), children=(fragment,))
    document = _document(
        _element(
            "list",
            _element(
                "list_item",
                _element("label", _fragment("1")),
                _element("list_body", _element("paragraph", figure)),
            ),
        )
    )
    icon_path = (0, 0, 1, 0, 0)
    sentence_hint = SentenceBreakHint((*icon_path, 0), (text.index("Next"),))
    icon_hint = InlineIconHint(
        child_path=icon_path,
        page_index=3,
        bbox=(100.0, 200.0, 109.0, 209.0),
        reference_font_size=6.5,
        width_ratio=9.0 / 6.5,
        height_ratio=9.0 / 6.5,
    )
    document = replace(
        document,
        sentence_break_hints=(sentence_hint,),
        inline_icon_hints=(icon_hint,),
    )
    monkeypatch.setattr(
        validation_module,
        "detect_sentence_break_hints",
        lambda actual: (sentence_hint,),
        raising=False,
    )
    monkeypatch.setattr(
        validation_module,
        "detect_inline_icon_hints",
        lambda actual: (icon_hint,),
        raising=False,
    )

    with pytest.raises(ValueError, match=r"sentence break.*inline icon"):
        validate_review_formatting_hints(document)


@pytest.mark.parametrize(
    ("replacement", "message"),
    [
        (
            {
                "route_separator_count": 3,
                "route_parenthesized": True,
            },
            "generic inline icon has route evidence",
        ),
        (
            {
                "reason": "navigation_route_inline_figure",
                "route_separator_count": None,
                "route_parenthesized": None,
            },
            "invalid navigation route icon evidence",
        ),
        (
            {"reason": "manual"},
            "invalid inline icon reason",
        ),
    ],
)
def test_inline_icon_hint_rejects_invalid_reason_specific_evidence(
    monkeypatch: pytest.MonkeyPatch,
    replacement: dict[str, object],
    message: str,
) -> None:
    document, _, _ = _readability_document()
    hint = replace(document.inline_icon_hints[0], **replacement)
    document = replace(document, inline_icon_hints=(hint,))
    monkeypatch.setattr(
        validation_module,
        "detect_inline_icon_hints",
        lambda actual: (hint,),
        raising=False,
    )

    with pytest.raises(ValueError, match=message):
        validate_review_formatting_hints(document)
