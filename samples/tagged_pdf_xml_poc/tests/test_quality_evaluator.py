from __future__ import annotations

import random
from difflib import SequenceMatcher
from pathlib import Path

import pymupdf
import pytest

from tagged_pdf_extractor.application.evaluate_quality import QualityEvaluator
from tagged_pdf_extractor.domain.models import (
    ContentFragment,
    Diagnostic,
    StructureElement,
    TaggedDocument,
)
from tagged_pdf_extractor.infrastructure.pymupdf_baseline import (
    PyMuPdfBaselineReader,
)
import tagged_pdf_extractor.infrastructure.pymupdf_baseline as baseline_module


SPECIAL_CHARACTERS = ">→/&:[]()"


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
        }
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
    root_children = SinglePassChildren(
        (
            StructureElement("H1", "heading", 1, children=heading_children),
            StructureElement("P", "paragraph", children=body_children),
        )
    )
    document = _document()
    object.__setattr__(document, "children", root_children)

    report = QualityEvaluator().evaluate(
        document,
        "Head ing First part Second part",
        xml_round_trip_ok=True,
    )

    assert root_children.iterations == 1
    assert heading_children.iterations == 1
    assert body_children.iterations == 1
    assert [
        (decision["element_path"], decision["fragment_child_index"])
        for decision in report.join_decisions
    ] == [
        ("/heading[0]", 0),
        ("/paragraph[1]", 0),
        ("/paragraph[1]", 1),
    ]
    assert report.metrics["character_match_ratio"] == 1.0


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


def test_small_character_comparison_uses_exact_sequence_matcher_semantics() -> None:
    tagged = "Heading The quick brown fox"
    baseline = "Heading The quick blue fox"
    expected_matched = sum(
        block.size
        for block in SequenceMatcher(
            None, baseline, tagged, autojunk=False
        ).get_matching_blocks()
    )

    report = QualityEvaluator().evaluate(
        _passing_document("The quick brown fox"),
        baseline,
        xml_round_trip_ok=True,
    )

    assert report.metrics["character_match_ratio"] == expected_matched / len(baseline)
    assert report.metrics["comparison_mode"] == "exact_sequence_matcher"
    assert report.metrics["comparison_parameters"] == {
        "autojunk": False,
        "exact_threshold": 8_192,
    }


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
    assert report.metrics["comparison_mode"] == "sparse_lcs"


def test_large_modes_never_call_sequence_matcher(monkeypatch) -> None:
    import tagged_pdf_extractor.application.evaluate_quality as quality_module

    def fail_if_called(*args, **kwargs):
        raise AssertionError("large comparison must not use SequenceMatcher")

    monkeypatch.setattr(quality_module, "SequenceMatcher", fail_if_called)
    long_text = "abcd" * 2_100

    report = QualityEvaluator().evaluate(
        _body_only_document(long_text),
        long_text,
        xml_round_trip_ok=True,
    )

    assert report.metrics["character_match_ratio"] == 1.0
    assert report.metrics["comparison_mode"] == "bit_parallel_lcs"


def test_bit_parallel_large_mode_matches_dynamic_programming_oracle(
    monkeypatch,
) -> None:
    import tagged_pdf_extractor.application.evaluate_quality as quality_module

    monkeypatch.setattr(quality_module, "_EXACT_COMPARISON_THRESHOLD", 0)
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

    monkeypatch.setattr(quality_module, "_EXACT_COMPARISON_THRESHOLD", 0)
    monkeypatch.setattr(
        quality_module, "_BIT_PARALLEL_MAX_UNIQUE_CHARACTERS", 2
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
    assert reported.status == "pass"
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
        "resolved_references_reported",
    )
    assert report.hard_gates == {
        "is_marked": False,
        "has_structure": False,
        "has_heading": False,
        "has_body": False,
        "xml_round_trip": False,
        "resolved_references_reported": True,
    }
    assert report.status == "fail"
