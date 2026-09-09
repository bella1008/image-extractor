from __future__ import annotations

from pathlib import Path

import pytest

from tagged_pdf_extractor.domain.language_interval_resolution import (
    resolve_language_intervals,
)
from tagged_pdf_extractor.domain.models import (
    BookmarkPageBounds,
    ContentFragment,
    HeadingPromotion,
    PdfProfile,
    StructureElement,
    TaggedDocument,
)


def _text(value: str, page_index: int) -> ContentFragment:
    return ContentFragment(page_index, None, (value,))


def _heading(value: str, *page_indices: int) -> StructureElement:
    return StructureElement(
        "H2",
        "heading",
        heading_level=2,
        children=tuple(_text(value, page_index) for page_index in page_indices),
    )


def _paragraph(value: str, page_index: int) -> StructureElement:
    return StructureElement(
        "P",
        "paragraph",
        children=(_text(value, page_index),),
    )


def _section(page_index: int, value: str) -> StructureElement:
    return StructureElement(
        "Sect",
        "section",
        children=(
            _heading(value, page_index),
            _paragraph(f"body-{value}", page_index),
        ),
    )


def _profile(doc_type: str, *languages: str) -> PdfProfile:
    return PdfProfile("XX_L05" if doc_type == "BOOK" else "XX_L02", doc_type, languages, len(languages))


def _document(
    children: tuple[StructureElement, ...],
    *,
    bounds: tuple[BookmarkPageBounds, ...] = (),
    promotions: tuple[HeadingPromotion, ...] = (),
) -> TaggedDocument:
    return TaggedDocument(
        Path("arbitrary.pdf"),
        True,
        None,
        (),
        children,
        heading_promotions=promotions,
        bookmark_page_bounds=bounds,
    )


def _bounds(*titles: str) -> tuple[BookmarkPageBounds, ...]:
    return tuple(
        BookmarkPageBounds(index + 1, index, index, title)
        for index, title in enumerate(titles)
    )


def _promotion(path: tuple[int, ...]) -> HeadingPromotion:
    return HeadingPromotion(
        child_path=path,
        level=2,
        label="01",
        title="ignored",
        series_index=0,
        heading_font_size=12.0,
        body_font_size=8.0,
        font_size_ratio=1.5,
        promotion_reason="numbered_chapter_structure_sequence_typography",
    )


def test_book_maps_five_arbitrary_titles_to_profile_languages_only_by_ordinal() -> None:
    languages = ("AAA", "BBB", "CCC", "DDD", "EEE")
    document = _document(
        tuple(_section(index, f"wording-{index}") for index in range(5)),
        bounds=_bounds("one", "??", "unrelated", "four", "last"),
    )

    resolution = resolve_language_intervals(_profile("BOOK", *languages), document)

    assert resolution.diagnostic is None
    assert tuple(interval.language for interval in resolution.intervals) == languages
    assert tuple(
        (interval.start_page_index, interval.end_page_index)
        for interval in resolution.intervals
    ) == tuple((index, index) for index in range(5))
    assert all(
        interval.evidence_origin == "bookmark"
        for interval in resolution.intervals
    )


def test_book_title_wording_changes_do_not_change_intervals() -> None:
    children = tuple(_section(index, f"text-{index}") for index in range(5))
    profile = _profile("BOOK", "AAA", "BBB", "CCC", "DDD", "EEE")
    left = _document(children, bounds=_bounds("a", "b", "c", "d", "e"))
    right = _document(children, bounds=_bounds("5", "4", "3", "2", "1"))

    assert resolve_language_intervals(profile, left).intervals == (
        resolve_language_intervals(profile, right).intervals
    )


@pytest.mark.parametrize(
    ("document", "code", "observed"),
    [
        (
            _document((_section(0, "a"), _section(1, "b"))),
            "language_interval_bookmark_bounds_missing",
            0,
        ),
        (
            _document(
                (_section(0, "a"), _section(1, "b")),
                bounds=_bounds("only-one"),
            ),
            "language_interval_bookmark_count_mismatch",
            1,
        ),
        (
            _document(
                (_section(0, "a"), _section(1, "b")),
                bounds=(
                    BookmarkPageBounds(1, 0, 1, "a"),
                    BookmarkPageBounds(2, 1, 1, "b"),
                ),
            ),
            "language_interval_bookmark_order_invalid",
            2,
        ),
        (
            _document(
                (_section(0, "a"), _section(1, "b")),
                bounds=(
                    BookmarkPageBounds(1, 0, 0, "a"),
                    BookmarkPageBounds(2, 1, 9, "b"),
                ),
            ),
            "language_interval_bookmark_out_of_page",
            2,
        ),
    ],
)
def test_book_invalid_raw_bounds_fail_closed(
    document: TaggedDocument, code: str, observed: int
) -> None:
    resolution = resolve_language_intervals(
        _profile("BOOK", "AAA", "BBB"), document
    )

    assert resolution.intervals == ()
    assert resolution.observed_interval_count == observed
    assert resolution.diagnostic is not None
    assert resolution.diagnostic.code == code


def test_book_raw_empty_failure_precedes_missing_heading_evidence() -> None:
    document = _document((_paragraph("body only", 0),))

    resolution = resolve_language_intervals(
        _profile("BOOK", "AAA", "BBB"), document
    )

    assert resolution.intervals == ()
    assert resolution.diagnostic is not None
    assert resolution.diagnostic.code == "language_interval_bookmark_bounds_missing"


def test_book_cross_bound_heading_fails_closed() -> None:
    document = _document(
        (
            StructureElement("Sect", "section", children=(_heading("cross", 0, 1),)),
            _section(1, "second"),
        ),
        bounds=_bounds("first", "second"),
    )

    resolution = resolve_language_intervals(
        _profile("BOOK", "AAA", "BBB"), document
    )

    assert resolution.intervals == ()
    assert resolution.diagnostic is not None
    assert resolution.diagnostic.code == "language_interval_heading_page_evidence_ambiguous"


def test_missing_promoted_heading_path_fails_closed() -> None:
    document = _document(
        (_section(0, "first"), _section(1, "second")),
        bounds=_bounds("first", "second"),
        promotions=(_promotion((9,)),),
    )

    resolution = resolve_language_intervals(
        _profile("BOOK", "AAA", "BBB"), document
    )

    assert resolution.intervals == ()
    assert resolution.diagnostic is not None
    assert resolution.diagnostic.code == "language_interval_heading_path_missing"


def test_non_book_maps_two_heading_pages_to_canonical_order_without_wording() -> None:
    profile = _profile("A2", "AAA", "BBB")
    document = _document((_section(3, "first"), _section(7, "second")))
    changed = _document((_section(3, "anything"), _section(7, "else")))

    resolution = resolve_language_intervals(profile, document)
    changed_resolution = resolve_language_intervals(profile, changed)

    assert resolution.diagnostic is None
    assert tuple(
        (item.language, item.start_page_index, item.end_page_index, item.evidence_origin)
        for item in resolution.intervals
    ) == (
        ("AAA", 3, 3, "structural_language_section"),
        ("BBB", 7, 7, "structural_language_section"),
    )
    assert resolution.intervals == changed_resolution.intervals


@pytest.mark.parametrize(
    ("children", "code", "observed"),
    [
        (
            (_section(0, "first"), _section(0, "second")),
            "language_interval_heading_page_count_mismatch",
            1,
        ),
        (
            (_section(0, "first"), _section(1, "second"), _section(2, "third")),
            "language_interval_heading_page_count_mismatch",
            3,
        ),
        (
            (
                StructureElement(
                    "Sect", "section", children=(_heading("cross", 0, 1),)
                ),
                _section(1, "second"),
            ),
            "language_interval_heading_page_evidence_ambiguous",
            0,
        ),
        (
            (
                StructureElement(
                    "Sect", "section", children=(_heading("missing"),)
                ),
                _section(1, "second"),
            ),
            "language_interval_heading_page_evidence_missing",
            0,
        ),
        (
            (
                _section(0, "first"),
                _section(1, "second"),
                _paragraph("returns-to-first-page", 0),
            ),
            "language_interval_structure_ranges_invalid",
            2,
        ),
    ],
)
def test_non_book_ambiguous_or_unprovable_structure_fails_closed(
    children: tuple[StructureElement, ...], code: str, observed: int
) -> None:
    resolution = resolve_language_intervals(
        _profile("A2", "AAA", "BBB"), _document(children)
    )

    assert resolution.intervals == ()
    assert resolution.observed_interval_count == observed
    assert resolution.diagnostic is not None
    assert resolution.diagnostic.code == code


def test_non_heading_pages_outside_sheet_ranges_stay_unassigned() -> None:
    document = _document(
        (
            _paragraph("common-before", 2),
            _section(3, "first"),
            _section(7, "second"),
            _paragraph("common-after", 8),
        )
    )

    resolution = resolve_language_intervals(
        _profile("A2", "AAA", "BBB"), document
    )

    assert resolution.diagnostic is None
    assert tuple(
        (interval.start_page_index, interval.end_page_index)
        for interval in resolution.intervals
    ) == ((3, 3), (7, 7))
    assert resolution.intervals[0].start_path == (1,)
    assert resolution.intervals[1].end_path == (2, 1)
