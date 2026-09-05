from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from tagged_pdf_extractor.domain.models import (
    ContentFragment,
    LineBreakHint,
    StructureElement,
    TaggedDocument,
)
from tagged_pdf_extractor.domain.review_formatting import detect_rf_line_break_hints


def _fragment(text: str) -> ContentFragment:
    return ContentFragment(page_index=0, mcid=1, text_parts=(text,))


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
    paragraph_children: tuple[StructureElement | ContentFragment, ...],
    *,
    in_table_cell: bool = True,
) -> TaggedDocument:
    paragraph = _element("paragraph", *paragraph_children)
    if in_table_cell:
        children = (
            _element(
                "table",
                _element("table_row", _element("table_cell", paragraph)),
            ),
        )
    else:
        children = (paragraph,)
    return TaggedDocument(Path("manual.pdf"), True, "en", (), children)


def _newline(actual_text: str = "\n") -> StructureElement:
    return _element("span", actual_text=actual_text)


def test_line_break_hint_is_frozen_and_document_default_is_compatible() -> None:
    hint = LineBreakHint(child_path=(0, 1, 0, 2))

    assert hint.child_path == (0, 1, 0, 2)
    assert hint.reason == "source_actual_text_newline_after_comma_in_table_cell"
    assert TaggedDocument(Path("manual.pdf"), True, None, (), ()).line_break_hints == ()
    with pytest.raises(FrozenInstanceError):
        hint.child_path = ()  # type: ignore[misc]


def test_detects_exact_newline_boundary_and_uses_all_child_indices() -> None:
    document = _document((_fragment("first,"), _newline(), _fragment("second")))

    assert detect_rf_line_break_hints(document.children) == (
        LineBreakHint(
            child_path=(0, 0, 0, 0, 1),
            reason="source_actual_text_newline_after_comma_in_table_cell",
        ),
    )


def test_detects_boundary_across_nested_inline_wrappers_without_leaving_paragraph() -> None:
    document = _document(
        (
            _element("span", _element("link", _fragment("nested,"))),
            _element("span", _element("span", actual_text="\n")),
            _element("link", _element("span", _fragment("continuation"))),
        )
    )

    assert detect_rf_line_break_hints(document.children) == (
        LineBreakHint(
            child_path=(0, 0, 0, 0, 1, 0),
            reason="source_actual_text_newline_after_comma_in_table_cell",
        ),
    )


@pytest.mark.parametrize(
    "paragraph_children",
    [
        (_fragment("ordinary, continuation"),),
        (_fragment("not comma"), _newline(), _fragment("continuation")),
        (_fragment("comma,"), _newline("\r"), _fragment("continuation")),
        (_fragment("comma,"), _newline("\x03"), _fragment("continuation")),
        (_fragment("comma,"), _newline("\n "), _fragment("continuation")),
        (_fragment("comma,"), _newline(), _fragment("   ")),
        (_fragment("   "), _newline(), _fragment("continuation")),
        (_fragment("comma,"), _fragment("   "), _newline(), _fragment("continuation")),
        (_fragment("comma,"), _newline(), _fragment("   "), _fragment("continuation")),
        (_newline(), _fragment("continuation")),
        (_fragment("comma,"), _newline()),
    ],
)
def test_rejects_missing_or_malformed_boundary_evidence(
    paragraph_children: tuple[StructureElement | ContentFragment, ...],
) -> None:
    document = _document(paragraph_children)

    assert detect_rf_line_break_hints(document.children) == ()


def test_rejects_newline_outside_table_cell() -> None:
    document = _document(
        (_fragment("comma,"), _newline(), _fragment("continuation")),
        in_table_cell=False,
    )

    assert detect_rf_line_break_hints(document.children) == ()


def test_does_not_cross_paragraph_boundary_for_adjacent_visible_text() -> None:
    first = _element("paragraph", _fragment("comma,"))
    second = _element("paragraph", _newline(), _fragment("continuation"))
    document = TaggedDocument(
        Path("manual.pdf"),
        True,
        "en",
        (),
        (_element("table", _element("table_row", _element("table_cell", first, second))),),
    )

    assert detect_rf_line_break_hints(document.children) == ()


def test_does_not_descend_through_a_block_inside_a_paragraph() -> None:
    nested_block = _element(
        "list",
        _fragment("comma,"),
        _newline(),
        _fragment("continuation"),
    )
    document = _document((nested_block,))

    assert detect_rf_line_break_hints(document.children) == ()
