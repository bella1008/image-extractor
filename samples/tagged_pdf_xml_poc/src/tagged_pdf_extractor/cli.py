from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TextIO
from xml.etree import ElementTree as ET

from tagged_pdf_extractor.application.evaluate_quality import (
    QualityEvaluationLimitError,
    QualityEvaluator,
)
from tagged_pdf_extractor.application.extract_document import ExtractDocument
from tagged_pdf_extractor.infrastructure.output_bundle import (
    BundlePublicationErrorGroup,
    BundlePublicationStateError,
    BundleRollbackError,
    BundleTransactionError,
    OutputBusyError,
    OutputBundleWriter,
    OutputCollisionError,
)
from tagged_pdf_extractor.infrastructure.json_profile_repository import (
    JsonProfileRepository,
)
from tagged_pdf_extractor.infrastructure.pymupdf_baseline import (
    PyMuPdfBaselineReader,
)
from tagged_pdf_extractor.infrastructure.pypdf_reader import (
    TaggedPdfError,
    TaggedPdfReader,
)
from tagged_pdf_extractor.ports.profile_repository import (
    ProfileMappingFileError,
    ProfileRepositoryError,
)


_PROFILE_MAPPING_RELATIVE_PATH = (
    Path("metadata")
    / "pdf_profile_mapping"
    / "pdf_profile_mapping.json"
)


_EXPECTED_ERRORS = (
    OSError,
    TaggedPdfError,
    OutputCollisionError,
    OutputBusyError,
    QualityEvaluationLimitError,
    BundleRollbackError,
    BundleTransactionError,
    BundlePublicationStateError,
    ET.ParseError,
    ValueError,
    TypeError,
    ProfileRepositoryError,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extract tagged PDF structure to auditable XML"
    )
    parser.add_argument("pdf", type=Path, help="source tagged PDF")
    parser.add_argument(
        "--output", type=Path, required=True, help="artifact output directory"
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="replace only the four required artifacts if they exist",
    )
    return parser


def _configure_utf8(stream: TextIO) -> None:
    reconfigure = getattr(stream, "reconfigure", None)
    if callable(reconfigure):
        reconfigure(encoding="utf-8", errors="backslashreplace")


def _resolve_profile_mapping_path(
    profile_mapping_path: str | Path | None = None,
    *,
    repository_root: str | Path | None = None,
    module_file: str | Path | None = None,
) -> Path:
    if profile_mapping_path is not None:
        if repository_root is not None:
            raise ValueError(
                "profile_mapping_path and repository_root are mutually exclusive"
            )
        return Path(profile_mapping_path)

    if repository_root is not None:
        candidate = Path(repository_root).resolve() / _PROFILE_MAPPING_RELATIVE_PATH
        if not candidate.is_file():
            raise ProfileMappingFileError(
                "Canonical PDF profile mapping was not found under repository root: "
                f"{_PROFILE_MAPPING_RELATIVE_PATH.as_posix()}"
            )
        return candidate

    anchor = Path(module_file) if module_file is not None else Path(__file__)
    module_path = anchor.resolve()
    search_roots: list[Path] = []
    for parent in module_path.parents:
        search_roots.append(parent)
        if (parent / ".git").exists():
            break
    candidates = tuple(
        parent / _PROFILE_MAPPING_RELATIVE_PATH
        for parent in search_roots
        if (parent / _PROFILE_MAPPING_RELATIVE_PATH).is_file()
    )
    portable_relative_path = _PROFILE_MAPPING_RELATIVE_PATH.as_posix()
    if not candidates:
        raise ProfileMappingFileError(
            "Canonical PDF profile mapping was not found in module ancestors: "
            f"{portable_relative_path}"
        )
    if len(candidates) != 1:
        raise ProfileMappingFileError(
            "Canonical PDF profile mapping is ambiguous across module ancestors: "
            f"{portable_relative_path}"
        )
    return candidates[0]


def _build_use_case(
    profile_mapping_path: str | Path | None = None,
) -> ExtractDocument:
    mapping_path = _resolve_profile_mapping_path(profile_mapping_path)
    return ExtractDocument(
        TaggedPdfReader(),
        PyMuPdfBaselineReader(),
        QualityEvaluator(),
        OutputBundleWriter(),
        JsonProfileRepository(mapping_path),
    )


def _format_exception_group(group: BundlePublicationErrorGroup) -> str:
    leaves: list[str] = []

    def collect(error: Exception) -> None:
        if isinstance(error, ExceptionGroup):
            for nested in error.exceptions:
                collect(nested)
            return
        message = " ".join(str(error).split())
        leaves.append(
            f"{type(error).__name__}: {message}" if message else type(error).__name__
        )

    collect(group)
    return " | ".join(leaves)


def main(argv: list[str] | None = None) -> int:
    _configure_utf8(sys.stdout)
    _configure_utf8(sys.stderr)
    args = build_parser().parse_args(argv)

    try:
        _, report, artifacts = _build_use_case().run(
            args.pdf, args.output, args.overwrite
        )
    except BundlePublicationErrorGroup as exc:
        print(
            f"error: output transaction failed: {_format_exception_group(exc)}",
            file=sys.stderr,
        )
        return 2
    except _EXPECTED_ERRORS as exc:
        if getattr(exc, "published", False):
            committed_artifacts = getattr(exc, "artifacts", None)
            report_path = (
                committed_artifacts.report_json
                if committed_artifacts is not None
                else args.output / "extraction_report.json"
            )
            print(
                "error: outputs committed, but transaction cleanup failed; "
                f"report: {report_path}; details: {exc}",
                file=sys.stderr,
            )
        else:
            print(f"error: {exc}", file=sys.stderr)
        return 2

    completion = (
        "hard gates passed"
        if report.status == "pass"
        else "extraction completed; one or more hard gates failed"
    )
    print(f"status: {report.status} ({completion})")
    print(f"report: {artifacts.report_json}")
    return 0 if report.status == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
