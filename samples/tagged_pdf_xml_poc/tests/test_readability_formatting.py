from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
import unicodedata

import pytest

from tagged_pdf_extractor.domain.models import (
    ContentFragment,
    InlineIconHint,
    LineBreakHint,
    SentenceBreakHint,
    StructureElement,
    SubtitleHint,
    TaggedDocument,
    TextStyle,
)
from tagged_pdf_extractor.domain.readability_formatting import (
    apply_readability_formatting,
    detect_inline_icon_hints,
    detect_sentence_break_hints,
    verified_subtitle_linked_body_paths,
)
from tagged_pdf_extractor.domain.text_joining import join_text_parts


def _fragment(*text_parts: str, mcid: int = 1) -> ContentFragment:
    return ContentFragment(page_index=0, mcid=mcid, text_parts=text_parts)


def _element(
    role: str,
    *children: StructureElement | ContentFragment,
    actual_text: str | None = None,
    page_index: int | None = None,
    alternate_text: str | None = None,
    attributes: tuple[tuple[str, str], ...] = (),
) -> StructureElement:
    return StructureElement(
        source_role=role,
        semantic_role=role,
        actual_text=actual_text,
        page_index=page_index,
        alternate_text=alternate_text,
        attributes=attributes,
        children=children,
    )


def _document(
    *children: StructureElement | ContentFragment,
    line_break_hints: tuple[LineBreakHint, ...] = (),
    subtitle_hints: tuple[SubtitleHint, ...] = (),
) -> TaggedDocument:
    return TaggedDocument(
        source_path=Path("manual.pdf"),
        marked=True,
        language=None,
        role_map=(),
        children=children,
        line_break_hints=line_break_hints,
        subtitle_hints=subtitle_hints,
    )


def _list_body_document(
    *body_children: StructureElement | ContentFragment,
    line_break_hints: tuple[LineBreakHint, ...] = (),
) -> TaggedDocument:
    label = _element("label", _fragment("1", mcid=90))
    body = _element("list_body", *body_children)
    item = _element("list_item", label, body)
    return _document(
        _element("list", item),
        line_break_hints=line_break_hints,
    )


def _resolve_path(
    document: TaggedDocument,
    path: tuple[int, ...],
) -> StructureElement | ContentFragment:
    siblings = document.children
    target: StructureElement | ContentFragment
    for index, component in enumerate(path):
        target = siblings[component]
        if index < len(path) - 1:
            assert isinstance(target, StructureElement)
            siblings = target.children
    return target


def _assert_fragment_targets(
    document: TaggedDocument,
    hints: tuple[SentenceBreakHint, ...],
) -> None:
    assert all(
        isinstance(_resolve_path(document, hint.child_path), ContentFragment)
        for hint in hints
    )


def _styled_fragment(
    *text_parts: str,
    page_index: int = 3,
    font_sizes: tuple[float | None, ...] | None = None,
    mcid: int = 100,
) -> ContentFragment:
    if font_sizes is None:
        font_sizes = tuple(6.5 for _ in text_parts)
    return ContentFragment(
        page_index=page_index,
        mcid=mcid,
        text_parts=text_parts,
        text_styles=tuple(
            TextStyle("Synthetic", font_size) for font_size in font_sizes
        ),
    )


def _figure(
    *children: StructureElement | ContentFragment,
    page_index: int | None = 3,
    bbox_name: str = "/BBox",
    bbox_value: str = "[100.0, 200.0, 109.0, 209.0]",
    extra_attributes: tuple[tuple[str, str], ...] = (),
    alternate_text: str | None = "Smart Hub",
    actual_text: str | None = None,
) -> StructureElement:
    return _element(
        "figure",
        *children,
        page_index=page_index,
        alternate_text=alternate_text,
        actual_text=actual_text,
        attributes=(
            (bbox_name, bbox_value),
            ("/Placement", "/Block"),
            *extra_attributes,
        ),
    )


def test_readability_hints_are_frozen_and_document_defaults_are_empty() -> None:
    sentence = SentenceBreakHint(
        child_path=(0, 1, 2),
        offsets=(41, 97),
    )
    icon = InlineIconHint(
        child_path=(0, 1, 3),
        page_index=4,
        bbox=(10.0, 20.0, 19.0, 29.0),
        reference_font_size=6.5,
        width_ratio=9.0 / 6.5,
        height_ratio=9.0 / 6.5,
    )

    assert sentence.child_path == (0, 1, 2)
    assert sentence.offsets == (41, 97)
    assert (
        sentence.reason
        == "conservative_sentence_terminal_in_review_container"
    )
    assert icon.child_path == (0, 1, 3)
    assert icon.page_index == 4
    assert icon.bbox == (10.0, 20.0, 19.0, 29.0)
    assert icon.reference_font_size == 6.5
    assert icon.width_ratio == 9.0 / 6.5
    assert icon.height_ratio == 9.0 / 6.5
    assert icon.reason == "small_inline_figure_with_adjacent_text"

    with pytest.raises(FrozenInstanceError):
        sentence.offsets = ()  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        icon.page_index = 0  # type: ignore[misc]

    document = TaggedDocument(Path("manual.pdf"), True, None, (), ())
    assert document.sentence_break_hints == ()
    assert document.inline_icon_hints == ()


def test_detects_four_sentence_french_flow_in_direct_list_body_fragments() -> None:
    first = _fragment(
        "Première phrase. Deuxième ",
        "phrase. Troisième phrase.",
        mcid=10,
    )
    last = _fragment("Quatrième phrase.", mcid=11)
    document = _list_body_document(first, last)
    original_hierarchy = deepcopy(document.children)
    first_text, _ = join_text_parts(first.text_parts)

    hints = detect_sentence_break_hints(document)

    assert hints == (
        SentenceBreakHint(
            child_path=(0, 0, 1, 0),
            offsets=(
                first_text.index("Deuxième"),
                first_text.index("Troisième"),
            ),
        ),
        SentenceBreakHint(child_path=(0, 0, 1, 1), offsets=(0,)),
    )
    assert sum(len(hint.offsets) for hint in hints) == 4 - 1
    _assert_fragment_targets(document, hints)
    assert document.children == original_hierarchy


def test_detects_three_sentence_german_flow_in_list_body_leaf_paragraph() -> None:
    first = _fragment("Erster Satz. Zweiter Satz.", mcid=20)
    last = _fragment(" Dritter Satz.", mcid=21)
    paragraph = _element("paragraph", first, last)
    document = _list_body_document(paragraph)
    first_text, _ = join_text_parts(first.text_parts)
    last_text, _ = join_text_parts(last.text_parts)

    hints = detect_sentence_break_hints(document)

    assert hints == (
        SentenceBreakHint(
            child_path=(0, 0, 1, 0, 0),
            offsets=(first_text.index("Zweiter"),),
        ),
        SentenceBreakHint(
            child_path=(0, 0, 1, 0, 1),
            offsets=(last_text.index("Dritter"),),
        ),
    )
    assert sum(len(hint.offsets) for hint in hints) == 3 - 1
    _assert_fragment_targets(document, hints)


def test_detects_korean_flow_in_table_cell_leaf_paragraph_by_unicode_category() -> None:
    text = "문장입니다. 다음 문장입니다."
    assert unicodedata.category("다") == "Lo"
    fragment = _fragment(text, mcid=30)
    paragraph = _element("paragraph", fragment)
    document = _document(
        _element(
            "table",
            _element("table_row", _element("table_cell", paragraph)),
        )
    )

    hints = detect_sentence_break_hints(document)

    assert hints == (
        SentenceBreakHint(
            child_path=(0, 0, 0, 0, 0),
            offsets=(text.index("다음"),),
        ),
    )
    _assert_fragment_targets(document, hints)


def test_url_internal_punctuation_is_protected_but_terminal_period_splits() -> None:
    text = "Visit https://www.samsung.com/support. Next step."
    document = _list_body_document(_fragment(text))

    assert detect_sentence_break_hints(document) == (
        SentenceBreakHint((0, 0, 1, 0), (text.index("Next"),)),
    )


def test_url_terminal_period_before_unicode_closing_quote_splits() -> None:
    text = "Visit “https://www.samsung.com/support.” Next step."
    document = _list_body_document(_fragment(text))

    assert detect_sentence_break_hints(document) == (
        SentenceBreakHint((0, 0, 1, 0), (text.index("Next"),)),
    )


def test_url_terminal_period_before_external_closing_parenthesis_splits() -> None:
    text = "Visit (https://www.samsung.com/support.) Next step."
    document = _list_body_document(_fragment(text))

    assert detect_sentence_break_hints(document) == (
        SentenceBreakHint((0, 0, 1, 0), (text.index("Next"),)),
    )


def test_balanced_parentheses_remain_part_of_url_protected_range() -> None:
    text = "Visit https://www.samsung.com/support(topic?Details). Next step."
    document = _list_body_document(_fragment(text))

    assert detect_sentence_break_hints(document) == (
        SentenceBreakHint((0, 0, 1, 0), (text.index("Next"),)),
    )


def test_email_internal_punctuation_is_protected_but_terminal_period_splits() -> None:
    text = "Write to service.team@example.co.kr. Next step."
    document = _list_body_document(_fragment(text))

    assert detect_sentence_break_hints(document) == (
        SentenceBreakHint((0, 0, 1, 0), (text.index("Next"),)),
    )


def test_decimal_points_do_not_split_sentences() -> None:
    text = "Use 2.5 GHz and 0.3 W. Next step."
    document = _list_body_document(_fragment(text))

    assert detect_sentence_break_hints(document) == (
        SentenceBreakHint((0, 0, 1, 0), (text.index("Next"),)),
    )


def test_dotted_version_and_standard_points_do_not_split_sentences() -> None:
    text = "Supports EN 301 489-1 V2.2.3. Next step."
    document = _list_body_document(_fragment(text))

    assert detect_sentence_break_hints(document) == (
        SentenceBreakHint((0, 0, 1, 0), (text.index("Next"),)),
    )


def test_one_period_uppercase_dotted_tokens_do_not_split_internally() -> None:
    text = "Open README.PDF. Next use ABC.DEF. Final step."
    document = _list_body_document(_fragment(text))

    assert detect_sentence_break_hints(document) == (
        SentenceBreakHint(
            (0, 0, 1, 0),
            (text.index("Next"), text.index("Final")),
        ),
    )


def test_mixed_case_basename_with_uppercase_extension_does_not_split() -> None:
    text = "Open manual.PDF. Next step."
    document = _list_body_document(_fragment(text))

    assert detect_sentence_break_hints(document) == (
        SentenceBreakHint((0, 0, 1, 0), (text.index("Next"),)),
    )


def test_one_period_titlecase_words_are_not_blanket_protected() -> None:
    text = "First Sentence.Next sentence."
    document = _list_body_document(_fragment(text))

    assert detect_sentence_break_hints(document) == (
        SentenceBreakHint((0, 0, 1, 0), (text.index("Next"),)),
    )


def test_compact_abbreviations_and_initials_do_not_split_sentences() -> None:
    text = (
        "Use e.g. Certified parts and i.e. Approved parts. "
        "Meet A. B. Smith. Next step."
    )
    document = _list_body_document(_fragment(text))

    assert detect_sentence_break_hints(document) == (
        SentenceBreakHint(
            (0, 0, 1, 0),
            (text.index("Meet"), text.index("Next")),
        ),
    )


def test_singular_uppercase_initial_before_name_does_not_split() -> None:
    text = "Meet A. Smith. Next step."
    document = _list_body_document(_fragment(text))

    assert detect_sentence_break_hints(document) == (
        SentenceBreakHint((0, 0, 1, 0), (text.index("Next"),)),
    )


def test_unicode_ellipsis_does_not_create_a_sentence_break() -> None:
    document = _list_body_document(_fragment("Wait… Continue carefully."))

    assert detect_sentence_break_hints(document) == ()


def test_unicode_closing_punctuation_is_skipped_before_next_sentence() -> None:
    text = "첫 문장.」 다음 문장."
    document = _list_body_document(_fragment(text))

    assert detect_sentence_break_hints(document) == (
        SentenceBreakHint((0, 0, 1, 0), (text.index("다음"),)),
    )


def test_unicode_opening_punctuation_is_checked_before_next_sentence() -> None:
    text = "첫 문장. 「다음 문장.」"
    document = _list_body_document(_fragment(text))

    assert detect_sentence_break_hints(document) == (
        SentenceBreakHint((0, 0, 1, 0), (text.index("「"),)),
    )


def test_model_and_file_tokens_are_protected_but_terminal_period_splits() -> None:
    text = "Use QE65LS03DAUXXN and manual.v2.xml. Next step."
    document = _list_body_document(_fragment(text))

    assert detect_sentence_break_hints(document) == (
        SentenceBreakHint((0, 0, 1, 0), (text.index("Next"),)),
    )


def test_lowercase_or_ambiguous_continuation_does_not_split() -> None:
    document = _list_body_document(_fragment("First thought. perhaps continue."))

    assert detect_sentence_break_hints(document) == ()


@pytest.mark.parametrize(
    ("text", "next_sentence"),
    [
        ("Stop! Next sentence.", "Next"),
        ("Ready? Continue reading.", "Continue"),
    ],
)
def test_exclamation_and_question_marks_are_terminators(
    text: str,
    next_sentence: str,
) -> None:
    document = _list_body_document(_fragment(text))

    assert detect_sentence_break_hints(document) == (
        SentenceBreakHint((0, 0, 1, 0), (text.index(next_sentence),)),
    )


def test_nonterminal_punctuation_does_not_create_boundaries() -> None:
    text = "First clause, Next clause; Another clause: Final clause."
    document = _list_body_document(_fragment(text))

    assert detect_sentence_break_hints(document) == ()


def test_digit_can_start_the_next_sentence() -> None:
    text = "Setup complete. 2 steps remain."
    document = _list_body_document(_fragment(text))

    assert detect_sentence_break_hints(document) == (
        SentenceBreakHint((0, 0, 1, 0), (text.index("2 steps"),)),
    )


@pytest.mark.parametrize("opening_quote", ['"', "“"])
def test_explicit_opening_quotes_allow_sentence_starts(opening_quote: str) -> None:
    text = f"First sentence. {opening_quote}Next sentence."
    document = _list_body_document(_fragment(text))

    assert detect_sentence_break_hints(document) == (
        SentenceBreakHint((0, 0, 1, 0), (text.index(opening_quote),)),
    )


@pytest.mark.parametrize("closing_punctuation", ['"', "”", ")", "]"])
def test_explicit_closing_quotes_and_brackets_are_skipped(
    closing_punctuation: str,
) -> None:
    text = f"First sentence.{closing_punctuation} Next sentence."
    document = _list_body_document(_fragment(text))

    assert detect_sentence_break_hints(document) == (
        SentenceBreakHint((0, 0, 1, 0), (text.index("Next"),)),
    )


def test_general_body_paragraph_outside_approved_context_does_not_split() -> None:
    document = _document(
        _element("paragraph", _fragment("First sentence. Next sentence."))
    )

    assert detect_sentence_break_hints(document) == ()


def _verified_subtitle_table() -> tuple[StructureElement, tuple[int, ...]]:
    table = _element(
        "table",
        _element(
            "table_row",
            _element("table_cell", _element("figure")),
            _element(
                "table_cell",
                _element("paragraph", _fragment("Verified subtitle", mcid=201)),
                _element("paragraph", _fragment("(Qualifier)", mcid=202)),
            ),
        ),
    )
    return table, (0, 0, 0, 0, 1, 0)


def _subtitle_linked_document(
    *section_children: StructureElement | ContentFragment,
    subtitle_path: tuple[int, ...],
    duplicate_hint: bool = False,
) -> TaggedDocument:
    hint = SubtitleHint(
        child_path=subtitle_path,
        font_weight=600,
        comparison_body_font_weight=400,
        observed_line_count=1,
    )
    hints = (hint, hint) if duplicate_hint else (hint,)
    return _document(
        _element("section", *section_children),
        subtitle_hints=hints,
    )


def test_verified_table_subtitle_links_only_immediately_following_leaf_body() -> None:
    table, subtitle_path = _verified_subtitle_table()
    text = "First sentence. Second sentence. Third sentence."
    document = _subtitle_linked_document(
        _element("paragraph", table),
        _element("paragraph", _fragment(text, mcid=203)),
        subtitle_path=subtitle_path,
    )

    assert detect_sentence_break_hints(document) == (
        SentenceBreakHint(
            (0, 1, 0),
            (text.index("Second"), text.index("Third")),
        ),
    )


@pytest.mark.parametrize(
    "barrier_role",
    ["heading", "caption", "label", "figure", "list", "table"],
)
def test_subtitle_linked_body_inside_flow_barrier_is_not_discovered(
    barrier_role: str,
) -> None:
    table, _ = _verified_subtitle_table()
    text = "First sentence. Second sentence."
    subtitle_path = (0, 0, 0, 0, 0, 1, 0)
    hint = SubtitleHint(
        child_path=subtitle_path,
        font_weight=600,
        comparison_body_font_weight=400,
        observed_line_count=1,
    )
    document = _document(
        _element(
            "section",
            _element(
                barrier_role,
                _element("paragraph", table),
                _element("paragraph", _fragment(text, mcid=216)),
            ),
        ),
        subtitle_hints=(hint,),
    )

    assert verified_subtitle_linked_body_paths(document) == ()
    assert apply_readability_formatting(document).sentence_break_hints == ()


def test_actual_text_only_inline_body_has_domain_candidate_parity() -> None:
    table, subtitle_path = _verified_subtitle_table()
    document = _subtitle_linked_document(
        _element("paragraph", table),
        _element(
            "paragraph",
            _element("span", actual_text="Actual-text-only body."),
        ),
        subtitle_path=subtitle_path,
    )

    assert verified_subtitle_linked_body_paths(document) == ((0, 1),)
    assert detect_sentence_break_hints(document) == ()


def test_whitespace_actual_text_only_inline_body_is_not_a_candidate() -> None:
    table, subtitle_path = _verified_subtitle_table()
    document = _subtitle_linked_document(
        _element("paragraph", table),
        _element("paragraph", _element("span", actual_text=" \n ")),
        subtitle_path=subtitle_path,
    )

    assert verified_subtitle_linked_body_paths(document) == ()


def test_verified_table_subtitle_allows_whitespace_only_wrapper_sibling() -> None:
    table, subtitle_path = _verified_subtitle_table()
    text = "First sentence. Second sentence."
    document = _subtitle_linked_document(
        _element("paragraph", _fragment(" \n ", mcid=204), table),
        _element("paragraph", _fragment(text, mcid=205)),
        subtitle_path=(0, 0, 1, 0, 1, 0),
    )

    assert detect_sentence_break_hints(document) == (
        SentenceBreakHint((0, 1, 0), (text.index("Second"),)),
    )


def test_subtitle_outside_wrapper_table_does_not_link_body() -> None:
    text = "First sentence. Second sentence."
    document = _subtitle_linked_document(
        _element(
            "paragraph",
            _element("span", _fragment("Verified subtitle", mcid=206)),
        ),
        _element("paragraph", _fragment(text, mcid=207)),
        subtitle_path=(0, 0, 0),
    )

    assert detect_sentence_break_hints(document) == ()


def test_non_adjacent_paragraph_after_verified_subtitle_wrapper_is_rejected() -> None:
    table, subtitle_path = _verified_subtitle_table()
    text = "First sentence. Second sentence."
    document = _subtitle_linked_document(
        _element("paragraph", table),
        _element("paragraph", _fragment("Immediate single sentence.", mcid=208)),
        _element("paragraph", _fragment(text, mcid=209)),
        subtitle_path=subtitle_path,
    )

    assert detect_sentence_break_hints(document) == ()


def test_multi_meaningful_child_subtitle_wrapper_is_rejected() -> None:
    table, subtitle_path = _verified_subtitle_table()
    text = "First sentence. Second sentence."
    document = _subtitle_linked_document(
        _element(
            "paragraph",
            table,
            _element("span", _fragment("Unexpected content", mcid=210)),
        ),
        _element("paragraph", _fragment(text, mcid=211)),
        subtitle_path=subtitle_path,
    )

    assert detect_sentence_break_hints(document) == ()


def test_subtitle_linked_body_must_be_nonempty_inline_leaf_paragraph() -> None:
    table, subtitle_path = _verified_subtitle_table()
    document = _subtitle_linked_document(
        _element("paragraph", table),
        _element(
            "paragraph",
            _fragment("First sentence. Second sentence.", mcid=212),
            _element("list", _element("list_item")),
        ),
        subtitle_path=subtitle_path,
    )

    assert detect_sentence_break_hints(document) == ()


def test_whitespace_only_subtitle_linked_body_is_not_an_eligible_path() -> None:
    table, subtitle_path = _verified_subtitle_table()
    document = _subtitle_linked_document(
        _element("paragraph", table),
        _element("paragraph", _fragment(" \n ", mcid=215)),
        subtitle_path=subtitle_path,
    )

    assert verified_subtitle_linked_body_paths(document) == ()


def test_duplicate_subtitle_hints_add_body_sentence_offsets_once() -> None:
    table, subtitle_path = _verified_subtitle_table()
    text = "First sentence. Second sentence."
    document = _subtitle_linked_document(
        _element("paragraph", table),
        _element("paragraph", _fragment(text, mcid=213)),
        subtitle_path=subtitle_path,
        duplicate_hint=True,
    )

    assert detect_sentence_break_hints(document) == (
        SentenceBreakHint((0, 1, 0), (text.index("Second"),)),
    )


def test_unverified_table_title_does_not_link_following_body() -> None:
    table, _ = _verified_subtitle_table()
    document = _document(
        _element(
            "section",
            _element("paragraph", table),
            _element(
                "paragraph",
                _fragment("First sentence. Second sentence.", mcid=214),
            ),
        )
    )

    assert detect_sentence_break_hints(document) == ()


@pytest.mark.parametrize("role", ["heading", "caption", "label", "figure"])
def test_non_body_semantic_roles_do_not_split_inside_list_body(role: str) -> None:
    excluded = _element(role, _fragment("First sentence. Next sentence."))
    document = _list_body_document(excluded)

    assert detect_sentence_break_hints(document) == ()


@pytest.mark.parametrize("role", ["heading", "caption", "label", "figure"])
def test_non_body_roles_are_barriers_between_outer_text_fragments(role: str) -> None:
    document = _list_body_document(
        _fragment("Before barrier."),
        _element(role, _fragment("Inside barrier.")),
        _fragment("After barrier."),
    )

    assert detect_sentence_break_hints(document) == ()


@pytest.mark.parametrize("nested_role", ["list", "table"])
def test_nested_blocks_form_their_own_flow_without_merging_outer_text(
    nested_role: str,
) -> None:
    inner_text = "Inner one. Inner two."
    if nested_role == "list":
        nested = _element(
            "list",
            _element(
                "list_item",
                _element("list_body", _fragment(inner_text, mcid=41)),
            ),
        )
        inner_path = (0, 0, 1, 1, 0, 0, 0)
    else:
        nested = _element(
            "table",
            _element(
                "table_row",
                _element(
                    "table_cell",
                    _element(
                        "paragraph",
                        _fragment(inner_text, mcid=42),
                    ),
                ),
            ),
        )
        inner_path = (0, 0, 1, 1, 0, 0, 0, 0)
    document = _list_body_document(
        _fragment("Outer sentence.", mcid=40),
        nested,
        _fragment("Outer continuation.", mcid=43),
    )

    assert detect_sentence_break_hints(document) == (
        SentenceBreakHint(inner_path, (inner_text.index("Inner two"),)),
    )


def test_existing_line_break_marker_prevents_duplicate_sentence_boundary() -> None:
    marker_path = (0, 0, 1, 0, 1)
    paragraph = _element(
        "paragraph",
        _fragment("Première phrase.", mcid=50),
        _element("link", actual_text="\n"),
        _fragment("Deuxième phrase.", mcid=51),
    )
    document = _list_body_document(
        paragraph,
        line_break_hints=(LineBreakHint(marker_path),),
    )

    assert detect_sentence_break_hints(document) == ()


def test_terminator_in_own_fragment_still_detects_next_sentence() -> None:
    document = _list_body_document(
        _fragment("First sentence", mcid=61),
        _fragment(". ", mcid=62),
        _fragment("Next sentence.", mcid=63),
    )

    assert detect_sentence_break_hints(document) == (
        SentenceBreakHint((0, 0, 1, 2), (0,)),
    )


def test_leading_period_fragment_preserves_split_decimal_token() -> None:
    document = _list_body_document(
        _fragment("Use 2", mcid=64),
        _fragment(".5 GHz. ", mcid=65),
        _fragment("Next sentence.", mcid=66),
    )

    assert detect_sentence_break_hints(document) == (
        SentenceBreakHint((0, 0, 1, 2), (0,)),
    )


def test_detects_inline_icon_between_wrapped_text_in_leaf_paragraph() -> None:
    figure = _figure()
    document = _document(
        _element(
            "paragraph",
            _element("span", _styled_fragment("Open ", mcid=101)),
            figure,
            _element(
                "link",
                _element(
                    "span",
                    _styled_fragment("Smart Hub", mcid=102),
                ),
            ),
        )
    )

    hints = detect_inline_icon_hints(document)

    assert hints == (
        InlineIconHint(
            child_path=(0, 1),
            page_index=3,
            bbox=(100.0, 200.0, 109.0, 209.0),
            reference_font_size=6.5,
            width_ratio=9.0 / 6.5,
            height_ratio=9.0 / 6.5,
        ),
    )
    assert figure.attributes == (
        ("/BBox", "[100.0, 200.0, 109.0, 209.0]"),
        ("/Placement", "/Block"),
    )
    assert figure.alternate_text == "Smart Hub"


def test_detects_inline_icon_before_one_sided_list_body_text() -> None:
    document = _list_body_document(
        _figure(),
        _styled_fragment("   ", font_sizes=(None,), mcid=103),
        _element("link", _styled_fragment("Settings", mcid=104)),
    )

    assert detect_inline_icon_hints(document) == (
        InlineIconHint(
            child_path=(0, 0, 1, 0),
            page_index=3,
            bbox=(100.0, 200.0, 109.0, 209.0),
            reference_font_size=6.5,
            width_ratio=9.0 / 6.5,
            height_ratio=9.0 / 6.5,
        ),
    )


def test_detects_inline_icon_after_one_sided_paragraph_text() -> None:
    document = _document(
        _element(
            "paragraph",
            _element("span", _styled_fragment("Source", mcid=105)),
            _figure(bbox_name="bBoX"),
        )
    )

    assert detect_inline_icon_hints(document) == (
        InlineIconHint(
            child_path=(0, 1),
            page_index=3,
            bbox=(100.0, 200.0, 109.0, 209.0),
            reference_font_size=6.5,
            width_ratio=9.0 / 6.5,
            height_ratio=9.0 / 6.5,
        ),
    )


def test_inline_icon_hint_is_equivalent_for_none_and_arbitrary_alt_text() -> None:
    alternate_texts = (None, "Arbitrary metadata, not a rendered icon name")
    figures = tuple(
        _figure(alternate_text=alternate_text)
        for alternate_text in alternate_texts
    )
    documents = tuple(
        _document(
            _element(
                "paragraph",
                _styled_fragment("Before", mcid=119),
                figure,
                _styled_fragment("After", mcid=120),
            )
        )
        for figure in figures
    )

    hints = tuple(detect_inline_icon_hints(document) for document in documents)

    expected = (
        InlineIconHint(
            child_path=(0, 1),
            page_index=3,
            bbox=(100.0, 200.0, 109.0, 209.0),
            reference_font_size=6.5,
            width_ratio=9.0 / 6.5,
            height_ratio=9.0 / 6.5,
        ),
    )
    assert hints == (expected, expected)
    assert tuple(figure.alternate_text for figure in figures) == alternate_texts


def test_reference_size_is_visible_character_weighted_median() -> None:
    document = _document(
        _element(
            "paragraph",
            _styled_fragment(
                "AA",
                "   ",
                "BBBBB",
                font_sizes=(6.0, None, 8.0),
                mcid=106,
            ),
            _figure(),
            _styled_fragment("C", font_sizes=(12.0,), mcid=107),
        )
    )

    hint = detect_inline_icon_hints(document)[0]

    assert hint.reference_font_size == 8.0
    assert hint.width_ratio == 9.0 / 8.0
    assert hint.height_ratio == 9.0 / 8.0


def test_inline_icon_ratio_boundaries_are_inclusive() -> None:
    document = _document(
        _element(
            "paragraph",
            _styled_fragment("Before", mcid=108),
            _figure(bbox_value="[100.0, 200.0, 119.5, 213.0]"),
            _styled_fragment("After", mcid=109),
        )
    )

    hint = detect_inline_icon_hints(document)[0]

    assert hint.width_ratio == 3.0
    assert hint.height_ratio == 2.0


@pytest.mark.parametrize(
    "page_index",
    [None, -1],
)
def test_inline_icon_requires_nonnegative_figure_page_index(
    page_index: int | None,
) -> None:
    document = _document(
        _element(
            "paragraph",
            _styled_fragment("Before"),
            _figure(page_index=page_index),
            _styled_fragment("After"),
        )
    )

    assert detect_inline_icon_hints(document) == ()


@pytest.mark.parametrize(
    "bbox_value",
    [
        "",
        "not-a-box",
        "[100.0, 200.0, 109.0]",
        "[100.0, 200.0, 109.0, 209.0, 210.0]",
        "[nan, 200.0, 109.0, 209.0]",
        "[100.0, -inf, 109.0, 209.0]",
        "[100.0, 200.0, inf, 209.0]",
        "[100.0, 200.0, 100.0, 209.0]",
        "[100.0, 200.0, 99.0, 209.0]",
        "[100.0, 200.0, 109.0, 200.0]",
        "[100.0, 200.0, 109.0, 199.0]",
    ],
)
def test_inline_icon_rejects_invalid_bbox(bbox_value: str) -> None:
    document = _document(
        _element(
            "paragraph",
            _styled_fragment("Before"),
            _figure(bbox_value=bbox_value),
            _styled_fragment("After"),
        )
    )

    assert detect_inline_icon_hints(document) == ()


def test_inline_icon_rejects_missing_bbox() -> None:
    figure = _element(
        "figure",
        page_index=3,
        attributes=(("/Placement", "/Block"),),
    )
    document = _document(
        _element(
            "paragraph",
            _styled_fragment("Before"),
            figure,
            _styled_fragment("After"),
        )
    )

    assert detect_inline_icon_hints(document) == ()


def test_inline_icon_rejects_bbox_coordinate_that_overflows_float() -> None:
    enormous_integer = "1" + ("0" * 400)
    document = _document(
        _element(
            "paragraph",
            _styled_fragment("Before"),
            _figure(bbox_value=f"[0, 0, {enormous_integer}, 9]"),
            _styled_fragment("After"),
        )
    )

    assert detect_inline_icon_hints(document) == ()


def test_inline_icon_rejects_conflicting_duplicate_bbox_attributes() -> None:
    document = _document(
        _element(
            "paragraph",
            _styled_fragment("Before"),
            _figure(
                extra_attributes=(
                    ("bbox", "[100.0, 200.0, 110.0, 209.0]"),
                )
            ),
            _styled_fragment("After"),
        )
    )

    assert detect_inline_icon_hints(document) == ()


def test_inline_icon_accepts_equivalent_duplicate_bbox_attributes() -> None:
    document = _document(
        _element(
            "paragraph",
            _styled_fragment("Before"),
            _figure(
                extra_attributes=(
                    ("BBOX", "[100.0, 200.0, 109.0, 209.0]"),
                )
            ),
        )
    )

    assert len(detect_inline_icon_hints(document)) == 1


@pytest.mark.parametrize(
    "bbox_name",
    [" BBox", "BBox ", " /BBox", "/BBox ", "//BBox", "[0]/BBox"],
)
def test_inline_icon_rejects_non_exact_bbox_attribute_names(
    bbox_name: str,
) -> None:
    document = _document(
        _element(
            "paragraph",
            _styled_fragment("Before"),
            _figure(bbox_name=bbox_name),
            _styled_fragment("After"),
        )
    )

    assert detect_inline_icon_hints(document) == ()


def test_inline_icon_rejects_standalone_figure_even_with_alt_and_placement() -> None:
    document = _document(_element("paragraph", _figure()))

    assert detect_inline_icon_hints(document) == ()


def test_inline_icon_rejects_text_available_only_in_another_leaf_flow() -> None:
    document = _document(
        _element("paragraph", _styled_fragment("Nearby")),
        _element("paragraph", _figure()),
    )

    assert detect_inline_icon_hints(document) == ()


def test_inline_icon_rejects_adjacent_text_on_another_page() -> None:
    document = _document(
        _element(
            "paragraph",
            _figure(),
            _styled_fragment("Other page", page_index=4),
        )
    )

    assert detect_inline_icon_hints(document) == ()


def test_inline_icon_rejects_adjacent_text_without_styles() -> None:
    unstyled = ContentFragment(3, 110, ("Visible",))
    document = _document(_element("paragraph", _figure(), unstyled))

    assert detect_inline_icon_hints(document) == ()


def test_inline_icon_rejects_malformed_side_even_when_other_side_is_valid() -> None:
    unstyled = ContentFragment(3, 115, ("Malformed side",))
    document = _document(
        _element(
            "paragraph",
            _styled_fragment("Valid side", mcid=116),
            _figure(),
            unstyled,
        )
    )

    assert detect_inline_icon_hints(document) == ()


@pytest.mark.parametrize(
    "font_size",
    [None, 0.0, -1.0, float("nan"), float("inf"), -float("inf")],
)
def test_inline_icon_rejects_unavailable_or_invalid_adjacent_font_size(
    font_size: float | None,
) -> None:
    document = _document(
        _element(
            "paragraph",
            _figure(),
            _styled_fragment("Visible", font_sizes=(font_size,)),
        )
    )

    assert detect_inline_icon_hints(document) == ()


def test_inline_icon_rejects_font_size_that_overflows_float() -> None:
    enormous_font_size = 10**400
    document = _document(
        _element(
            "paragraph",
            _figure(),
            _styled_fragment(
                "Visible",
                font_sizes=(enormous_font_size,),
            ),
        )
    )

    assert detect_inline_icon_hints(document) == ()


def test_inline_icon_rejects_mismatched_text_style_evidence() -> None:
    mismatched = ContentFragment(3, 111, ("Visible", " text"))
    object.__setattr__(
        mismatched,
        "text_styles",
        (TextStyle("Synthetic", 6.5),),
    )
    document = _document(_element("paragraph", _figure(), mismatched))

    assert detect_inline_icon_hints(document) == ()


@pytest.mark.parametrize(
    "bbox_value",
    [
        "[100.0, 200.0, 119.500001, 213.0]",
        "[100.0, 200.0, 119.5, 213.000001]",
    ],
)
def test_inline_icon_rejects_ratio_above_either_limit(
    bbox_value: str,
) -> None:
    document = _document(
        _element(
            "paragraph",
            _styled_fragment("Before"),
            _figure(bbox_value=bbox_value),
            _styled_fragment("After"),
        )
    )

    assert detect_inline_icon_hints(document) == ()


def test_inline_icon_rejects_figure_with_visible_extracted_text() -> None:
    figure = _figure(
        _element("span", ContentFragment(3, 112, ("Smart Hub",)))
    )
    document = _document(
        _element(
            "paragraph",
            _styled_fragment("Before"),
            figure,
            _styled_fragment("After"),
        )
    )

    assert detect_inline_icon_hints(document) == ()


def test_inline_icon_rejects_visible_actual_text_on_figure() -> None:
    document = _document(
        _element(
            "paragraph",
            _styled_fragment("Before"),
            _figure(actual_text="Rendered icon text"),
            _styled_fragment("After"),
        )
    )

    assert detect_inline_icon_hints(document) == ()


def test_inline_icon_rejects_visible_actual_text_on_nested_structure() -> None:
    figure = _figure(_element("span", actual_text="Rendered icon text"))
    document = _document(
        _element(
            "paragraph",
            _styled_fragment("Before"),
            figure,
            _styled_fragment("After"),
        )
    )

    assert detect_inline_icon_hints(document) == ()


@pytest.mark.parametrize(
    "container_role",
    ["table_cell", "heading", "caption", "label", "list", "table"],
)
def test_inline_icon_rejects_direct_child_of_non_inline_flow_container(
    container_role: str,
) -> None:
    document = _document(
        _element(
            container_role,
            _styled_fragment("Before"),
            _figure(),
            _styled_fragment("After"),
        )
    )

    assert detect_inline_icon_hints(document) == ()


def test_inline_icon_does_not_use_text_across_structural_barrier() -> None:
    document = _document(
        _element(
            "paragraph",
            _styled_fragment("Before"),
            _element("caption", _styled_fragment("Barrier")),
            _figure(),
        )
    )

    assert detect_inline_icon_hints(document) == ()


def test_inline_icon_hints_are_unique_and_in_document_order() -> None:
    document = _list_body_document(
        _element(
            "paragraph",
            _styled_fragment("Before", mcid=113),
            _figure(),
        ),
        _element(
            "paragraph",
            _figure(),
            _styled_fragment("After", mcid=114),
        ),
    )

    hints = detect_inline_icon_hints(document)

    assert [hint.child_path for hint in hints] == [
        (0, 0, 1, 0, 1),
        (0, 0, 1, 1, 0),
    ]
    assert len(hints) == len({hint.child_path for hint in hints})


def test_apply_readability_formatting_replaces_only_detected_hint_fields() -> None:
    text = "First sentence. Next sentence."
    source = _list_body_document(
        _element("paragraph", _fragment(text, mcid=60)),
        _element(
            "paragraph",
            _styled_fragment("Before", mcid=117),
            _figure(),
            _styled_fragment("After", mcid=118),
        ),
    )
    stale_sentence = SentenceBreakHint((9,), (1,))
    stale_icon = InlineIconHint(
        child_path=(9,),
        page_index=0,
        bbox=(0.0, 0.0, 1.0, 1.0),
        reference_font_size=1.0,
        width_ratio=1.0,
        height_ratio=1.0,
    )
    source = replace(
        source,
        sentence_break_hints=(stale_sentence,),
        inline_icon_hints=(stale_icon,),
    )

    formatted = apply_readability_formatting(source)

    assert formatted is not source
    assert formatted.children is source.children
    assert formatted.sentence_break_hints
    assert formatted.inline_icon_hints
    assert formatted.sentence_break_hints == (
        SentenceBreakHint((0, 0, 1, 0, 0), (text.index("Next"),)),
    )
    assert formatted.inline_icon_hints == (
        InlineIconHint(
            child_path=(0, 0, 1, 1, 1),
            page_index=3,
            bbox=(100.0, 200.0, 109.0, 209.0),
            reference_font_size=6.5,
            width_ratio=9.0 / 6.5,
            height_ratio=9.0 / 6.5,
        ),
    )
    assert source.sentence_break_hints == (stale_sentence,)
    assert source.inline_icon_hints == (stale_icon,)
