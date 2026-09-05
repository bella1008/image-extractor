from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from tagged_pdf_extractor.domain.models import (
    ContentFragment,
    HeadingPromotion,
    StructureElement,
    SubtitleHint,
    TaggedDocument,
    TextStyle,
)
from tagged_pdf_extractor.domain.subtitle_detection import (
    detect_subtitle_hints,
    detect_table_subtitles,
    normalize_font_weight,
)


def _fragment(
    text: str,
    font_name: str | None,
    *,
    page_index: int = 0,
    mcid: int | None = 1,
) -> ContentFragment:
    return ContentFragment(
        page_index=page_index,
        mcid=mcid,
        text_parts=(text,),
        text_styles=(TextStyle(font_name, 6.5),),
    )


def _element(
    role: str,
    *children: StructureElement | ContentFragment,
) -> StructureElement:
    return StructureElement(role, role, children=children)


def _valid_children(
    *,
    title: StructureElement | None = None,
    qualifier: StructureElement | None = None,
    body: StructureElement | None = None,
    figure_cell: StructureElement | None = None,
    text_cell_prefix: tuple[StructureElement | ContentFragment, ...] = (),
) -> tuple[StructureElement | ContentFragment, ...]:
    title = title or _element(
        "paragraph", _fragment("任意の地域向け回収案内", "SamsungOne-600", mcid=11)
    )
    qualifier = qualifier or _element(
        "paragraph", _fragment("（対象製品のみ）", "SamsungOne-600", mcid=12)
    )
    body = body or _element(
        "paragraph",
        _fragment("地域の回収規則に従って処分してください。", "SamsungOne-400", mcid=13),
    )
    figure_cell = figure_cell or _element(
        "table_cell", _element("figure")
    )
    text_cell = _element(
        "table_cell", *text_cell_prefix, title, qualifier
    )
    row = _element("table_row", figure_cell, text_cell)
    table = _element("table", row)
    wrapper = _element("paragraph", table)
    section = _element("section", wrapper, body)
    return (section,)


def _qualifying_row(title_text: str, mcid: int) -> StructureElement:
    return _element(
        "table_row",
        _element("table_cell", _element("figure")),
        _element(
            "table_cell",
            _element(
                "paragraph",
                _fragment(title_text, "SamsungOne-600", mcid=mcid),
            ),
            _element(
                "paragraph",
                _fragment("qualifier", "SamsungOne-600", mcid=mcid + 1),
            ),
        ),
    )


@pytest.mark.parametrize(
    ("font_name", "expected"),
    [
        ("ABCDEF+SamsungOne-600", 600),
        ("Family-100", 100),
        ("Family-900", 900),
        ("Family-Black", 900),
        ("Family-ExtraBold", 800),
        ("SamsungOne-Semibold", 600),
        ("SamsungOne_DemiBold", 600),
        ("Family-Medium", 500),
        ("Family-Regular", 400),
        ("Family-Normal", 400),
        ("Family-Light", 300),
        ("Arial-Bold", 700),
        ("Regular", 400),
        ("MysteryBlackbird", None),
        ("NotSemiboldish", None),
        ("Highlight", None),
        ("Moonlight", None),
        ("Irregular", None),
        ("Family-950", None),
        ("MysteryTypeface", None),
        (None, None),
    ],
)
def test_normalize_font_weight_uses_only_verified_numeric_or_keyword_evidence(
    font_name: str | None, expected: int | None
) -> None:
    assert normalize_font_weight(font_name) == expected


def test_detects_language_independent_table_subtitle_from_following_body_weight() -> None:
    children = _valid_children(
        title=_element(
            "paragraph",
            _fragment("地域固有の題名", "AAAAAA+SamsungOne-600", mcid=21),
            _fragment(" 続き", "SamsungOne-SemiBold", mcid=21),
        )
    )

    assert detect_subtitle_hints(children) == (
        SubtitleHint(
            child_path=(0, 0, 0, 0, 1, 0),
            font_weight=600,
            comparison_body_font_weight=400,
            observed_line_count=1,
        ),
    )


def test_detect_table_subtitles_returns_replaced_immutable_document() -> None:
    document = TaggedDocument(Path("localized.pdf"), True, "xx", (), _valid_children())

    detected = detect_table_subtitles(document)

    assert detected is not document
    assert document.subtitle_hints == ()
    assert detected.subtitle_hints == (
        SubtitleHint((0, 0, 0, 0, 1, 0), 600, 400, 1),
    )


@pytest.mark.parametrize("source_role", ("Heading2", "Cover_Title"))
def test_rejects_source_role_heading_or_title_candidates(source_role: str) -> None:
    title = StructureElement(
        source_role,
        "paragraph",
        children=(_fragment("candidate", "SamsungOne-600", mcid=21),),
    )

    assert detect_subtitle_hints(_valid_children(title=title)) == ()


def test_actual_zg_style_p_paragraph_remains_subtitle_eligible() -> None:
    title = StructureElement(
        "P",
        "paragraph",
        children=(_fragment("disposal title", "SamsungOne-600", mcid=21),),
    )

    assert detect_subtitle_hints(_valid_children(title=title)) == (
        SubtitleHint((0, 0, 0, 0, 1, 0), 600, 400, 1),
    )


def test_rejects_actual_semantic_heading_as_subtitle() -> None:
    title = StructureElement(
        "P",
        "heading",
        heading_level=2,
        children=(_fragment("semantic heading", "SamsungOne-600", mcid=21),),
    )

    assert detect_subtitle_hints(_valid_children(title=title)) == ()


def test_rejects_numbered_promotion_target_as_subtitle() -> None:
    document = TaggedDocument(
        Path("manual.pdf"),
        True,
        "en",
        (),
        _valid_children(),
        heading_promotions=(
            HeadingPromotion(
                child_path=(0, 0, 0, 0, 1, 0),
                level=2,
                label="01",
                title="candidate",
                series_index=0,
                heading_font_size=12.0,
                body_font_size=8.0,
                font_size_ratio=1.5,
                promotion_reason="numbered_chapter_structure_sequence_typography",
            ),
        ),
    )

    assert detect_table_subtitles(document).subtitle_hints == ()


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
def test_rejects_title_paragraph_with_block_descendant(block_role: str) -> None:
    title = _element(
        "paragraph",
        _fragment("title", "SamsungOne-600", mcid=21),
        _element(block_role),
    )

    assert detect_subtitle_hints(_valid_children(title=title)) == ()


def test_allows_title_paragraph_with_inline_span_descendant() -> None:
    title = StructureElement(
        "P",
        "paragraph",
        children=(
            StructureElement(
                "Span",
                "span",
                children=(
                    StructureElement(
                        "Link",
                        "link",
                        children=(
                            _fragment(
                                "inline title", "SamsungOne-600", mcid=21
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )

    assert detect_subtitle_hints(_valid_children(title=title)) == (
        SubtitleHint((0, 0, 0, 0, 1, 0), 600, 400, 1),
    )


@pytest.mark.parametrize(
    "title_font,body_font",
    [
        ("SamsungOne-400", "SamsungOne-400"),
        ("UnknownTitle", "SamsungOne-400"),
        ("SamsungOne-600", "UnknownBody"),
    ],
)
def test_rejects_insufficient_or_unresolved_font_weight(
    title_font: str, body_font: str
) -> None:
    title = _element("paragraph", _fragment("제목", title_font, mcid=21))
    body = _element("paragraph", _fragment("본문", body_font, mcid=22))

    assert detect_subtitle_hints(_valid_children(title=title, body=body)) == ()


def test_rejects_title_longer_than_160_normalized_characters() -> None:
    title = _element(
        "paragraph", _fragment("가 " * 81, "SamsungOne-600", mcid=21)
    )

    assert detect_subtitle_hints(_valid_children(title=title)) == ()


def test_rejects_empty_normalized_title() -> None:
    title = _element(
        "paragraph", _fragment(" \t\n ", "SamsungOne-600", mcid=21)
    )

    assert detect_subtitle_hints(_valid_children(title=title)) == ()


def test_accepts_title_with_exactly_160_normalized_characters() -> None:
    title = _element(
        "paragraph", _fragment("x" * 160, "SamsungOne-600", mcid=21)
    )

    assert detect_subtitle_hints(_valid_children(title=title)) == (
        SubtitleHint((0, 0, 0, 0, 1, 0), 600, 400, 1),
    )


def test_accepts_title_observed_on_exactly_two_distinct_lines() -> None:
    title = _element(
        "paragraph",
        _fragment("first", "SamsungOne-600", mcid=21),
        _fragment("second", "SamsungOne-600", mcid=22),
    )

    assert detect_subtitle_hints(_valid_children(title=title)) == (
        SubtitleHint((0, 0, 0, 0, 1, 0), 600, 400, 2),
    )


def test_rejects_title_observed_on_more_than_two_distinct_lines() -> None:
    title = _element(
        "paragraph",
        _fragment("첫째", "SamsungOne-600", mcid=21),
        _fragment("둘째", "SamsungOne-600", mcid=22),
        _fragment("셋째", "SamsungOne-600", mcid=23),
    )

    assert detect_subtitle_hints(_valid_children(title=title)) == ()


def test_rejects_nonempty_title_or_body_part_without_styles() -> None:
    title = _element(
        "paragraph", ContentFragment(0, 21, ("스타일 없는 제목",))
    )

    assert detect_subtitle_hints(_valid_children(title=title)) == ()


def test_rejects_mixed_resolved_and_unresolved_font_names() -> None:
    title = _element(
        "paragraph",
        ContentFragment(
            0,
            21,
            ("resolved", " unresolved"),
            text_styles=(
                TextStyle("SamsungOne-600", 6.5),
                TextStyle("UnknownFont", 6.5),
            ),
        ),
    )

    assert detect_subtitle_hints(_valid_children(title=title)) == ()


def test_rejects_row_without_immediately_preceding_figure_only_cell() -> None:
    nonfigure_cell = _element("table_cell", _element("paragraph"))

    assert detect_subtitle_hints(_valid_children(figure_cell=nonfigure_cell)) == ()


def test_rejects_figure_cell_that_contains_visible_text() -> None:
    figure_cell = _element(
        "table_cell",
        _element("figure"),
        _fragment("visible caption", "SamsungOne-400", mcid=9),
    )

    assert detect_subtitle_hints(_valid_children(figure_cell=figure_cell)) == ()


@pytest.mark.parametrize("metadata_field", ["title", "alternate_text"])
def test_figure_description_metadata_does_not_disqualify_figure_only_cell(
    metadata_field: str,
) -> None:
    figure = StructureElement(
        "Figure",
        "figure",
        **{metadata_field: "descriptive metadata"},
    )
    figure_cell = _element("table_cell", figure)

    assert detect_subtitle_hints(_valid_children(figure_cell=figure_cell)) == (
        SubtitleHint((0, 0, 0, 0, 1, 0), 600, 400, 1),
    )


def test_figure_actual_text_disqualifies_figure_only_cell() -> None:
    figure = StructureElement(
        "Figure",
        "figure",
        actual_text="substitutive visible text",
    )
    figure_cell = _element("table_cell", figure)

    assert detect_subtitle_hints(_valid_children(figure_cell=figure_cell)) == ()


def test_rejects_wrapper_without_immediately_following_body_paragraph() -> None:
    children = _valid_children()
    section = children[0]
    assert isinstance(section, StructureElement)

    assert detect_subtitle_hints((replace(section, children=section.children[:1]),)) == ()


@pytest.mark.parametrize("page_index,mcid", [(-1, 21), (0, None)])
@pytest.mark.parametrize("target", ["title", "body"])
def test_rejects_unresolved_title_or_body_line_identity(
    target: str, page_index: int, mcid: int | None
) -> None:
    title = _element(
        "paragraph",
        _fragment(
            "제목",
            "SamsungOne-600",
            page_index=page_index if target == "title" else 0,
            mcid=mcid if target == "title" else 21,
        ),
    )
    body = _element(
        "paragraph",
        _fragment(
            "본문",
            "SamsungOne-400",
            page_index=page_index if target == "body" else 0,
            mcid=mcid if target == "body" else 22,
        ),
    )

    assert detect_subtitle_hints(_valid_children(title=title, body=body)) == ()


def test_rejects_paragraph_outside_required_table_structure() -> None:
    title = _element("paragraph", _fragment("제목", "SamsungOne-600", mcid=1))
    body = _element("paragraph", _fragment("본문", "SamsungOne-400", mcid=2))

    assert detect_subtitle_hints((_element("section", title, body),)) == ()


def test_never_selects_a_nonleading_text_cell_paragraph() -> None:
    plain_lead = _element(
        "paragraph", _fragment("일반 선행 문단", "SamsungOne-400", mcid=31)
    )
    strong_second = _element(
        "paragraph", _fragment("강한 둘째 문단", "SamsungOne-700", mcid=32)
    )

    assert (
        detect_subtitle_hints(
            _valid_children(title=plain_lead, qualifier=strong_second)
        )
        == ()
    )


def test_rejects_text_cell_with_leading_content_fragment_before_paragraphs() -> None:
    leading_fragment = _fragment(
        "구조 밖 선행 텍스트", "SamsungOne-400", mcid=30
    )

    assert (
        detect_subtitle_hints(
            _valid_children(text_cell_prefix=(leading_fragment,))
        )
        == ()
    )


def test_requires_wrapper_to_contain_exactly_one_table() -> None:
    children = _valid_children()
    section = children[0]
    assert isinstance(section, StructureElement)
    wrapper, body = section.children
    assert isinstance(wrapper, StructureElement)
    extra = _element("paragraph", _fragment("extra", "SamsungOne-400", mcid=99))
    malformed_wrapper = replace(wrapper, children=(*wrapper.children, extra))

    assert (
        detect_subtitle_hints(
            (replace(section, children=(malformed_wrapper, body)),)
        )
        == ()
    )


def test_rejects_candidate_row_belonging_only_to_a_nested_table() -> None:
    nested_table = _element("table", _qualifying_row("nested title", 51))
    outer_row_group = _element("table_body", nested_table)
    outer_table = _element("table", outer_row_group)
    wrapper = _element("paragraph", outer_table)
    body = _element(
        "paragraph", _fragment("outer body", "SamsungOne-400", mcid=60)
    )

    assert detect_subtitle_hints((_element("section", wrapper, body),)) == ()


def test_allows_current_table_rows_inside_structural_row_group_wrappers() -> None:
    row_group = _element("table_body", _qualifying_row("grouped title", 51))
    table = _element("table", row_group)
    wrapper = _element("paragraph", table)
    body = _element(
        "paragraph", _fragment("following body", "SamsungOne-400", mcid=60)
    )

    assert detect_subtitle_hints((_element("section", wrapper, body),)) == (
        SubtitleHint((0, 0, 0, 0, 0, 1, 0), 600, 400, 1),
    )


def test_character_weighted_median_controls_title_and_body_comparison() -> None:
    title = _element(
        "paragraph",
        ContentFragment(
            0,
            41,
            ("X", "긴 제목 문자열"),
            text_styles=(TextStyle("Font-900", 6.5), TextStyle("Font-600", 6.5)),
        ),
    )
    body = _element(
        "paragraph",
        ContentFragment(
            0,
            42,
            ("Y", "긴 본문 문자열"),
            text_styles=(TextStyle("Font-100", 6.5), TextStyle("Font-400", 6.5)),
        ),
    )

    assert detect_subtitle_hints(_valid_children(title=title, body=body)) == (
        SubtitleHint((0, 0, 0, 0, 1, 0), 600, 400, 1),
    )


def test_detects_multiple_qualifying_rows_with_globally_unique_paths() -> None:
    table = _element(
        "table",
        _qualifying_row("first title", 51),
        _qualifying_row("second title", 61),
    )
    wrapper = _element("paragraph", table)
    body = _element(
        "paragraph", _fragment("following body", "SamsungOne-400", mcid=70)
    )

    hints = detect_subtitle_hints((_element("section", wrapper, body),))

    assert tuple(hint.child_path for hint in hints) == (
        (0, 0, 0, 0, 1, 0),
        (0, 0, 0, 1, 1, 0),
    )
    assert len(hints) == len({hint.child_path for hint in hints})


def test_returns_at_most_one_hint_for_multiple_candidate_cell_pairs_in_row() -> None:
    first = _qualifying_row("first title", 51)
    second = _qualifying_row("second title", 61)
    row = replace(first, children=(*first.children, *second.children))
    table = _element("table", row)
    wrapper = _element("paragraph", table)
    body = _element(
        "paragraph", _fragment("following body", "SamsungOne-400", mcid=70)
    )

    hints = detect_subtitle_hints((_element("section", wrapper, body),))

    assert tuple(hint.child_path for hint in hints) == ((0, 0, 0, 0, 1, 0),)


def test_detection_has_no_language_buyer_or_title_dictionary_dependency() -> None:
    first = TaggedDocument(Path("one.pdf"), True, "zz", (), _valid_children())
    second = replace(first, source_path=Path("buyer-token.pdf"), language="yy")

    assert detect_table_subtitles(first).subtitle_hints == detect_table_subtitles(
        second
    ).subtitle_hints
