from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from tagged_pdf_extractor.domain.models import (
    ContentFragment,
    LineBreakHint,
    StructureElement,
    TaggedDocument,
)
from tagged_pdf_extractor.domain import review_formatting
from tagged_pdf_extractor.domain.review_formatting import detect_rf_line_break_hints
from tagged_pdf_extractor.infrastructure.pypdf_reader import TaggedPdfReader

from .acceptance_support import require_sample


ZG_NAME = "BN68-25448A-00_SUG_Y26 TV ALL_ZG XN ZT_L05_260204.0.pdf"
ZG_SAMPLE = Path(__file__).parents[2] / "SUG_RAW" / "TV_ZG" / ZG_NAME


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
    filename: str = "manual.pdf",
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
    return TaggedDocument(Path(filename), True, "en", (), children)


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


def test_detects_inner_paragraph_inside_outer_paragraph_table_wrapper() -> None:
    inner_paragraph = _element(
        "paragraph",
        _fragment("first,"),
        _newline(),
        _fragment("second"),
    )
    children = (
        _element(
            "paragraph",
            _element(
                "table",
                _element(
                    "table_row",
                    _element("table_cell", inner_paragraph),
                ),
            ),
        ),
    )

    assert detect_rf_line_break_hints(children) == (
        LineBreakHint(child_path=(0, 0, 0, 0, 0, 1)),
    )


def test_outer_table_wrapper_does_not_join_separate_inner_paragraphs() -> None:
    first_paragraph = _element("paragraph", _fragment("first,"))
    second_paragraph = _element(
        "paragraph",
        _newline(),
        _fragment("second"),
    )
    children = (
        _element(
            "paragraph",
            _element(
                "table",
                _element(
                    "table_row",
                    _element(
                        "table_cell",
                        first_paragraph,
                        second_paragraph,
                    ),
                ),
            ),
        ),
    )

    assert detect_rf_line_break_hints(children) == ()


def test_zg_sample_contains_90_source_authored_table_line_breaks() -> None:
    sample = require_sample(ZG_SAMPLE if ZG_SAMPLE.is_file() else None, "ZG")
    document = TaggedPdfReader().read(sample)

    assert len(detect_rf_line_break_hints(document.children)) == 90


def test_exposes_profile_scoped_review_formatting_application() -> None:
    assert callable(
        getattr(review_formatting, "apply_profile_review_formatting", None)
    )


def test_enabled_profile_replaces_manual_hints_with_detected_source_truth() -> None:
    document = _document(
        (_fragment("first,"), _newline(), _fragment("second")),
        filename=ZG_NAME,
    )
    manual_hint = LineBreakHint((9,), "manual")
    document = replace(document, line_break_hints=(manual_hint, manual_hint))

    formatted = review_formatting.apply_profile_review_formatting(document)

    detected = detect_rf_line_break_hints(document.children)
    assert formatted.line_break_hints == detected
    assert formatted.line_break_hints != document.line_break_hints
    assert len(formatted.line_break_hints) == 1
    assert replace(formatted, line_break_hints=document.line_break_hints) == document


def test_enabled_profile_clears_manual_hints_when_source_has_no_evidence() -> None:
    document = _document((_fragment("ordinary text"),), filename=ZG_NAME)
    document = replace(document, line_break_hints=(LineBreakHint((9,), "manual"),))

    formatted = review_formatting.apply_profile_review_formatting(document)

    assert formatted is not document
    assert formatted.line_break_hints == ()


@pytest.mark.parametrize(
    "filename",
    [
        "BN68-25100B-00_SUG_Y26 TV ALL_ZC_L02_260122.0.pdf",
        "BN68-25099B-00_SUG_Y26 TV ALL_ZA_ENG_260126.0.pdf",
        "BN68-25031B-00_SUG_Y26 TV ALL_XY_ENG_251229.0.pdf",
        "BN68-25108A-00_SUG_Y26 TV ALL_KR_KOR_251218.0.pdf",
    ],
)
def test_disabled_profiles_preserve_identity_and_manual_hints(filename: str) -> None:
    document = _document(
        (_fragment("first,"), _newline(), _fragment("second")),
        filename=filename,
    )
    document = replace(document, line_break_hints=(LineBreakHint((9,), "manual"),))

    formatted = review_formatting.apply_profile_review_formatting(document)

    assert formatted is document
    assert formatted.line_break_hints == document.line_break_hints


def test_malformed_filename_preserves_identity_and_manual_hints() -> None:
    document = _document(
        (_fragment("first,"), _newline(), _fragment("second")),
        filename="BN68-invalid_ZG XN ZT_L05.pdf",
    )
    document = replace(document, line_break_hints=(LineBreakHint((9,), "manual"),))

    assert review_formatting.apply_profile_review_formatting(document) is document


def test_parent_folder_cannot_enable_xy_filename() -> None:
    filename = str(
        Path("ZG XN ZT_L05")
        / "BN68-25031B-00_SUG_Y26 TV ALL_XY_ENG_251229.0.pdf"
    )
    document = _document(
        (_fragment("first,"), _newline(), _fragment("second")),
        filename=filename,
    )

    assert review_formatting.apply_profile_review_formatting(document) is document
