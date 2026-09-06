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
    TaggedDocument,
)
from tagged_pdf_extractor.domain.readability_formatting import (
    apply_readability_formatting,
    detect_inline_icon_hints,
    detect_sentence_break_hints,
)
from tagged_pdf_extractor.domain.text_joining import join_text_parts


def _fragment(*text_parts: str, mcid: int = 1) -> ContentFragment:
    return ContentFragment(page_index=0, mcid=mcid, text_parts=text_parts)


def _element(
    role: str,
    *children: StructureElement | ContentFragment,
    actual_text: str | None = None,
) -> StructureElement:
    return StructureElement(
        source_role=role,
        semantic_role=role,
        actual_text=actual_text,
        children=children,
    )


def _document(
    *children: StructureElement | ContentFragment,
    line_break_hints: tuple[LineBreakHint, ...] = (),
) -> TaggedDocument:
    return TaggedDocument(
        source_path=Path("manual.pdf"),
        marked=True,
        language=None,
        role_map=(),
        children=children,
        line_break_hints=line_break_hints,
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


def test_unicode_ellipsis_does_not_create_a_sentence_break() -> None:
    document = _list_body_document(_fragment("Wait… Continue carefully."))

    assert detect_sentence_break_hints(document) == ()


def test_model_and_file_tokens_are_protected_but_terminal_period_splits() -> None:
    text = "Use QE65LS03DAUXXN and manual.v2.xml. Next step."
    document = _list_body_document(_fragment(text))

    assert detect_sentence_break_hints(document) == (
        SentenceBreakHint((0, 0, 1, 0), (text.index("Next"),)),
    )


def test_lowercase_or_ambiguous_continuation_does_not_split() -> None:
    document = _list_body_document(_fragment("First thought. perhaps continue."))

    assert detect_sentence_break_hints(document) == ()


def test_general_body_paragraph_outside_approved_context_does_not_split() -> None:
    document = _document(
        _element("paragraph", _fragment("First sentence. Next sentence."))
    )

    assert detect_sentence_break_hints(document) == ()


@pytest.mark.parametrize("role", ["heading", "caption", "label", "figure"])
def test_non_body_semantic_roles_do_not_split_inside_list_body(role: str) -> None:
    excluded = _element(role, _fragment("First sentence. Next sentence."))
    document = _list_body_document(excluded)

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


def test_apply_readability_formatting_replaces_only_detected_hint_fields() -> None:
    text = "First sentence. Next sentence."
    source = _list_body_document(_fragment(text, mcid=60))
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
    assert formatted.sentence_break_hints == (
        SentenceBreakHint((0, 0, 1, 0), (text.index("Next"),)),
    )
    assert formatted.inline_icon_hints == ()
    assert detect_inline_icon_hints(source) == ()
    assert source.sentence_break_hints == (stale_sentence,)
    assert source.inline_icon_hints == (stale_icon,)
