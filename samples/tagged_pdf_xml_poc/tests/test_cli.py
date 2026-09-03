from pathlib import Path

import pytest

from tagged_pdf_extractor.domain.models import ExtractionArtifacts, QualityReport
from tagged_pdf_extractor.infrastructure.output_bundle import (
    BundleTransactionError,
    OutputCollisionError,
)


def _artifacts(root: Path) -> ExtractionArtifacts:
    return ExtractionArtifacts(
        root / "raw_structure.xml",
        root / "semantic_document.xml",
        root / "extraction_report.json",
    )


def _install_result(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, status: str) -> None:
    from tagged_pdf_extractor import cli

    report = QualityReport(status, {}, {"has_heading": status == "pass"}, ())
    artifacts = _artifacts(tmp_path / "한글 결과")
    monkeypatch.setattr(
        cli.ExtractDocument,
        "run",
        lambda self, pdf, output, overwrite=False: (object(), report, artifacts),
    )


def test_cli_requires_pdf_and_output_paths() -> None:
    from tagged_pdf_extractor.cli import build_parser

    args = build_parser().parse_args(["manual.pdf", "--output", "out"])
    assert args.pdf == Path("manual.pdf")
    assert args.output == Path("out")
    assert args.overwrite is False


def test_cli_forwards_overwrite_and_returns_zero_for_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from tagged_pdf_extractor import cli

    calls: list[tuple[Path, Path, bool]] = []
    report = QualityReport("pass", {}, {"has_heading": True}, ())
    artifacts = _artifacts(tmp_path / "결과")

    def run(self, pdf: Path, output: Path, overwrite: bool = False):
        calls.append((pdf, output, overwrite))
        return object(), report, artifacts

    monkeypatch.setattr(cli.ExtractDocument, "run", run)

    result = cli.main(["입력.pdf", "--output", "결과", "--overwrite"])

    assert result == 0
    assert calls == [(Path("입력.pdf"), Path("결과"), True)]
    captured = capsys.readouterr()
    assert "status: pass" in captured.out
    assert str(artifacts.report_json) in captured.out
    assert captured.err == ""


def test_cli_returns_one_when_extraction_completes_but_hard_gate_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from tagged_pdf_extractor import cli

    _install_result(monkeypatch, tmp_path, "fail")

    result = cli.main(["manual.pdf", "--output", "out"])

    assert result == 1
    captured = capsys.readouterr()
    assert "status: fail" in captured.out
    assert "extraction completed" in captured.out
    assert captured.err == ""


@pytest.mark.parametrize(
    "error",
    [
        OSError("cannot read PDF"),
        OutputCollisionError("required output already exists"),
    ],
)
def test_cli_returns_two_for_expected_operational_errors(
    error: Exception,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from tagged_pdf_extractor import cli

    def fail(self, pdf: Path, output: Path, overwrite: bool = False):
        raise error

    monkeypatch.setattr(cli.ExtractDocument, "run", fail)

    assert cli.main(["manual.pdf", "--output", "out"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert f"error: {error}" in captured.err


def test_cli_reports_when_outputs_were_committed_before_cleanup_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from tagged_pdf_extractor import cli

    artifacts = _artifacts(tmp_path / "완료된 결과")
    transaction_error = BundleTransactionError(
        None,
        ((tmp_path / ".result.lock", OSError("cleanup failed")),),
        published=True,
        artifacts=artifacts,
    )

    def fail(self, pdf: Path, output: Path, overwrite: bool = False):
        raise transaction_error

    monkeypatch.setattr(cli.ExtractDocument, "run", fail)

    assert cli.main(["manual.pdf", "--output", "out"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "outputs committed" in captured.err
    assert "cleanup" in captured.err
    assert str(artifacts.report_json) in captured.err


def test_cli_does_not_swallow_keyboard_interrupt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tagged_pdf_extractor import cli

    def interrupt(self, pdf: Path, output: Path, overwrite: bool = False):
        raise KeyboardInterrupt

    monkeypatch.setattr(cli.ExtractDocument, "run", interrupt)

    with pytest.raises(KeyboardInterrupt):
        cli.main(["manual.pdf", "--output", "out"])

