from __future__ import annotations

import random
import sys
from dataclasses import replace
from pathlib import Path

import pymupdf
import pytest

from tagged_pdf_extractor.application import evaluate_quality as evaluate_quality_module
from tagged_pdf_extractor.application.evaluate_quality import (
    QualityEvaluationLimitError,
    QualityEvaluator,
)
from tagged_pdf_extractor.domain.models import (
    ContentFragment,
    Diagnostic,
    HeadingMismatchPosition,
    HeadingPromotion,
    HeadingSignatureEntry,
    LanguageHeadingSignature,
    LanguageIntervalEvidence,
    MultilingualHeadingAudit,
    NumberedHeadingSeriesAudit,
    StructureElement,
    TaggedDocument,
)
from tagged_pdf_extractor.infrastructure.pymupdf_baseline import (
    PyMuPdfBaselineReader,
)
import tagged_pdf_extractor.infrastructure.pymupdf_baseline as baseline_module


SPECIAL_CHARACTERS = ">→/&:[]()"


def test_quality_evaluator_uses_shared_heading_candidate_helpers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        evaluate_quality_module,
        "is_heading_candidate",
        lambda source_role: source_role == "SharedCandidate",
    )
    monkeypatch.setattr(
        evaluate_quality_module,
        "heading_candidate_level",
        lambda source_role: 4 if source_role == "SharedCandidate" else None,
    )
    document = TaggedDocument(
        Path("manual.pdf"),
        True,
        "en",
        (),
        (
            StructureElement(
                "SharedCandidate",
                "paragraph",
                children=(ContentFragment(0, 1, ("Shared title",)),),
            ),
        ),
    )

    report = QualityEvaluator().evaluate(
        document, "Shared title", xml_round_trip_ok=True
    )

    assert report.heading_hierarchy == (
        {
            "structure_path": "/paragraph[0]",
            "source_role": "SharedCandidate",
            "semantic_role": "paragraph",
            "level": 4,
            "joined_text": "Shared title",
            "title": None,
            "classification": "source_role_candidate",
        },
    )


def _document(
    *children: StructureElement | ContentFragment,
    marked: bool = True,
    diagnostics: tuple[Diagnostic, ...] = (),
) -> TaggedDocument:
    return TaggedDocument(
        source_path=Path("manual.pdf"),
        marked=marked,
        language="en",
        role_map=(),
        children=children,
        diagnostics=diagnostics,
    )


def _passing_document(text: str = "Body") -> TaggedDocument:
    return _document(
        StructureElement(
            "H1",
            "heading",
            1,
            children=(ContentFragment(0, 1, ("Heading",)),),
        ),
        StructureElement(
            "P",
            "paragraph",
            children=(ContentFragment(0, 2, (text,)),),
        ),
    )


def _nonrepetitive_text(length: int = 9_000) -> str:
    bmp_count = min(length, 0xF8FF - 0xE000 + 1)
    return "".join(chr(0xE000 + index) for index in range(bmp_count)) + "".join(
        chr(0xF0000 + index) for index in range(length - bmp_count)
    )


def _body_only_document(text: str) -> TaggedDocument:
    return _document(
        StructureElement(
            "P",
            "paragraph",
            children=(ContentFragment(0, 1, (text,)),),
        )
    )


def _entry(
    level: int = 1,
    origin: str = "source",
    label: str | None = None,
) -> HeadingSignatureEntry:
    return HeadingSignatureEntry(level, origin, label)  # type: ignore[arg-type]


def _signature(
    language: str,
    ordinal: int,
    entries: tuple[HeadingSignatureEntry, ...],
) -> LanguageHeadingSignature:
    interval = LanguageIntervalEvidence(
        language=language,
        start_page_index=ordinal - 1,
        end_page_index=ordinal - 1,
        start_path=(ordinal - 1,),
        end_path=(ordinal - 1,),
        evidence_origin=(
            "bookmark" if ordinal == 1 else "structural_language_section"
        ),
    )
    return LanguageHeadingSignature(language, interval, entries)


def _audit(
    *,
    component: str | None = None,
) -> MultilingualHeadingAudit:
    expected_entries = (_entry(1), _entry(2, "promoted", "01"))
    observed_entries = expected_entries
    states = {"count": True, "level": True, "origin": True, "numbered_label": True}
    mismatches: tuple[HeadingMismatchPosition, ...] = ()
    if component == "count":
        observed_entries = expected_entries[:1]
        states[component] = False
        mismatches = (
            HeadingMismatchPosition("C-FRA", 1, component, expected_entries[1], None),
        )
    elif component == "level":
        observed_entries = (expected_entries[0], _entry(3, "promoted", "01"))
        states[component] = False
        mismatches = (
            HeadingMismatchPosition(
                "C-FRA", 1, component, expected_entries[1], observed_entries[1]
            ),
        )
    elif component == "origin":
        observed_entries = (expected_entries[0], _entry(2))
        states[component] = False
        mismatches = (
            HeadingMismatchPosition(
                "C-FRA", 1, component, expected_entries[1], observed_entries[1]
            ),
        )
    elif component == "numbered_label":
        observed_entries = (expected_entries[0], _entry(2, "promoted", "02"))
        states[component] = False
        mismatches = (
            HeadingMismatchPosition(
                "C-FRA", 1, component, expected_entries[1], observed_entries[1]
            ),
        )
    return MultilingualHeadingAudit(
        applicable=True,
        passed=component is None,
        expected_interval_count=2,
        observed_interval_count=2,
        interval_count_matches=True,
        total_heading_count_matches=states["count"],
        heading_level_sequence_matches=states["level"],
        heading_origin_sequence_matches=states["origin"],
        numbered_label_sequence_matches=states["numbered_label"],
        signatures=(
            _signature("ENG", 1, expected_entries),
            _signature("C-FRA", 2, observed_entries),
        ),
        mismatch_positions=mismatches,
    )


def _evaluate_with_audit(audit: MultilingualHeadingAudit | None) -> QualityReport:
    return QualityEvaluator().evaluate(
        replace(_passing_document(), multilingual_heading_audit=audit),
        "Heading Body",
        xml_round_trip_ok=True,
    )


def _promotion(
    child_path: tuple[int, ...],
    label: str,
    title: str,
    *,
    series_index: int = 0,
) -> HeadingPromotion:
    return HeadingPromotion(
        child_path=child_path,
        level=2,
        label=label,
        title=title,
        series_index=series_index,
        heading_font_size=12.0,
        body_font_size=8.0,
        font_size_ratio=1.5,
        promotion_reason="numbered_chapter_structure_sequence_typography",
        heading_font_names=("HeadingFont",),
        body_font_names=("BodyFont",),
    )


def _numbered_item(label: str, title: str) -> StructureElement:
    return StructureElement(
        "LI",
        "list_item",
        children=(
            StructureElement(
                "Lbl",
                "label",
                children=(ContentFragment(0, None, (label,)),),
            ),
            StructureElement(
                "LBody",
                "list_body",
                children=(ContentFragment(0, None, (title,)),),
            ),
        ),
    )


def _lcs_oracle(left: str, right: str) -> int:
    previous = [0] * (len(right) + 1)
    for left_character in left:
        current = [0]
        for index, right_character in enumerate(right, start=1):
            if left_character == right_character:
                current.append(previous[index - 1] + 1)
            else:
                current.append(max(previous[index], current[-1]))
        previous = current
    return previous[-1]


def test_pymupdf_baseline_joins_page_text_with_newline(tmp_path: Path) -> None:
    assert baseline_module.pymupdf is pymupdf
    pdf_path = tmp_path / "two-pages.pdf"
    document = pymupdf.open()
    first = document.new_page()
    first.insert_text((72, 72), "First page")
    second = document.new_page()
    second.insert_text((72, 72), "Second page")
    document.save(pdf_path)
    document.close()

    with pymupdf.open(pdf_path) as expected_document:
        expected = "\n".join(page.get_text("text") for page in expected_document)

    assert PyMuPdfBaselineReader().read_text(pdf_path) == expected


def test_quality_report_counts_structure_roles_and_special_characters() -> None:
    text = "Settings > General → A/B & C: [D] (E)"
    document = _document(
        StructureElement(
            "Sect",
            "section",
            children=(
                StructureElement(
                    "H1",
                    "heading",
                    1,
                    children=(ContentFragment(0, 1, ("Accessibility",)),),
                ),
                StructureElement(
                    "P",
                    "paragraph",
                    children=(ContentFragment(0, 2, (text,)),),
                ),
                StructureElement("Custom", "unknown"),
            ),
        )
    )
    baseline = f"Accessibility {text}"

    report = QualityEvaluator().evaluate(document, baseline, xml_round_trip_ok=True)

    assert report.metrics["element_count"] == 4
    assert report.metrics["fragment_count"] == 2
    assert report.metrics["heading_count"] == 1
    assert report.metrics["body_count"] == 1
    assert report.metrics["unknown_role_count"] == 1
    assert report.metrics["empty_element_count"] == 1
    assert report.metrics["character_match_ratio"] == 1.0
    for character in SPECIAL_CHARACTERS:
        assert report.metrics["special_characters"][character] == {
            "tagged": baseline.count(character),
            "baseline": baseline.count(character),
            "count_preserved": True,
        }
    assert report.hard_gates["special_character_counts_preserved"] is True
    assert report.status == "pass"


def test_traverses_each_child_sequence_once_and_records_unambiguous_join_paths() -> None:
    class SinglePassChildren:
        def __init__(self, values: tuple[object, ...]) -> None:
            self.values = values
            self.iterations = 0

        def __iter__(self):
            self.iterations += 1
            if self.iterations > 1:
                raise AssertionError("children traversed more than once")
            return iter(self.values)

        def __bool__(self) -> bool:
            return bool(self.values)

    heading_children = SinglePassChildren(
        (ContentFragment(0, 1, ("Head", "ing")),)
    )
    body_children = SinglePassChildren(
        (
            ContentFragment(0, None, ("First", "part")),
            ContentFragment(0, None, ("Second", "part")),
        )
    )
    promoted_children = SinglePassChildren(
        (ContentFragment(0, 3, ("03", "Title")),)
    )
    root_children = SinglePassChildren(
        (
            StructureElement("H1", "heading", 1, children=heading_children),
            StructureElement("P", "paragraph", children=body_children),
            StructureElement("LI", "list_item", children=promoted_children),
        )
    )
    document = _document()
    object.__setattr__(document, "children", root_children)
    object.__setattr__(
        document,
        "heading_promotions",
        (_promotion((2,), "03", "Title"),),
    )

    report = QualityEvaluator().evaluate(
        document,
        "Head ing First part Second part 03 Title",
        xml_round_trip_ok=True,
    )

    assert root_children.iterations == 1
    assert heading_children.iterations == 1
    assert body_children.iterations == 1
    assert promoted_children.iterations == 1
    assert [
        (decision["element_path"], decision["fragment_child_index"])
        for decision in report.join_decisions
    ] == [
        ("/heading[0]", 0),
        ("/paragraph[1]", 0),
        ("/paragraph[1]", 1),
        ("/heading[2]", 0),
    ]
    assert report.metrics["character_match_ratio"] == 1.0


def test_numbered_promotions_are_counted_and_reported_as_heading_evidence() -> None:
    document = _document(
        StructureElement(
            "L",
            "list",
            children=(
                _numbered_item("01", "Package Content"),
                _numbered_item("02", "Connecting the TV"),
            ),
        )
    )
    document = replace(
        document,
        heading_promotions=(
            _promotion((0, 0), "01", "Package Content"),
            _promotion((0, 1), "02", "Connecting the TV"),
        ),
        numbered_heading_series=(
            NumberedHeadingSeriesAudit(0, ("01", "02"), True),
        ),
    )

    report = QualityEvaluator().evaluate(
        document,
        "01 Package Content 02 Connecting the TV",
        xml_round_trip_ok=True,
    )

    assert report.metrics["heading_count"] == 2
    assert report.metrics["numbered_heading_promotion_count"] == 2
    assert report.metrics["numbered_heading_promotion_count"] == len(
        [
            entry
            for entry in report.heading_hierarchy
            if entry["classification"] == "numbered_chapter_promotion"
        ]
    )
    assert report.hard_gates["has_heading"] is True
    assert report.heading_hierarchy == (
        {
            "structure_path": "/list[0]/heading[0]",
            "source_role": "LI",
            "semantic_role": "list_item",
            "level": 2,
            "joined_text": "01 Package Content",
            "title": "Package Content",
            "label": "01",
            "classification": "numbered_chapter_promotion",
            "series_index": 0,
            "heading_font_size": 12.0,
            "body_font_size": 8.0,
            "font_size_ratio": 1.5,
            "heading_font_names": ("HeadingFont",),
            "body_font_names": ("BodyFont",),
            "promotion_reason": "numbered_chapter_structure_sequence_typography",
        },
        {
            "structure_path": "/list[0]/heading[1]",
            "source_role": "LI",
            "semantic_role": "list_item",
            "level": 2,
            "joined_text": "02 Connecting the TV",
            "title": "Connecting the TV",
            "label": "02",
            "classification": "numbered_chapter_promotion",
            "series_index": 0,
            "heading_font_size": 12.0,
            "body_font_size": 8.0,
            "font_size_ratio": 1.5,
            "heading_font_names": ("HeadingFont",),
            "body_font_names": ("BodyFont",),
            "promotion_reason": "numbered_chapter_structure_sequence_typography",
        },
    )


def test_one_valid_numbered_heading_series_has_consistent_count_gate() -> None:
    document = replace(
        _passing_document(),
        numbered_heading_series=(
            NumberedHeadingSeriesAudit(0, ("01", "02"), True),
        ),
        numbered_heading_series_consistent=None,
    )

    report = QualityEvaluator().evaluate(
        document, "Heading Body", xml_round_trip_ok=True
    )

    assert report.metrics["numbered_heading_series"] == [
        {"series_index": 0, "labels": ["01", "02"], "valid_sequence": True}
    ]
    assert report.hard_gates["numbered_heading_series_valid"] is True
    assert report.hard_gates["numbered_heading_series_counts_consistent"] is True
    assert report.status == "pass"


def test_mismatched_numbered_heading_series_counts_fail_without_hiding_promotions() -> None:
    base = _passing_document()
    document = replace(
        base,
        children=(base.children[0], _numbered_item("01", "Body")),
        heading_promotions=(_promotion((1,), "01", "Body"),),
        numbered_heading_series=(
            NumberedHeadingSeriesAudit(0, ("01", "02"), True),
            NumberedHeadingSeriesAudit(1, ("01", "02", "03"), True),
        ),
        numbered_heading_series_consistent=False,
    )

    report = QualityEvaluator().evaluate(
        document, "Heading 01 Body", xml_round_trip_ok=True
    )

    assert report.metrics["numbered_heading_promotion_count"] == 1
    assert report.metrics["heading_count"] == 2
    assert report.hard_gates["numbered_heading_series_counts_consistent"] is False
    assert report.status == "fail"


def test_invalid_numbered_heading_sequence_fails_series_gate() -> None:
    document = replace(
        _passing_document(),
        numbered_heading_series=(
            NumberedHeadingSeriesAudit(0, ("01", "03"), False),
        ),
        diagnostics=(
            Diagnostic(
                "error",
                "numbered_heading_sequence_invalid",
                "invalid sequence",
            ),
        ),
    )

    report = QualityEvaluator().evaluate(
        document, "Heading Body", xml_round_trip_ok=True
    )

    assert report.hard_gates["numbered_heading_series_valid"] is False
    assert report.status == "fail"


@pytest.mark.parametrize(
    "code",
    (
        "numbered_heading_typography_insufficient",
        "numbered_heading_label_body_size_mismatch",
        "numbered_heading_font_ratio_below_threshold",
    ),
)
def test_numbered_heading_typography_diagnostics_fail_hard_gate(code: str) -> None:
    document = replace(
        _passing_document(),
        diagnostics=(Diagnostic("error", code, "typography failed"),),
    )

    report = QualityEvaluator().evaluate(
        document, "Heading Body", xml_round_trip_ok=True
    )

    assert report.hard_gates["numbered_heading_typography_valid"] is False
    assert report.status == "fail"


def test_no_numbered_heading_candidates_leave_new_gates_open() -> None:
    report = QualityEvaluator().evaluate(
        _body_only_document("Body"), "Body", xml_round_trip_ok=True
    )

    assert report.metrics["numbered_heading_promotion_count"] == 0
    assert report.metrics["numbered_heading_series"] == []
    assert report.hard_gates["numbered_heading_series_valid"] is True
    assert report.hard_gates["numbered_heading_series_counts_consistent"] is True
    assert report.hard_gates["numbered_heading_typography_valid"] is True
    assert report.hard_gates["has_heading"] is False


def test_actual_heading_and_numbered_promotion_count_once_each() -> None:
    base = _passing_document()
    document = replace(
        base,
        children=(base.children[0], _numbered_item("01", "Body")),
        heading_promotions=(_promotion((1,), "01", "Body"),),
    )

    report = QualityEvaluator().evaluate(
        document, "Heading 01 Body", xml_round_trip_ok=True
    )

    assert report.metrics["heading_count"] == 2
    assert [item["classification"] for item in report.heading_hierarchy] == [
        "heading",
        "numbered_chapter_promotion",
    ]


def test_evaluator_rejects_promotion_targeting_an_actual_heading() -> None:
    document = replace(
        _passing_document(),
        heading_promotions=(_promotion((0,), "01", "Heading"),),
    )

    with pytest.raises(ValueError, match="must target a list_item StructureElement"):
        QualityEvaluator().evaluate(
            document, "Heading Body", xml_round_trip_ok=True
        )


def test_evaluator_rejects_unresolved_promotion_path() -> None:
    document = replace(
        _passing_document(),
        heading_promotions=(_promotion((9,), "01", "Missing"),),
    )

    with pytest.raises(ValueError, match="unresolved heading promotion path"):
        QualityEvaluator().evaluate(
            document, "Heading Body", xml_round_trip_ok=True
        )


def test_comparison_normalizes_nfc_and_whitespace_without_mutating_raw_text() -> None:
    raw_parts = ("Cafe\u0301\n", "  menu")
    document = _passing_document("")
    body = StructureElement(
        "P",
        "paragraph",
        children=(ContentFragment(0, 2, raw_parts),),
    )
    object.__setattr__(document, "children", (document.children[0], body))

    report = QualityEvaluator().evaluate(
        document, "Heading Café menu", xml_round_trip_ok=True
    )

    assert report.metrics["character_match_ratio"] == 1.0
    assert report.metrics["tagged_character_count"] == len("Heading Café menu")
    assert raw_parts == ("Cafe\u0301\n", "  menu")


def test_empty_baseline_ratio_distinguishes_empty_and_nonempty_tagged_text() -> None:
    evaluator = QualityEvaluator()

    empty = evaluator.evaluate(_document(), "", xml_round_trip_ok=True)
    nonempty = evaluator.evaluate(
        _passing_document("Body"), "", xml_round_trip_ok=True
    )

    assert empty.metrics["character_match_ratio"] == 1.0
    assert nonempty.metrics["character_match_ratio"] == 0.0


def test_small_character_comparison_uses_exact_lcs_semantics() -> None:
    tagged = "Heading The quick brown fox"
    baseline = "Heading The quick blue fox"
    expected_matched = _lcs_oracle(baseline, tagged)

    report = QualityEvaluator().evaluate(
        _passing_document("The quick brown fox"),
        baseline,
        xml_round_trip_ok=True,
    )

    assert report.metrics["character_match_ratio"] == expected_matched / len(baseline)
    assert report.metrics["comparison_mode"] == "bit_parallel_lcs"


def test_large_character_comparison_is_deterministic_and_auditable() -> None:
    tagged_body = "".join(f"item-{index:04d} " for index in range(1200))
    baseline = f"Heading {tagged_body}tail"
    document = _passing_document(tagged_body)

    first = QualityEvaluator().evaluate(document, baseline, xml_round_trip_ok=True)
    second = QualityEvaluator().evaluate(document, baseline, xml_round_trip_ok=True)

    assert first.metrics["character_match_ratio"] == second.metrics[
        "character_match_ratio"
    ]
    assert first.metrics["comparison_mode"] == "bit_parallel_lcs"
    assert first.metrics["comparison_parameters"]["bitset_dimension"] == "shorter"
    assert "character_match_chunk_size" not in first.metrics
    assert "character_match_window_size" not in first.metrics
    assert "character_match_drift_allowance" not in first.metrics


def test_repeated_text_severe_deletion_cannot_reuse_tagged_characters() -> None:
    baseline = "x" * 8_193
    tagged = "x" * 2_048
    document = _document(
        StructureElement(
            "P",
            "paragraph",
            children=(ContentFragment(0, 1, (tagged,)),),
        )
    )

    report = QualityEvaluator().evaluate(document, baseline, xml_round_trip_ok=True)

    assert report.metrics["character_match_ratio"] == 2_048 / 8_193
    assert report.metrics["character_match_ratio"] <= len(tagged) / len(baseline)


@pytest.mark.parametrize("amount", (256, 1_024))
@pytest.mark.parametrize("position_name", ("beginning", "middle", "end"))
def test_large_lcs_retains_full_coverage_after_pure_insertion(
    amount: int, position_name: str
) -> None:
    baseline = _nonrepetitive_text()
    positions = {"beginning": 0, "middle": len(baseline) // 2, "end": len(baseline)}
    position = positions[position_name]
    tagged = baseline[:position] + ("!" * amount) + baseline[position:]

    report = QualityEvaluator().evaluate(
        _body_only_document(tagged), baseline, xml_round_trip_ok=True
    )

    assert report.metrics["character_match_ratio"] == 1.0


@pytest.mark.parametrize("amount", (256, 1_024))
@pytest.mark.parametrize("position_name", ("beginning", "middle", "end"))
def test_large_lcs_tracks_theoretical_pure_deletion_coverage(
    amount: int, position_name: str
) -> None:
    baseline = _nonrepetitive_text()
    positions = {
        "beginning": 0,
        "middle": (len(baseline) - amount) // 2,
        "end": len(baseline) - amount,
    }
    position = positions[position_name]
    tagged = baseline[:position] + baseline[position + amount :]

    report = QualityEvaluator().evaluate(
        _body_only_document(tagged), baseline, xml_round_trip_ok=True
    )
    theoretical_ratio = len(tagged) / len(baseline)

    assert report.metrics["character_match_ratio"] == pytest.approx(
        theoretical_ratio, abs=1 / len(baseline)
    )


def test_reviewer_leading_deletion_counterexample_is_exact() -> None:
    baseline = _nonrepetitive_text(12_288)
    tagged = baseline[4_096:]

    report = QualityEvaluator().evaluate(
        _body_only_document(tagged), baseline, xml_round_trip_ok=True
    )

    assert report.metrics["character_match_ratio"] == pytest.approx(
        2 / 3
    )
    assert report.metrics["comparison_mode"] in {"bit_parallel_lcs", "sparse_lcs"}


def test_quality_evaluator_has_no_sequence_matcher_import() -> None:
    import tagged_pdf_extractor.application.evaluate_quality as quality_module

    assert not hasattr(quality_module, "SequenceMatcher")


def test_bit_parallel_large_mode_matches_dynamic_programming_oracle(
) -> None:
    generator = random.Random(260903)
    cases: list[tuple[str, str]] = []
    alphabet = "abCDβU0001f600\x01"
    for _ in range(20):
        baseline = "".join(generator.choice(alphabet) for _ in range(28))
        tagged = "".join(generator.choice(alphabet) for _ in range(31))
        cases.append((baseline, tagged))
    cases.append(("abcdefghij", "defabcghij"))

    for baseline, tagged in cases:
        report = QualityEvaluator().evaluate(
            _body_only_document(tagged), baseline, xml_round_trip_ok=True
        )
        expected = _lcs_oracle(baseline, tagged) / len(baseline)
        assert report.metrics["character_match_ratio"] == expected
        assert report.metrics["comparison_mode"] == "bit_parallel_lcs"


def test_sparse_fallback_matches_dynamic_programming_oracle(monkeypatch) -> None:
    import tagged_pdf_extractor.application.evaluate_quality as quality_module

    monkeypatch.setattr(
        quality_module, "_BIT_MASK_MEMORY_BUDGET_BYTES", 1
    )
    baseline = "abcdefghijklmno"
    tagged = "acegikmobdfhjln"

    report = QualityEvaluator().evaluate(
        _body_only_document(tagged), baseline, xml_round_trip_ok=True
    )

    assert report.metrics["character_match_ratio"] == (
        _lcs_oracle(baseline, tagged) / len(baseline)
    )
    assert report.metrics["comparison_mode"] == "sparse_lcs"
    assert report.metrics["comparison_parameters"]["fallback_reason"] == (
        "bit_mask_memory_bound"
    )


@pytest.mark.parametrize("length", (31_000, 32_500))
def test_runtime_mask_estimate_bounds_actual_final_mask_dictionary(
    length: int,
) -> None:
    import tagged_pdf_extractor.application.evaluate_quality as quality_module

    indexed_text = _nonrepetitive_text(length)
    estimate = QualityEvaluator._estimate_bit_mask_memory(indexed_text)
    max_positions = {
        character: position for position, character in enumerate(indexed_text)
    }
    expected_storage = sys.getsizeof(max_positions) + sum(
        sys.getsizeof(character) for character in max_positions
    ) + sum(
        sys.getsizeof(1 << position) for position in max_positions.values()
    )
    expected_key_bytes = sum(
        sys.getsizeof(character) for character in max_positions
    )
    del max_positions
    masks = QualityEvaluator._build_bit_masks(indexed_text)
    actual = sys.getsizeof(masks) + sum(
        sys.getsizeof(character) for character in masks
    ) + sum(
        sys.getsizeof(mask) for mask in masks.values()
    ) + estimate["algorithm_working_bytes"]

    assert estimate["mask_storage_bytes"] == expected_storage
    assert estimate["estimated_mask_bytes"] == (
        expected_storage + estimate["algorithm_working_bytes"]
    )
    assert estimate["algorithm_working_bytes"] >= 2 * sys.getsizeof(
        (1 << length) - 1
    )
    assert actual <= estimate["estimated_mask_bytes"]
    report = QualityEvaluator().evaluate(
        _body_only_document(indexed_text), indexed_text, xml_round_trip_ok=True
    )
    assert estimate["mask_key_bytes"] == expected_key_bytes
    if length == 31_000:
        assert estimate["estimated_mask_bytes"] > (
            quality_module._BIT_MASK_MEMORY_BUDGET_BYTES
        )
        assert report.metrics["comparison_mode"] == "sparse_lcs"


def test_mixed_high_cardinality_case_selects_bit_parallel_backend() -> None:
    unique = _nonrepetitive_text(2_048)
    text = unique + ("x" * 6_145)

    report = QualityEvaluator().evaluate(
        _body_only_document(text), text, xml_round_trip_ok=True
    )

    assert len(text) == 8_193
    assert len(set(text)) == 2_049
    assert report.metrics["character_match_ratio"] == 1.0
    assert report.metrics["comparison_mode"] == "bit_parallel_lcs"


def test_sparse_parameters_report_exact_match_pair_count(monkeypatch) -> None:
    import tagged_pdf_extractor.application.evaluate_quality as quality_module

    monkeypatch.setattr(quality_module, "_BIT_MASK_MEMORY_BUDGET_BYTES", 1)
    baseline = "aaabbc"
    tagged = "aaaabcc"
    expected_pairs = (3 * 4) + (2 * 1) + (1 * 2)

    report = QualityEvaluator().evaluate(
        _body_only_document(tagged), baseline, xml_round_trip_ok=True
    )

    assert report.metrics["comparison_mode"] == "sparse_lcs"
    assert report.metrics["comparison_parameters"]["match_pair_count"] == (
        expected_pairs
    )


def test_ordinary_12k_unique_sparse_candidate_remains_exact(monkeypatch) -> None:
    import tagged_pdf_extractor.application.evaluate_quality as quality_module

    monkeypatch.setattr(quality_module, "_BIT_MASK_MEMORY_BUDGET_BYTES", 1)
    text = _nonrepetitive_text(12_000)

    report = QualityEvaluator().evaluate(
        _body_only_document(text), text, xml_round_trip_ok=True
    )

    assert report.metrics["character_match_ratio"] == 1.0
    assert report.metrics["comparison_mode"] == "sparse_lcs"
    parameters = report.metrics["comparison_parameters"]
    assert parameters["estimated_sparse_bytes"] <= parameters[
        "sparse_memory_budget_bytes"
    ]


def test_high_unique_sparse_candidate_fails_memory_guard_before_work() -> None:
    import tagged_pdf_extractor.application.evaluate_quality as quality_module

    text = _nonrepetitive_text(60_000)

    with pytest.raises(QualityEvaluationLimitError) as caught:
        QualityEvaluator().evaluate(
            _body_only_document(text), text, xml_round_trip_ok=True
        )

    error = caught.value
    assert error.match_pair_estimate == len(text)
    assert error.match_pair_estimate <= quality_module._SPARSE_MATCH_PAIR_BUDGET
    assert error.sparse_memory_estimate > (
        quality_module._SPARSE_MEMORY_BUDGET_BYTES
    )
    assert error.sparse_memory_budget == quality_module._SPARSE_MEMORY_BUDGET_BYTES
    assert error.reason == "exact_backend_resource_budget"


def test_prepass_memory_guard_fails_incrementally(monkeypatch) -> None:
    import tagged_pdf_extractor.application.evaluate_quality as quality_module

    monkeypatch.setattr(quality_module, "_PREPASS_MEMORY_BUDGET_BYTES", 2_048)
    text = _nonrepetitive_text(10_000)

    with pytest.raises(QualityEvaluationLimitError) as caught:
        QualityEvaluator().evaluate(
            _body_only_document(text), text, xml_round_trip_ok=True
        )

    assert caught.value.reason == "prepass_memory_budget"
    assert caught.value.prepass_memory_estimate > 2_048
    assert caught.value.prepass_memory_budget == 2_048


def test_fails_fast_when_no_exact_backend_fits_resource_budgets() -> None:
    import tagged_pdf_extractor.application.evaluate_quality as quality_module

    text = _nonrepetitive_text(32_500) + ("x" * 10_000)

    with pytest.raises(QualityEvaluationLimitError) as caught:
        QualityEvaluator().evaluate(
            _body_only_document(text), text, xml_round_trip_ok=True
        )

    error = caught.value
    assert error.baseline_length == len(text)
    assert error.tagged_length == len(text)
    assert error.mask_estimate > quality_module._BIT_MASK_MEMORY_BUDGET_BYTES
    assert error.match_pair_estimate > quality_module._SPARSE_MATCH_PAIR_BUDGET
    assert error.mask_budget == quality_module._BIT_MASK_MEMORY_BUDGET_BYTES
    assert error.match_pair_budget == quality_module._SPARSE_MATCH_PAIR_BUDGET
    assert error.sparse_memory_estimate > 0
    assert error.sparse_memory_budget == quality_module._SPARSE_MEMORY_BUDGET_BYTES


@pytest.mark.parametrize("padding_length", (8_150, 8_200))
def test_random_lcs_semantics_do_not_change_across_old_threshold(
    padding_length: int,
) -> None:
    generator = random.Random(padding_length)
    alphabet = "abcdef"
    baseline_core = "".join(generator.choice(alphabet) for _ in range(32))
    tagged_core = "".join(generator.choice(alphabet) for _ in range(29))
    padding = _nonrepetitive_text(padding_length)

    report = QualityEvaluator().evaluate(
        _body_only_document(padding + tagged_core),
        padding + baseline_core,
        xml_round_trip_ok=True,
    )
    expected_lcs = padding_length + _lcs_oracle(baseline_core, tagged_core)

    assert report.metrics["character_match_ratio"] == (
        expected_lcs / (padding_length + len(baseline_core))
    )
    assert report.metrics["comparison_mode"] == "bit_parallel_lcs"


def test_bit_parallel_lcs_handles_unicode_and_xml_controls() -> None:
    baseline = ("A\x01βU0001f600" * 2_100) + "tail"
    tagged = baseline[:3_000] + ("\x02" * 256) + baseline[3_000:]

    report = QualityEvaluator().evaluate(
        _body_only_document(tagged), baseline, xml_round_trip_ok=True
    )

    assert report.metrics["character_match_ratio"] == 1.0
    assert report.metrics["comparison_mode"] == "bit_parallel_lcs"


@pytest.mark.parametrize(
    ("baseline", "tagged"),
    (
        ("abcd" * 2_100, "abc" * 700),
        (_nonrepetitive_text(), _nonrepetitive_text()[1_024:]),
        ("x" * 8_193, "x" * 2_048),
    ),
    ids=("repeated-pattern", "high-cardinality", "single-character"),
)
def test_large_lcs_ratio_obeys_coverage_invariants(
    baseline: str, tagged: str
) -> None:
    report = QualityEvaluator().evaluate(
        _body_only_document(tagged), baseline, xml_round_trip_ok=True
    )
    ratio = report.metrics["character_match_ratio"]

    assert 0.0 <= ratio <= 1.0
    assert ratio <= len(tagged) / len(baseline)


def test_empty_figure_is_empty_but_does_not_satisfy_body_gate() -> None:
    document = _document(
        StructureElement(
            "H1",
            "heading",
            1,
            children=(ContentFragment(0, 1, ("Heading",)),),
        ),
        StructureElement("Figure", "figure"),
    )

    report = QualityEvaluator().evaluate(
        document, "Heading", xml_round_trip_ok=True
    )

    assert report.metrics["body_count"] == 0
    assert report.metrics["body_role_node_count"] == 1
    assert report.metrics["empty_element_count"] == 1
    assert report.metrics["unresolved_mcid_count"] == 0
    assert report.hard_gates["has_body"] is False
    assert report.status == "fail"


def test_unresolved_mcid_gate_requires_useful_page_and_mcid_context() -> None:
    useful = Diagnostic(
        "warning",
        "unresolved_mcid",
        "missing text",
        {"page_index": 0, "mcid": 7, "object_ref": "1 0 R"},
    )
    incomplete = Diagnostic(
        "warning",
        "unresolved_mcid",
        "missing page",
        {"page_index": -1, "mcid": None},
    )

    reported_document = _passing_document()
    object.__setattr__(reported_document, "diagnostics", (useful,))
    incomplete_document = _passing_document()
    object.__setattr__(incomplete_document, "diagnostics", (incomplete,))

    reported = QualityEvaluator().evaluate(
        reported_document, "Heading Body", xml_round_trip_ok=True
    )
    unreported = QualityEvaluator().evaluate(
        incomplete_document, "Heading Body", xml_round_trip_ok=True
    )

    assert reported.metrics["unresolved_mcid_count"] == 1
    assert reported.hard_gates["resolved_references_reported"] is True
    assert reported.hard_gates["resolved_references"] is False
    assert reported.status == "fail"
    assert unreported.hard_gates["resolved_references_reported"] is False
    assert unreported.status == "fail"
    assert reported.diagnostics == (useful,)


def test_document_diagnostics_are_preserved_without_override() -> None:
    diagnostic = Diagnostic("warning", "other", "kept", {"value": 1})
    document = _passing_document()
    object.__setattr__(document, "diagnostics", (diagnostic,))

    report = QualityEvaluator().evaluate(
        document, "Heading Body", xml_round_trip_ok=True
    )

    assert report.diagnostics == (diagnostic,)


def test_counts_forbidden_xml_controls_by_occurrence_and_source_field() -> None:
    document = TaggedDocument(
        source_path=Path("manual.pdf"),
        marked=True,
        language="en\x01",
        role_map=(("Custom\x02", "P"),),
        children=(
            StructureElement(
                "H1",
                "heading",
                1,
                title="Title\x03\x04",
                children=(ContentFragment(0, 1, ("Head\x07",)),),
            ),
            StructureElement(
                "P",
                "paragraph",
                attributes=(("/A", "one\x08two\x0e"),),
                children=(ContentFragment(0, 2, ("Body",)),),
            ),
        ),
    )

    report = QualityEvaluator().evaluate(
        document, "Head\x07 Body", xml_round_trip_ok=True
    )

    assert report.metrics["forbidden_xml_control_count"] == 7
    assert report.metrics["forbidden_xml_control_field_count"] == 5
    assert report.hard_gates["no_forbidden_xml_controls"] is False
    assert report.status == "fail"


def test_reports_raw_content_fragment_text_quality_by_numeric_page_order() -> None:
    document = _document(
        StructureElement(
            "P",
            "paragraph",
            children=(
                ContentFragment(7, 3, ("é", "\x03x")),
                ContentFragment(2, 1, ("ab", " c")),
                ContentFragment(2, 2, ("d",)),
            ),
        )
    )

    report = QualityEvaluator().evaluate(
        document, "ab c d é x", xml_round_trip_ok=True
    )

    assert list(report.metrics["text_quality_by_page"]) == ["2", "7"]
    assert report.metrics["text_quality_by_page"] == {
        "2": {
            "fragment_count": 2,
            "character_count": 5,
            "forbidden_xml_control_count": 0,
        },
        "7": {
            "fragment_count": 1,
            "character_count": 3,
            "forbidden_xml_control_count": 1,
        },
    }


def test_hard_gates_are_fixed_and_all_must_pass() -> None:
    report = QualityEvaluator().evaluate(
        _document(marked=False), "body", xml_round_trip_ok=False
    )

    assert tuple(report.hard_gates) == (
        "is_marked",
        "has_structure",
        "has_heading",
        "has_body",
        "xml_round_trip",
        "resolved_references",
        "resolved_references_reported",
        "no_known_text_loss",
        "no_forbidden_xml_controls",
        "special_character_counts_preserved",
        "numbered_heading_series_valid",
        "numbered_heading_series_counts_consistent",
        "numbered_heading_typography_valid",
        "multilingual_interval_count_valid",
        "multilingual_heading_count_parity",
        "multilingual_heading_level_parity",
        "multilingual_heading_origin_parity",
        "multilingual_numbered_label_parity",
    )
    assert report.hard_gates == {
        "is_marked": False,
        "has_structure": False,
        "has_heading": False,
        "has_body": False,
        "xml_round_trip": False,
        "resolved_references": True,
        "resolved_references_reported": True,
        "no_known_text_loss": True,
        "no_forbidden_xml_controls": True,
        "special_character_counts_preserved": True,
        "numbered_heading_series_valid": True,
        "numbered_heading_series_counts_consistent": True,
        "numbered_heading_typography_valid": True,
        "multilingual_interval_count_valid": True,
        "multilingual_heading_count_parity": True,
        "multilingual_heading_level_parity": True,
        "multilingual_heading_origin_parity": True,
        "multilingual_numbered_label_parity": True,
    }
    assert report.status == "fail"


def test_report_contains_deterministic_document_audit_and_heading_candidates() -> None:
    document = TaggedDocument(
        source_path=Path("manual.pdf"),
        marked=True,
        language=None,
        role_map=(("Zed", "P"), ("Heading2", "P")),
        children=(
            StructureElement(
                "Sect",
                "section",
                children=(
                    StructureElement(
                        "Heading2",
                        "paragraph",
                        title="Menu title",
                        children=(ContentFragment(0, 1, ("Set", "tings")),),
                    ),
                    StructureElement(
                        "H1", "heading", 1,
                        children=(ContentFragment(0, 2, ("Real heading",)),),
                    ),
                    StructureElement(
                        "Cover_Title", "paragraph",
                        children=(ContentFragment(0, 3, ("Cover",)),),
                    ),
                ),
            ),
        ),
    )

    report = QualityEvaluator().evaluate(
        document, "Set tings Real heading Cover", xml_round_trip_ok=True
    )

    assert report.source_path == Path("manual.pdf")
    assert report.language is None
    assert report.marked is True
    assert report.role_map == (("Heading2", "P"), ("Zed", "P"))
    assert report.source_role_counts == {
        "Cover_Title": 1, "H1": 1, "Heading2": 1, "Sect": 1,
    }
    assert report.heading_hierarchy == (
        {
            "structure_path": "/section[0]/paragraph[0]",
            "source_role": "Heading2", "semantic_role": "paragraph",
            "level": 2, "joined_text": "Set tings", "title": "Menu title",
            "classification": "source_role_candidate",
        },
        {
            "structure_path": "/section[0]/heading[1]",
            "source_role": "H1", "semantic_role": "heading",
            "level": 1, "joined_text": "Real heading", "title": None,
            "classification": "heading",
        },
        {
            "structure_path": "/section[0]/paragraph[2]",
            "source_role": "Cover_Title", "semantic_role": "paragraph",
            "level": None, "joined_text": "Cover", "title": None,
            "classification": "source_role_candidate",
        },
    )
    assert report.metrics["heading_count"] == 1


def test_heading_hierarchy_preserves_document_order_for_nested_headings() -> None:
    document = _document(
        StructureElement(
            "H1",
            "heading",
            1,
            children=(
                ContentFragment(0, 1, ("Parent",)),
                StructureElement(
                    "H2", "heading", 2,
                    children=(ContentFragment(0, 2, ("Child",)),),
                ),
            ),
        )
    )

    report = QualityEvaluator().evaluate(
        document, "Parent Child", xml_round_trip_ok=True
    )

    assert [item["source_role"] for item in report.heading_hierarchy] == [
        "H1", "H2"
    ]
    assert [item["structure_path"] for item in report.heading_hierarchy] == [
        "/heading[0]", "/heading[0]/heading[1]"
    ]


def test_decorated_heading_source_role_is_candidate_without_promotion() -> None:
    document = _document(
        StructureElement(
            "Heading2_0_2", "paragraph",
            children=(ContentFragment(0, 1, ("Troubleshooting",)),),
        ),
        StructureElement(
            "Heading20", "paragraph",
            children=(ContentFragment(0, 2, ("Not a heading",)),),
        ),
    )

    report = QualityEvaluator().evaluate(
        document, "Troubleshooting Not a heading", xml_round_trip_ok=True
    )

    assert report.heading_hierarchy == (
        {
            "structure_path": "/paragraph[0]",
            "source_role": "Heading2_0_2",
            "semantic_role": "paragraph",
            "level": 2,
            "joined_text": "Troubleshooting",
            "title": None,
            "classification": "source_role_candidate",
        },
    )
    assert report.metrics["heading_count"] == 0


@pytest.mark.parametrize(
    ("code", "metric"),
    [("unresolved_mcid", "unresolved_mcid_count"),
     ("unresolved_page_reference", "unresolved_page_reference_count"),
     ("unsupported_objr", "unsupported_objr_count")],
)
def test_each_unresolved_reference_code_fails_resolved_references_gate(
    code: str, metric: str
) -> None:
    diagnostic = Diagnostic("warning", code, "reference issue", {"object_ref": "1 0 R"})
    document = _passing_document()
    object.__setattr__(document, "diagnostics", (diagnostic,))
    report = QualityEvaluator().evaluate(document, "Heading Body", xml_round_trip_ok=True)
    assert report.metrics[metric] == 1
    assert report.metrics["unresolved_reference_count"] == 1
    assert report.hard_gates["resolved_references"] is False
    assert report.status == "fail"


def test_unconfigured_audit_preserves_legacy_gates_with_explicit_metric_status() -> None:
    report = _evaluate_with_audit(None)

    assert report.status == "pass"
    assert all(report.hard_gates[name] for name in tuple(report.hard_gates)[-5:])
    assert report.metrics["multilingual_heading_audit"] == {
        "applicable": None,
        "status": "not_configured",
        "passed": None,
        "expected_interval_count": None,
        "observed_interval_count": None,
        "interval_count_matches": None,
        "total_heading_count_matches": None,
        "heading_level_sequence_matches": None,
        "heading_origin_sequence_matches": None,
        "numbered_label_sequence_matches": None,
        "languages": [],
        "mismatch_positions": [],
        "diagnostics": [],
    }


def test_single_language_audit_is_not_applicable_without_failing_gates() -> None:
    audit = MultilingualHeadingAudit(
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

    report = _evaluate_with_audit(audit)

    assert report.status == "pass"
    assert all(report.hard_gates[name] for name in tuple(report.hard_gates)[-5:])
    metric = report.metrics["multilingual_heading_audit"]
    assert metric["applicable"] is False
    assert metric["status"] == "not_applicable"
    assert metric["passed"] is True
    assert metric["expected_interval_count"] == 1
    assert metric["observed_interval_count"] == 0


@pytest.mark.parametrize(
    ("expected_count", "observed_count", "matches", "code"),
    (
        (2, 1, False, "multilingual_heading_interval_count_mismatch"),
        (2, 2, True, "multilingual_heading_interval_boundary_invalid"),
    ),
    ids=("count-mismatch", "same-count-invalid-boundary"),
)
def test_pending_interval_failure_only_fails_interval_gate(
    expected_count: int,
    observed_count: int,
    matches: bool,
    code: str,
) -> None:
    audit = MultilingualHeadingAudit(
        applicable=True,
        passed=False,
        expected_interval_count=expected_count,
        observed_interval_count=observed_count,
        interval_count_matches=matches,
        total_heading_count_matches=None,
        heading_level_sequence_matches=None,
        heading_origin_sequence_matches=None,
        numbered_label_sequence_matches=None,
        diagnostics=(
            Diagnostic(
                "error",
                code,
                "interval resolution failed",
                {"reason": "missing_start_path", "path": (1, 0)},
            ),
        ),
    )

    report = _evaluate_with_audit(audit)

    assert report.status == "fail"
    assert report.hard_gates["multilingual_interval_count_valid"] is False
    assert all(
        report.hard_gates[name]
        for name in (
            "multilingual_heading_count_parity",
            "multilingual_heading_level_parity",
            "multilingual_heading_origin_parity",
            "multilingual_numbered_label_parity",
        )
    )
    metric = report.metrics["multilingual_heading_audit"]
    assert metric["status"] == "blocked_by_invalid_interval"
    assert metric["diagnostics"] == [
        {
            "severity": "error",
            "code": code,
            "message": "interval resolution failed",
            "context": {"path": [1, 0], "reason": "missing_start_path"},
        }
    ]


@pytest.mark.parametrize(
    ("component", "failed_gate"),
    (
        ("count", "multilingual_heading_count_parity"),
        ("level", "multilingual_heading_level_parity"),
        ("origin", "multilingual_heading_origin_parity"),
        ("numbered_label", "multilingual_numbered_label_parity"),
    ),
)
def test_each_signature_mismatch_fails_only_its_matching_gate(
    component: str,
    failed_gate: str,
) -> None:
    report = _evaluate_with_audit(_audit(component=component))

    failed = [name for name, passed in report.hard_gates.items() if not passed]
    assert failed == [failed_gate]
    assert report.status == "fail"
    metric = report.metrics["multilingual_heading_audit"]
    assert metric["status"] == "failed"
    assert metric["mismatch_positions"][0]["interval_ordinal"] == 2


def test_mismatch_metric_contains_expected_and_observed_entries_without_wording() -> None:
    metric = _evaluate_with_audit(_audit(component="level")).metrics[
        "multilingual_heading_audit"
    ]

    assert metric["mismatch_positions"] == [
        {
            "interval_ordinal": 2,
            "language": "C-FRA",
            "position": 1,
            "component": "level",
            "expected": {
                "heading_level": 2,
                "heading_origin": "promoted",
                "numbered_label": "01",
            },
            "observed": {
                "heading_level": 3,
                "heading_origin": "promoted",
                "numbered_label": "01",
            },
        }
    ]
    assert "wording" not in repr(metric).lower()


def test_mismatch_metric_rejects_language_without_signature_interval() -> None:
    audit = _audit(component="level")
    mismatch = replace(audit.mismatch_positions[0], language="DEU")
    object.__setattr__(audit, "mismatch_positions", (mismatch,))

    with pytest.raises(ValueError, match="mismatch language has no signature"):
        _evaluate_with_audit(audit)


def test_passing_audit_report_has_exact_deterministic_json_ready_shape() -> None:
    report = _evaluate_with_audit(_audit())

    assert report.status == "pass"
    assert report.metrics["multilingual_heading_audit"] == {
        "applicable": True,
        "status": "passed",
        "passed": True,
        "expected_interval_count": 2,
        "observed_interval_count": 2,
        "interval_count_matches": True,
        "total_heading_count_matches": True,
        "heading_level_sequence_matches": True,
        "heading_origin_sequence_matches": True,
        "numbered_label_sequence_matches": True,
        "languages": [
            {
                "ordinal": 1,
                "language": "ENG",
                "interval": {
                    "start_page_index": 0,
                    "end_page_index": 0,
                    "start_path": [0],
                    "end_path": [0],
                    "evidence_origin": "bookmark",
                },
                "heading_total": 2,
                "heading_levels": [1, 2],
                "heading_origins": ["source", "promoted"],
                "numbered_labels": [None, "01"],
            },
            {
                "ordinal": 2,
                "language": "C-FRA",
                "interval": {
                    "start_page_index": 1,
                    "end_page_index": 1,
                    "start_path": [1],
                    "end_path": [1],
                    "evidence_origin": "structural_language_section",
                },
                "heading_total": 2,
                "heading_levels": [1, 2],
                "heading_origins": ["source", "promoted"],
                "numbered_labels": [None, "01"],
            },
        ],
        "mismatch_positions": [],
        "diagnostics": [],
    }


def test_negative_page_index_is_retained_as_auditable_page_bucket() -> None:
    document = _document(
        StructureElement(
            "P",
            "paragraph",
            children=(ContentFragment(-1, 7, ("unresolved text",)),),
        )
    )

    report = QualityEvaluator().evaluate(
        document, "unresolved text", xml_round_trip_ok=True
    )

    assert report.metrics["text_quality_by_page"]["-1"] == {
        "fragment_count": 1,
        "character_count": 15,
        "forbidden_xml_control_count": 0,
    }


def test_unresolved_tagged_xobject_fails_reference_and_text_loss_gates() -> None:
    diagnostic = Diagnostic(
        "warning",
        "tagged_xobject_unresolved",
        "Tagged XObject reference could not be resolved",
        {"page_index": 6, "operand_repr": "'/Missing'"},
    )
    document = _passing_document()
    object.__setattr__(document, "diagnostics", (diagnostic,))

    report = QualityEvaluator().evaluate(
        document, "Heading Body", xml_round_trip_ok=True
    )

    assert report.hard_gates["resolved_references"] is False
    assert report.metrics["unresolved_reference_count"] == 1
    assert report.hard_gates["resolved_references_reported"] is True
    assert report.hard_gates["no_known_text_loss"] is False


@pytest.mark.parametrize(
    "code",
    (
        "unresolved_mcid",
        "unresolved_page_reference",
        "unsupported_objr",
        "unsupported_stream_mcr",
        "tagged_form_xobject_unsupported",
        "tagged_xobject_unresolved",
        "tagged_xobject_unsupported",
        "invalid_mcid",
        "unsupported_structure_kid",
    ),
)
def test_each_known_extraction_loss_diagnostic_fails_text_loss_gate(
    code: str,
) -> None:
    diagnostic = Diagnostic("warning", code, "content may be lost", {"source": "test"})
    document = _passing_document()
    object.__setattr__(document, "diagnostics", (diagnostic,))

    report = QualityEvaluator().evaluate(
        document, "Heading Body", xml_round_trip_ok=True
    )

    assert report.metrics["extraction_loss_diagnostic_counts"][code] == 1
    assert report.metrics["extraction_loss_diagnostic_total"] == 1
    assert report.hard_gates["no_known_text_loss"] is False
    assert report.status == "fail"


@pytest.mark.parametrize(
    "code", ("unbalanced_emc", "unclosed_marked_content")
)
def test_structural_balancing_warning_is_not_assumed_to_be_text_loss(
    code: str,
) -> None:
    diagnostic = Diagnostic(
        "warning", code, "marked-content scope imbalance", {}
    )
    document = _passing_document()
    object.__setattr__(document, "diagnostics", (diagnostic,))

    report = QualityEvaluator().evaluate(
        document, "Heading Body", xml_round_trip_ok=True
    )

    assert report.metrics["extraction_loss_diagnostic_total"] == 0
    assert report.hard_gates["no_known_text_loss"] is True
    assert report.status == "pass"


def test_special_character_gate_ignores_absent_baseline_characters() -> None:
    report = QualityEvaluator().evaluate(
        _passing_document("A/B"), "Heading A/B", xml_round_trip_ok=True
    )
    assert report.metrics["special_characters"]["\u2192"] == {
        "tagged": 0, "baseline": 0, "count_preserved": True,
    }
    assert report.hard_gates["special_character_counts_preserved"] is True


@pytest.mark.parametrize("character", tuple(">\u2192/&:[]()"))
def test_special_character_deficit_fails_preservation_gate(character: str) -> None:
    report = QualityEvaluator().evaluate(
        _passing_document("Body"), f"Heading Body {character}", xml_round_trip_ok=True
    )
    assert report.metrics["special_characters"][character]["count_preserved"] is False
    assert report.hard_gates["special_character_counts_preserved"] is False
    assert report.status == "fail"
