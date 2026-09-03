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
    BundlePublicationStateError,
    BundleRollbackError,
    BundleTransactionError,
    OutputBusyError,
    OutputBundleWriter,
    OutputCollisionError,
)
from tagged_pdf_extractor.infrastructure.pymupdf_baseline import (
    PyMuPdfBaselineReader,
)
from tagged_pdf_extractor.infrastructure.pypdf_reader import (
    TaggedPdfError,
    TaggedPdfReader,
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
        help="replace only the three required artifacts if they exist",
    )
    return parser


def _configure_utf8(stream: TextIO) -> None:
    reconfigure = getattr(stream, "reconfigure", None)
    if callable(reconfigure):
        reconfigure(encoding="utf-8", errors="backslashreplace")


def _build_use_case() -> ExtractDocument:
    return ExtractDocument(
        TaggedPdfReader(),
        PyMuPdfBaselineReader(),
        QualityEvaluator(),
        OutputBundleWriter(),
    )


def main(argv: list[str] | None = None) -> int:
    _configure_utf8(sys.stdout)
    _configure_utf8(sys.stderr)
    args = build_parser().parse_args(argv)

    try:
        _, report, artifacts = _build_use_case().run(
            args.pdf, args.output, args.overwrite
        )
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
