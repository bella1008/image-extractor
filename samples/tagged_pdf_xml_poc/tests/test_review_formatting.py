from dataclasses import FrozenInstanceError, replace
import os
from pathlib import Path
from typing import Literal, get_type_hints

import pytest

from tagged_pdf_extractor.domain.models import (
    ContentFragment,
    HeadingPromotion,
    LineBreakHint,
    StructureElement,
    SubtitleHint,
    TaggedDocument,
    TextDisplayHint,
    TextStyle,
)
from tagged_pdf_extractor.domain import review_formatting
from tagged_pdf_extractor.domain.display_hint_validation import (
    validate_review_formatting_hints,
)
from tagged_pdf_extractor.domain.review_formatting import (
    detect_form_cluster_hints,
    detect_rf_line_break_hints,
)
from tagged_pdf_extractor.infrastructure.pypdf_reader import TaggedPdfReader

from .acceptance_support import require_sample


ZG_NAME = "BN68-25448A-00_SUG_Y26 TV ALL_ZG XN ZT_L05_260204.0.pdf"
ZG_SAMPLE = Path(
    os.environ.get(
        "TAGGED_PDF_ZG_SAMPLE",
        Path(__file__).parents[2] / "SUG_RAW" / "TV_ZG" / ZG_NAME,
    )
)


def _fragment(
    text: str,
    *,
    weight: int | None = None,
    size: float | None = None,
    mcid: int = 1,
) -> ContentFragment:
    styles = ()
    if weight is not None:
        styles = (TextStyle(f"Synthetic-{weight}", size),)
    return ContentFragment(
        page_index=0,
        mcid=mcid,
        text_parts=(text,),
        text_styles=styles,
    )


def _element(
    role: str,
    *children: StructureElement | ContentFragment,
    actual_text: str | None = None,
    source_role: str | None = None,
) -> StructureElement:
    return StructureElement(
        source_role=source_role or role,
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


def _styled_paragraph(
    text: str,
    weight: int,
    size: float | None,
    *,
    source_role: str = "P",
    line_count: int = 1,
) -> StructureElement:
    return _element(
        "paragraph",
        *(
            _fragment(
                text if index == 0 else " continued",
                weight=weight,
                size=size,
                mcid=index + 1,
            )
            for index in range(line_count)
        ),
        source_role=source_role,
    )


def _form_document(
    *,
    filename: str = ZG_NAME,
    title_weight: int = 800,
    title_size: float | None = 8.0,
    title_text: str = "Top form title",
    title_source_role: str = "Heading_B",
    title_line_count: int = 1,
    direct_label_count: int = 3,
    direct_label_weight: int = 600,
    direct_label_size: float | None = 7.0,
    direct_label_line_count: int = 1,
    direct_detail_weight: int = 400,
    direct_detail_size: float | None = 6.5,
    direct_detail_text: str | None = None,
    table_cell_count: int = 2,
    table_detail_weight: int = 400,
    table_detail_size: float | None = 6.5,
    include_table: bool = True,
    extra_title: bool = False,
) -> TaggedDocument:
    children: list[StructureElement] = [
        _styled_paragraph(
            title_text,
            title_weight,
            title_size,
            source_role=title_source_role,
            line_count=title_line_count,
        )
    ]
    if extra_title:
        children.append(_styled_paragraph("Second top title", 800, 8.0))
    for index in range(direct_label_count):
        children.extend(
            (
                _styled_paragraph(
                    f"Direct label {index}",
                    direct_label_weight,
                    direct_label_size,
                    line_count=direct_label_line_count,
                ),
                _styled_paragraph(
                    direct_detail_text or f"Direct detail {index}",
                    direct_detail_weight,
                    direct_detail_size,
                ),
            )
        )
    if include_table:
        cells = tuple(
            _element(
                "table_cell",
                _styled_paragraph(f"Cell label {index}", 600, 7.0),
                _styled_paragraph(
                    f"Cell detail {index}",
                    table_detail_weight,
                    table_detail_size,
                ),
            )
            for index in range(table_cell_count)
        )
        children.append(
            _element(
                "paragraph",
                _element("table", _element("table_row", *cells)),
                source_role="Table-Wrapper",
            )
        )
    return TaggedDocument(
        Path(filename),
        True,
        "en",
        (),
        (_element("section", *children, source_role="Story"),),
    )


def _promotion(path: tuple[int, ...]) -> HeadingPromotion:
    return HeadingPromotion(
        child_path=path,
        level=2,
        label="01",
        title="Promoted",
        series_index=0,
        heading_font_size=12.0,
        body_font_size=7.0,
        font_size_ratio=12.0 / 7.0,
        promotion_reason="test",
    )


def _wrap_paragraph_contents(
    document: TaggedDocument,
    path: tuple[int, ...],
    wrapper_role: str,
) -> TaggedDocument:
    def replace_at_path(
        children: tuple[StructureElement | ContentFragment, ...],
        remaining: tuple[int, ...],
    ) -> tuple[StructureElement | ContentFragment, ...]:
        index, *tail = remaining
        target = children[index]
        assert isinstance(target, StructureElement)
        if tail:
            replacement = replace(
                target,
                children=replace_at_path(target.children, tuple(tail)),
            )
        else:
            replacement = replace(
                target,
                children=(_element(wrapper_role, *target.children),),
            )
        return (*children[:index], replacement, *children[index + 1 :])

    return replace(document, children=replace_at_path(document.children, path))


def test_text_display_hint_is_frozen_and_document_default_is_compatible() -> None:
    hint = TextDisplayHint(
        child_path=(0, 1),
        display_role="strong_label",
        font_weight=600,
        font_size=7.0,
        comparison_body_font_weight=400,
        comparison_body_font_size=6.5,
        reason="form_cluster_middle_tier_with_weaker_detail",
    )

    assert hint.display_role == "strong_label"
    assert TaggedDocument(Path("manual.pdf"), True, None, (), ()).text_display_hints == ()
    with pytest.raises(FrozenInstanceError):
        hint.display_role = "section_heading"  # type: ignore[misc]


def test_complete_form_cluster_emits_one_heading_and_direct_and_table_labels() -> None:
    document = _form_document()

    hints = detect_form_cluster_hints(document)

    assert [(hint.child_path, hint.display_role) for hint in hints] == [
        ((0, 0), "section_heading"),
        ((0, 1), "strong_label"),
        ((0, 3), "strong_label"),
        ((0, 5), "strong_label"),
        ((0, 7, 0, 0, 0, 0), "strong_label"),
        ((0, 7, 0, 0, 1, 0), "strong_label"),
    ]
    assert hints[0].font_weight == 800
    assert hints[0].font_size == 8.0
    assert hints[0].comparison_body_font_weight == 400
    assert hints[0].comparison_body_font_size == 6.5
    assert len({hint.child_path for hint in hints}) == len(hints)
    assert not any(
        left.child_path != right.child_path
        and (
            left.child_path[: len(right.child_path)] == right.child_path
            or right.child_path[: len(left.child_path)] == left.child_path
        )
        for left in hints
        for right in hints
    )


@pytest.mark.parametrize(
    ("path", "wrapper_role"),
    [
        ((0, 0), "figure"),
        ((0, 1), "caption"),
        ((0, 7, 0, 0, 0, 0), "division"),
    ],
    ids=["title-figure", "direct-label-caption", "table-label-division"],
)
def test_form_cluster_with_non_inline_paragraph_descendant_stays_plain(
    path: tuple[int, ...],
    wrapper_role: str,
) -> None:
    document = _wrap_paragraph_contents(_form_document(), path, wrapper_role)

    assert detect_form_cluster_hints(document) == ()

    formatted = review_formatting.apply_profile_review_formatting(document)
    assert formatted.text_display_hints == ()
    validated = validate_review_formatting_hints(formatted)
    assert dict(validated.text_display_by_path) == {}


def test_long_direct_detail_remains_valid_body_evidence() -> None:
    document = _form_document(direct_detail_text="body " * 50)

    hints = detect_form_cluster_hints(document)

    assert sum(hint.display_role == "strong_label" for hint in hints) == 5


def test_parent_cluster_does_not_use_nested_section_table_evidence() -> None:
    parent_document = _form_document(include_table=False)
    parent = parent_document.children[0]
    nested = _form_document().children[0]
    assert isinstance(parent, StructureElement)
    assert isinstance(nested, StructureElement)
    nested_index = len(parent.children)
    document = replace(
        parent_document,
        children=(replace(parent, children=(*parent.children, nested)),),
    )

    hints = detect_form_cluster_hints(document)

    nested_path = (0, nested_index)
    assert len(hints) == 6
    assert all(hint.child_path[: len(nested_path)] == nested_path for hint in hints)


def test_cluster_accepts_multiple_valid_tables_and_includes_all_table_labels() -> None:
    document = _form_document()
    section = document.children[0]
    assert isinstance(section, StructureElement)
    first_table_wrapper = section.children[-1]
    document = replace(
        document,
        children=(
            replace(
                section,
                children=(*section.children, first_table_wrapper),
            ),
        ),
    )

    hints = detect_form_cluster_hints(document)

    assert sum(hint.display_role == "section_heading" for hint in hints) == 1
    assert sum(hint.display_role == "strong_label" for hint in hints) == 7
    assert {hint.child_path for hint in hints if hint.display_role == "strong_label"} >= {
        (0, 7, 0, 0, 0, 0),
        (0, 7, 0, 0, 1, 0),
        (0, 8, 0, 0, 0, 0),
        (0, 8, 0, 0, 1, 0),
    }


def test_display_hint_role_parameter_uses_closed_literal_type() -> None:
    annotations = get_type_hints(review_formatting._display_hint)

    assert annotations["role"] == Literal["section_heading", "strong_label"]


@pytest.mark.parametrize(
    "document",
    [
        _form_document(extra_title=True),
        _form_document(direct_label_count=2),
        _form_document(title_weight=600),
        _form_document(title_size=7.0),
        _form_document(include_table=False),
        _form_document(direct_detail_weight=600),
        _form_document(direct_detail_size=7.0),
        _form_document(table_cell_count=1),
        _form_document(table_detail_weight=600),
        _form_document(table_detail_size=7.0),
        _form_document(title_text="x" * 161),
        _form_document(title_line_count=3),
        _form_document(direct_label_line_count=3),
        _form_document(title_size=None),
        _form_document(direct_label_size=None),
        _form_document(direct_label_weight=500),
        _form_document(title_source_role="Heading1"),
    ],
    ids=[
        "nonunique-title",
        "too-few-direct-label-groups",
        "title-weight-not-stronger",
        "title-size-not-larger",
        "missing-table",
        "direct-detail-weight-not-weaker",
        "direct-detail-size-not-smaller",
        "too-few-table-cells",
        "table-detail-weight-not-weaker",
        "table-detail-size-not-smaller",
        "title-over-short-bound",
        "title-over-line-bound",
        "label-over-line-bound",
        "missing-style-size",
        "missing-label-size",
        "label-tier-mismatch-with-table",
        "source-heading-conflict",
    ],
)
def test_incomplete_or_ambiguous_form_cluster_is_rejected(
    document: TaggedDocument,
) -> None:
    assert detect_form_cluster_hints(document) == ()


@pytest.mark.parametrize(
    ("conflict_field", "conflict_value"),
    [
        ("heading_promotions", (_promotion((0,)),)),
        ("heading_promotions", (_promotion((0, 0, 0)),)),
        (
            "subtitle_hints",
            (
                SubtitleHint(
                    child_path=(0, 1),
                    font_weight=600,
                    comparison_body_font_weight=400,
                    observed_line_count=1,
                ),
            ),
        ),
        (
            "subtitle_hints",
            (
                SubtitleHint(
                    child_path=(0, 1, 0),
                    font_weight=600,
                    comparison_body_font_weight=400,
                    observed_line_count=1,
                ),
            ),
        ),
    ],
)
def test_form_cluster_rejects_existing_path_or_descendant_conflicts(
    conflict_field: str,
    conflict_value: tuple[HeadingPromotion, ...] | tuple[SubtitleHint, ...],
) -> None:
    document = replace(_form_document(), **{conflict_field: conflict_value})

    assert detect_form_cluster_hints(document) == ()


def test_enabled_profile_sets_both_review_hint_sets_from_source_truth() -> None:
    document = replace(
        _form_document(),
        line_break_hints=(LineBreakHint((9,), "manual"),),
        text_display_hints=(
            TextDisplayHint((8,), "strong_label", 1, 1.0, 1, 1.0, "manual"),
        ),
    )

    formatted = review_formatting.apply_profile_review_formatting(document)

    assert formatted.line_break_hints == ()
    assert formatted.text_display_hints == detect_form_cluster_hints(document)
    assert len(formatted.text_display_hints) == 6


def test_xu_applies_source_line_break_without_zg_form_formatting() -> None:
    document = _document(
        (_fragment("First specification,"), _newline(), _fragment("Second specification")),
        filename="BN68-24437C-01_SUG_Y26 TV ALL_XU_ENG_260129.0.pdf",
    )

    formatted = review_formatting.apply_profile_review_formatting(document)

    assert len(formatted.line_break_hints) == 1
    assert formatted.text_display_hints == ()


@pytest.mark.parametrize(
    "filename",
    [
        "BN68-25100B-00_SUG_Y26 TV ALL_ZC_L02_260122.0.pdf",
        "BN68-25099B-00_SUG_Y26 TV ALL_ZA_ENG_260126.0.pdf",
        "BN68-25031B-00_SUG_Y26 TV ALL_XY_ENG_251229.0.pdf",
        "BN68-25108A-00_SUG_Y26 TV ALL_KR_KOR_251218.0.pdf",
        "malformed_ZG XN ZT_L05.pdf",
    ],
)
def test_disabled_profiles_preserve_manual_text_display_hints(filename: str) -> None:
    document = replace(
        _form_document(filename=filename),
        text_display_hints=(
            TextDisplayHint((8,), "strong_label", 1, 1.0, 1, 1.0, "manual"),
        ),
    )

    assert review_formatting.apply_profile_review_formatting(document) is document


def test_zg_sample_contains_ten_form_headings_and_retains_90_line_breaks() -> None:
    sample = require_sample(ZG_SAMPLE if ZG_SAMPLE.is_file() else None, "ZG")
    document = review_formatting.apply_profile_review_formatting(
        TaggedPdfReader().read(sample)
    )

    assert len(document.line_break_hints) == 90
    assert sum(
        hint.display_role == "section_heading"
        for hint in document.text_display_hints
    ) == 10
    assert sum(
        hint.display_role == "strong_label"
        for hint in document.text_display_hints
    ) == 70


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


@pytest.mark.parametrize("block_role", ["list", "table"])
def test_block_between_comma_and_newline_interrupts_inline_adjacency(
    block_role: str,
) -> None:
    document = _document(
        (
            _fragment("first,"),
            _element(block_role),
            _newline(),
            _fragment("second"),
        )
    )

    assert detect_rf_line_break_hints(document.children) == ()


@pytest.mark.parametrize("block_role", ["list", "table"])
def test_block_between_newline_and_following_text_interrupts_inline_adjacency(
    block_role: str,
) -> None:
    document = _document(
        (
            _fragment("first,"),
            _newline(),
            _element(block_role),
            _fragment("second"),
        )
    )

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
def test_non_zg_profiles_replace_manual_hints_with_source_line_breaks(
    filename: str,
) -> None:
    document = _document(
        (_fragment("first,"), _newline(), _fragment("second")),
        filename=filename,
    )
    document = replace(document, line_break_hints=(LineBreakHint((9,), "manual"),))

    formatted = review_formatting.apply_profile_review_formatting(document)

    assert formatted is not document
    assert formatted.line_break_hints == detect_rf_line_break_hints(document.children)
    assert formatted.line_break_hints != document.line_break_hints
    assert formatted.text_display_hints == document.text_display_hints


def test_malformed_filename_still_uses_source_line_break_evidence() -> None:
    document = _document(
        (_fragment("first,"), _newline(), _fragment("second")),
        filename="BN68-invalid_ZG XN ZT_L05.pdf",
    )
    document = replace(document, line_break_hints=(LineBreakHint((9,), "manual"),))

    formatted = review_formatting.apply_profile_review_formatting(document)

    assert formatted.line_break_hints == detect_rf_line_break_hints(document.children)
    assert formatted.line_break_hints != document.line_break_hints
    assert formatted.text_display_hints == ()


def test_parent_folder_does_not_enable_zg_form_formatting_for_xy_filename() -> None:
    filename = str(
        Path("ZG XN ZT_L05")
        / "BN68-25031B-00_SUG_Y26 TV ALL_XY_ENG_251229.0.pdf"
    )
    document = _document(
        (_fragment("first,"), _newline(), _fragment("second")),
        filename=filename,
    )

    formatted = review_formatting.apply_profile_review_formatting(document)

    assert len(formatted.line_break_hints) == 1
    assert formatted.text_display_hints == ()
