import os
from pathlib import Path

import pytest


HEADING_ONLY_FAILURE_HARD_GATES = {
    "is_marked": True,
    "has_structure": True,
    "has_heading": False,
    "has_body": True,
    "xml_round_trip": True,
    "resolved_references": True,
    "resolved_references_reported": True,
    "no_known_text_loss": True,
    "no_forbidden_xml_controls": True,
    "special_character_counts_preserved": True,
    "numbered_heading_series_valid": True,
    "numbered_heading_series_counts_consistent": True,
    "numbered_heading_typography_valid": True,
    "multilingual_interval_count_valid": True,
    "multilingual_heading_count_parity": True,
    "multilingual_heading_level_parity": True,
    "multilingual_heading_origin_parity": True,
    "multilingual_numbered_label_parity": True,
}


def require_sample(
    path: Path | None,
    sample: str,
    *,
    required: bool | None = None,
) -> Path:
    if path is not None:
        return path
    if required is None:
        required = os.environ.get("TAGGED_PDF_REQUIRE_SAMPLES") == "1"
    message = f"{sample} tagged PDF sample is not available"
    if required:
        pytest.fail(message)
    pytest.skip(message)


def assert_heading_only_failure(report) -> None:
    assert report.hard_gates == HEADING_ONLY_FAILURE_HARD_GATES
    assert [name for name, passed in report.hard_gates.items() if not passed] == [
        "has_heading"
    ]
    assert report.status == "fail"
    assert report.diagnostics == ()
    assert report.metrics["extraction_loss_diagnostic_total"] == 0
