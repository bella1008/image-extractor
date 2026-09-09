from __future__ import annotations

from dataclasses import FrozenInstanceError, fields, replace
from pathlib import Path

import pytest

from tagged_pdf_extractor.domain.models import (
    ContentFragment,
    Diagnostic,
    HeadingMismatchPosition,
    HeadingPromotion,
    HeadingSignatureEntry,
    LanguageHeadingSignature,
    LanguageIntervalEvidence,
    MultilingualHeadingAudit,
    PdfProfile,
    StructureElement,
    TaggedDocument,
    TextDisplayHint,
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


def _document_with_signatures(
    expected: tuple[HeadingSignatureEntry, ...],
    observed: tuple[HeadingSignatureEntry, ...],
) -> TaggedDocument:
    sections: list[StructureElement] = []
    promotions: list[HeadingPromotion] = []
    for section_index, (language, entries) in enumerate(
        (("ENG", expected), ("FRA", observed))
    ):
        children: list[StructureElement] = []
        for entry_index, entry in enumerate(entries):
            text = f"wording-{section_index}-{entry_index}"
            if entry.heading_origin == "source":
                children.append(
                    _heading(text, entry.heading_level, section_index)
                )
            else:
                children.append(_list_item(text, section_index))
                promotions.append(
                    _promotion(
                        (section_index, entry_index),
                        entry.numbered_label or "",
                        entry.heading_level,
                    )
                )
        sections.append(_section(language, section_index, *children))
    return _document(*sections, promotions=tuple(promotions))


def _audit_for_signatures(
    expected: tuple[HeadingSignatureEntry, ...],
    observed: tuple[HeadingSignatureEntry, ...],
) -> MultilingualHeadingAudit:
    return validate_multilingual_headings(
        _profile("ENG", "FRA"),
        _intervals("ENG", "FRA"),
        _document_with_signatures(expected, observed),
    )


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


def test_source_role_heading_candidates_mapped_to_paragraph_join_signature() -> None:
    def candidate(text: str, page_index: int) -> StructureElement:
        return StructureElement(
            "Heading3_0_2",
            "paragraph",
            page_index=page_index,
            children=(_text(text, page_index),),
        )

    document = _document(
        _section("ENG", 0, candidate("Warranty wording", 0)),
        _section("FRA", 1, candidate("Texte sans traduction runtime", 1)),
    )

    audit = validate_multilingual_headings(
        _profile("ENG", "FRA"), _intervals("ENG", "FRA"), document
    )

    expected = (HeadingSignatureEntry(4, "source", None),)
    assert tuple(signature.entries for signature in audit.signatures) == (
        expected,
        expected,
    )
    assert audit.passed is True


def test_unlevelled_title_candidate_is_outside_structural_signature() -> None:
    def title(text: str, page_index: int) -> StructureElement:
        return StructureElement(
            "Cover_Title",
            "paragraph",
            page_index=page_index,
            children=(_text(text, page_index),),
        )

    document = _document(
        _section("ENG", 0, title("English title wording", 0)),
        _section("FRA", 1, title("Different localized title wording", 1)),
    )

    audit = validate_multilingual_headings(
        _profile("ENG", "FRA"), _intervals("ENG", "FRA"), document
    )

    assert audit.passed is True
    assert tuple(signature.entries for signature in audit.signatures) == ((), ())


def test_structurally_detected_section_heading_joins_full_signature() -> None:
    document = _document(
        _section("ENG", 0, _paragraph("Declaration title", 0)),
        _section("FRA", 1, _paragraph("Titre de déclaration", 1)),
    )
    hints = tuple(
        TextDisplayHint(
            child_path=(index, 0),
            display_role="section_heading",
            font_weight=600,
            font_size=10.0,
            comparison_body_font_weight=400,
            comparison_body_font_size=8.0,
            reason="structural_test_evidence",
        )
        for index in range(2)
    )
    document = replace(document, text_display_hints=hints)

    audit = validate_multilingual_headings(
        _profile("ENG", "FRA"), _intervals("ENG", "FRA"), document
    )

    expected = (HeadingSignatureEntry(2, "source", None),)
    assert tuple(signature.entries for signature in audit.signatures) == (
        expected,
        expected,
    )
    assert audit.passed is True


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


def test_middle_insertion_reports_only_the_true_additional_position() -> None:
    first = HeadingSignatureEntry(2, "source", None)
    inserted = HeadingSignatureEntry(5, "promoted", "09")
    second = HeadingSignatureEntry(3, "promoted", "01")
    third = HeadingSignatureEntry(4, "source", None)

    audit = _audit_for_signatures(
        (first, second, third), (first, inserted, second, third)
    )

    assert audit.total_heading_count_matches is False
    assert audit.heading_level_sequence_matches is True
    assert audit.heading_origin_sequence_matches is True
    assert audit.numbered_label_sequence_matches is True
    assert audit.mismatch_positions == (
        HeadingMismatchPosition("FRA", 1, "count", None, inserted),
    )


def test_middle_deletion_reports_only_the_true_missing_position() -> None:
    first = HeadingSignatureEntry(2, "source", None)
    missing = HeadingSignatureEntry(5, "promoted", "09")
    second = HeadingSignatureEntry(3, "promoted", "01")
    third = HeadingSignatureEntry(4, "source", None)

    audit = _audit_for_signatures(
        (first, missing, second, third), (first, second, third)
    )

    assert audit.total_heading_count_matches is False
    assert audit.heading_level_sequence_matches is True
    assert audit.heading_origin_sequence_matches is True
    assert audit.numbered_label_sequence_matches is True
    assert audit.mismatch_positions == (
        HeadingMismatchPosition("FRA", 1, "count", missing, None),
    )


def test_repeated_adjacent_entries_do_not_hide_a_later_aligned_mismatch() -> None:
    repeated = HeadingSignatureEntry(2, "source", None)
    anchor = HeadingSignatureEntry(6, "source", None)
    expected_tail = HeadingSignatureEntry(3, "promoted", "01")
    observed_tail = HeadingSignatureEntry(4, "promoted", "01")

    audit = _audit_for_signatures(
        (repeated, repeated, anchor, expected_tail),
        (repeated, repeated, repeated, anchor, observed_tail),
    )

    assert audit.mismatch_positions == (
        HeadingMismatchPosition("FRA", 2, "count", None, repeated),
        HeadingMismatchPosition(
            "FRA", 3, "level", expected_tail, observed_tail
        ),
    )
    assert audit.heading_origin_sequence_matches is True
    assert audit.numbered_label_sequence_matches is True


@pytest.mark.parametrize(
    ("expected_count", "observed_count", "expected_position"),
    [(2, 3, 2), (3, 2, 2)],
)
def test_alignment_ties_choose_the_same_rightmost_duplicate_gap(
    expected_count: int, observed_count: int, expected_position: int
) -> None:
    repeated = HeadingSignatureEntry(2, "source", None)

    audits = tuple(
        _audit_for_signatures(
            (repeated,) * expected_count, (repeated,) * observed_count
        )
        for _ in range(3)
    )

    assert audits[0] == audits[1] == audits[2]
    assert audits[0].mismatch_positions[0].position == expected_position


def test_alignment_compares_components_only_after_middle_gap_alignment() -> None:
    first = HeadingSignatureEntry(2, "source", None)
    inserted = HeadingSignatureEntry(6, "promoted", "09")
    anchor = HeadingSignatureEntry(7, "promoted", "07")
    expected_middle = HeadingSignatureEntry(3, "promoted", "01")
    observed_middle = HeadingSignatureEntry(3, "source", None)
    expected_tail = HeadingSignatureEntry(4, "promoted", "02")
    observed_tail = HeadingSignatureEntry(5, "promoted", "03")

    audit = _audit_for_signatures(
        (first, anchor, expected_middle, expected_tail),
        (first, inserted, anchor, observed_middle, observed_tail),
    )

    assert audit.mismatch_positions == (
        HeadingMismatchPosition("FRA", 1, "count", None, inserted),
        HeadingMismatchPosition(
            "FRA", 2, "origin", expected_middle, observed_middle
        ),
        HeadingMismatchPosition(
            "FRA", 3, "level", expected_tail, observed_tail
        ),
        HeadingMismatchPosition(
            "FRA", 3, "numbered_label", expected_tail, observed_tail
        ),
    )


def test_exact_anchor_prevents_cascade_when_weighted_substitution_ties() -> None:
    exact = HeadingSignatureEntry(2, "source", None)
    expected_tail = HeadingSignatureEntry(3, "source", None)
    additional = HeadingSignatureEntry(8, "source", None)
    observed_tail = HeadingSignatureEntry(9, "promoted", "09")

    audit = _audit_for_signatures(
        (exact, expected_tail), (additional, exact, observed_tail)
    )

    assert audit.mismatch_positions == (
        HeadingMismatchPosition("FRA", 0, "count", None, additional),
        HeadingMismatchPosition(
            "FRA", 1, "level", expected_tail, observed_tail
        ),
        HeadingMismatchPosition(
            "FRA", 1, "origin", expected_tail, observed_tail
        ),
    )
    assert audit.numbered_label_sequence_matches is True


def test_no_exact_anchor_pairs_unmatched_segment_positionally() -> None:
    expected = (
        HeadingSignatureEntry(2, "source", None),
        HeadingSignatureEntry(3, "promoted", "01"),
    )
    observed = (
        HeadingSignatureEntry(8, "source", None),
        HeadingSignatureEntry(9, "promoted", "09"),
        HeadingSignatureEntry(10, "source", None),
    )

    audit = _audit_for_signatures(expected, observed)

    assert audit.mismatch_positions == (
        HeadingMismatchPosition("FRA", 0, "level", expected[0], observed[0]),
        HeadingMismatchPosition("FRA", 1, "level", expected[1], observed[1]),
        HeadingMismatchPosition(
            "FRA", 1, "numbered_label", expected[1], observed[1]
        ),
        HeadingMismatchPosition("FRA", 2, "count", None, observed[2]),
    )


def test_equal_length_level_reorder_is_compared_positionally_without_count_gaps() -> None:
    expected = (
        HeadingSignatureEntry(2, "source", None),
        HeadingSignatureEntry(3, "source", None),
    )
    observed = tuple(reversed(expected))

    audit = _audit_for_signatures(expected, observed)

    assert audit.total_heading_count_matches is True
    assert audit.heading_level_sequence_matches is False
    assert audit.heading_origin_sequence_matches is True
    assert audit.numbered_label_sequence_matches is True
    assert audit.mismatch_positions == (
        HeadingMismatchPosition("FRA", 0, "level", expected[0], observed[0]),
        HeadingMismatchPosition("FRA", 1, "level", expected[1], observed[1]),
    )


def test_equal_length_origin_and_label_reorder_has_only_component_mismatches() -> None:
    expected = (
        HeadingSignatureEntry(2, "promoted", "01"),
        HeadingSignatureEntry(2, "promoted", "02"),
        HeadingSignatureEntry(2, "source", None),
    )
    observed = (expected[1], expected[2], expected[0])

    audit = _audit_for_signatures(expected, observed)

    assert audit.total_heading_count_matches is True
    assert audit.heading_level_sequence_matches is True
    assert audit.heading_origin_sequence_matches is False
    assert audit.numbered_label_sequence_matches is False
    assert audit.mismatch_positions == (
        HeadingMismatchPosition(
            "FRA", 0, "numbered_label", expected[0], observed[0]
        ),
        HeadingMismatchPosition("FRA", 1, "origin", expected[1], observed[1]),
        HeadingMismatchPosition("FRA", 2, "origin", expected[2], observed[2]),
    )


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


def test_interval_with_missing_boundary_fails_closed() -> None:
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
    assert audit.diagnostics[-1].code == (
        "multilingual_heading_interval_boundary_invalid"
    )
    assert audit.diagnostics[-1].context["reason"] == "missing_start_path"


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


def _valid_multilingual_audit() -> MultilingualHeadingAudit:
    interval = LanguageIntervalEvidence(
        "ENG", 0, 0, (0,), (0,), "structural_language_section"
    )
    signature = LanguageHeadingSignature(
        "ENG", interval, (HeadingSignatureEntry(2, "source", None),)
    )
    return MultilingualHeadingAudit(
        applicable=True,
        passed=True,
        expected_interval_count=1,
        observed_interval_count=1,
        interval_count_matches=True,
        total_heading_count_matches=True,
        heading_level_sequence_matches=True,
        heading_origin_sequence_matches=True,
        numbered_label_sequence_matches=True,
        signatures=(signature,),
    )


def _component_mismatch(component: str) -> HeadingMismatchPosition:
    source = HeadingSignatureEntry(2, "source", None)
    promoted = HeadingSignatureEntry(2, "promoted", "01")
    if component == "count":
        return HeadingMismatchPosition("FRA", 0, "count", None, source)
    if component == "level":
        return HeadingMismatchPosition(
            "FRA", 0, "level", source, HeadingSignatureEntry(3, "source", None)
        )
    if component == "origin":
        return HeadingMismatchPosition("FRA", 0, "origin", source, promoted)
    return HeadingMismatchPosition(
        "FRA",
        0,
        "numbered_label",
        promoted,
        HeadingSignatureEntry(2, "promoted", "02"),
    )


_COMPONENT_FIELDS = {
    "count": "total_heading_count_matches",
    "level": "heading_level_sequence_matches",
    "origin": "heading_origin_sequence_matches",
    "numbered_label": "numbered_label_sequence_matches",
}


@pytest.mark.parametrize(
    "changes",
    [
        {"applicable": False},
        {"passed": False},
        {"interval_count_matches": False},
        {"total_heading_count_matches": None},
        {"heading_level_sequence_matches": False},
        {"expected_interval_count": 2},
        {"observed_interval_count": 2},
    ],
)
def test_multilingual_heading_audit_rejects_contradictory_states(
    changes: dict[str, object],
) -> None:
    with pytest.raises(ValueError):
        replace(_valid_multilingual_audit(), **changes)


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("signatures", []),
        ("signatures", (object(),)),
        ("mismatch_positions", []),
        ("mismatch_positions", (object(),)),
        ("diagnostics", []),
        ("diagnostics", (object(),)),
    ],
)
def test_multilingual_heading_audit_rejects_invalid_evidence_collections(
    field_name: str, invalid_value: object
) -> None:
    with pytest.raises(ValueError):
        replace(_valid_multilingual_audit(), **{field_name: invalid_value})


def test_multilingual_heading_audit_preserves_valid_failed_and_not_applicable_states() -> None:
    diagnostic = Diagnostic("error", "invalid", "invalid evidence")
    failed = MultilingualHeadingAudit(
        applicable=True,
        passed=False,
        expected_interval_count=2,
        observed_interval_count=1,
        interval_count_matches=False,
        total_heading_count_matches=None,
        heading_level_sequence_matches=None,
        heading_origin_sequence_matches=None,
        numbered_label_sequence_matches=None,
        diagnostics=(diagnostic,),
    )
    not_applicable = MultilingualHeadingAudit(
        applicable=False,
        passed=True,
        expected_interval_count=1,
        observed_interval_count=0,
        interval_count_matches=None,
        total_heading_count_matches=None,
        heading_level_sequence_matches=None,
        heading_origin_sequence_matches=None,
        numbered_label_sequence_matches=None,
    )

    assert failed.diagnostics == (diagnostic,)
    assert not_applicable.passed is True


@pytest.mark.parametrize("component", tuple(_COMPONENT_FIELDS))
def test_audit_true_component_flag_forbids_its_mismatch_kind(
    component: str,
) -> None:
    support = "level" if component != "level" else "origin"
    changes = {
        "passed": False,
        _COMPONENT_FIELDS[support]: False,
        "mismatch_positions": (
            _component_mismatch(support),
            _component_mismatch(component),
        ),
    }

    with pytest.raises(ValueError, match="contradicts mismatch positions"):
        replace(_valid_multilingual_audit(), **changes)


@pytest.mark.parametrize("component", tuple(_COMPONENT_FIELDS))
def test_audit_false_component_flag_requires_its_mismatch_kind(
    component: str,
) -> None:
    support = "level" if component != "level" else "origin"
    changes = {
        "passed": False,
        _COMPONENT_FIELDS[component]: False,
        _COMPONENT_FIELDS[support]: False,
        "mismatch_positions": (_component_mismatch(support),),
    }

    with pytest.raises(ValueError, match="contradicts mismatch positions"):
        replace(_valid_multilingual_audit(), **changes)


def test_evaluated_audit_rejects_interval_failure_diagnostics() -> None:
    diagnostic = Diagnostic("error", "interval_invalid", "invalid interval")

    with pytest.raises(ValueError):
        replace(_valid_multilingual_audit(), diagnostics=(diagnostic,))


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


def test_bcp47_markers_are_not_translated_to_profile_language_codes() -> None:
    document = _document(
        _section("fr-FR", 0, _heading("source", 2, 0)),
        _section("en-US", 1, _heading("localized", 2, 1)),
    )

    audit = validate_multilingual_headings(
        _profile("ENG", "FRA"), _intervals("ENG", "FRA"), document
    )

    assert audit.passed is True


def test_absent_element_language_markers_do_not_fail_validation() -> None:
    document = _document(
        _section("ENG", 0, _heading("source", 2, 0)),
        _section("FRA", 1, _heading("localized", 2, 1)),
    )
    document = replace(
        document,
        children=tuple(replace(section, language=None) for section in document.children),
    )

    audit = validate_multilingual_headings(
        _profile("ENG", "FRA"), _intervals("ENG", "FRA"), document
    )

    assert audit.passed is True


def test_interval_local_bcp47_markers_are_normalized_only_for_consistency() -> None:
    nested = StructureElement(
        "Div",
        "division",
        page_index=0,
        language="EN-us",
        children=(_heading("source", 2, 0),),
    )
    document = _document(
        _section("en-US", 0, nested),
        _section("fr-FR", 1, _heading("localized", 2, 1)),
    )

    audit = validate_multilingual_headings(
        _profile("ENG", "FRA"), _intervals("ENG", "FRA"), document
    )

    assert audit.passed is True


@pytest.mark.parametrize(
    ("boundary_marker", "nested_marker"),
    [("ENG", "en-US"), ("en-US", "ENG")],
    ids=("canonical-then-bcp47", "bcp47-then-canonical"),
)
def test_mixed_exact_canonical_and_bcp47_marker_schemes_fail_closed(
    boundary_marker: str, nested_marker: str
) -> None:
    marked_heading = replace(
        _heading("source", 2, 0), language=nested_marker
    )
    document = _document(
        _section(boundary_marker, 0, marked_heading),
        _section("FRA", 1, _heading("localized", 2, 1)),
    )

    audit = validate_multilingual_headings(
        _profile("ENG", "FRA"), _intervals("ENG", "FRA"), document
    )

    assert audit.passed is False
    assert audit.signatures == ()
    assert audit.diagnostics[-1].context == {
        "language": "ENG",
        "child_path": (0, 0),
        "observed_marker": nested_marker,
        "inherited_marker": boundary_marker,
        "reason": "mixed_language_marker_schemes",
    }


def test_repeated_matching_exact_canonical_markers_are_allowed() -> None:
    document = _document(
        _section(
            "ENG",
            0,
            replace(_heading("source", 2, 0), language="ENG"),
        ),
        _section(
            "FRA",
            1,
            replace(_heading("localized", 2, 1), language="FRA"),
        ),
    )

    audit = validate_multilingual_headings(
        _profile("ENG", "FRA"), _intervals("ENG", "FRA"), document
    )

    assert audit.passed is True


def test_language_inherited_only_from_ancestor_outside_interval_is_ignored() -> None:
    wrapper = StructureElement(
        "Part",
        "part",
        language="en-US",
        children=(
            _section("ENG", 0, _heading("source", 2, 0)),
            _section("FRA", 1, _heading("localized", 2, 1)),
        ),
    )
    wrapper = replace(
        wrapper,
        children=tuple(replace(section, language=None) for section in wrapper.children),
    )
    document = TaggedDocument(Path("wrapped.pdf"), True, None, (), (wrapper,))
    intervals = (
        LanguageIntervalEvidence(
            "ENG", 0, 0, (0, 0), (0, 0), "structural_language_section"
        ),
        LanguageIntervalEvidence(
            "FRA", 1, 1, (0, 1), (0, 1), "structural_language_section"
        ),
    )

    audit = validate_multilingual_headings(
        _profile("ENG", "FRA"), intervals, document
    )

    assert audit.passed is True
    assert audit.diagnostics == ()


def test_malformed_language_on_ancestor_outside_interval_is_ignored() -> None:
    wrapper = StructureElement(
        "Part",
        "part",
        language="English (US)",
        children=(
            _section("ENG", 0, _heading("source", 2, 0)),
            _section("FRA", 1, _heading("localized", 2, 1)),
        ),
    )
    wrapper = replace(
        wrapper,
        children=tuple(replace(section, language=None) for section in wrapper.children),
    )
    document = TaggedDocument(Path("wrapped.pdf"), True, None, (), (wrapper,))
    intervals = (
        LanguageIntervalEvidence(
            "ENG", 0, 0, (0, 0), (0, 0), "structural_language_section"
        ),
        LanguageIntervalEvidence(
            "FRA", 1, 1, (0, 1), (0, 1), "structural_language_section"
        ),
    )

    audit = validate_multilingual_headings(
        _profile("ENG", "FRA"), intervals, document
    )

    assert audit.passed is True
    assert audit.diagnostics == ()


def test_explicit_interval_markers_unambiguously_override_outer_language() -> None:
    wrapper = StructureElement(
        "Part",
        "part",
        language="English (US)",
        children=(
            _section("en-US", 0, _heading("source", 2, 0)),
            _section("fr-FR", 1, _heading("localized", 2, 1)),
        ),
    )
    document = TaggedDocument(
        Path("wrapped.pdf"),
        True,
        "de-DE",
        (),
        (wrapper,),
    )
    intervals = (
        LanguageIntervalEvidence(
            "ENG", 0, 0, (0, 0), (0, 0), "structural_language_section"
        ),
        LanguageIntervalEvidence(
            "FRA", 1, 1, (0, 1), (0, 1), "structural_language_section"
        ),
    )

    audit = validate_multilingual_headings(
        _profile("ENG", "FRA"), intervals, document
    )

    assert audit.passed is True


def test_conflicting_nested_body_language_marker_fails_closed() -> None:
    conflicting = StructureElement(
        "P",
        "paragraph",
        page_index=0,
        language="fr-FR",
        children=(_text("body", 0),),
    )
    document = _document(
        _section("en-US", 0, _heading("source", 2, 0), conflicting),
        _section("fr-FR", 1, _heading("localized", 2, 1)),
    )

    audit = validate_multilingual_headings(
        _profile("ENG", "FRA"), _intervals("ENG", "FRA"), document
    )

    assert audit.passed is False
    diagnostic = audit.diagnostics[-1]
    assert diagnostic.code == "multilingual_heading_language_marker_invalid"
    assert diagnostic.context == {
        "language": "ENG",
        "child_path": (0, 1),
        "observed_marker": "fr-FR",
        "inherited_marker": "en-US",
        "reason": "conflicting_language_markers",
    }


def test_malformed_interval_language_marker_fails_closed() -> None:
    document = _document(
        _section("English (US)", 0, _heading("source", 2, 0)),
        _section("fr-FR", 1, _heading("localized", 2, 1)),
    )

    audit = validate_multilingual_headings(
        _profile("ENG", "FRA"), _intervals("ENG", "FRA"), document
    )

    assert audit.passed is False
    assert audit.diagnostics[-1].context["reason"] == "malformed_language_marker"


@pytest.mark.parametrize("heading_origin", ["source", "promoted"])
def test_heading_with_conflicting_structural_language_is_rejected(
    heading_origin: str,
) -> None:
    if heading_origin == "source":
        target = replace(_heading("source", 2, 0), language="fr-FR")
        promotions: tuple[HeadingPromotion, ...] = ()
    else:
        target = replace(_list_item("source", 0), language="fr-FR")
        promotions = (_promotion((0, 0), "01"), _promotion((1, 0), "01"))
    right_target = (
        _heading("localized", 2, 1)
        if heading_origin == "source"
        else _list_item("localized", 1)
    )
    document = _document(
        _section("en-US", 0, target),
        _section("fr-FR", 1, right_target),
        promotions=promotions,
    )

    audit = validate_multilingual_headings(
        _profile("ENG", "FRA"), _intervals("ENG", "FRA"), document
    )

    assert audit.passed is False
    assert audit.diagnostics[-1].code == "multilingual_heading_language_marker_invalid"
    assert audit.diagnostics[-1].context["child_path"] == (0, 0)


def test_document_level_pdf_language_is_not_interval_evidence() -> None:
    document = replace(
        _document(
            _section("ENG", 0, _heading("source", 2, 0)),
            _section("FRA", 1, _heading("localized", 2, 1)),
        ),
        language="de-DE",
    )

    audit = validate_multilingual_headings(
        _profile("ENG", "FRA"), _intervals("ENG", "FRA"), document
    )

    assert audit.passed is True


def test_exact_canonical_interval_markers_confirm_supplied_languages() -> None:
    document = _document(
        _section("ENG", 0, _heading("source", 2, 0)),
        _section("C-FRA", 1, _heading("localized", 2, 1)),
    )

    audit = validate_multilingual_headings(
        _profile("ENG", "C-FRA"), _intervals("ENG", "C-FRA"), document
    )

    assert audit.passed is True


def test_other_exact_profile_language_marker_conflicts_with_interval() -> None:
    document = _document(
        _section("C-FRA", 0, _heading("source", 2, 0)),
        _section("C-FRA", 1, _heading("localized", 2, 1)),
    )

    audit = validate_multilingual_headings(
        _profile("ENG", "C-FRA"), _intervals("ENG", "C-FRA"), document
    )

    assert audit.passed is False
    assert audit.diagnostics[-1].context["reason"] == (
        "conflicting_canonical_language"
    )


@pytest.mark.parametrize(
    ("replacement", "reason"),
    [
        ({"start_path": (0, 0, 0, 9), "end_path": (0, 1)}, "missing_start_path"),
        ({"start_path": (0,), "end_path": (0, 0, 0)}, "end_path_not_structure"),
    ],
)
def test_interval_boundaries_must_identify_existing_structure_elements(
    replacement: dict[str, tuple[int, ...]], reason: str
) -> None:
    document = _document(
        _section(
            "ENG",
            0,
            _heading("source", 2, 0),
            _paragraph("body", 0),
        ),
        _section("FRA", 1, _heading("localized", 2, 1)),
    )
    first, second = _intervals("ENG", "FRA")
    first = replace(first, **replacement)

    audit = validate_multilingual_headings(
        _profile("ENG", "FRA"), (first, second), document
    )

    assert audit.passed is False
    assert audit.signatures == ()
    assert audit.diagnostics[-1].code == "multilingual_heading_interval_boundary_invalid"
    assert audit.diagnostics[-1].context["reason"] == reason


def test_tagged_document_default_construction_remains_compatible() -> None:
    document = TaggedDocument(Path("legacy.pdf"), True, None, (), ())

    assert document.multilingual_heading_audit is None
