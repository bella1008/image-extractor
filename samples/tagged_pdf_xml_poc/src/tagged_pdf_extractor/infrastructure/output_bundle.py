from __future__ import annotations

import hashlib
import json
import os
import tempfile
import uuid
from pathlib import Path
from typing import Callable
from xml.etree import ElementTree as ET

from tagged_pdf_extractor.domain.models import (
    ExtractionArtifacts,
    QualityReport,
    TaggedDocument,
)
from tagged_pdf_extractor.infrastructure.json_report_writer import JsonReportWriter
from tagged_pdf_extractor.infrastructure.markdown_writer import MarkdownDocumentWriter
from tagged_pdf_extractor.infrastructure.xml_writer import XmlDocumentWriter
from tagged_pdf_extractor.ports.output_writer import OutputValidation


RAW_XML_NAME = "raw_structure.xml"
SEMANTIC_XML_NAME = "semantic_document.xml"
REPORT_JSON_NAME = "extraction_report.json"
MARKDOWN_NAME = "semantic_document.md"
REQUIRED_OUTPUT_NAMES = (
    RAW_XML_NAME,
    SEMANTIC_XML_NAME,
    REPORT_JSON_NAME,
    MARKDOWN_NAME,
)
_COMMIT_MARKER_NAME = ".tagged-pdf-xml-commit"
_LOCK_OWNER_MARKER_NAME = ".owner-token"


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


class BundlePublicationErrorGroup(ExceptionGroup):
    """Ordinary publication and rollback failures safe for CLI handling."""

    def __new__(
        cls, message: str, exceptions: tuple[Exception, ...] | list[Exception]
    ) -> BundlePublicationErrorGroup:
        instance = super().__new__(cls, message, exceptions)
        instance._tagged_pdf_rollback_complete = True
        return instance

    def derive(
        self, exceptions: tuple[Exception, ...]
    ) -> BundlePublicationErrorGroup:
        return BundlePublicationErrorGroup(self.message, exceptions)


class BundleRollbackError(RuntimeError):
    def __init__(
        self,
        publication_error: BaseException,
        restoration_errors: tuple[BaseException, ...],
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


class BundleRollbackBaseExceptionGroup(BaseExceptionGroup):
    def __new__(
        cls,
        publication_error: BaseException,
        restoration_errors: tuple[BaseException, ...],
        backup_path: Path,
        affected_files: tuple[str, ...],
    ) -> BundleRollbackBaseExceptionGroup:
        resolved_backup = backup_path.resolve()
        affected = ", ".join(affected_files) or "unknown"
        instance = super().__new__(
            cls,
            "bundle publication and rollback failed; "
            f"backup preserved at {resolved_backup}; affected files: {affected}",
            (publication_error, *restoration_errors),
        )
        instance.publication_error = publication_error
        instance.restoration_errors = restoration_errors
        instance.backup_path = resolved_backup
        instance.affected_files = affected_files
        return instance

    def __init__(
        self,
        publication_error: BaseException,
        restoration_errors: tuple[BaseException, ...],
        backup_path: Path,
        affected_files: tuple[str, ...],
    ) -> None:
        pass

    def derive(
        self, exceptions: tuple[BaseException, ...]
    ) -> BaseExceptionGroup:
        derived = BaseExceptionGroup(self.message, exceptions)
        derived.publication_error = self.publication_error
        derived.restoration_errors = self.restoration_errors
        derived.backup_path = self.backup_path
        derived.affected_files = self.affected_files
        return derived


class BundleTransactionError(RuntimeError):
    def __init__(
        self,
        primary_error: BaseException | None,
        cleanup_failures: tuple[tuple[Path, BaseException], ...],
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


class BundleTransactionBaseExceptionGroup(BaseExceptionGroup):
    def __new__(
        cls,
        primary_error: BaseException | None,
        cleanup_failures: tuple[tuple[Path, BaseException], ...],
        *,
        published: bool,
        artifacts: ExtractionArtifacts,
    ) -> BundleTransactionBaseExceptionGroup:
        cleanup_errors = tuple(error for _, error in cleanup_failures)
        members = (
            ((primary_error,) if primary_error is not None else ())
            + cleanup_errors
        )
        cleanup_paths = tuple(path.resolve() for path, _ in cleanup_failures)
        state = "published" if published else "not published"
        paths = ", ".join(str(path) for path in cleanup_paths)
        instance = super().__new__(
            cls,
            f"bundle transaction cleanup interrupted ({state}); "
            f"preserved paths: {paths}",
            members,
        )
        instance.primary_error = primary_error
        instance.cleanup_errors = cleanup_errors
        instance.cleanup_paths = cleanup_paths
        instance.published = published
        instance.artifacts = artifacts if published else None
        return instance

    def __init__(
        self,
        primary_error: BaseException | None,
        cleanup_failures: tuple[tuple[Path, BaseException], ...],
        *,
        published: bool,
        artifacts: ExtractionArtifacts,
    ) -> None:
        pass

    def derive(
        self, exceptions: tuple[BaseException, ...]
    ) -> BaseExceptionGroup:
        derived = BaseExceptionGroup(self.message, exceptions)
        derived.primary_error = self.primary_error
        derived.cleanup_errors = self.cleanup_errors
        derived.cleanup_paths = self.cleanup_paths
        derived.published = self.published
        derived.artifacts = self.artifacts
        return derived


class BundlePublicationStateError(RuntimeError):
    def __init__(
        self,
        primary_error: BaseException,
        inference_error: BaseException | None,
        *,
        state: str,
        artifacts: ExtractionArtifacts,
        backup_path: Path | None,
        staging_path: Path | None,
    ) -> None:
        self.primary_error = primary_error
        self.inference_error = inference_error
        self.state = state
        self.published = state == "published"
        self.artifacts = artifacts if self.published else None
        self.backup_path = backup_path.resolve() if backup_path is not None else None
        self.staging_path = staging_path.resolve() if staging_path is not None else None
        super().__init__(
            f"bundle publication state is {state}; primary={primary_error!r}; "
            f"backup={self.backup_path}; staging={self.staging_path}"
        )


class BundlePublicationStateBaseExceptionGroup(BaseExceptionGroup):
    def __new__(
        cls,
        primary_error: BaseException,
        inference_error: BaseException | None,
        *,
        state: str,
        artifacts: ExtractionArtifacts,
        backup_path: Path | None,
        staging_path: Path | None,
    ) -> BundlePublicationStateBaseExceptionGroup:
        resolved_backup = backup_path.resolve() if backup_path is not None else None
        resolved_staging = staging_path.resolve() if staging_path is not None else None
        members = (
            (primary_error, inference_error)
            if inference_error is not None
            else (primary_error,)
        )
        instance = super().__new__(
            cls,
            f"bundle publication state is {state}; backup={resolved_backup}; "
            f"staging={resolved_staging}",
            members,
        )
        instance.primary_error = primary_error
        instance.inference_error = inference_error
        instance.state = state
        instance.published = state == "published"
        instance.artifacts = artifacts if instance.published else None
        instance.backup_path = resolved_backup
        instance.staging_path = resolved_staging
        return instance

    def __init__(
        self,
        primary_error: BaseException,
        inference_error: BaseException | None,
        *,
        state: str,
        artifacts: ExtractionArtifacts,
        backup_path: Path | None,
        staging_path: Path | None,
    ) -> None:
        pass

    def derive(
        self, exceptions: tuple[BaseException, ...]
    ) -> BaseExceptionGroup:
        derived = BaseExceptionGroup(self.message, exceptions)
        derived.primary_error = self.primary_error
        derived.inference_error = self.inference_error
        derived.state = self.state
        derived.published = self.published
        derived.artifacts = self.artifacts
        derived.backup_path = self.backup_path
        derived.staging_path = self.staging_path
        return derived


class OutputBundleWriter:
    def __init__(
        self,
        xml_writer: XmlDocumentWriter | None = None,
        json_writer: JsonReportWriter | None = None,
        markdown_writer: MarkdownDocumentWriter | None = None,
    ) -> None:
        self.xml_writer = xml_writer or XmlDocumentWriter()
        self.json_writer = json_writer or JsonReportWriter()
        self.markdown_writer = markdown_writer or MarkdownDocumentWriter()

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
        initial_targets = self._preflight_required_targets(output_dir, overwrite)

        parent = output_dir.parent
        parent.mkdir(parents=True, exist_ok=True)
        artifacts = ExtractionArtifacts(
            raw_xml=output_dir / RAW_XML_NAME,
            semantic_xml=output_dir / SEMANTIC_XML_NAME,
            report_json=output_dir / REPORT_JSON_NAME,
            semantic_markdown=output_dir / MARKDOWN_NAME,
        )
        transaction_token = uuid.uuid4().hex
        lock_path = parent / f".{output_dir.name}.lock"
        lock_candidate = parent / (
            f".{output_dir.name}.lock-candidate-{transaction_token}"
        )
        staging: Path | None = None
        backup: Path | None = None
        acquisition_completed = False
        preserve_backup = False
        preserve_staging = False
        preserve_commit_marker = False
        published = False
        publication_attempted = False
        commit_evidence = False
        expected_fingerprints: dict[str, tuple[int, str]] | None = None
        primary_error: BaseException | None = None
        primary_traceback = None
        try:
            try:
                self._acquire_lock(
                    lock_candidate, lock_path, transaction_token
                )
                acquisition_completed = True
                staging = Path(
                    tempfile.mkdtemp(
                        prefix=f".{output_dir.name}.staging-", dir=parent
                    )
                )
                self._write_and_validate_staging(document, report, staging)
                expected_fingerprints = self._bundle_fingerprints(staging)
                currently_exists = self._inspect_output_directory(output_dir)
                if currently_exists != initially_exists:
                    raise OutputCollisionError(
                        f"output changed during transaction: {output_dir}"
                    )
                self._preflight_required_targets(output_dir, overwrite)

                if not initially_exists:
                    self._write_commit_marker(staging, transaction_token, committed=True)
                    publication_attempted = True
                    os.rename(staging, output_dir)
                    staging = None
                    commit_evidence = True
                else:
                    backup = Path(
                        tempfile.mkdtemp(
                            prefix=f".{output_dir.name}.backup-", dir=parent
                        )
                    )
                    self._write_commit_marker(
                        backup, transaction_token, committed=False
                    )
                    publication_attempted = True
                    if overwrite:
                        self._publish_into_existing(staging, backup, output_dir)
                    else:
                        self._publish_into_existing(
                            staging, backup, output_dir, overwrite=False
                        )
                    commit_evidence = True
                published = True
            except BaseException as exc:
                primary_error = exc
                primary_traceback = exc.__traceback__
                preserve_backup = backup is not None and any(
                    os.path.lexists(backup / name)
                    for name in REQUIRED_OUTPUT_NAMES
                )
                rollback_complete = bool(
                    getattr(exc, "_tagged_pdf_rollback_complete", False)
                )
                rollback_failed = isinstance(
                    exc, (BundleRollbackError, BundleRollbackBaseExceptionGroup)
                )
                if (
                    publication_attempted
                    and expected_fingerprints is not None
                    and not rollback_complete
                    and not rollback_failed
                ):
                    try:
                        state = self._infer_publication_state(
                            output_dir,
                            staging,
                            expected_fingerprints,
                            initially_exists=initially_exists,
                            backup=backup,
                            transaction_token=transaction_token,
                            commit_evidence=commit_evidence,
                        )
                    except BaseException as inference_error:
                        preserve_backup = backup is not None
                        preserve_staging = staging is not None
                        preserve_commit_marker = True
                        primary_error = self._publication_state_error(
                            exc,
                            inference_error,
                            state="unknown",
                            artifacts=artifacts,
                            backup_path=backup,
                            staging_path=staging,
                        )
                        primary_traceback = primary_error.__traceback__
                    else:
                        if state == "published":
                            published = True
                            preserve_backup = bool(initial_targets) and backup is not None
                            primary_error = self._publication_state_error(
                                exc,
                                None,
                                state="published",
                                artifacts=artifacts,
                                backup_path=backup if initial_targets else None,
                                staging_path=staging,
                            )
                            primary_traceback = primary_error.__traceback__
                        elif state == "unknown":
                            preserve_backup = backup is not None
                            preserve_staging = staging is not None
                            preserve_commit_marker = True
                            primary_error = self._publication_state_error(
                                exc,
                                None,
                                state="unknown",
                                artifacts=artifacts,
                                backup_path=backup,
                                staging_path=staging,
                            )
                            primary_traceback = primary_error.__traceback__
        finally:
            cleanup_failures: list[tuple[Path, BaseException]] = []
            if staging is not None and not preserve_staging:
                self._capture_cleanup(
                    staging, self._remove_owned_directory, cleanup_failures
                )
            if backup is not None and not preserve_backup:
                self._capture_cleanup(
                    backup, self._remove_owned_directory, cleanup_failures
                )
            if (
                not initially_exists
                and published
                and not preserve_commit_marker
                and transaction_token is not None
            ):
                marker = output_dir / _COMMIT_MARKER_NAME
                self._capture_cleanup(
                    marker,
                    lambda path: self._remove_owned_commit_marker(
                        path, transaction_token
                    ),
                    cleanup_failures,
                )
            self._capture_cleanup(
                lock_candidate,
                lambda path: self._remove_lock_candidate_if_owned(
                    path, transaction_token
                ),
                cleanup_failures,
            )
            if acquisition_completed:
                self._capture_cleanup(
                    lock_path,
                    lambda path: self._remove_owned_lock(
                        path, transaction_token
                    ),
                    cleanup_failures,
                )
            else:
                self._capture_cleanup(
                    lock_path,
                    lambda path: self._remove_lock_if_owned(
                        path, transaction_token
                    ),
                    cleanup_failures,
                )

        if cleanup_failures:
            members = (
                ((primary_error,) if primary_error is not None else ())
                + tuple(error for _, error in cleanup_failures)
            )
            if all(isinstance(member, Exception) for member in members):
                raise BundleTransactionError(
                    primary_error,
                    tuple(cleanup_failures),
                    published=published,
                    artifacts=artifacts,
                ) from primary_error
            raise BundleTransactionBaseExceptionGroup(
                primary_error,
                tuple(cleanup_failures),
                published=published,
                artifacts=artifacts,
            ) from primary_error
        if primary_error is not None:
            raise primary_error.with_traceback(primary_traceback)
        return artifacts

    @staticmethod
    def _publication_state_error(
        primary_error: BaseException,
        inference_error: BaseException | None,
        *,
        state: str,
        artifacts: ExtractionArtifacts,
        backup_path: Path | None,
        staging_path: Path | None,
    ) -> BaseException:
        members = (
            (primary_error, inference_error)
            if inference_error is not None
            else (primary_error,)
        )
        if all(isinstance(member, Exception) for member in members):
            return BundlePublicationStateError(
                primary_error,
                inference_error,
                state=state,
                artifacts=artifacts,
                backup_path=backup_path,
                staging_path=staging_path,
            )
        return BundlePublicationStateBaseExceptionGroup(
            primary_error,
            inference_error,
            state=state,
            artifacts=artifacts,
            backup_path=backup_path,
            staging_path=staging_path,
        )

    @classmethod
    def _bundle_fingerprints(
        cls, directory: Path
    ) -> dict[str, tuple[int, str]]:
        return {
            name: cls._file_fingerprint(directory / name)
            for name in REQUIRED_OUTPUT_NAMES
        }

    @staticmethod
    def _file_fingerprint(path: Path) -> tuple[int, str]:
        digest = hashlib.sha256()
        size = 0
        with path.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                size += len(chunk)
                digest.update(chunk)
        return size, digest.hexdigest()

    @staticmethod
    def _commit_marker_text(transaction_token: str, *, committed: bool) -> str:
        state = "committed" if committed else "prepared"
        return f"{state}:{transaction_token}\n"

    @classmethod
    def _write_commit_marker(
        cls, directory: Path, transaction_token: str, *, committed: bool
    ) -> None:
        (directory / _COMMIT_MARKER_NAME).write_text(
            cls._commit_marker_text(transaction_token, committed=committed),
            encoding="ascii",
        )

    @classmethod
    def _remove_owned_commit_marker(
        cls, marker: Path, transaction_token: str
    ) -> None:
        if not os.path.lexists(marker):
            return
        expected = cls._commit_marker_text(transaction_token, committed=True)
        if not marker.is_file() or marker.is_symlink() or marker.read_text(
            encoding="ascii"
        ) != expected:
            raise OSError(f"commit marker ownership changed: {marker}")
        marker.unlink()

    @classmethod
    def _infer_publication_state(
        cls,
        output_dir: Path,
        staging: Path | None,
        expected_fingerprints: dict[str, tuple[int, str]],
        *,
        initially_exists: bool,
        backup: Path | None,
        transaction_token: str,
        commit_evidence: bool,
    ) -> str:
        for name in REQUIRED_OUTPUT_NAMES:
            destination = output_dir / name
            if (
                not os.path.lexists(destination)
                or not destination.is_file()
                or destination.is_symlink()
                or cls._file_fingerprint(destination)
                != expected_fingerprints[name]
            ):
                return "uncommitted"
        staging_consumed = staging is None or all(
            not os.path.lexists(staging / name) for name in REQUIRED_OUTPUT_NAMES
        )
        if not staging_consumed:
            return "uncommitted"
        if commit_evidence:
            return "published"
        marker_directory = backup if initially_exists else output_dir
        if marker_directory is None:
            return "unknown"
        marker = marker_directory / _COMMIT_MARKER_NAME
        expected_marker = cls._commit_marker_text(
            transaction_token, committed=True
        )
        if (
            os.path.lexists(marker)
            and marker.is_file()
            and not marker.is_symlink()
            and marker.read_text(encoding="ascii") == expected_marker
        ):
            return "published"
        return "unknown"

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
    def _lock_owner_text(transaction_token: str) -> str:
        return f"{transaction_token}\n"

    @classmethod
    def _acquire_lock(
        cls,
        candidate_path: Path,
        lock_path: Path,
        transaction_token: str,
    ) -> None:
        cls._create_lock_candidate(candidate_path)
        cls._write_lock_owner_marker(candidate_path, transaction_token)
        try:
            os.rename(candidate_path, lock_path)
        except FileExistsError as exc:
            raise OutputBusyError(lock_path) from exc

    @staticmethod
    def _create_lock_candidate(candidate_path: Path) -> None:
        candidate_path.mkdir()

    @classmethod
    def _write_lock_owner_marker(
        cls, candidate_path: Path, transaction_token: str
    ) -> None:
        (candidate_path / _LOCK_OWNER_MARKER_NAME).write_text(
            cls._lock_owner_text(transaction_token), encoding="ascii"
        )

    @classmethod
    def _has_lock_owner_token(cls, lock_path: Path, transaction_token: str) -> bool:
        marker = lock_path / _LOCK_OWNER_MARKER_NAME
        return (
            os.path.lexists(marker)
            and marker.is_file()
            and not marker.is_symlink()
            and marker.read_text(encoding="ascii")
            == cls._lock_owner_text(transaction_token)
        )

    @classmethod
    def _remove_lock_candidate_if_owned(
        cls, candidate_path: Path, transaction_token: str
    ) -> None:
        if not os.path.lexists(candidate_path):
            return
        if candidate_path.is_symlink() or not candidate_path.is_dir():
            return
        if not candidate_path.name.endswith(f"-{transaction_token}"):
            return
        entries = tuple(candidate_path.iterdir())
        marker = candidate_path / _LOCK_OWNER_MARKER_NAME
        if not entries:
            candidate_path.rmdir()
            return
        if entries == (marker,):
            marker.unlink()
            candidate_path.rmdir()

    @classmethod
    def _remove_lock_if_owned(
        cls, lock_path: Path, transaction_token: str
    ) -> None:
        if not os.path.lexists(lock_path):
            return
        if (
            lock_path.is_symlink()
            or not lock_path.is_dir()
            or not cls._has_lock_owner_token(lock_path, transaction_token)
        ):
            return
        marker = lock_path / _LOCK_OWNER_MARKER_NAME
        if tuple(lock_path.iterdir()) != (marker,):
            return
        marker.unlink()
        lock_path.rmdir()

    @classmethod
    def _remove_owned_lock(
        cls, lock_path: Path, transaction_token: str
    ) -> None:
        if not os.path.lexists(lock_path):
            return
        if (
            lock_path.is_symlink()
            or not lock_path.is_dir()
            or not cls._has_lock_owner_token(lock_path, transaction_token)
        ):
            raise OSError(f"transaction lock ownership changed: {lock_path}")
        marker = lock_path / _LOCK_OWNER_MARKER_NAME
        if tuple(lock_path.iterdir()) != (marker,):
            raise OSError(f"transaction lock contents changed: {lock_path}")
        marker.unlink()
        lock_path.rmdir()

    @staticmethod
    def _capture_cleanup(
        path: Path,
        cleanup: Callable[[Path], None],
        failures: list[tuple[Path, BaseException]],
    ) -> None:
        try:
            cleanup(path)
        except BaseException as exc:
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
        markdown_path = staging / MARKDOWN_NAME

        self.xml_writer.write_raw(document, raw_path)
        semantic_decisions = self.xml_writer.write_semantic(document, semantic_path)
        ET.parse(raw_path)
        ET.parse(semantic_path)
        if semantic_decisions != report.join_decisions:
            raise ValueError(
                "semantic XML join decisions do not match report join decisions"
            )
        self.json_writer.write(report, report_path)
        self.markdown_writer.write(
            semantic_path,
            report,
            markdown_path,
            source_name=document.source_path.name,
        )

        parsed_report = json.loads(report_path.read_text(encoding="utf-8"))
        if parsed_report != self.json_writer.to_data(report):
            raise ValueError("JSON report round trip mismatch")
        self._validate_markdown(
            markdown_path,
            semantic_path,
            report,
            source_name=document.source_path.name,
        )

    @staticmethod
    def _validate_markdown(
        path: Path,
        semantic_path: Path,
        report: QualityReport,
        *,
        source_name: str,
    ) -> None:
        if not os.path.lexists(path) or not path.is_file() or path.is_symlink():
            raise ValueError(f"Markdown output is not a regular file: {path}")

        markdown = path.read_text(encoding="utf-8")
        if not markdown.strip():
            raise ValueError("Markdown output is empty")

        expected_markdown = MarkdownDocumentWriter.render_text(
            semantic_path,
            report,
            source_name=source_name,
        )
        if markdown != expected_markdown:
            raise ValueError("Markdown output does not match renderer")

    @staticmethod
    def _publish_into_existing(
        staging: Path,
        backup: Path,
        output_dir: Path,
        *,
        overwrite: bool = True,
    ) -> None:
        backed_up: list[str] = []
        published: list[tuple[str, os.stat_result | None]] = []
        try:
            if overwrite:
                for name in REQUIRED_OUTPUT_NAMES:
                    destination = output_dir / name
                    if destination.exists():
                        backed_up.append(name)
                        os.replace(destination, backup / name)
            for name in REQUIRED_OUTPUT_NAMES:
                source = staging / name
                destination = output_dir / name
                if overwrite:
                    published.append((name, None))
                    os.replace(source, destination)
                else:
                    source_identity = source.stat(follow_symlinks=False)
                    published.append((name, source_identity))
                    try:
                        os.link(source, destination)
                    except FileExistsError as exc:
                        raise OutputCollisionError(
                            f"required output already exists: {destination.name}"
                        ) from exc
                    source.unlink()
        except BaseException as publication_error:
            removal_errors: list[BaseException] = []
            for name, source_identity in reversed(published):
                source = staging / name
                destination = output_dir / name
                if source_identity is None:
                    owns_destination = not os.path.lexists(source)
                else:
                    owns_destination = OutputBundleWriter._matches_file_identity(
                        destination, source_identity
                    )
                if not owns_destination:
                    continue
                try:
                    destination.unlink(missing_ok=True)
                except BaseException as exc:
                    removal_errors.append(exc)
            restoration_errors: list[BaseException] = []
            for name in reversed(backed_up):
                if not os.path.lexists(backup / name):
                    continue
                try:
                    os.replace(backup / name, output_dir / name)
                except BaseException as exc:
                    restoration_errors.append(exc)
            if restoration_errors:
                affected_files = tuple(
                    name for name in backed_up if (backup / name).exists()
                )
                members = (publication_error, *restoration_errors)
                if all(isinstance(member, Exception) for member in members):
                    raise BundleRollbackError(
                        publication_error,
                        tuple(restoration_errors),
                        backup,
                        affected_files,
                    ) from publication_error
                raise BundleRollbackBaseExceptionGroup(
                    publication_error,
                    tuple(restoration_errors),
                    backup,
                    affected_files,
                ) from publication_error
            if removal_errors:
                members = [publication_error, *removal_errors]
                if all(isinstance(member, Exception) for member in members):
                    raise BundlePublicationErrorGroup(
                        "bundle publication and rollback failed", members
                    ) from publication_error
                group = BaseExceptionGroup(
                    "bundle publication and rollback failed", members
                )
                setattr(group, "_tagged_pdf_rollback_complete", True)
                raise group from publication_error
            setattr(publication_error, "_tagged_pdf_rollback_complete", True)
            raise

        marker = backup / _COMMIT_MARKER_NAME
        prepared = marker.read_text(encoding="ascii")
        prefix = "prepared:"
        if not prepared.startswith(prefix) or not prepared.endswith("\n"):
            raise ValueError(f"invalid prepared commit marker: {marker}")
        transaction_token = prepared[len(prefix) : -1]
        OutputBundleWriter._write_commit_marker(
            backup, transaction_token, committed=True
        )

    @staticmethod
    def _matches_file_identity(path: Path, expected: os.stat_result) -> bool:
        try:
            actual = path.stat(follow_symlinks=False)
        except OSError:
            return False
        return os.path.samestat(expected, actual)

    @staticmethod
    def _remove_owned_directory(directory: Path) -> None:
        if not directory.exists():
            return
        for name in REQUIRED_OUTPUT_NAMES:
            (directory / name).unlink(missing_ok=True)
        (directory / _COMMIT_MARKER_NAME).unlink(missing_ok=True)
        directory.rmdir()
