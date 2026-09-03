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
    BundlePublicationErrorGroup,
    BundlePublicationStateBaseExceptionGroup,
    BundleRollbackBaseExceptionGroup,
    BundleRollbackError,
    BundleTransactionBaseExceptionGroup,
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
    ) + list(parent.glob(f".{output_name}.lock-candidate-*"))
    lock = parent / f".{output_name}.lock"
    return paths + ([lock] if lock.exists() else [])


def test_required_output_names_are_the_four_atomic_artifacts() -> None:
    assert output_bundle_module.REQUIRED_OUTPUT_NAMES == (
        "raw_structure.xml",
        "semantic_document.xml",
        "extraction_report.json",
        "semantic_document.md",
    )


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
        "source_path",
        "language",
        "marked",
        "role_map",
        "source_role_counts",
        "heading_hierarchy",
    ]
    assert parsed["metrics"]["path"] == str(Path("근거/화면.png"))
    assert parsed["diagnostics"][0]["context"] == {"page": 3}


def test_json_report_writer_serializes_audit_metadata_exactly(tmp_path: Path) -> None:
    report = QualityReport(
        "fail", {}, {}, (), (),
        source_path=Path("manual.pdf"),
        language=None,
        marked=True,
        role_map=(("Heading2", "P"),),
        source_role_counts={"Heading2": 2},
        heading_hierarchy=({"structure_path": "/paragraph[0]"},),
    )
    target = tmp_path / "report.json"

    JsonReportWriter().write(report, target)

    parsed = json.loads(target.read_text(encoding="utf-8"))
    assert parsed["source_path"] == "manual.pdf"
    assert parsed["language"] is None
    assert parsed["marked"] is True
    assert parsed["role_map"] == [["Heading2", "P"]]
    assert parsed["source_role_counts"] == {"Heading2": 2}
    assert parsed["heading_hierarchy"] == [
        {"structure_path": "/paragraph[0]"}
    ]


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


def test_refuses_existing_markdown_without_overwrite(tmp_path: Path) -> None:
    output = tmp_path / "result"
    output.mkdir()
    existing = output / "semantic_document.md"
    existing.write_text("old markdown", encoding="utf-8")
    document = _document(tmp_path)

    with pytest.raises(OutputCollisionError, match="semantic_document.md"):
        OutputBundleWriter().write(document, _report(document), output)

    assert existing.read_text(encoding="utf-8") == "old markdown"
    assert _owned_temporary_paths(tmp_path, "result") == []


def test_absent_output_directory_is_published_as_complete_bundle(tmp_path: Path) -> None:
    document = _document(tmp_path)
    report = _report(document)
    output = tmp_path / "nested" / "result"

    artifacts = OutputBundleWriter().write(document, report, output)

    assert {
        path.name
        for path in (
            artifacts.raw_xml,
            artifacts.semantic_xml,
            artifacts.report_json,
            artifacts.semantic_markdown,
        )
    } == {
        "raw_structure.xml",
        "semantic_document.xml",
        "extraction_report.json",
        "semantic_document.md",
    }
    assert all(path.parent == output and path.is_file() for path in (
        artifacts.raw_xml,
        artifacts.semantic_xml,
        artifacts.report_json,
        artifacts.semantic_markdown,
    ))
    ET.parse(artifacts.raw_xml)
    ET.parse(artifacts.semantic_xml)
    assert json.loads(artifacts.report_json.read_text(encoding="utf-8"))["status"] == "pass"
    assert artifacts.semantic_markdown.read_text(encoding="utf-8").strip()
    assert _owned_temporary_paths(output.parent, output.name) == []


def test_existing_markdown_is_replaced_with_overwrite(tmp_path: Path) -> None:
    output = tmp_path / "result"
    output.mkdir()
    markdown = output / "semantic_document.md"
    markdown.write_text("old markdown", encoding="utf-8")
    document = _document(tmp_path)

    artifacts = OutputBundleWriter().write(
        document, _report(document), output, overwrite=True
    )

    assert artifacts.semantic_markdown == markdown
    assert markdown.read_text(encoding="utf-8") != "old markdown"
    assert markdown.read_text(encoding="utf-8").strip()
    assert _owned_temporary_paths(tmp_path, "result") == []


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

    publication_calls = [call for call in calls if call[1] == output]
    assert len(publication_calls) == 1


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


def test_keyboard_interrupt_after_candidate_mkdir_cleans_owned_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "result"
    output.mkdir()
    original = OutputBundleWriter._create_lock_candidate

    def create_then_interrupt(path: Path) -> None:
        original(path)
        raise KeyboardInterrupt("candidate mkdir interrupted")

    monkeypatch.setattr(
        OutputBundleWriter,
        "_create_lock_candidate",
        staticmethod(create_then_interrupt),
    )
    document = _document(tmp_path)

    with pytest.raises(KeyboardInterrupt, match="candidate mkdir interrupted"):
        OutputBundleWriter().write(document, _report(document), output)

    assert not (tmp_path / ".result.lock").exists()
    assert _owned_temporary_paths(tmp_path, "result") == []


def test_keyboard_interrupt_after_lock_marker_write_cleans_owned_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "result"
    output.mkdir()
    original = OutputBundleWriter._write_lock_owner_marker

    def write_then_interrupt(path: Path, token: str) -> None:
        original(path, token)
        raise KeyboardInterrupt("marker write interrupted")

    monkeypatch.setattr(
        OutputBundleWriter,
        "_write_lock_owner_marker",
        staticmethod(write_then_interrupt),
    )
    document = _document(tmp_path)

    with pytest.raises(KeyboardInterrupt, match="marker write interrupted"):
        OutputBundleWriter().write(document, _report(document), output)

    assert not (tmp_path / ".result.lock").exists()
    assert _owned_temporary_paths(tmp_path, "result") == []


def test_keyboard_interrupt_after_lock_rename_cleans_owned_final_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "result"
    output.mkdir()
    real_rename = os.rename

    def rename_then_interrupt(source: str | Path, destination: str | Path) -> None:
        real_rename(source, destination)
        if Path(destination) == tmp_path / ".result.lock":
            raise KeyboardInterrupt("lock rename interrupted")

    monkeypatch.setattr(output_bundle_module.os, "rename", rename_then_interrupt)
    document = _document(tmp_path)

    with pytest.raises(KeyboardInterrupt, match="lock rename interrupted"):
        OutputBundleWriter().write(document, _report(document), output)

    assert not (tmp_path / ".result.lock").exists()
    assert _owned_temporary_paths(tmp_path, "result") == []


def test_keyboard_interrupt_after_acquire_lock_returns_cleans_owned_final_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "result"
    output.mkdir()
    original = OutputBundleWriter._acquire_lock

    def acquire_then_interrupt(
        candidate_path: Path, lock_path: Path, transaction_token: str
    ) -> None:
        original(candidate_path, lock_path, transaction_token)
        raise KeyboardInterrupt("after acquire return")

    monkeypatch.setattr(
        OutputBundleWriter,
        "_acquire_lock",
        staticmethod(acquire_then_interrupt),
    )
    document = _document(tmp_path)

    with pytest.raises(KeyboardInterrupt, match="after acquire return"):
        OutputBundleWriter().write(document, _report(document), output)

    assert not (tmp_path / ".result.lock").exists()
    assert _owned_temporary_paths(tmp_path, "result") == []


def test_interrupt_after_acquire_does_not_remove_foreign_token_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "result"
    output.mkdir()
    lock = tmp_path / ".result.lock"
    original = OutputBundleWriter._acquire_lock

    def acquire_change_owner_then_interrupt(
        candidate_path: Path, lock_path: Path, transaction_token: str
    ) -> None:
        original(candidate_path, lock_path, transaction_token)
        (lock_path / ".owner-token").write_text(
            "foreign-token\n", encoding="ascii"
        )
        raise KeyboardInterrupt("after foreign takeover")

    monkeypatch.setattr(
        OutputBundleWriter,
        "_acquire_lock",
        staticmethod(acquire_change_owner_then_interrupt),
    )
    document = _document(tmp_path)

    with pytest.raises(KeyboardInterrupt, match="after foreign takeover"):
        OutputBundleWriter().write(document, _report(document), output)

    assert (lock / ".owner-token").read_text(encoding="ascii") == "foreign-token\n"
    assert list(tmp_path.glob(".result.lock-candidate-*")) == []


def test_competing_owned_lock_remains_and_own_candidate_is_cleaned(
    tmp_path: Path,
) -> None:
    output = tmp_path / "result"
    output.mkdir()
    lock = tmp_path / ".result.lock"
    lock.mkdir()
    owner_marker = lock / ".owner-token"
    owner_marker.write_text("competitor-token\n", encoding="ascii")
    document = _document(tmp_path)

    with pytest.raises(OutputBusyError):
        OutputBundleWriter().write(document, _report(document), output)

    assert owner_marker.read_text(encoding="ascii") == "competitor-token\n"
    assert list(tmp_path.glob(".result.lock-candidate-*")) == []


def test_normal_cleanup_refuses_to_remove_lock_with_changed_owner_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "result"
    output.mkdir()
    original = OutputBundleWriter._write_and_validate_staging
    lock = tmp_path / ".result.lock"

    def stage_then_change_lock_owner(
        writer: OutputBundleWriter,
        document: TaggedDocument,
        report: QualityReport,
        staging: Path,
    ) -> None:
        original(writer, document, report, staging)
        (lock / ".owner-token").write_text("competitor-token\n", encoding="ascii")

    monkeypatch.setattr(
        OutputBundleWriter,
        "_write_and_validate_staging",
        stage_then_change_lock_owner,
    )
    document = _document(tmp_path)

    with pytest.raises(BundleTransactionError) as captured:
        OutputBundleWriter().write(document, _report(document), output)

    assert captured.value.published is True
    assert any("ownership changed" in str(error) for error in captured.value.cleanup_errors)
    assert (lock / ".owner-token").read_text(encoding="ascii") == "competitor-token\n"


def test_system_exit_during_final_preflight_cleans_only_owned_lock_and_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "result"
    output.mkdir()
    original = OutputBundleWriter._preflight_required_targets
    calls = 0

    def exit_final_preflight(output_dir: Path, overwrite: bool) -> tuple[Path, ...]:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise SystemExit(23)
        return original(output_dir, overwrite)

    monkeypatch.setattr(
        OutputBundleWriter,
        "_preflight_required_targets",
        staticmethod(exit_final_preflight),
    )
    document = _document(tmp_path)

    with pytest.raises(SystemExit) as captured:
        OutputBundleWriter().write(document, _report(document), output)

    assert captured.value.code == 23
    assert list(output.iterdir()) == []
    assert _owned_temporary_paths(tmp_path, "result") == []


def test_competitor_markdown_after_final_preflight_is_not_overwritten(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "result"
    output.mkdir()
    competitor = output / output_bundle_module.MARKDOWN_NAME
    original = OutputBundleWriter._preflight_required_targets
    calls = 0

    def final_preflight_then_compete(
        output_dir: Path, overwrite: bool
    ) -> tuple[Path, ...]:
        nonlocal calls
        existing = original(output_dir, overwrite)
        calls += 1
        if calls == 2:
            competitor.write_text("competitor markdown", encoding="utf-8")
        return existing

    monkeypatch.setattr(
        OutputBundleWriter,
        "_preflight_required_targets",
        staticmethod(final_preflight_then_compete),
    )
    monkeypatch.setattr(output_bundle_module.os, "rename", os.replace)
    document = _document(tmp_path)

    with pytest.raises(OutputCollisionError, match="semantic_document.md"):
        OutputBundleWriter().write(document, _report(document), output)

    assert competitor.read_text(encoding="utf-8") == "competitor markdown"
    assert {path.name for path in output.iterdir()} == {
        output_bundle_module.MARKDOWN_NAME
    }
    assert _owned_temporary_paths(tmp_path, "result") == []


def test_keyboard_interrupt_after_no_replace_link_removes_owned_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "result"
    output.mkdir()
    real_link = os.link

    def interrupt_after_link(source: str | Path, destination: str | Path) -> None:
        real_link(source, destination)
        raise KeyboardInterrupt("link completed then interrupted")

    monkeypatch.setattr(output_bundle_module.os, "link", interrupt_after_link)
    document = _document(tmp_path)

    with pytest.raises(KeyboardInterrupt, match="link completed then interrupted"):
        OutputBundleWriter().write(document, _report(document), output)

    assert list(output.iterdir()) == []
    assert _owned_temporary_paths(tmp_path, "result") == []


def test_system_exit_after_no_replace_source_unlink_removes_owned_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "result"
    output.mkdir()
    real_unlink = Path.unlink
    interrupted = False

    def interrupt_after_source_unlink(
        path: Path, missing_ok: bool = False
    ) -> None:
        nonlocal interrupted
        existed_before = path.exists()
        real_unlink(path, missing_ok=missing_ok)
        if not interrupted and existed_before and ".staging-" in path.parent.name:
            interrupted = True
            raise SystemExit("source unlink completed then interrupted")

    monkeypatch.setattr(Path, "unlink", interrupt_after_source_unlink)
    document = _document(tmp_path)

    with pytest.raises(SystemExit, match="source unlink completed then interrupted"):
        OutputBundleWriter().write(document, _report(document), output)

    assert list(output.iterdir()) == []
    assert _owned_temporary_paths(tmp_path, "result") == []


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


@pytest.mark.parametrize("fail_publication_number", [1, 2, 3, 4])
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


@pytest.mark.parametrize("fail_publication_number", [1, 2, 3, 4])
def test_keyboard_interrupt_during_publication_restores_all_old_files_and_reraises(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fail_publication_number: int,
) -> None:
    document = _document(tmp_path)
    output = tmp_path / "result"
    output.mkdir()
    old = {}
    for name in output_bundle_module.REQUIRED_OUTPUT_NAMES:
        old[name] = f"old::{name}"
        (output / name).write_text(old[name], encoding="utf-8")
    real_replace = os.replace
    publication_count = 0

    def interrupt_publication(source: str | Path, destination: str | Path) -> None:
        nonlocal publication_count
        source_path = Path(source)
        destination_path = Path(destination)
        if ".staging-" in source_path.parent.name and destination_path.parent == output:
            publication_count += 1
            if publication_count == fail_publication_number:
                raise KeyboardInterrupt(f"publication {fail_publication_number} interrupted")
        real_replace(source, destination)

    monkeypatch.setattr(output_bundle_module.os, "replace", interrupt_publication)

    with pytest.raises(KeyboardInterrupt, match=f"publication {fail_publication_number} interrupted"):
        OutputBundleWriter().write(document, _report(document), output, overwrite=True)

    assert {name: (output / name).read_text(encoding="utf-8") for name in old} == old
    assert _owned_temporary_paths(tmp_path, "result") == []


def test_keyboard_interrupt_after_backup_replace_restores_old_bundle(
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
    interrupted = False

    def interrupt_after_backup_replace(
        source: str | Path, destination: str | Path
    ) -> None:
        nonlocal interrupted
        source_path = Path(source)
        destination_path = Path(destination)
        real_replace(source, destination)
        if (
            not interrupted
            and source_path == output / output_bundle_module.RAW_XML_NAME
            and ".backup-" in destination_path.parent.name
        ):
            interrupted = True
            raise KeyboardInterrupt("backup move completed then interrupted")

    monkeypatch.setattr(
        output_bundle_module.os, "replace", interrupt_after_backup_replace
    )

    with pytest.raises(
        KeyboardInterrupt, match="backup move completed then interrupted"
    ):
        OutputBundleWriter().write(
            document, _report(document), output, overwrite=True
        )

    assert {
        name: (output / name).read_text(encoding="utf-8") for name in old
    } == old
    assert _owned_temporary_paths(tmp_path, "result") == []


def test_system_exit_after_fourth_publication_restores_legacy_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    document = _document(tmp_path)
    output = tmp_path / "result"
    output.mkdir()
    legacy_names = output_bundle_module.REQUIRED_OUTPUT_NAMES[:3]
    old = {}
    for name in legacy_names:
        old[name] = f"old::{name}"
        (output / name).write_text(old[name], encoding="utf-8")
    real_replace = os.replace

    def interrupt_after_markdown_publication(
        source: str | Path, destination: str | Path
    ) -> None:
        source_path = Path(source)
        destination_path = Path(destination)
        real_replace(source, destination)
        if (
            source_path.parent.name.startswith(".result.staging-")
            and destination_path == output / output_bundle_module.MARKDOWN_NAME
        ):
            raise SystemExit("Markdown move completed then interrupted")

    monkeypatch.setattr(
        output_bundle_module.os, "replace", interrupt_after_markdown_publication
    )

    with pytest.raises(SystemExit, match="Markdown move completed then interrupted"):
        OutputBundleWriter().write(
            document, _report(document), output, overwrite=True
        )

    assert {
        name: (output / name).read_text(encoding="utf-8")
        for name in legacy_names
    } == old
    assert not (output / output_bundle_module.MARKDOWN_NAME).exists()
    assert _owned_temporary_paths(tmp_path, "result") == []


def test_keyboard_interrupt_and_restore_failure_preserve_backup_in_base_group(
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
    publication_interrupted = False

    def interrupt_then_fail_restore(source: str | Path, destination: str | Path) -> None:
        nonlocal publication_interrupted
        source_path = Path(source)
        destination_path = Path(destination)
        if ".staging-" in source_path.parent.name and destination_path.parent == output:
            publication_interrupted = True
            raise KeyboardInterrupt("publication interrupted")
        if publication_interrupted and ".backup-" in source_path.parent.name:
            raise OSError("restore failed")
        real_replace(source, destination)

    monkeypatch.setattr(output_bundle_module.os, "replace", interrupt_then_fail_restore)

    with pytest.raises(BundleRollbackBaseExceptionGroup) as captured:
        OutputBundleWriter().write(document, _report(document), output, overwrite=True)

    error = captured.value
    assert isinstance(error.publication_error, KeyboardInterrupt)
    assert any(isinstance(item, KeyboardInterrupt) for item in error.exceptions)
    assert any("restore failed" in str(item) for item in error.exceptions)
    assert error.backup_path.is_absolute()
    assert set(error.affected_files) == set(output_bundle_module.REQUIRED_OUTPUT_NAMES)
    assert all(
        (error.backup_path / name).read_text(encoding="utf-8") == old[name]
        for name in error.affected_files
    )
    assert error.backup_path.exists()


def test_ordinary_publication_and_removal_failures_use_typed_exception_group(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    staging = tmp_path / "staging"
    backup = tmp_path / "backup"
    output = tmp_path / "output"
    staging.mkdir()
    backup.mkdir()
    output.mkdir()
    for name in output_bundle_module.REQUIRED_OUTPUT_NAMES:
        (staging / name).write_text(name, encoding="utf-8")

    real_replace = os.replace
    real_unlink = Path.unlink
    publication_count = 0

    def fail_second_publication(source: str | Path, destination: str | Path) -> None:
        nonlocal publication_count
        if Path(source).parent == staging and Path(destination).parent == output:
            publication_count += 1
            if publication_count == 2:
                raise OSError("publication failed")
        real_replace(source, destination)

    def fail_published_file_removal(
        path: Path, missing_ok: bool = False
    ) -> None:
        if path == output / output_bundle_module.RAW_XML_NAME:
            raise RuntimeError("published file removal failed")
        real_unlink(path, missing_ok=missing_ok)

    monkeypatch.setattr(output_bundle_module.os, "replace", fail_second_publication)
    monkeypatch.setattr(Path, "unlink", fail_published_file_removal)

    with pytest.raises(BundlePublicationErrorGroup) as captured:
        OutputBundleWriter._publish_into_existing(staging, backup, output)

    error = captured.value
    assert any("publication failed" in str(item) for item in error.exceptions)
    assert any("published file removal failed" in str(item) for item in error.exceptions)
    assert getattr(error, "_tagged_pdf_rollback_complete") is True
    os_errors = error.subgroup(OSError)
    assert isinstance(os_errors, BundlePublicationErrorGroup)


def test_system_exit_during_publication_restores_old_files_and_reraises(
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

    def exit_during_publication(source: str | Path, destination: str | Path) -> None:
        source_path = Path(source)
        if ".staging-" in source_path.parent.name and Path(destination).parent == output:
            raise SystemExit(17)
        real_replace(source, destination)

    monkeypatch.setattr(output_bundle_module.os, "replace", exit_during_publication)

    with pytest.raises(SystemExit) as captured:
        OutputBundleWriter().write(document, _report(document), output, overwrite=True)

    assert captured.value.code == 17
    assert {name: (output / name).read_text(encoding="utf-8") for name in old} == old
    assert _owned_temporary_paths(tmp_path, "result") == []


def test_existing_publish_commits_then_wrapper_interrupt_reports_published_and_backup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "result"
    output.mkdir()
    old = {}
    for name in output_bundle_module.REQUIRED_OUTPUT_NAMES:
        old[name] = f"old::{name}"
        (output / name).write_text(old[name], encoding="utf-8")
    original = OutputBundleWriter._publish_into_existing

    def publish_then_interrupt(staging: Path, backup: Path, output_dir: Path) -> None:
        original(staging, backup, output_dir)
        raise KeyboardInterrupt("after existing commit")

    monkeypatch.setattr(
        OutputBundleWriter,
        "_publish_into_existing",
        staticmethod(publish_then_interrupt),
    )
    document = _document(tmp_path)

    with pytest.raises(BundlePublicationStateBaseExceptionGroup) as captured:
        OutputBundleWriter().write(document, _report(document), output, overwrite=True)

    error = captured.value
    assert error.state == "published"
    assert error.published is True
    assert error.artifacts is not None
    assert all(path.is_file() for path in (
        error.artifacts.raw_xml,
        error.artifacts.semantic_xml,
        error.artifacts.report_json,
        error.artifacts.semantic_markdown,
    ))
    assert error.backup_path is not None and error.backup_path.exists()
    assert all(
        (error.backup_path / name).read_text(encoding="utf-8") == old[name]
        for name in output_bundle_module.REQUIRED_OUTPUT_NAMES
    )
    assert any(isinstance(item, KeyboardInterrupt) for item in error.exceptions)
    assert not (tmp_path / ".result.lock").exists()


def test_absent_rename_commits_then_wrapper_interrupt_reports_published(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "result"
    real_rename = os.rename

    def rename_then_interrupt(source: str | Path, destination: str | Path) -> None:
        real_rename(source, destination)
        if Path(destination) == output:
            raise KeyboardInterrupt("after directory commit")

    monkeypatch.setattr(output_bundle_module.os, "rename", rename_then_interrupt)
    document = _document(tmp_path)

    with pytest.raises(BundlePublicationStateBaseExceptionGroup) as captured:
        OutputBundleWriter().write(document, _report(document), output)

    error = captured.value
    assert error.state == "published"
    assert error.published is True
    assert error.backup_path is None
    assert error.artifacts is not None
    assert all(path.is_file() for path in (
        error.artifacts.raw_xml,
        error.artifacts.semantic_xml,
        error.artifacts.report_json,
        error.artifacts.semantic_markdown,
    ))
    assert any(isinstance(item, KeyboardInterrupt) for item in error.exceptions)
    assert _owned_temporary_paths(tmp_path, "result") == []


def test_failed_publication_inference_reports_unknown_and_preserves_recovery_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "result"
    output.mkdir()
    for name in output_bundle_module.REQUIRED_OUTPUT_NAMES:
        (output / name).write_text(f"old::{name}", encoding="utf-8")
    original = OutputBundleWriter._publish_into_existing

    def publish_then_interrupt(staging: Path, backup: Path, output_dir: Path) -> None:
        original(staging, backup, output_dir)
        raise KeyboardInterrupt("after commit")

    def fail_inference(*args: object, **kwargs: object) -> str:
        raise OSError("fingerprint inference failed")

    monkeypatch.setattr(
        OutputBundleWriter,
        "_publish_into_existing",
        staticmethod(publish_then_interrupt),
    )
    monkeypatch.setattr(
        OutputBundleWriter,
        "_infer_publication_state",
        staticmethod(fail_inference),
    )
    document = _document(tmp_path)

    with pytest.raises(BundlePublicationStateBaseExceptionGroup) as captured:
        OutputBundleWriter().write(document, _report(document), output, overwrite=True)

    error = captured.value
    assert error.state == "unknown"
    assert error.published is False
    assert error.backup_path is not None and error.backup_path.exists()
    assert error.staging_path is not None and error.staging_path.exists()
    assert any(isinstance(item, KeyboardInterrupt) for item in error.exceptions)
    assert any("fingerprint inference failed" in str(item) for item in error.exceptions)
    assert not (tmp_path / ".result.lock").exists()


def test_identical_old_files_after_rollback_are_not_misclassified_as_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    document = _document(tmp_path)
    report = _report(document)
    reference = tmp_path / "reference"
    OutputBundleWriter().write(document, report, reference)
    output = tmp_path / "result"
    output.mkdir()
    old = {}
    for name in output_bundle_module.REQUIRED_OUTPUT_NAMES:
        old[name] = (reference / name).read_bytes()
        (output / name).write_bytes(old[name])
    real_replace = os.replace
    publication_count = 0

    def interrupt_after_third_move(source: str | Path, destination: str | Path) -> None:
        nonlocal publication_count
        source_path = Path(source)
        destination_path = Path(destination)
        if ".staging-" in source_path.parent.name and destination_path.parent == output:
            publication_count += 1
            if publication_count == 3:
                real_replace(source, destination)
                raise KeyboardInterrupt("third move completed then interrupted")
        real_replace(source, destination)

    monkeypatch.setattr(output_bundle_module.os, "replace", interrupt_after_third_move)

    with pytest.raises(KeyboardInterrupt, match="third move completed then interrupted"):
        OutputBundleWriter().write(document, report, output, overwrite=True)

    assert {name: (output / name).read_bytes() for name in old} == old
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
    real_link = os.link

    def fail_publication(source: str | Path, destination: str | Path) -> None:
        source_path = Path(source)
        if ".staging-" in source_path.parent.name and Path(destination).parent == output:
            raise OSError("primary publication failure")
        real_link(source, destination)

    original_cleanup = OutputBundleWriter._remove_owned_directory

    def fail_staging_cleanup(directory: Path) -> None:
        if ".staging-" in directory.name:
            raise OSError("staging cleanup failure")
        original_cleanup(directory)

    monkeypatch.setattr(output_bundle_module.os, "link", fail_publication)
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
            error.artifacts.semantic_markdown,
        )
    )
    assert any(".staging-" in path.name for path in error.cleanup_paths)


def test_primary_oserror_and_cleanup_keyboard_interrupt_are_both_visible(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "result"
    output.mkdir()
    document = _document(tmp_path)
    real_link = os.link

    def fail_publication(source: str | Path, destination: str | Path) -> None:
        source_path = Path(source)
        if ".staging-" in source_path.parent.name and Path(destination).parent == output:
            raise OSError("primary publication failure")
        real_link(source, destination)

    original_cleanup = OutputBundleWriter._remove_owned_directory

    def interrupt_staging_cleanup(directory: Path) -> None:
        if ".staging-" in directory.name:
            raise KeyboardInterrupt("cleanup interrupted")
        original_cleanup(directory)

    monkeypatch.setattr(output_bundle_module.os, "link", fail_publication)
    monkeypatch.setattr(
        OutputBundleWriter,
        "_remove_owned_directory",
        staticmethod(interrupt_staging_cleanup),
    )

    with pytest.raises(BundleTransactionBaseExceptionGroup) as captured:
        OutputBundleWriter().write(document, _report(document), output)

    error = captured.value
    assert isinstance(error.primary_error, OSError)
    assert "primary publication failure" in str(error.primary_error)
    assert any(isinstance(item, KeyboardInterrupt) for item in error.cleanup_errors)
    assert any(isinstance(item, KeyboardInterrupt) for item in error.exceptions)
    assert error.published is False
    assert all(path.exists() for path in error.cleanup_paths)


def test_published_success_then_cleanup_keyboard_interrupt_exposes_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "result"
    output.mkdir()
    original_cleanup = OutputBundleWriter._remove_owned_directory

    def interrupt_staging_cleanup(directory: Path) -> None:
        if ".staging-" in directory.name:
            raise KeyboardInterrupt("post-publication cleanup interrupted")
        original_cleanup(directory)

    monkeypatch.setattr(
        OutputBundleWriter,
        "_remove_owned_directory",
        staticmethod(interrupt_staging_cleanup),
    )
    document = _document(tmp_path)

    with pytest.raises(BundleTransactionBaseExceptionGroup) as captured:
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
            error.artifacts.semantic_markdown,
        )
    )
    assert any(isinstance(item, KeyboardInterrupt) for item in error.cleanup_errors)
    assert all(path.exists() for path in error.cleanup_paths)


def test_failed_publication_into_existing_empty_directory_removes_new_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    document = _document(tmp_path)
    output = tmp_path / "result"
    output.mkdir()
    real_link = os.link
    publication_count = 0

    def fail_second_publication(source: str | Path, destination: str | Path) -> None:
        nonlocal publication_count
        source_path = Path(source)
        destination_path = Path(destination)
        if ".staging-" in source_path.parent.name and destination_path.parent == output:
            publication_count += 1
            if publication_count == 2:
                raise OSError("second publication failed")
        real_link(source, destination)

    monkeypatch.setattr(output_bundle_module.os, "link", fail_second_publication)

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


def test_invalid_xml_prevents_report_and_markdown_writers(
    tmp_path: Path,
) -> None:
    calls: list[str] = []

    class InvalidXmlWriter:
        def write_raw(self, document: TaggedDocument, output: Path) -> None:
            output.write_text("<invalid", encoding="utf-8")

        def write_semantic(
            self, document: TaggedDocument, output: Path
        ) -> tuple[dict[str, object], ...]:
            output.write_text("<document />", encoding="utf-8")
            return ()

    class RecordingJsonWriter:
        delegate = JsonReportWriter()

        def write(self, report: QualityReport, output: Path) -> None:
            calls.append("json")
            self.delegate.write(report, output)

        def to_data(self, report: QualityReport) -> dict[str, object]:
            return self.delegate.to_data(report)

    class RecordingMarkdownWriter:
        def write(self, *args: object, **kwargs: object) -> None:
            calls.append("markdown")

    document = _document(tmp_path)
    report = QualityReport("pass", {}, {"xml_round_trip": True}, (), ())
    output = tmp_path / "result"

    with pytest.raises(ET.ParseError):
        OutputBundleWriter(
            xml_writer=InvalidXmlWriter(),
            json_writer=RecordingJsonWriter(),
            markdown_writer=RecordingMarkdownWriter(),
        ).write(document, report, output)

    assert calls == []
    assert not output.exists()
    assert _owned_temporary_paths(tmp_path, "result") == []


def test_injected_markdown_writer_receives_semantic_xml_report_and_source_name(
    tmp_path: Path,
) -> None:
    calls: list[tuple[Path, QualityReport, Path, str]] = []

    class RecordingMarkdownWriter:
        def write(
            self,
            semantic_xml: Path,
            report: QualityReport,
            output: Path,
            *,
            source_name: str,
        ) -> None:
            assert ET.parse(semantic_xml).getroot().tag == "document"
            calls.append((semantic_xml, report, output, source_name))
            output.write_text("# custom markdown\n", encoding="utf-8")

    document = _document(tmp_path)
    report = _report(document)
    output = tmp_path / "result"

    artifacts = OutputBundleWriter(
        markdown_writer=RecordingMarkdownWriter()
    ).write(document, report, output)

    assert len(calls) == 1
    assert calls[0][1] is report
    assert calls[0][3] == document.source_path.name
    assert (
        artifacts.semantic_markdown.read_text(encoding="utf-8")
        == "# custom markdown\n"
    )


def test_markdown_writer_failure_before_publication_leaves_outputs_safe(
    tmp_path: Path,
) -> None:
    class FailingMarkdownWriter:
        def write(self, *args: object, **kwargs: object) -> None:
            raise OSError("markdown write failed")

    document = _document(tmp_path)
    output = tmp_path / "result"

    with pytest.raises(OSError, match="markdown write failed"):
        OutputBundleWriter(markdown_writer=FailingMarkdownWriter()).write(
            document, _report(document), output
        )

    assert not output.exists()
    assert _owned_temporary_paths(tmp_path, "result") == []


def test_markdown_validation_counts_duplicate_candidate_entries_by_heading_line(
    tmp_path: Path,
) -> None:
    document = TaggedDocument(
        source_path=tmp_path / "source.pdf",
        marked=True,
        language="en",
        role_map=(),
        children=(
            StructureElement(
                "Cover_Title",
                "heading",
                children=(ContentFragment(0, 1, ("Repeated",)),),
            ),
            StructureElement(
                "Cover_Title",
                "heading",
                children=(ContentFragment(0, 2, ("Repeated",)),),
            ),
        ),
    )
    base_report = _report(document)
    report = QualityReport(
        status=base_report.status,
        metrics=base_report.metrics,
        hard_gates=base_report.hard_gates,
        diagnostics=base_report.diagnostics,
        join_decisions=base_report.join_decisions,
        heading_hierarchy=(
            {
                "structure_path": "/heading[0]",
                "source_role": "Cover_Title",
                "level": None,
                "joined_text": "Repeated",
                "classification": "source_role_candidate",
            },
            {
                "structure_path": "/heading[1]",
                "source_role": "Cover_Title",
                "level": None,
                "joined_text": "Repeated",
                "classification": "source_role_candidate",
            },
        ),
    )

    artifacts = OutputBundleWriter().write(document, report, tmp_path / "result")

    assert artifacts.semantic_markdown.read_text(encoding="utf-8").splitlines().count(
        "## Repeated"
    ) == 2


def test_markdown_validation_matches_renderer_whitespace_normalization(
    tmp_path: Path,
) -> None:
    document = TaggedDocument(
        source_path=tmp_path / "source.pdf",
        marked=True,
        language="en",
        role_map=(),
        children=(
            StructureElement(
                "Cover_Title",
                "heading",
                children=(ContentFragment(0, 1, (" Repeated   Heading ",)),),
            ),
        ),
    )
    base_report = _report(document)
    report = QualityReport(
        "pass",
        {},
        {"xml_round_trip": True},
        (),
        base_report.join_decisions,
        heading_hierarchy=(
            {
                "classification": "source_role_candidate",
                "source_role": "Cover_Title",
                "level": None,
                "joined_text": " Repeated   Heading ",
                "structure_path": "/heading[0]",
            },
        ),
    )

    artifacts = OutputBundleWriter().write(document, report, tmp_path / "result")

    assert "## Repeated Heading" in artifacts.semantic_markdown.read_text(
        encoding="utf-8"
    ).splitlines()


def test_markdown_validation_uses_renderer_punctuation_for_split_fragments(
    tmp_path: Path,
) -> None:
    document = TaggedDocument(
        source_path=tmp_path / "source.pdf",
        marked=True,
        language="en",
        role_map=(),
        children=(
            StructureElement(
                "Heading1",
                "paragraph",
                children=(
                    ContentFragment(0, 1, ("Warning ",)),
                    ContentFragment(0, 2, ("! Important",)),
                ),
            ),
        ),
    )
    base_report = _report(document)
    report = QualityReport(
        "pass",
        {},
        {"xml_round_trip": True},
        (),
        base_report.join_decisions,
        heading_hierarchy=(
            {
                "classification": "source_role_candidate",
                "source_role": "Heading1",
                "semantic_role": "paragraph",
                "level": 1,
                "joined_text": "Warning ! Important",
                "structure_path": "/paragraph[0]",
            },
        ),
    )

    artifacts = OutputBundleWriter().write(document, report, tmp_path / "result")

    assert "## Warning! Important" in artifacts.semantic_markdown.read_text(
        encoding="utf-8"
    ).splitlines()


def test_markdown_validation_rejects_missing_duplicate_candidate_before_publication(
    tmp_path: Path,
) -> None:
    class MissingDuplicateMarkdownWriter:
        def write(
            self,
            semantic_xml: Path,
            report: QualityReport,
            output: Path,
            *,
            source_name: str,
        ) -> None:
            output.write_text("## Repeated\n", encoding="utf-8")

    document = TaggedDocument(
        source_path=tmp_path / "source.pdf",
        marked=True,
        language="en",
        role_map=(),
        children=(
            StructureElement(
                "H1",
                "heading",
                1,
                children=(ContentFragment(0, 1, ("Repeated",)),),
            ),
            StructureElement(
                "H1",
                "heading",
                1,
                children=(ContentFragment(0, 2, ("Repeated",)),),
            ),
        ),
    )
    base_report = _report(document)
    report = QualityReport(
        "pass",
        {},
        {"xml_round_trip": True},
        (),
        base_report.join_decisions,
        heading_hierarchy=(
            {
                "classification": "source_role_candidate",
                "level": 1,
                "joined_text": "Repeated",
                "structure_path": "/heading[0]",
            },
            {
                "classification": "source_role_candidate",
                "level": 1,
                "joined_text": "Repeated",
                "structure_path": "/heading[1]",
            },
        ),
    )
    output = tmp_path / "result"

    with pytest.raises(ValueError, match="Markdown heading candidates"):
        OutputBundleWriter(markdown_writer=MissingDuplicateMarkdownWriter()).write(
            document, report, output
        )

    assert not output.exists()
    assert _owned_temporary_paths(tmp_path, "result") == []


def test_markdown_validation_rejects_four_space_code_block_heading_lookalike(
    tmp_path: Path,
) -> None:
    semantic = tmp_path / "semantic_document.xml"
    semantic.write_text(
        "<document><paragraph><text>Not a heading</text></paragraph></document>",
        encoding="utf-8",
    )
    markdown = tmp_path / "semantic_document.md"
    markdown.write_text("    ## Not a heading\n", encoding="utf-8")
    report = QualityReport(
        "pass",
        {},
        {},
        (),
        (),
        heading_hierarchy=(
            {
                "classification": "source_role_candidate",
                "level": 1,
                "structure_path": "/paragraph[0]",
            },
        ),
    )

    with pytest.raises(ValueError, match="Markdown heading candidates"):
        OutputBundleWriter._validate_markdown(markdown, semantic, report)


def test_markdown_validation_accepts_list_indented_promoted_heading(
    tmp_path: Path,
) -> None:
    semantic = tmp_path / "semantic_document.xml"
    semantic.write_text(
        "<document><list><list_item><paragraph><text>List heading</text>"
        "</paragraph></list_item></list></document>",
        encoding="utf-8",
    )
    markdown = tmp_path / "semantic_document.md"
    markdown.write_text("-\n  ## List heading\n", encoding="utf-8")
    report = QualityReport(
        "pass",
        {},
        {},
        (),
        (),
        heading_hierarchy=(
            {
                "classification": "source_role_candidate",
                "level": 1,
                "structure_path": "/list[0]/list_item[0]/paragraph[0]",
            },
        ),
    )

    OutputBundleWriter._validate_markdown(markdown, semantic, report)


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
