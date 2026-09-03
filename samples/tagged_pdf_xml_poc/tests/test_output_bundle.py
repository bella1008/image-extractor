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
    OutputBundleWriter,
    OutputCollisionError,
)


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
    return list(parent.glob(f".{output_name}.staging-*")) + list(
        parent.glob(f".{output_name}.backup-*")
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


@pytest.mark.parametrize("fail_publication_number", [1, 2])
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
        def write(self, actual_document: TaggedDocument, actual_report: QualityReport, output: Path, overwrite: bool = False) -> object:
            calls.append(("writer", (actual_document, actual_report, output, overwrite)))
            return artifacts

    source = tmp_path / "source.pdf"
    source.write_bytes(b"pdf")
    output = tmp_path / "out"
    use_case = ExtractDocument(Reader(), Baseline(), Evaluator(), Writer())

    assert use_case.run(source, output, overwrite=True) == (document, report, artifacts)
    assert [name for name, _ in calls] == ["reader", "baseline", "evaluator", "writer"]
    assert calls[2][1] == (document, "baseline", True)

    missing = tmp_path / "missing.pdf"
    with pytest.raises(FileNotFoundError, match="missing.pdf"):
        use_case.run(missing, output)
    directory = tmp_path / "directory.pdf"
    directory.mkdir()
    with pytest.raises(IsADirectoryError, match="directory.pdf"):
        use_case.run(directory, output)
    assert [name for name, _ in calls] == ["reader", "baseline", "evaluator", "writer"]
