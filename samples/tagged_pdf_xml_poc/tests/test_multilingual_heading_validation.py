from __future__ import annotations

from dataclasses import FrozenInstanceError, fields
from pathlib import Path

import pytest

from tagged_pdf_extractor.domain.models import (
    ContentFragment,
    HeadingMismatchPosition,
    HeadingPromotion,
    HeadingSignatureEntry,
    LanguageHeadingSignature,
    LanguageIntervalEvidence,
    PdfProfile,
    StructureElement,
    TaggedDocument,
)
from tagged_pdf_extractor.domain.multilingual_heading_validation import (
    validate_multilingual_headings,
)


def _text(value: str, page_index: int) -> ContentFragment:
    return ContentFragment(page_index, None, (value,))


def _heading(text: str, level: int, page_index: int) -> StructureElement:
    return StructureElement(
        f"H{level}",
        "heading",
        heading_level=level,
        page_index=page_index,
        children=(_text(text, page_index),),
    )


def _paragraph(text: str, page_index: int) -> StructureElement:
    return StructureElement(
        "P",
        "paragraph",
        page_index=page_index,
        children=(_text(text, page_index),),
    )


def _list_item(text: str, page_index: int) -> StructureElement:
    return StructureElement(
        "LI",
        "list_item",
        page_index=page_index,
        children=(_text(text, page_index),),
    )


def _section(
    language: str, page_index: int, *children: StructureElement
) -> StructureElement:
    return StructureElement(
        "Sect",
        "section",
        page_index=page_index,
        language=language,
        children=children,
    )


def _promotion(path: tuple[int, ...], label: str, level: int = 2) -> HeadingPromotion:
    return HeadingPromotion(
        child_path=path,
        level=level,
        label=label,
        title="ignored localized title",
        series_index=0,
        heading_font_size=12.0,
        body_font_size=8.0,
        font_size_ratio=1.5,
        promotion_reason="numbered_chapter_structure_sequence_typography",
    )


def _document(
    left: StructureElement,
    right: StructureElement,
    *,
    promotions: tuple[HeadingPromotion, ...] = (),
) -> TaggedDocument:
    return TaggedDocument(
        source_path=Path("manual.pdf"),
        marked=True,
        language=None,
        role_map=(),
        children=(left, right),
        heading_promotions=promotions,
    )


def _profile(*languages: str) -> PdfProfile:
    return PdfProfile("XX_L02", "A2", languages, len(languages))


def _intervals(*languages: str) -> tuple[LanguageIntervalEvidence, ...]:
    return tuple(
        LanguageIntervalEvidence(
            language=language,
            start_page_index=index,
            end_page_index=index,
            start_path=(index,),
            end_path=(index,),
            evidence_origin="structural_language_section",
        )
        for index, language in enumerate(languages)
    )


def _matching_document(
    *,
    right_level: int = 3,
    right_origin: str = "promoted",
    right_label: str = "01",
    right_extra_heading: bool = False,
) -> TaggedDocument:
    left = _section("ENG", 0, _heading("English words", 2, 0), _list_item("A", 0))
    right_children: list[StructureElement] = [
        _heading("Localized section words", 2, 1)
    ]
    promotions = [_promotion((0, 1), "01", 3)]
    if right_origin == "source":
        right_children.append(_heading("Localized words", right_level, 1))
    else:
        right_children.append(_list_item("Localized words", 1))
        promotions.append(_promotion((1, 1), right_label, right_level))
    if right_extra_heading:
        right_children.append(_heading("Additional localized words", 4, 1))
    right = _section("FRA", 1, *right_children)
    return _document(left, right, promotions=tuple(promotions))


def test_signature_is_wording_independent_and_contains_only_structural_fields() -> None:
    document = _document(
        _section("ENG", 0, _heading("Safety instructions", 2, 0)),
        _section("FRA", 1, _heading("Consignes totalement différentes", 2, 1)),
    )

    audit = validate_multilingual_headings(
        _profile("ENG", "FRA"), _intervals("ENG", "FRA"), document
    )

    assert audit.applicable is True
    assert audit.passed is True
    assert tuple(field.name for field in fields(HeadingSignatureEntry)) == (
        "heading_level",
        "heading_origin",
        "numbered_label",
    )
    assert audit.signatures == (
        LanguageHeadingSignature(
            "ENG",
            _intervals("ENG", "FRA")[0],
            (HeadingSignatureEntry(2, "source", None),),
        ),
        LanguageHeadingSignature(
            "FRA",
            _intervals("ENG", "FRA")[1],
            (HeadingSignatureEntry(2, "source", None),),
        ),
    )
    assert audit.mismatch_positions == ()


@pytest.mark.parametrize(
    ("document", "failed_field", "component"),
    [
        (
            _matching_document(right_extra_heading=True),
            "total_heading_count_matches",
            "count",
        ),
        (_matching_document(right_level=4), "heading_level_sequence_matches", "level"),
        (_matching_document(right_origin="source"), "heading_origin_sequence_matches", "origin"),
        (_matching_document(right_label="02"), "numbered_label_sequence_matches", "numbered_label"),
    ],
    ids=("count", "level", "origin", "numbered-label"),
)
def test_each_signature_mismatch_fails_only_its_own_component(
    document: TaggedDocument, failed_field: str, component: str
) -> None:
    audit = validate_multilingual_headings(
        _profile("ENG", "FRA"), _intervals("ENG", "FRA"), document
    )

    outcomes = {
        "total_heading_count_matches": audit.total_heading_count_matches,
        "heading_level_sequence_matches": audit.heading_level_sequence_matches,
        "heading_origin_sequence_matches": audit.heading_origin_sequence_matches,
        "numbered_label_sequence_matches": audit.numbered_label_sequence_matches,
    }
    assert outcomes.pop(failed_field) is False
    assert all(outcomes.values())
    assert {position.component for position in audit.mismatch_positions} == {component}


def test_expected_and_observed_interval_count_mismatch_is_independent() -> None:
    document = _document(
        _section("ENG", 0, _heading("One", 2, 0)),
        _section("FRA", 1, _heading("Deux", 2, 1)),
    )

    audit = validate_multilingual_headings(
        _profile("ENG", "FRA"), _intervals("ENG"), document
    )

    assert audit.expected_interval_count == 2
    assert audit.observed_interval_count == 1
    assert audit.interval_count_matches is False
    assert audit.passed is False
    assert audit.signatures == ()
    assert [item.code for item in audit.diagnostics] == [
        "multilingual_heading_interval_count_mismatch"
    ]


@pytest.mark.parametrize(
    ("intervals", "code"),
    [
        ((), "multilingual_heading_interval_count_mismatch"),
        (_intervals("ENG", "ENG"), "multilingual_heading_interval_languages_invalid"),
        (_intervals("FRA", "ENG"), "multilingual_heading_interval_languages_invalid"),
        (
            (
                _intervals("ENG", "FRA")[0],
                LanguageIntervalEvidence(
                    "FRA", 0, 1, (0, 0), (1,), "structural_language_section"
                ),
            ),
            "multilingual_heading_interval_bounds_invalid",
        ),
    ],
    ids=("missing", "duplicate", "reordered", "overlap"),
)
def test_missing_or_ambiguous_multilingual_intervals_fail_closed(
    intervals: tuple[LanguageIntervalEvidence, ...], code: str
) -> None:
    document = _document(
        _section("ENG", 0, _heading("One", 2, 0)),
        _section("FRA", 1, _heading("Deux", 2, 1)),
    )

    audit = validate_multilingual_headings(_profile("ENG", "FRA"), intervals, document)

    assert audit.passed is False
    assert audit.signatures == ()
    assert audit.diagnostics[-1].code == code


def test_interval_with_no_document_nodes_fails_closed() -> None:
    intervals = (
        _intervals("ENG", "FRA")[0],
        LanguageIntervalEvidence(
            "FRA", 2, 2, (9,), (9,), "structural_language_section"
        ),
    )
    document = _document(
        _section("ENG", 0, _heading("One", 2, 0)),
        _section("FRA", 1, _heading("Deux", 2, 1)),
    )

    audit = validate_multilingual_headings(_profile("ENG", "FRA"), intervals, document)

    assert audit.passed is False
    assert audit.signatures == ()
    assert audit.diagnostics[-1].code == "multilingual_heading_interval_empty"


def test_single_language_profile_returns_stable_not_applicable_audit() -> None:
    document = TaggedDocument(Path("one.pdf"), True, "ENG", (), ())

    first = validate_multilingual_headings(_profile("ENG"), (), document)
    second = validate_multilingual_headings(
        _profile("ENG"),
        (
            LanguageIntervalEvidence(
                "ENG", 99, 99, (99,), (99,), "structural_language_section"
            ),
        ),
        document,
    )

    assert first == second
    assert first.applicable is False
    assert first.passed is True
    assert first.signatures == ()
    assert first.diagnostics == ()


def test_new_evidence_models_are_frozen_and_validate_values() -> None:
    entry = HeadingSignatureEntry(2, "source", None)
    mismatch = HeadingMismatchPosition(
        "FRA", 0, "level", entry, HeadingSignatureEntry(3, "source", None)
    )

    with pytest.raises(FrozenInstanceError):
        entry.heading_level = 3  # type: ignore[misc]
    with pytest.raises(ValueError, match="positive"):
        HeadingSignatureEntry(0, "source", None)
    with pytest.raises(ValueError, match="heading_origin"):
        HeadingSignatureEntry(2, "guessed", None)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="numbered_label"):
        HeadingSignatureEntry(2, "source", "01")
    with pytest.raises(ValueError, match="numbered_label"):
        HeadingSignatureEntry(2, "promoted", None)
    with pytest.raises(ValueError, match="numbered_label"):
        HeadingSignatureEntry(2, "promoted", "chapter")
    with pytest.raises(ValueError, match="position"):
        HeadingMismatchPosition("FRA", -1, "level", entry, entry)
    with pytest.raises(ValueError, match="differ"):
        HeadingMismatchPosition("FRA", 0, "level", entry, entry)
    assert mismatch.position == 0


@pytest.mark.parametrize(
    ("languages", "language_count"),
    [
        (("ENG", "ENG"), 2),
        (("ENG", "FRA"), 3),
    ],
)
def test_pdf_profile_rejects_noncanonical_language_contract(
    languages: tuple[str, ...], language_count: int,
) -> None:
    with pytest.raises(ValueError):
        PdfProfile("XX_L02", "A2", languages, language_count)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"language": "fra"},
        {"language": 7},
        {"start_page_index": -1},
        {"end_page_index": -1},
        {"start_page_index": 2, "end_page_index": 1},
        {"start_path": ()},
        {"end_path": ()},
        {"start_path": (-1,)},
        {"start_path": (1,), "end_path": (0,)},
        {"evidence_origin": "translation_guess"},
    ],
)
def test_language_interval_evidence_rejects_noncanonical_or_invalid_bounds(
    kwargs: dict[str, object],
) -> None:
    values: dict[str, object] = {
        "language": "FRA",
        "start_page_index": 0,
        "end_page_index": 1,
        "start_path": (0,),
        "end_path": (1,),
        "evidence_origin": "bookmark",
    }
    values.update(kwargs)

    with pytest.raises(ValueError):
        LanguageIntervalEvidence(**values)  # type: ignore[arg-type]


def test_heading_page_evidence_must_be_fully_inside_the_interval() -> None:
    split_heading = StructureElement(
        "H2",
        "heading",
        heading_level=2,
        children=(_text("first", 0), _text("second", 2)),
    )
    document = _document(
        _section("ENG", 0, split_heading),
        _section("FRA", 1, _heading("localized", 2, 1)),
    )

    audit = validate_multilingual_headings(
        _profile("ENG", "FRA"), _intervals("ENG", "FRA"), document
    )

    assert audit.passed is False
    assert audit.diagnostics[-1].code == "multilingual_heading_evidence_invalid"


def test_invalid_numbered_promotion_path_fails_closed() -> None:
    document = _document(
        _section("ENG", 0, _heading("source", 2, 0)),
        _section("FRA", 1, _heading("localized", 2, 1)),
        promotions=(_promotion((9,), "01"),),
    )

    audit = validate_multilingual_headings(
        _profile("ENG", "FRA"), _intervals("ENG", "FRA"), document
    )

    assert audit.passed is False
    assert audit.signatures == ()
    assert audit.diagnostics[-1].code == "multilingual_heading_promotion_paths_invalid"


def test_tagged_document_default_construction_remains_compatible() -> None:
    document = TaggedDocument(Path("legacy.pdf"), True, None, (), ())

    assert document.multilingual_heading_audit is None
