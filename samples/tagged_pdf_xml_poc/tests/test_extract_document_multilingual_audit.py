from __future__ import annotations

from pathlib import Path

import pytest

from tagged_pdf_extractor.application.extract_document import ExtractDocument
from tagged_pdf_extractor.domain.models import (
    BookmarkPageBounds,
    ContentFragment,
    ExtractionArtifacts,
    PdfProfile,
    QualityReport,
    StructureElement,
    TaggedDocument,
)
from tagged_pdf_extractor.ports.output_writer import OutputValidation


def _heading(page_index: int, wording: str = "ignored wording") -> StructureElement:
    return StructureElement(
        "H2",
        "heading",
        heading_level=2,
        children=(ContentFragment(page_index, None, (wording,)),),
    )


def _section(page_index: int, wording: str) -> StructureElement:
    return StructureElement(
        "Sect",
        "section",
        children=(_heading(page_index, wording),),
    )


class _Reader:
    def __init__(self, document: TaggedDocument) -> None:
        self.document = document

    def read(self, path: Path) -> TaggedDocument:
        return self.document


class _Baseline:
    def read_text(self, path: Path) -> str:
        return "baseline"


class _Evaluator:
    def __init__(self) -> None:
        self.documents: list[TaggedDocument] = []

    def evaluate(
        self,
        document: TaggedDocument,
        baseline: str,
        xml_round_trip_ok: bool,
    ) -> QualityReport:
        self.documents.append(document)
        return QualityReport("pass", {}, {"has_heading": True}, ())


class _Writer:
    def validate(self, document: TaggedDocument) -> OutputValidation:
        return OutputValidation(())

    def write(
        self,
        document: TaggedDocument,
        report: QualityReport,
        output_dir: Path,
        overwrite: bool = False,
    ) -> ExtractionArtifacts:
        return ExtractionArtifacts(
            output_dir / "raw_structure.xml",
            output_dir / "semantic_document.xml",
            output_dir / "extraction_report.json",
            output_dir / "semantic_document.md",
        )


class _Repository:
    def __init__(self, profiles: dict[str, PdfProfile]) -> None:
        self.profiles = profiles
        self.paths: list[Path] = []

    def lookup(self, pdf_path: str | Path) -> PdfProfile:
        path = Path(pdf_path)
        self.paths.append(path)
        return self.profiles[path.name]


def _run(
    tmp_path: Path,
    filename: str,
    document: TaggedDocument,
    repository: _Repository | None,
) -> tuple[TaggedDocument, _Evaluator]:
    source = tmp_path / filename
    source.write_bytes(b"pdf")
    evaluator = _Evaluator()
    extracted, _, _ = ExtractDocument(
        _Reader(document),
        _Baseline(),
        evaluator,  # type: ignore[arg-type]
        _Writer(),
        repository,
    ).run(source, tmp_path / "out")
    return extracted, evaluator


def test_optional_repository_keeps_existing_callers_and_audit_none(
    tmp_path: Path,
) -> None:
    source = tmp_path / "legacy.pdf"
    document = TaggedDocument(source, True, None, (), (_section(0, "only"),))

    extracted, evaluator = _run(tmp_path, source.name, document, None)

    assert extracted.multilingual_heading_audit is None
    assert evaluator.documents == [extracted]


def test_repository_resolves_and_validates_within_one_multilingual_document(
    tmp_path: Path,
) -> None:
    filename = "first.pdf"
    profile = PdfProfile("XX_L02", "A2", ("AAA", "BBB"), 2)
    document = TaggedDocument(
        Path(filename),
        True,
        None,
        (),
        (_section(2, "first wording"), _section(9, "different wording")),
    )
    repository = _Repository({filename: profile})

    extracted, evaluator = _run(tmp_path, filename, document, repository)

    audit = extracted.multilingual_heading_audit
    assert audit is not None
    assert audit.applicable is True
    assert audit.passed is True
    assert tuple(signature.language for signature in audit.signatures) == (
        "AAA",
        "BBB",
    )
    assert repository.paths == [tmp_path / filename]
    assert evaluator.documents == [extracted]


def test_interval_resolution_failure_is_stored_as_pending_failed_audit(
    tmp_path: Path,
) -> None:
    filename = "ambiguous.pdf"
    profile = PdfProfile("XX_L02", "A2", ("AAA", "BBB"), 2)
    document = TaggedDocument(
        Path(filename),
        True,
        None,
        (),
        (_section(4, "first"), _section(4, "second")),
    )

    extracted, _ = _run(
        tmp_path, filename, document, _Repository({filename: profile})
    )

    audit = extracted.multilingual_heading_audit
    assert audit is not None
    assert audit.applicable is True
    assert audit.passed is False
    assert audit.expected_interval_count == 2
    assert audit.observed_interval_count == 1
    assert audit.interval_count_matches is False
    assert audit.total_heading_count_matches is None
    assert audit.signatures == ()
    assert audit.diagnostics[0].code == "language_interval_heading_page_count_mismatch"


def test_single_language_profile_uses_empty_resolution_for_not_applicable_audit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import tagged_pdf_extractor.application.extract_document as use_case_module

    filename = "single.pdf"
    profile = PdfProfile("XX_ENG", "A3", ("ENG",), 1)
    document = TaggedDocument(
        Path(filename),
        True,
        None,
        (),
        (_section(1, "one"), _section(7, "another heading page")),
    )
    actual_resolve = use_case_module.resolve_language_intervals
    resolved_documents: list[TaggedDocument] = []

    def resolve(actual_profile: PdfProfile, actual: TaggedDocument):
        resolved_documents.append(actual)
        return actual_resolve(actual_profile, actual)

    monkeypatch.setattr(use_case_module, "resolve_language_intervals", resolve)

    extracted, _ = _run(
        tmp_path, filename, document, _Repository({filename: profile})
    )

    audit = extracted.multilingual_heading_audit
    assert audit is not None
    assert audit.applicable is False
    assert audit.passed is True
    assert audit.expected_interval_count == 1
    assert audit.observed_interval_count == 0
    assert resolved_documents == [document]


def test_book_profile_resolves_bookmarks_then_validates_same_document(
    tmp_path: Path,
) -> None:
    filename = "book.pdf"
    profile = PdfProfile("XX_L02", "BOOK", ("AAA", "BBB"), 2)
    document = TaggedDocument(
        Path(filename),
        True,
        None,
        (),
        (_section(0, "first"), _section(1, "second")),
        bookmark_page_bounds=(
            BookmarkPageBounds(1, 0, 0, "arbitrary"),
            BookmarkPageBounds(2, 1, 1, "unrelated"),
        ),
    )

    extracted, _ = _run(
        tmp_path, filename, document, _Repository({filename: profile})
    )

    audit = extracted.multilingual_heading_audit
    assert audit is not None
    assert audit.passed is True
    assert tuple(signature.language for signature in audit.signatures) == (
        "AAA",
        "BBB",
    )
    assert all(
        signature.interval.evidence_origin == "bookmark"
        for signature in audit.signatures
    )


def test_book_resolution_failure_builds_pending_audit_with_preserved_count(
    tmp_path: Path,
) -> None:
    filename = "book-invalid.pdf"
    profile = PdfProfile("XX_L02", "BOOK", ("AAA", "BBB"), 2)
    document = TaggedDocument(
        Path(filename),
        True,
        None,
        (),
        (
            StructureElement("P", "paragraph", page_index=-1),
            _section(0, "first"),
            _section(1, "second"),
        ),
        bookmark_page_bounds=(
            BookmarkPageBounds(1, 0, 0, "first"),
            BookmarkPageBounds(2, 1, 1, "second"),
        ),
    )

    extracted, _ = _run(
        tmp_path, filename, document, _Repository({filename: profile})
    )

    audit = extracted.multilingual_heading_audit
    assert audit is not None
    assert audit.applicable is True
    assert audit.passed is False
    assert audit.observed_interval_count == 2
    assert audit.interval_count_matches is True
    assert audit.total_heading_count_matches is None
    assert audit.diagnostics[0].code == "language_interval_page_evidence_invalid"


def test_unrelated_profiles_are_looked_up_and_audited_only_for_their_own_pdf(
    tmp_path: Path,
) -> None:
    first_name = "first.pdf"
    second_name = "second.pdf"
    repository = _Repository(
        {
            first_name: PdfProfile("XX_L02", "A2", ("AAA", "BBB"), 2),
            second_name: PdfProfile("YY_ENG", "A3", ("CCC",), 1),
        }
    )
    first_document = TaggedDocument(
        Path(first_name),
        True,
        None,
        (),
        (_section(0, "first"), _section(1, "second")),
    )
    second_document = TaggedDocument(
        Path(second_name), True, None, (), (_section(0, "unrelated"),)
    )

    first, _ = _run(tmp_path, first_name, first_document, repository)
    second, _ = _run(tmp_path, second_name, second_document, repository)

    assert first.multilingual_heading_audit is not None
    assert first.multilingual_heading_audit.applicable is True
    assert second.multilingual_heading_audit is not None
    assert second.multilingual_heading_audit.applicable is False
    assert repository.paths == [tmp_path / first_name, tmp_path / second_name]


def test_audit_runs_after_promotion_and_before_formatting_or_evaluation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import tagged_pdf_extractor.application.extract_document as use_case_module

    filename = "ordered.pdf"
    source = tmp_path / filename
    source.write_bytes(b"pdf")
    document = TaggedDocument(
        source,
        True,
        None,
        (),
        (_section(0, "first"), _section(1, "second")),
    )
    profile = PdfProfile("XX_L02", "A2", ("AAA", "BBB"), 2)
    events: list[str] = []
    actual_resolve = use_case_module.resolve_language_intervals
    actual_validate = use_case_module.validate_multilingual_headings
    actual_format = use_case_module.detect_table_subtitles

    def promote(actual: TaggedDocument) -> TaggedDocument:
        events.append("promote")
        return actual

    def resolve(actual_profile: PdfProfile, actual: TaggedDocument):
        events.append("resolve")
        return actual_resolve(actual_profile, actual)

    def validate(actual_profile: PdfProfile, intervals, actual: TaggedDocument):
        events.append("validate")
        return actual_validate(actual_profile, intervals, actual)

    def format_document(actual: TaggedDocument) -> TaggedDocument:
        events.append("format")
        return actual_format(actual)

    class OrderedRepository(_Repository):
        def lookup(self, pdf_path: str | Path) -> PdfProfile:
            events.append("lookup")
            return super().lookup(pdf_path)

    class OrderedEvaluator(_Evaluator):
        def evaluate(self, document, baseline, xml_round_trip_ok):
            events.append("evaluate")
            return super().evaluate(document, baseline, xml_round_trip_ok)

    monkeypatch.setattr(
        use_case_module, "promote_numbered_chapter_headings", promote
    )
    monkeypatch.setattr(use_case_module, "resolve_language_intervals", resolve)
    monkeypatch.setattr(use_case_module, "validate_multilingual_headings", validate)
    monkeypatch.setattr(use_case_module, "detect_table_subtitles", format_document)
    evaluator = OrderedEvaluator()

    ExtractDocument(
        _Reader(document),
        _Baseline(),
        evaluator,  # type: ignore[arg-type]
        _Writer(),
        OrderedRepository({filename: profile}),
    ).run(source, tmp_path / "out")

    assert events == ["promote", "lookup", "resolve", "validate", "format", "evaluate"]
