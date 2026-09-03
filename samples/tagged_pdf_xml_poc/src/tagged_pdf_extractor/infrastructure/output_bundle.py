from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from xml.etree import ElementTree as ET

from tagged_pdf_extractor.domain.models import (
    ExtractionArtifacts,
    QualityReport,
    TaggedDocument,
)
from tagged_pdf_extractor.infrastructure.json_report_writer import JsonReportWriter
from tagged_pdf_extractor.infrastructure.xml_writer import XmlDocumentWriter


RAW_XML_NAME = "raw_structure.xml"
SEMANTIC_XML_NAME = "semantic_document.xml"
REPORT_JSON_NAME = "extraction_report.json"
REQUIRED_OUTPUT_NAMES = (RAW_XML_NAME, SEMANTIC_XML_NAME, REPORT_JSON_NAME)


class OutputCollisionError(FileExistsError):
    pass


class OutputBundleWriter:
    def __init__(
        self,
        xml_writer: XmlDocumentWriter | None = None,
        json_writer: JsonReportWriter | None = None,
    ) -> None:
        self.xml_writer = xml_writer or XmlDocumentWriter()
        self.json_writer = json_writer or JsonReportWriter()

    def write(
        self,
        document: TaggedDocument,
        report: QualityReport,
        output_dir: Path,
        overwrite: bool = False,
    ) -> ExtractionArtifacts:
        output_dir = Path(output_dir)
        if output_dir.exists() and not output_dir.is_dir():
            raise NotADirectoryError(f"output path is not a directory: {output_dir}")

        existing = tuple(
            output_dir / name
            for name in REQUIRED_OUTPUT_NAMES
            if (output_dir / name).exists()
        )
        if existing and not overwrite:
            names = ", ".join(path.name for path in existing)
            raise OutputCollisionError(f"required output already exists: {names}")

        parent = output_dir.parent
        parent.mkdir(parents=True, exist_ok=True)
        staging = Path(
            tempfile.mkdtemp(prefix=f".{output_dir.name}.staging-", dir=parent)
        )
        backup: Path | None = None
        try:
            self._write_and_validate_staging(document, report, staging)
            if not output_dir.exists():
                os.replace(staging, output_dir)
                staging = None  # type: ignore[assignment]
            else:
                backup = Path(
                    tempfile.mkdtemp(
                        prefix=f".{output_dir.name}.backup-", dir=parent
                    )
                )
                self._publish_into_existing(staging, backup, output_dir)
            return ExtractionArtifacts(
                raw_xml=output_dir / RAW_XML_NAME,
                semantic_xml=output_dir / SEMANTIC_XML_NAME,
                report_json=output_dir / REPORT_JSON_NAME,
            )
        finally:
            if staging is not None:
                self._remove_owned_directory(staging)
            if backup is not None:
                self._remove_owned_directory(backup)

    def _write_and_validate_staging(
        self,
        document: TaggedDocument,
        report: QualityReport,
        staging: Path,
    ) -> None:
        raw_path = staging / RAW_XML_NAME
        semantic_path = staging / SEMANTIC_XML_NAME
        report_path = staging / REPORT_JSON_NAME

        self.xml_writer.write_raw(document, raw_path)
        semantic_decisions = self.xml_writer.write_semantic(document, semantic_path)
        if semantic_decisions != report.join_decisions:
            raise ValueError(
                "semantic XML join decisions do not match report join decisions"
            )
        self.json_writer.write(report, report_path)

        ET.parse(raw_path)
        ET.parse(semantic_path)
        parsed_report = json.loads(report_path.read_text(encoding="utf-8"))
        if parsed_report != self.json_writer.to_data(report):
            raise ValueError("JSON report round trip mismatch")

    @staticmethod
    def _publish_into_existing(
        staging: Path,
        backup: Path,
        output_dir: Path,
    ) -> None:
        backed_up: list[str] = []
        published: list[str] = []
        try:
            for name in REQUIRED_OUTPUT_NAMES:
                destination = output_dir / name
                if destination.exists():
                    os.replace(destination, backup / name)
                    backed_up.append(name)
            for name in REQUIRED_OUTPUT_NAMES:
                os.replace(staging / name, output_dir / name)
                published.append(name)
        except Exception as publication_error:
            rollback_errors: list[Exception] = []
            for name in reversed(published):
                try:
                    (output_dir / name).unlink(missing_ok=True)
                except Exception as exc:
                    rollback_errors.append(exc)
            for name in reversed(backed_up):
                try:
                    os.replace(backup / name, output_dir / name)
                except Exception as exc:
                    rollback_errors.append(exc)
            if rollback_errors:
                raise ExceptionGroup(
                    "bundle publication and rollback failed",
                    [publication_error, *rollback_errors],
                )
            raise

    @staticmethod
    def _remove_owned_directory(directory: Path) -> None:
        if not directory.exists():
            return
        for name in REQUIRED_OUTPUT_NAMES:
            (directory / name).unlink(missing_ok=True)
        directory.rmdir()
