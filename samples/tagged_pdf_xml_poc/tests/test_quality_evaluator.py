from __future__ import annotations

from pathlib import Path
from difflib import SequenceMatcher

import pymupdf

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
    assert report.metrics["character_match_metric_mode"] == "exact"
    assert report.metrics["character_match_chunk_size"] is None


def test_large_character_comparison_is_deterministic_and_auditable() -> None:
    tagged_body = "".join(f"item-{index:04d} " for index in range(1200))
    baseline = f"Heading {tagged_body}tail"
    document = _passing_document(tagged_body)

    first = QualityEvaluator().evaluate(document, baseline, xml_round_trip_ok=True)
    second = QualityEvaluator().evaluate(document, baseline, xml_round_trip_ok=True)

    assert first.metrics["character_match_ratio"] == second.metrics[
        "character_match_ratio"
    ]
    assert first.metrics["character_match_metric_mode"] == "chunked_monotonic"
    assert first.metrics["character_match_chunk_size"] > 0
    assert first.metrics["character_match_window_margin"] == 0


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


def test_chunked_comparison_handles_insertion_across_chunk_boundary() -> None:
    baseline = "".join(f"{index:05d}|" for index in range(1_600))
    tagged = baseline[:2_048] + "INSERTED" + baseline[2_048:]
    document = _document(
        StructureElement(
            "P",
            "paragraph",
            children=(ContentFragment(0, 1, (tagged,)),),
        )
    )

    report = QualityEvaluator().evaluate(document, baseline, xml_round_trip_ok=True)

    assert 0.99 < report.metrics["character_match_ratio"] <= 1.0
    assert report.metrics["character_match_metric_mode"] == "chunked_monotonic"


def test_chunked_comparison_handles_deletion_across_chunk_boundary() -> None:
    baseline = "".join(f"{index:05d}|" for index in range(1_600))
    tagged = baseline[:2_040] + baseline[2_056:]
    document = _document(
        StructureElement(
            "P",
            "paragraph",
            children=(ContentFragment(0, 1, (tagged,)),),
        )
    )

    report = QualityEvaluator().evaluate(document, baseline, xml_round_trip_ok=True)
    maximum_ratio = len(tagged) / len(baseline)

    assert maximum_ratio - 0.01 < report.metrics["character_match_ratio"]
    assert report.metrics["character_match_ratio"] <= maximum_ratio


def test_large_comparison_bounds_every_sequence_matcher_call(monkeypatch) -> None:
    import tagged_pdf_extractor.application.evaluate_quality as quality_module

    calls: list[tuple[str, str, bool]] = []

    class FakeMatcher:
        def __init__(self, isjunk, baseline, tagged, autojunk):
            assert isjunk is None
            calls.append((baseline, tagged, autojunk))

        def get_matching_blocks(self):
            return (type("Block", (), {"size": 1})(),)

    monkeypatch.setattr(quality_module, "SequenceMatcher", FakeMatcher)
    long_text = "x" * (quality_module._EXACT_COMPARISON_THRESHOLD + 1)

    report = QualityEvaluator().evaluate(
        _passing_document(long_text),
        f"Heading {long_text}",
        xml_round_trip_ok=True,
    )

    assert len(calls) > 1
    assert all(autojunk is False for _, _, autojunk in calls)
    assert max(len(baseline) for baseline, _, _ in calls) <= (
        quality_module._COMPARISON_CHUNK_SIZE
    )
    assert max(len(tagged) for _, tagged, _ in calls) <= (
        quality_module._COMPARISON_CHUNK_SIZE
    )
    assert "".join(baseline for baseline, _, _ in calls) == f"Heading {long_text}"
    assert "".join(tagged for _, tagged, _ in calls) == f"Heading {long_text}"
    assert report.metrics["character_match_metric_mode"] == "chunked_monotonic"


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
