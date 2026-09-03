from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Callable
from xml.etree import ElementTree as ET

from tagged_pdf_extractor.domain.models import (
    ExtractionArtifacts,
    QualityReport,
    TaggedDocument,
)
from tagged_pdf_extractor.infrastructure.json_report_writer import JsonReportWriter
from tagged_pdf_extractor.infrastructure.xml_writer import XmlDocumentWriter
from tagged_pdf_extractor.ports.output_writer import OutputValidation


RAW_XML_NAME = "raw_structure.xml"
SEMANTIC_XML_NAME = "semantic_document.xml"
REPORT_JSON_NAME = "extraction_report.json"
REQUIRED_OUTPUT_NAMES = (RAW_XML_NAME, SEMANTIC_XML_NAME, REPORT_JSON_NAME)


class OutputCollisionError(FileExistsError):
    pass


class OutputBusyError(RuntimeError):
    """Raised for an existing transaction lock; stale locks require manual review."""

    def __init__(self, lock_path: Path) -> None:
        self.lock_path = lock_path.resolve()
        super().__init__(
            f"output transaction is busy: {self.lock_path}; "
            "stale locks are never removed automatically"
        )


class BundleRollbackError(RuntimeError):
    def __init__(
        self,
        publication_error: Exception,
        restoration_errors: tuple[Exception, ...],
        backup_path: Path,
        affected_files: tuple[str, ...],
    ) -> None:
        self.publication_error = publication_error
        self.restoration_errors = restoration_errors
        self.backup_path = backup_path.resolve()
        self.affected_files = affected_files
        affected = ", ".join(affected_files) or "unknown"
        super().__init__(
            "bundle publication failed and old outputs could not be fully "
            f"restored; backup preserved at {self.backup_path}; "
            f"affected files: {affected}"
        )


class BundleTransactionError(RuntimeError):
    def __init__(
        self,
        primary_error: BaseException | None,
        cleanup_failures: tuple[tuple[Path, Exception], ...],
        *,
        published: bool,
        artifacts: ExtractionArtifacts,
    ) -> None:
        self.primary_error = primary_error
        self.cleanup_errors = tuple(error for _, error in cleanup_failures)
        self.cleanup_paths = tuple(path.resolve() for path, _ in cleanup_failures)
        self.published = published
        self.artifacts = artifacts if published else None
        state = "published" if published else "not published"
        paths = ", ".join(str(path) for path in self.cleanup_paths)
        primary = repr(primary_error) if primary_error is not None else "none"
        super().__init__(
            f"bundle transaction cleanup failed ({state}); primary={primary}; "
            f"preserved paths: {paths}"
        )


class OutputBundleWriter:
    def __init__(
        self,
        xml_writer: XmlDocumentWriter | None = None,
        json_writer: JsonReportWriter | None = None,
    ) -> None:
        self.xml_writer = xml_writer or XmlDocumentWriter()
        self.json_writer = json_writer or JsonReportWriter()

    def validate(self, document: TaggedDocument) -> OutputValidation:
        with tempfile.TemporaryDirectory(prefix="tagged-pdf-xml-validation-") as temp:
            validation_dir = Path(temp)
            raw_path = validation_dir / RAW_XML_NAME
            semantic_path = validation_dir / SEMANTIC_XML_NAME
            self.xml_writer.write_raw(document, raw_path)
            decisions = self.xml_writer.write_semantic(document, semantic_path)
            ET.parse(raw_path)
            ET.parse(semantic_path)
            return OutputValidation(decisions)

    def write(
        self,
        document: TaggedDocument,
        report: QualityReport,
        output_dir: Path,
        overwrite: bool = False,
    ) -> ExtractionArtifacts:
        output_dir = Path(output_dir)
        initially_exists = self._inspect_output_directory(output_dir)
        self._preflight_required_targets(output_dir, overwrite)

        parent = output_dir.parent
        parent.mkdir(parents=True, exist_ok=True)
        lock_path = parent / f".{output_dir.name}.lock"
        try:
            lock_path.mkdir()
        except FileExistsError as exc:
            raise OutputBusyError(lock_path) from exc
        lock_identity = self._path_identity(lock_path)

        artifacts = ExtractionArtifacts(
            raw_xml=output_dir / RAW_XML_NAME,
            semantic_xml=output_dir / SEMANTIC_XML_NAME,
            report_json=output_dir / REPORT_JSON_NAME,
        )
        staging: Path | None = None
        backup: Path | None = None
        preserve_backup = False
        published = False
        primary_error: BaseException | None = None
        primary_traceback = None
        try:
            staging = Path(
                tempfile.mkdtemp(prefix=f".{output_dir.name}.staging-", dir=parent)
            )
            self._write_and_validate_staging(document, report, staging)
            currently_exists = self._inspect_output_directory(output_dir)
            if currently_exists != initially_exists:
                raise OutputCollisionError(
                    f"output changed during transaction: {output_dir}"
                )
            self._preflight_required_targets(output_dir, overwrite)

            if not initially_exists:
                os.rename(staging, output_dir)
                staging = None
            else:
                backup = Path(
                    tempfile.mkdtemp(
                        prefix=f".{output_dir.name}.backup-", dir=parent
                    )
                )
                self._publish_into_existing(staging, backup, output_dir)
            published = True
        except BaseException as exc:
            primary_error = exc
            primary_traceback = exc.__traceback__
            preserve_backup = isinstance(exc, BundleRollbackError)

        cleanup_failures: list[tuple[Path, Exception]] = []
        if staging is not None:
            self._capture_cleanup(
                staging, self._remove_owned_directory, cleanup_failures
            )
        if backup is not None and not preserve_backup:
            self._capture_cleanup(
                backup, self._remove_owned_directory, cleanup_failures
            )
        self._capture_cleanup(
            lock_path,
            lambda path: self._remove_owned_lock(path, lock_identity),
            cleanup_failures,
        )

        if cleanup_failures:
            raise BundleTransactionError(
                primary_error,
                tuple(cleanup_failures),
                published=published,
                artifacts=artifacts,
            ) from primary_error
        if primary_error is not None:
            raise primary_error.with_traceback(primary_traceback)
        return artifacts

    @staticmethod
    def _inspect_output_directory(output_dir: Path) -> bool:
        if not os.path.lexists(output_dir):
            return False
        if not output_dir.is_dir() or output_dir.is_symlink():
            raise NotADirectoryError(f"output path is not a directory: {output_dir}")
        return True

    @staticmethod
    def _preflight_required_targets(
        output_dir: Path, overwrite: bool
    ) -> tuple[Path, ...]:
        existing: list[Path] = []
        for name in REQUIRED_OUTPUT_NAMES:
            destination = output_dir / name
            if not os.path.lexists(destination):
                continue
            if not destination.is_file() or destination.is_symlink():
                raise OutputCollisionError(
                    f"required output target is not a regular file: {destination}"
                )
            existing.append(destination)
        if existing and not overwrite:
            names = ", ".join(path.name for path in existing)
            raise OutputCollisionError(f"required output already exists: {names}")
        return tuple(existing)

    @staticmethod
    def _path_identity(path: Path) -> tuple[int, int]:
        stat = path.stat(follow_symlinks=False)
        return stat.st_dev, stat.st_ino

    @classmethod
    def _remove_owned_lock(
        cls, lock_path: Path, expected_identity: tuple[int, int]
    ) -> None:
        if not os.path.lexists(lock_path):
            return
        if cls._path_identity(lock_path) != expected_identity:
            raise OSError(f"transaction lock ownership changed: {lock_path}")
        lock_path.rmdir()

    @staticmethod
    def _capture_cleanup(
        path: Path,
        cleanup: Callable[[Path], None],
        failures: list[tuple[Path, Exception]],
    ) -> None:
        try:
            cleanup(path)
        except Exception as exc:
            failures.append((path, exc))

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
            removal_errors: list[Exception] = []
            for name in reversed(published):
                try:
                    (output_dir / name).unlink(missing_ok=True)
                except Exception as exc:
                    removal_errors.append(exc)
            restoration_errors: list[Exception] = []
            for name in reversed(backed_up):
                try:
                    os.replace(backup / name, output_dir / name)
                except Exception as exc:
                    restoration_errors.append(exc)
            if restoration_errors:
                affected_files = tuple(
                    name for name in backed_up if (backup / name).exists()
                )
                raise BundleRollbackError(
                    publication_error,
                    tuple(restoration_errors),
                    backup,
                    affected_files,
                ) from publication_error
            if removal_errors:
                raise ExceptionGroup(
                    "bundle publication and rollback failed",
                    [publication_error, *removal_errors],
                )
            raise

    @staticmethod
    def _remove_owned_directory(directory: Path) -> None:
        if not directory.exists():
            return
        for name in REQUIRED_OUTPUT_NAMES:
            (directory / name).unlink(missing_ok=True)
        directory.rmdir()
