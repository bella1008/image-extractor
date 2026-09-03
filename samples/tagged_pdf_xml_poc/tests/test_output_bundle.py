import json
import os
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from tagged_pdf_extractor.application.extract_document import ExtractDocument
from tagged_pdf_extractor.domain.models import (
    ContentFragment,
    Diagnostic,
    QualityReport,
    StructureElement,
    TaggedDocument,
)
from tagged_pdf_extractor.infrastructure.json_report_writer import JsonReportWriter
from tagged_pdf_extractor.infrastructure import output_bundle as output_bundle_module
from tagged_pdf_extractor.infrastructure.output_bundle import (
    BundleRollbackError,
    BundleTransactionError,
    OutputBusyError,
    OutputBundleWriter,
    OutputCollisionError,
)
from tagged_pdf_extractor.ports.output_writer import OutputValidation


def _document(tmp_path: Path) -> TaggedDocument:
    fragment = ContentFragment(0, 7, ("설정 > 일반", " > 접근성 & 도움말"))
    heading = StructureElement("H2", "heading", 2, children=(fragment,))
    return TaggedDocument(
        tmp_path / "입력.pdf",
        True,
        "ko-KR",
        (("사용자", "H2"),),
        (heading,),
        (Diagnostic("warning", "검토", "한글 진단", {"경로": Path("증거/화면.png")}),),
    )


def _report(document: TaggedDocument) -> QualityReport:
    decisions_path = Path("unused.xml")
    from tagged_pdf_extractor.infrastructure.xml_writer import XmlDocumentWriter

    try:
        decisions = XmlDocumentWriter().write_semantic(document, decisions_path)
    finally:
        decisions_path.unlink(missing_ok=True)
    return QualityReport(
        "pass",
        {"비율": 1.0, "경로": Path("결과/검토")},
        {"xml_round_trip": True},
        document.diagnostics,
        decisions,
    )


def _owned_temporary_paths(parent: Path, output_name: str) -> list[Path]:
    paths = list(parent.glob(f".{output_name}.staging-*")) + list(
        parent.glob(f".{output_name}.backup-*")
    )
    lock = parent / f".{output_name}.lock"
    return paths + ([lock] if lock.exists() else [])


def test_json_report_writer_preserves_dataclass_order_unicode_paths_and_controls(
    tmp_path: Path,
) -> None:
    report = QualityReport(
        "fail",
        {"한글": "값\x01", "path": Path("근거/화면.png"), "items": (1, True)},
        {"xml_round_trip": False},
        (Diagnostic("error", "E1", "실패", {"page": 3}),),
        ({"action": "join", "path": Path("a/b")},),
    )
    target = tmp_path / "report.json"

    JsonReportWriter().write(report, target)

    raw = target.read_text(encoding="utf-8")
    assert raw.endswith("\n")
    assert "한글" in raw and "\\u0001" in raw
    parsed = json.loads(raw)
    assert list(parsed) == [
        "status",
        "metrics",
        "hard_gates",
        "diagnostics",
        "join_decisions",
    ]
    assert parsed["metrics"]["path"] == str(Path("근거/화면.png"))
    assert parsed["diagnostics"][0]["context"] == {"page": 3}


def test_json_report_writer_fails_clearly_for_unsupported_context_value(
    tmp_path: Path,
) -> None:
    report = QualityReport("fail", {"bad": {1, 2}}, {}, ())

    with pytest.raises(TypeError, match=r"metrics\.bad.*set"):
        JsonReportWriter().write(report, tmp_path / "report.json")

    assert not (tmp_path / "report.json").exists()


def test_json_report_writer_atomically_preserves_lone_surrogate_and_korean(
    tmp_path: Path,
) -> None:
    target = tmp_path / "report.json"
    target.write_text("old report", encoding="utf-8")
    report = QualityReport("fail", {"문자": "한글\ud800끝"}, {}, ())

    JsonReportWriter().write(report, target)

    raw = target.read_text(encoding="utf-8")
    assert "한글" in raw
    assert "\\ud800" in raw.lower()
    assert json.loads(raw)["metrics"]["문자"] == "한글\ud800끝"
    assert list(tmp_path.glob(".report.json.*.tmp")) == []


def test_json_report_writer_failure_preserves_destination_and_cleans_temp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "report.json"
    target.write_text("old report", encoding="utf-8")

    def fail_replace(source: str | Path, destination: str | Path) -> None:
        raise OSError("replace failed")

    monkeypatch.setattr(
        "tagged_pdf_extractor.infrastructure.json_report_writer.os.replace",
        fail_replace,
    )

    with pytest.raises(OSError, match="replace failed"):
        JsonReportWriter().write(QualityReport("fail", {}, {}, ()), target)

    assert target.read_text(encoding="utf-8") == "old report"
    assert list(tmp_path.glob(".report.json.*.tmp")) == []


def test_refuses_any_existing_required_output_before_writing(tmp_path: Path) -> None:
    output = tmp_path / "result"
    output.mkdir()
    existing = output / "semantic_document.xml"
    existing.write_text("old", encoding="utf-8")
    document = _document(tmp_path)

    with pytest.raises(OutputCollisionError, match="semantic_document.xml"):
        OutputBundleWriter().write(document, _report(document), output)

    assert existing.read_text(encoding="utf-8") == "old"
    assert not (output / "raw_structure.xml").exists()
    assert not (output / "extraction_report.json").exists()
    assert _owned_temporary_paths(tmp_path, "result") == []


def test_absent_output_directory_is_published_as_complete_bundle(tmp_path: Path) -> None:
    document = _document(tmp_path)
    report = _report(document)
    output = tmp_path / "nested" / "result"

    artifacts = OutputBundleWriter().write(document, report, output)

    assert {path.name for path in (artifacts.raw_xml, artifacts.semantic_xml, artifacts.report_json)} == {
        "raw_structure.xml",
        "semantic_document.xml",
        "extraction_report.json",
    }
    assert all(path.parent == output and path.is_file() for path in (
        artifacts.raw_xml,
        artifacts.semantic_xml,
        artifacts.report_json,
    ))
    ET.parse(artifacts.raw_xml)
    ET.parse(artifacts.semantic_xml)
    assert json.loads(artifacts.report_json.read_text(encoding="utf-8"))["status"] == "pass"
    assert _owned_temporary_paths(output.parent, output.name) == []


def test_absent_output_uses_no_replace_rename(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output = tmp_path / "result"
    real_rename = os.rename
    calls: list[tuple[Path, Path]] = []

    def record_rename(source: str | Path, destination: str | Path) -> None:
        calls.append((Path(source), Path(destination)))
        real_rename(source, destination)

    monkeypatch.setattr(output_bundle_module.os, "rename", record_rename)

    document = _document(tmp_path)
    OutputBundleWriter().write(document, _report(document), output)

    assert len(calls) == 1
    assert calls[0][1] == output


def test_concurrent_creation_cannot_replace_initially_absent_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "result"
    competitor_text = "competitor owns this"
    original = OutputBundleWriter._write_and_validate_staging

    def stage_then_compete(
        writer: OutputBundleWriter,
        document: TaggedDocument,
        report: QualityReport,
        staging: Path,
    ) -> None:
        original(writer, document, report, staging)
        output.mkdir()
        (output / "raw_structure.xml").write_text(competitor_text, encoding="utf-8")

    monkeypatch.setattr(OutputBundleWriter, "_write_and_validate_staging", stage_then_compete)
    document = _document(tmp_path)

    with pytest.raises(OutputCollisionError, match="changed during transaction"):
        OutputBundleWriter().write(document, _report(document), output)

    assert (output / "raw_structure.xml").read_text(encoding="utf-8") == competitor_text
    assert _owned_temporary_paths(tmp_path, "result") == []


def test_concurrent_required_file_in_existing_output_is_rechecked_before_publish(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "result"
    output.mkdir()
    unrelated = output / "keep.txt"
    unrelated.write_text("keep", encoding="utf-8")
    original = OutputBundleWriter._write_and_validate_staging

    def stage_then_compete(
        writer: OutputBundleWriter,
        document: TaggedDocument,
        report: QualityReport,
        staging: Path,
    ) -> None:
        original(writer, document, report, staging)
        (output / "semantic_document.xml").write_text("competitor", encoding="utf-8")

    monkeypatch.setattr(OutputBundleWriter, "_write_and_validate_staging", stage_then_compete)
    document = _document(tmp_path)

    with pytest.raises(OutputCollisionError, match="semantic_document.xml"):
        OutputBundleWriter().write(document, _report(document), output, overwrite=False)

    assert (output / "semantic_document.xml").read_text(encoding="utf-8") == "competitor"
    assert unrelated.read_text(encoding="utf-8") == "keep"
    assert _owned_temporary_paths(tmp_path, "result") == []


def test_existing_transaction_lock_is_busy_and_never_deleted(tmp_path: Path) -> None:
    output = tmp_path / "result"
    output.mkdir()
    lock = tmp_path / ".result.lock"
    lock.mkdir()
    marker = lock / "owner.txt"
    marker.write_text("other process", encoding="utf-8")
    document = _document(tmp_path)

    with pytest.raises(OutputBusyError) as captured:
        OutputBundleWriter().write(document, _report(document), output)

    assert captured.value.lock_path == lock.resolve()
    assert marker.read_text(encoding="utf-8") == "other process"


def test_existing_directory_overwrite_preserves_unrelated_files(tmp_path: Path) -> None:
    document = _document(tmp_path)
    report = _report(document)
    output = tmp_path / "result"
    output.mkdir()
    unrelated = output / "reviewer-notes.txt"
    unrelated.write_text("keep me", encoding="utf-8")
    for name in output_bundle_module.REQUIRED_OUTPUT_NAMES:
        (output / name).write_text(f"old {name}", encoding="utf-8")

    OutputBundleWriter().write(document, report, output, overwrite=True)

    assert unrelated.read_text(encoding="utf-8") == "keep me"
    assert ET.parse(output / "raw_structure.xml").getroot().tag == "tagged-document"
    assert ET.parse(output / "semantic_document.xml").getroot().tag == "document"
    assert json.loads((output / "extraction_report.json").read_text(encoding="utf-8"))["status"] == "pass"
    assert _owned_temporary_paths(tmp_path, "result") == []


@pytest.mark.parametrize(
    ("existing_names", "overwrite", "should_succeed"),
    [
        ((), False, True),
        (("raw_structure.xml",), False, False),
        (("extraction_report.json",), True, True),
        (tuple(output_bundle_module.REQUIRED_OUTPUT_NAMES), True, True),
    ],
)
def test_existing_and_missing_required_target_matrix(
    tmp_path: Path,
    existing_names: tuple[str, ...],
    overwrite: bool,
    should_succeed: bool,
) -> None:
    output = tmp_path / "result"
    output.mkdir()
    for name in existing_names:
        (output / name).write_text(f"old::{name}", encoding="utf-8")
    document = _document(tmp_path)

    if should_succeed:
        OutputBundleWriter().write(document, _report(document), output, overwrite)
        assert all((output / name).is_file() for name in output_bundle_module.REQUIRED_OUTPUT_NAMES)
    else:
        with pytest.raises(OutputCollisionError):
            OutputBundleWriter().write(document, _report(document), output, overwrite)
        assert {path.name for path in output.iterdir()} == set(existing_names)
    assert _owned_temporary_paths(tmp_path, "result") == []


@pytest.mark.parametrize("fail_publication_number", [1, 2, 3])
def test_mid_publication_os_replace_failure_restores_complete_previous_bundle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fail_publication_number: int,
) -> None:
    document = _document(tmp_path)
    report = _report(document)
    output = tmp_path / "result"
    output.mkdir()
    old = {}
    for name in output_bundle_module.REQUIRED_OUTPUT_NAMES:
        old[name] = f"old::{name}"
        (output / name).write_text(old[name], encoding="utf-8")
    unrelated = output / "keep.txt"
    unrelated.write_text("safe", encoding="utf-8")
    real_replace = os.replace
    publication_count = 0

    def fail_during_publication(source: str | Path, destination: str | Path) -> None:
        nonlocal publication_count
        source_path = Path(source)
        destination_path = Path(destination)
        if ".staging-" in source_path.parent.name and destination_path.parent == output:
            publication_count += 1
            if publication_count == fail_publication_number:
                raise OSError(f"publication {fail_publication_number} failed")
        real_replace(source, destination)

    monkeypatch.setattr(output_bundle_module.os, "replace", fail_during_publication)

    with pytest.raises(OSError, match=f"publication {fail_publication_number} failed"):
        OutputBundleWriter().write(document, report, output, overwrite=True)

    assert {name: (output / name).read_text(encoding="utf-8") for name in old} == old
    assert unrelated.read_text(encoding="utf-8") == "safe"
    assert _owned_temporary_paths(tmp_path, "result") == []


def test_restore_failure_preserves_backup_and_surfaces_recovery_details(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    document = _document(tmp_path)
    output = tmp_path / "result"
    output.mkdir()
    old = {}
    for name in output_bundle_module.REQUIRED_OUTPUT_NAMES:
        old[name] = f"old::{name}"
        (output / name).write_text(old[name], encoding="utf-8")
    real_replace = os.replace
    publication_failed = False

    def fail_publication_then_restore(source: str | Path, destination: str | Path) -> None:
        nonlocal publication_failed
        source_path = Path(source)
        destination_path = Path(destination)
        if ".staging-" in source_path.parent.name and destination_path.parent == output:
            publication_failed = True
            raise OSError("publication failed")
        if publication_failed and ".backup-" in source_path.parent.name:
            raise OSError("restore failed")
        real_replace(source, destination)

    monkeypatch.setattr(output_bundle_module.os, "replace", fail_publication_then_restore)

    with pytest.raises(BundleRollbackError) as captured:
        OutputBundleWriter().write(document, _report(document), output, overwrite=True)

    error = captured.value
    assert error.backup_path.is_absolute()
    assert str(error.backup_path) in str(error)
    assert set(error.affected_files) == set(output_bundle_module.REQUIRED_OUTPUT_NAMES)
    assert all(
        (error.backup_path / name).read_text(encoding="utf-8") == old[name]
        for name in error.affected_files
    )
    assert list(tmp_path.glob(".result.staging-*")) == []
    assert error.backup_path in list(tmp_path.glob(".result.backup-*"))


def test_primary_publication_and_cleanup_failures_are_both_preserved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "result"
    output.mkdir()
    document = _document(tmp_path)
    real_replace = os.replace

    def fail_publication(source: str | Path, destination: str | Path) -> None:
        source_path = Path(source)
        if ".staging-" in source_path.parent.name and Path(destination).parent == output:
            raise OSError("primary publication failure")
        real_replace(source, destination)

    original_cleanup = OutputBundleWriter._remove_owned_directory

    def fail_staging_cleanup(directory: Path) -> None:
        if ".staging-" in directory.name:
            raise OSError("staging cleanup failure")
        original_cleanup(directory)

    monkeypatch.setattr(output_bundle_module.os, "replace", fail_publication)
    monkeypatch.setattr(OutputBundleWriter, "_remove_owned_directory", staticmethod(fail_staging_cleanup))

    with pytest.raises(BundleTransactionError) as captured:
        OutputBundleWriter().write(document, _report(document), output)

    error = captured.value
    assert isinstance(error.primary_error, OSError)
    assert "primary publication failure" in str(error.primary_error)
    assert any("staging cleanup failure" in str(item) for item in error.cleanup_errors)
    assert error.published is False
    assert any(".staging-" in path.name for path in error.cleanup_paths)


def test_successful_publication_with_cleanup_failure_reports_committed_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "result"
    output.mkdir()
    original_cleanup = OutputBundleWriter._remove_owned_directory

    def fail_staging_cleanup(directory: Path) -> None:
        if ".staging-" in directory.name:
            raise OSError("post-publication cleanup failure")
        original_cleanup(directory)

    monkeypatch.setattr(OutputBundleWriter, "_remove_owned_directory", staticmethod(fail_staging_cleanup))
    document = _document(tmp_path)

    with pytest.raises(BundleTransactionError) as captured:
        OutputBundleWriter().write(document, _report(document), output)

    error = captured.value
    assert error.primary_error is None
    assert error.published is True
    assert error.artifacts is not None
    assert all(
        path.is_file()
        for path in (
            error.artifacts.raw_xml,
            error.artifacts.semantic_xml,
            error.artifacts.report_json,
        )
    )
    assert any(".staging-" in path.name for path in error.cleanup_paths)


def test_failed_publication_into_existing_empty_directory_removes_new_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    document = _document(tmp_path)
    output = tmp_path / "result"
    output.mkdir()
    real_replace = os.replace
    publication_count = 0

    def fail_second_publication(source: str | Path, destination: str | Path) -> None:
        nonlocal publication_count
        source_path = Path(source)
        destination_path = Path(destination)
        if ".staging-" in source_path.parent.name and destination_path.parent == output:
            publication_count += 1
            if publication_count == 2:
                raise OSError("second publication failed")
        real_replace(source, destination)

    monkeypatch.setattr(output_bundle_module.os, "replace", fail_second_publication)

    with pytest.raises(OSError, match="second publication failed"):
        OutputBundleWriter().write(document, _report(document), output)

    assert list(output.iterdir()) == []
    assert _owned_temporary_paths(tmp_path, "result") == []


def test_join_decision_mismatch_fails_before_publication(tmp_path: Path) -> None:
    document = _document(tmp_path)
    report = QualityReport("pass", {}, {"xml_round_trip": True}, (), ())
    output = tmp_path / "result"

    with pytest.raises(ValueError, match="join decisions"):
        OutputBundleWriter().write(document, report, output)

    assert not output.exists()
    assert _owned_temporary_paths(tmp_path, "result") == []


@pytest.mark.parametrize("invalid_kind", ["directory", "symlink"])
def test_preflight_rejects_non_regular_required_targets_before_staging(
    tmp_path: Path, invalid_kind: str
) -> None:
    output = tmp_path / "result"
    output.mkdir()
    invalid = output / "raw_structure.xml"
    if invalid_kind == "directory":
        invalid.mkdir()
    else:
        source = tmp_path / "linked.xml"
        source.write_text("linked", encoding="utf-8")
        try:
            invalid.symlink_to(source)
        except OSError:
            pytest.skip("symlinks unavailable")
    untouched = output / "semantic_document.xml"
    untouched.write_text("old", encoding="utf-8")

    with pytest.raises(OutputCollisionError, match="regular file"):
        OutputBundleWriter().write(_document(tmp_path), _report(_document(tmp_path)), output, overwrite=True)

    assert invalid.exists()
    assert untouched.read_text(encoding="utf-8") == "old"
    assert _owned_temporary_paths(tmp_path, "result") == []


def test_destination_parent_creation_failure_leaves_no_staging_or_outputs(
    tmp_path: Path,
) -> None:
    parent_file = tmp_path / "not-a-directory"
    parent_file.write_text("occupied", encoding="utf-8")
    output = parent_file / "result"
    document = _document(tmp_path)

    with pytest.raises((FileExistsError, NotADirectoryError, OSError)):
        OutputBundleWriter().write(document, _report(document), output)

    assert parent_file.read_text(encoding="utf-8") == "occupied"
    assert not output.exists()
    assert _owned_temporary_paths(tmp_path, "result") == []


def test_output_path_that_is_a_file_is_rejected_before_staging(tmp_path: Path) -> None:
    output = tmp_path / "result"
    output.write_text("not a directory", encoding="utf-8")

    with pytest.raises(NotADirectoryError, match="not a directory"):
        OutputBundleWriter().write(
            _document(tmp_path), _report(_document(tmp_path)), output, overwrite=True
        )

    assert output.read_text(encoding="utf-8") == "not a directory"
    assert _owned_temporary_paths(tmp_path, "result") == []


def test_extract_document_validates_source_and_wires_dependencies(tmp_path: Path) -> None:
    calls: list[tuple[str, object]] = []
    document = _document(tmp_path)
    report = _report(document)
    artifacts = object()

    class Reader:
        def read(self, path: Path) -> TaggedDocument:
            calls.append(("reader", path))
            return document

    class Baseline:
        def read_text(self, path: Path) -> str:
            calls.append(("baseline", path))
            return "baseline"

    class Evaluator:
        def evaluate(self, actual_document: TaggedDocument, baseline: str, xml_round_trip_ok: bool) -> QualityReport:
            calls.append(("evaluator", (actual_document, baseline, xml_round_trip_ok)))
            return report

    class Writer:
        def validate(self, actual_document: TaggedDocument) -> OutputValidation:
            calls.append(("validate", actual_document))
            return OutputValidation(report.join_decisions)

        def write(self, actual_document: TaggedDocument, actual_report: QualityReport, output: Path, overwrite: bool = False) -> object:
            calls.append(("writer", (actual_document, actual_report, output, overwrite)))
            return artifacts

    source = tmp_path / "source.pdf"
    source.write_bytes(b"pdf")
    output = tmp_path / "out"
    use_case = ExtractDocument(Reader(), Baseline(), Evaluator(), Writer())

    assert use_case.run(source, output, overwrite=True) == (document, report, artifacts)
    assert [name for name, _ in calls] == ["reader", "baseline", "validate", "evaluator", "writer"]
    assert calls[3][1] == (document, "baseline", True)

    missing = tmp_path / "missing.pdf"
    with pytest.raises(FileNotFoundError, match="missing.pdf"):
        use_case.run(missing, output)
    directory = tmp_path / "directory.pdf"
    directory.mkdir()
    with pytest.raises(IsADirectoryError, match="directory.pdf"):
        use_case.run(directory, output)
    assert [name for name, _ in calls] == ["reader", "baseline", "validate", "evaluator", "writer"]


def test_extract_document_validation_failure_prevents_evaluation_and_write(
    tmp_path: Path,
) -> None:
    calls: list[str] = []
    document = _document(tmp_path)

    class Reader:
        def read(self, path: Path) -> TaggedDocument:
            calls.append("reader")
            return document

    class Baseline:
        def read_text(self, path: Path) -> str:
            calls.append("baseline")
            return "baseline"

    class Evaluator:
        def evaluate(self, *args: object, **kwargs: object) -> QualityReport:
            calls.append("evaluator")
            raise AssertionError("must not evaluate")

    class Writer:
        def validate(self, actual_document: TaggedDocument) -> OutputValidation:
            calls.append("validate")
            raise ValueError("XML proof failed")

        def write(self, *args: object, **kwargs: object) -> object:
            calls.append("writer")
            raise AssertionError("must not write")

    source = tmp_path / "source.pdf"
    source.write_bytes(b"pdf")

    with pytest.raises(ValueError, match="XML proof failed"):
        ExtractDocument(Reader(), Baseline(), Evaluator(), Writer()).run(
            source, tmp_path / "out"
        )

    assert calls == ["reader", "baseline", "validate"]
    assert not (tmp_path / "out").exists()


def test_extract_document_rejects_writer_without_validation_contract(
    tmp_path: Path,
) -> None:
    document = _document(tmp_path)

    class Reader:
        def read(self, path: Path) -> TaggedDocument:
            return document

    class Baseline:
        def read_text(self, path: Path) -> str:
            return "baseline"

    class Evaluator:
        def evaluate(self, *args: object, **kwargs: object) -> QualityReport:
            raise AssertionError("must not evaluate")

    class WriterWithoutValidation:
        def write(self, *args: object, **kwargs: object) -> object:
            raise AssertionError("must not write")

    source = tmp_path / "source.pdf"
    source.write_bytes(b"pdf")

    with pytest.raises(AttributeError, match="validate"):
        ExtractDocument(
            Reader(), Baseline(), Evaluator(), WriterWithoutValidation()
        ).run(source, tmp_path / "out")

    assert not (tmp_path / "out").exists()
