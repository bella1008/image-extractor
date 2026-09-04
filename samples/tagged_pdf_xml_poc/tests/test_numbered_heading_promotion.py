from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from tagged_pdf_extractor.domain.models import (
    ContentFragment,
    Diagnostic,
    HeadingPromotion,
    NumberedHeadingSeriesAudit,
    StructureElement,
    TaggedDocument,
    TextStyle,
)
from tagged_pdf_extractor.domain.numbered_heading_promotion import (
    promote_numbered_chapter_headings,
)


def _fragment(
    text: str,
    size: float | None,
    *,
    page_index: int = 0,
    font_name: str | None = "SamsungOne",
) -> ContentFragment:
    return ContentFragment(
        page_index,
        None,
        (text,),
        text_styles=(TextStyle(font_name, size),),
    )


def _element(
    role: str,
    *children: StructureElement | ContentFragment,
    page_index: int | None = None,
) -> StructureElement:
    return StructureElement(
        source_role=role,
        semantic_role=role,
        page_index=page_index,
        children=children,
    )


def _candidate(
    label: str,
    title: str = "Chapter title",
    *,
    label_size: float | None = 12.0,
    title_size: float | None = 12.0,
    page_index: int = 0,
    extra_children: tuple[StructureElement | ContentFragment, ...] = (),
) -> StructureElement:
    return _element(
        "list_item",
        _element("label", _fragment(label, label_size, page_index=page_index)),
        _element("list_body", _fragment(title, title_size, page_index=page_index)),
        *extra_children,
        page_index=page_index,
    )


def _paragraph(
    text: str = "Ordinary body text",
    size: float | None = 8.0,
    *,
    page_index: int = 0,
) -> StructureElement:
    return _element("paragraph", _fragment(text, size, page_index=page_index))


def _document(*children: StructureElement | ContentFragment) -> TaggedDocument:
    return TaggedDocument(
        source_path=Path("manual.pdf"),
        marked=True,
        language="en",
        role_map=(),
        children=children,
    )


def _series(
    labels: tuple[str, ...],
    *,
    heading_size: float = 12.0,
    body_size: float = 8.0,
) -> StructureElement:
    children: list[StructureElement] = []
    for index, label in enumerate(labels):
        children.extend(
            (
                _candidate(
                    label,
                    f"Title {label}",
                    label_size=heading_size,
                    title_size=heading_size,
                    page_index=index,
                ),
                _paragraph(size=body_size, page_index=index),
            )
        )
    return _element("list", *children)


def _diagnostics(document: TaggedDocument, code: str) -> list[Diagnostic]:
    return [diagnostic for diagnostic in document.diagnostics if diagnostic.code == code]


def test_heading_promotion_is_frozen() -> None:
    promotion = HeadingPromotion(
        child_path=(0,),
        level=2,
        label="01",
        title="Title",
        series_index=0,
        heading_font_size=12.0,
        body_font_size=8.0,
        font_size_ratio=1.5,
        promotion_reason="numbered_chapter_structure_sequence_typography",
    )

    with pytest.raises(FrozenInstanceError):
        promotion.level = 3  # type: ignore[misc]


def test_numbered_heading_series_audit_is_frozen() -> None:
    audit = NumberedHeadingSeriesAudit(0, ("01", "02"), True)

    with pytest.raises(FrozenInstanceError):
        audit.valid_sequence = False  # type: ignore[misc]


def test_promotes_contiguous_series_through_09_and_10() -> None:
    source = _document(_series(tuple(f"{number:02d}" for number in range(1, 11))))

    result = promote_numbered_chapter_headings(source)

    assert [promotion.label for promotion in result.heading_promotions] == [
        f"{number:02d}" for number in range(1, 11)
    ]
    assert result.numbered_heading_series[0].valid_sequence is True
    assert result.numbered_heading_series[0].labels == tuple(
        f"{number:02d}" for number in range(1, 11)
    )
    assert all(promotion.level == 2 for promotion in result.heading_promotions)
    assert all(
        promotion.promotion_reason
        == "numbered_chapter_structure_sequence_typography"
        for promotion in result.heading_promotions
    )


@pytest.mark.parametrize("label", ("00", "1.", "(1)", "０１", "①"))
def test_rejects_non_ascii_two_digit_labels(label: str) -> None:
    source = _document(_element("list", _candidate(label), _paragraph()))

    result = promote_numbered_chapter_headings(source)

    assert result.heading_promotions == ()
    assert result.numbered_heading_series == ()


def test_rejects_nested_label_and_list_body() -> None:
    nested = _element(
        "list_item",
        _element("container", _element("label", _fragment("01", 12.0))),
        _element("container", _element("list_body", _fragment("Nested", 12.0))),
    )
    source = _document(_element("list", nested, _paragraph()))

    result = promote_numbered_chapter_headings(source)

    assert result.numbered_heading_series == ()
    assert result.heading_promotions == ()


@pytest.mark.parametrize(
    "bad_item",
    (
        _element("list_item", _element("label", _fragment("01", 12.0))),
        _element(
            "list_item",
            _element("label", _fragment("01", 12.0)),
            _element("label", _fragment("01", 12.0)),
            _element("list_body", _fragment("Title", 12.0)),
        ),
        _element(
            "list_item",
            _element("label", _fragment("01", 12.0)),
            _element("list_body", _fragment("Title", 12.0)),
            _element("list_body", _fragment("Again", 12.0)),
        ),
    ),
)
def test_rejects_missing_or_duplicate_direct_label_body(
    bad_item: StructureElement,
) -> None:
    source = _document(_element("list", bad_item, _paragraph()))

    result = promote_numbered_chapter_headings(source)

    assert result.numbered_heading_series == ()
    assert result.heading_promotions == ()


def test_rejects_empty_normalized_title() -> None:
    source = _document(_element("list", _candidate("01", " \n\t "), _paragraph()))

    result = promote_numbered_chapter_headings(source)

    assert result.numbered_heading_series == ()
    assert result.heading_promotions == ()


def test_candidates_can_occupy_different_sibling_positions_among_other_items() -> None:
    ordinary = _element("list_item", _fragment("Not a numbered chapter", 8.0))
    source = _document(
        _element(
            "list",
            ordinary,
            _candidate("01", "First"),
            _paragraph(),
            ordinary,
            _candidate("02", "Second"),
            _paragraph(),
            ordinary,
        )
    )

    result = promote_numbered_chapter_headings(source)

    assert [promotion.child_path for promotion in result.heading_promotions] == [
        (0, 1),
        (0, 4),
    ]


@pytest.mark.parametrize(
    ("labels", "expected_labels"),
    (
        (("01", "03"), ("01", "02")),
        (("01", "02", "02"), ("01", "02", "03")),
        (("02", "03"), ("01", "02")),
        (("01",), ("01", "02")),
    ),
)
def test_invalid_sequences_are_audited_without_promotions(
    labels: tuple[str, ...], expected_labels: tuple[str, ...]
) -> None:
    source = _document(_series(labels))

    result = promote_numbered_chapter_headings(source)

    assert result.heading_promotions == ()
    assert len(result.numbered_heading_series) == 1
    assert result.numbered_heading_series[0].labels == labels
    assert result.numbered_heading_series[0].valid_sequence is False
    diagnostic = _diagnostics(result, "numbered_heading_sequence_invalid")[0]
    assert diagnostic.severity == "error"
    assert diagnostic.context["series_index"] == 0
    assert diagnostic.context["actual_labels"] == labels
    assert diagnostic.context["expected_labels"] == expected_labels
    assert diagnostic.context["candidate_evidence"] == tuple(
        {"page_index": index, "child_path": (0, index * 2)}
        for index in range(len(labels))
    )


def test_valid_three_heading_sequence_promotes() -> None:
    result = promote_numbered_chapter_headings(
        _document(_series(("01", "02", "03")))
    )

    assert [promotion.label for promotion in result.heading_promotions] == [
        "01",
        "02",
        "03",
    ]


@pytest.mark.parametrize(
    ("heading_size", "body_size", "expected_ratio"),
    ((12.0, 8.0, 1.5), (16.0, 7.0, 16.0 / 7.0), (12.0, 6.5, 12.0 / 6.5)),
)
def test_typography_at_or_above_ratio_threshold_promotes(
    heading_size: float, body_size: float, expected_ratio: float
) -> None:
    result = promote_numbered_chapter_headings(
        _document(
            _series(
                ("01", "02"), heading_size=heading_size, body_size=body_size
            )
        )
    )

    assert len(result.heading_promotions) == 2
    assert result.heading_promotions[0].font_size_ratio == pytest.approx(expected_ratio)


def test_ratio_below_threshold_rejects_candidate_but_keeps_valid_sibling() -> None:
    source = _document(
        _element(
            "list",
            _candidate("01", label_size=11.9, title_size=11.9),
            _paragraph(size=8.0),
            _candidate("02", label_size=12.0, title_size=12.0),
            _paragraph(size=8.0),
        )
    )

    result = promote_numbered_chapter_headings(source)

    assert [promotion.label for promotion in result.heading_promotions] == ["02"]
    diagnostic = _diagnostics(
        result, "numbered_heading_font_ratio_below_threshold"
    )[0]
    assert diagnostic.context == {
        "series_index": 0,
        "label": "01",
        "child_path": (0, 0),
        "page_index": 0,
        "label_font_size": 11.9,
        "list_body_font_size": 11.9,
        "heading_font_size": 11.9,
        "body_font_size": 8.0,
        "font_size_ratio": 11.9 / 8.0,
    }


def test_label_body_size_mismatch_rejects_candidate() -> None:
    source = _document(
        _element(
            "list",
            _candidate("01", label_size=16.0, title_size=7.0),
            _paragraph(),
            _candidate("02"),
            _paragraph(),
        )
    )

    result = promote_numbered_chapter_headings(source)

    assert [promotion.label for promotion in result.heading_promotions] == ["02"]
    diagnostic = _diagnostics(
        result, "numbered_heading_label_body_size_mismatch"
    )[0]
    assert diagnostic.context["label_font_size"] == 16.0
    assert diagnostic.context["list_body_font_size"] == 7.0
    assert diagnostic.context["relative_difference"] == pytest.approx(9.0 / 16.0)


@pytest.mark.parametrize("missing", ("baseline", "label", "body"))
def test_missing_required_typography_rejects_candidate(missing: str) -> None:
    first = _candidate(
        "01",
        label_size=None if missing == "label" else 12.0,
        title_size=None if missing == "body" else 12.0,
    )
    source = _document(
        _element(
            "list",
            first,
            _paragraph(size=None if missing == "baseline" else 8.0),
            _candidate("02"),
            _paragraph(size=None if missing == "baseline" else 8.0),
        )
    )

    result = promote_numbered_chapter_headings(source)

    assert "01" not in [promotion.label for promotion in result.heading_promotions]
    diagnostic = _diagnostics(
        result, "numbered_heading_typography_insufficient"
    )[0]
    assert diagnostic.context["series_index"] == 0
    assert diagnostic.context["label"] == "01"
    assert diagnostic.context["child_path"] == (0, 0)
    assert diagnostic.context["page_index"] == 0


def test_weighted_median_uses_text_character_counts() -> None:
    body = _element(
        "paragraph",
        ContentFragment(
            0,
            None,
            ("x", "ordinary body text"),
            text_styles=(TextStyle("Footnote", 4.0), TextStyle("Body", 8.0)),
        ),
    )
    source = _document(
        _element("list", _candidate("01"), body, _candidate("02"), body)
    )

    result = promote_numbered_chapter_headings(source)

    assert len(result.heading_promotions) == 2
    assert {promotion.body_font_size for promotion in result.heading_promotions} == {8.0}


def test_ignores_none_nonfinite_nonpositive_style_samples() -> None:
    invalid_sizes = (None, float("nan"), float("inf"), -1.0, 0.0)
    invalid_parts = ("none ", "nan ", "infinite ", "negative ", "zero ")
    heading = _element(
        "list_item",
        _element(
            "label",
            ContentFragment(
                0,
                None,
                (" ", "\t", "\n", "  ", " ", "01"),
                text_styles=tuple(TextStyle(None, size) for size in invalid_sizes)
                + (TextStyle(None, 12.0),),
            ),
        ),
        _element(
            "list_body",
            ContentFragment(
                0,
                None,
                (*invalid_parts, "Exact title"),
                text_styles=tuple(TextStyle(None, size) for size in invalid_sizes)
                + (TextStyle(None, 12.0),),
            ),
        ),
    )
    body = _element(
        "paragraph",
        ContentFragment(
            0,
            None,
            (*invalid_parts, "ordinary body text"),
            text_styles=tuple(TextStyle(None, size) for size in invalid_sizes)
            + (TextStyle(None, 8.0),),
        ),
    )
    source = _document(
        _element("list", heading, body, _candidate("02"), body)
    )

    result = promote_numbered_chapter_headings(source)

    assert len(result.heading_promotions) == 2
    assert result.heading_promotions[0].heading_font_size == 12.0
    assert result.heading_promotions[0].body_font_size == 8.0


def test_all_nonempty_typography_samples_invalid_is_insufficient() -> None:
    source = _document(
        _element(
            "list",
            _candidate("01", label_size=None, title_size=float("nan")),
            _paragraph("infinite body", float("inf")),
            _candidate("02", label_size=0.0, title_size=-1.0),
            _paragraph("negative body", -2.0),
        )
    )

    result = promote_numbered_chapter_headings(source)

    assert result.heading_promotions == ()
    diagnostics = _diagnostics(result, "numbered_heading_typography_insufficient")
    assert [diagnostic.context["label"] for diagnostic in diagnostics] == ["01", "02"]
    assert all(
        diagnostic.context["body_font_size"] is None for diagnostic in diagnostics
    )
    assert all(
        diagnostic.context["label_font_size"] is None for diagnostic in diagnostics
    )
    assert all(
        diagnostic.context["list_body_font_size"] is None
        for diagnostic in diagnostics
    )


def test_equal_series_counts_are_consistent() -> None:
    source = _document(
        _series(("01", "02")),
        _paragraph("Between series"),
        _series(("01", "02")),
    )

    result = promote_numbered_chapter_headings(source)

    assert result.numbered_heading_series_consistent is True
    assert [audit.series_index for audit in result.numbered_heading_series] == [0, 1]
    assert len(result.heading_promotions) == 4


def test_unequal_series_counts_retain_local_promotions_and_report_mismatch() -> None:
    source = _document(_series(("01", "02")), _series(("01", "02", "03")))

    result = promote_numbered_chapter_headings(source)

    assert result.numbered_heading_series_consistent is False
    assert len(result.heading_promotions) == 5
    diagnostic = _diagnostics(
        result, "numbered_heading_series_count_mismatch"
    )[0]
    assert diagnostic.severity == "error"
    assert diagnostic.context == {
        "series_counts": (2, 3),
        "labels_by_series": (("01", "02"), ("01", "02", "03")),
    }


def test_invalid_pre_01_series_is_excluded_from_cross_series_consistency() -> None:
    source = _document(_series(("02",)), _series(("01", "02")))

    result = promote_numbered_chapter_headings(source)

    assert [audit.valid_sequence for audit in result.numbered_heading_series] == [
        False,
        True,
    ]
    assert [promotion.label for promotion in result.heading_promotions] == ["01", "02"]
    assert result.numbered_heading_series_consistent is None
    assert _diagnostics(result, "numbered_heading_sequence_invalid")
    assert not _diagnostics(result, "numbered_heading_series_count_mismatch")


@pytest.mark.parametrize("series_count", (0, 1))
def test_zero_or_one_series_has_unknown_cross_series_consistency(
    series_count: int,
) -> None:
    source = _document(*((_series(("01", "02")),) if series_count else ()))

    result = promote_numbered_chapter_headings(source)

    assert result.numbered_heading_series_consistent is None


def test_preserves_source_document_tree_and_existing_diagnostics() -> None:
    existing = Diagnostic("warning", "existing", "Keep me", {"value": 1})
    source = _document(_series(("01", "02")))
    source = TaggedDocument(
        source.source_path,
        source.marked,
        source.language,
        source.role_map,
        source.children,
        (existing,),
    )
    original_children = source.children

    result = promote_numbered_chapter_headings(source)

    assert result is not source
    assert source.children is original_children
    assert result.children is original_children
    assert source.heading_promotions == ()
    assert source.numbered_heading_series == ()
    assert source.numbered_heading_series_consistent is None
    assert result.diagnostics[0] is existing


def test_title_preserves_non_english_source_and_punctuation_after_whitespace_normalization() -> None:
    body = _element(
        "list_body",
        _fragment("  설치 및 ", 12.0),
        _element("span", _fragment("연결: Wi-Fi!  ", 12.0)),
    )
    first = _element(
        "list_item",
        _element("label", _fragment("01", 12.0)),
        body,
        page_index=4,
    )
    source = _document(
        _element("list", first, _paragraph(), _candidate("02"), _paragraph())
    )

    result = promote_numbered_chapter_headings(source)

    assert result.heading_promotions[0].title == "설치 및 연결: Wi-Fi!"
    assert result.heading_promotions[0].child_path == (0, 0)
    assert result.heading_promotions[0].series_index == 0


def test_title_joins_adjacent_nested_lexical_fragments() -> None:
    first = _element(
        "list_item",
        _element("label", _fragment("01", 12.0)),
        _element(
            "list_body",
            _fragment("Setup", 12.0),
            _element("span", _fragment("Guide", 12.0)),
        ),
    )
    source = _document(
        _element("list", first, _paragraph(), _candidate("02"), _paragraph())
    )

    result = promote_numbered_chapter_headings(source)

    assert result.heading_promotions[0].title == "Setup Guide"


def test_title_preserves_joining_policy_for_adjacent_punctuation() -> None:
    first = _element(
        "list_item",
        _element("label", _fragment("01", 12.0)),
        _element(
            "list_body",
            _fragment("Settings", 12.0),
            _element("span", _fragment(">", 12.0)),
        ),
    )
    source = _document(
        _element("list", first, _paragraph(), _candidate("02"), _paragraph())
    )

    result = promote_numbered_chapter_headings(source)

    assert result.heading_promotions[0].title == "Settings>"


def test_body_baseline_excludes_all_candidate_subtrees() -> None:
    source = _document(
        _element(
            "list",
            _candidate(
                "01",
                extra_children=(_element("paragraph", _fragment("huge", 100.0)),),
            ),
            _paragraph(size=8.0),
            _candidate(
                "02",
                extra_children=(_element("paragraph", _fragment("huge", 100.0)),),
            ),
            _paragraph(size=8.0),
        )
    )

    result = promote_numbered_chapter_headings(source)

    assert len(result.heading_promotions) == 2
    assert result.heading_promotions[0].body_font_size == 8.0
