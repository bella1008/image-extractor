import json
from pathlib import Path

import pytest

from tagged_pdf_extractor.application.extract_document import ExtractDocument
from tagged_pdf_extractor.domain.models import (
    ExtractionArtifacts,
    HeadingPromotion,
    QualityReport,
    TaggedDocument,
)
from tagged_pdf_extractor.infrastructure.output_bundle import (
    BundlePublicationErrorGroup,
    BundleTransactionError,
    OutputCollisionError,
)
from tagged_pdf_extractor.ports.output_writer import OutputValidation


def _artifacts(root: Path) -> ExtractionArtifacts:
    return ExtractionArtifacts(
        root / "raw_structure.xml",
        root / "semantic_document.xml",
        root / "extraction_report.json",
        root / "semantic_document.md",
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


def test_extract_document_promotes_once_and_passes_promoted_document_everywhere(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import tagged_pdf_extractor.application.extract_document as use_case_module

    source = tmp_path / "source.pdf"
    source.write_bytes(b"pdf")
    output = tmp_path / "out"
    original = TaggedDocument(source, True, "en", (), ())
    promotion = HeadingPromotion(
        child_path=(0,),
        level=2,
        label="01",
        title="Package Content",
        series_index=0,
        heading_font_size=12.0,
        body_font_size=8.0,
        font_size_ratio=1.5,
        promotion_reason="numbered_chapter_structure_sequence_typography",
    )
    promoted = TaggedDocument(
        source,
        True,
        "en",
        (),
        (),
        heading_promotions=(promotion,),
    )
    report = QualityReport(
        "pass", {}, {"has_heading": True}, (), ({"element_path": "/"},)
    )
    artifacts = _artifacts(output)
    promotion_calls: list[TaggedDocument] = []
    observed: list[tuple[str, object]] = []

    def promote(document: TaggedDocument) -> TaggedDocument:
        promotion_calls.append(document)
        return promoted

    monkeypatch.setattr(
        use_case_module, "promote_numbered_chapter_headings", promote
    )

    class Reader:
        def read(self, path: Path) -> TaggedDocument:
            observed.append(("read", path))
            return original

    class Baseline:
        def read_text(self, path: Path) -> str:
            observed.append(("baseline", path))
            return "baseline"

    class Evaluator:
        def evaluate(
            self,
            document: TaggedDocument,
            baseline: str,
            xml_round_trip_ok: bool,
        ) -> QualityReport:
            observed.append(
                ("evaluate", (document, baseline, xml_round_trip_ok))
            )
            return report

    class Writer:
        def validate(self, document: TaggedDocument) -> OutputValidation:
            observed.append(("validate", document))
            return OutputValidation(report.join_decisions)

        def write(
            self,
            document: TaggedDocument,
            actual_report: QualityReport,
            output_dir: Path,
            overwrite: bool = False,
        ) -> ExtractionArtifacts:
            observed.append(
                ("write", (document, actual_report, output_dir, overwrite))
            )
            return artifacts

    result = ExtractDocument(Reader(), Baseline(), Evaluator(), Writer()).run(
        source, output, overwrite=True
    )

    assert promotion_calls == [original]
    assert original.heading_promotions == ()
    assert result == (promoted, report, artifacts)
    assert observed == [
        ("read", source),
        ("baseline", source),
        ("validate", promoted),
        ("evaluate", (promoted, "baseline", True)),
        ("write", (promoted, report, output, True)),
    ]


def test_cli_requires_pdf_and_output_paths() -> None:
    from tagged_pdf_extractor.cli import build_parser

    args = build_parser().parse_args(["manual.pdf", "--output", "out"])
    assert args.pdf == Path("manual.pdf")
    assert args.output == Path("out")
    assert args.overwrite is False


def test_cli_help_describes_four_overwritten_artifacts() -> None:
    from tagged_pdf_extractor.cli import build_parser

    help_text = build_parser().format_help()

    assert "replace only the four required artifacts if they exist" in help_text
    assert "three required artifacts" not in help_text


def test_cli_returns_two_for_reader_translated_decoder_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from tagged_pdf_extractor import cli
    from tagged_pdf_extractor.infrastructure.pypdf_operation_text import (
        PypdfOperationTextError,
    )
    from tagged_pdf_extractor.infrastructure.pypdf_reader import TaggedPdfError

    decoder_error = PypdfOperationTextError("decoder state failed")
    translated = TaggedPdfError(
        "Failed to decode tagged text on page index 0: decoder state failed"
    )
    translated.__cause__ = decoder_error

    class FailingUseCase:
        def run(self, pdf: Path, output: Path, overwrite: bool = False):
            raise translated

    output = tmp_path / "out"
    monkeypatch.setattr(cli, "_build_use_case", lambda: FailingUseCase())

    assert cli.main(["manual.pdf", "--output", str(output)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == (
        "error: Failed to decode tagged text on page index 0: decoder state failed\n"
    )
    assert "Traceback" not in captured.err
    assert not output.exists()


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


def test_cli_returns_two_for_nested_output_transaction_exception_group(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from tagged_pdf_extractor import cli

    transaction_error = BundlePublicationErrorGroup(
        "publication failed",
        [
            OSError("replace failed"),
            ExceptionGroup(
                "rollback failed",
                [ValueError("invalid marker"), RuntimeError("cleanup failed")],
            ),
        ],
    )

    def fail(self, pdf: Path, output: Path, overwrite: bool = False):
        raise transaction_error

    monkeypatch.setattr(cli.ExtractDocument, "run", fail)

    assert cli.main(["manual.pdf", "--output", "out"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "output transaction failed" in captured.err
    assert "OSError: replace failed" in captured.err
    assert "ValueError: invalid marker" in captured.err
    assert "RuntimeError: cleanup failed" in captured.err
    assert "Traceback" not in captured.err
    assert captured.err.count("\n") == 1


def test_cli_does_not_swallow_untyped_exception_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tagged_pdf_extractor import cli

    unexpected = ExceptionGroup(
        "reader invariant failed",
        [AssertionError("unexpected reader state")],
    )

    def fail(self, pdf: Path, output: Path, overwrite: bool = False):
        raise unexpected

    monkeypatch.setattr(cli.ExtractDocument, "run", fail)

    with pytest.raises(ExceptionGroup) as captured:
        cli.main(["manual.pdf", "--output", "out"])
    assert captured.value is unexpected


def test_cli_does_not_swallow_base_exception_group_with_keyboard_interrupt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tagged_pdf_extractor import cli

    transaction_interrupt = BaseExceptionGroup(
        "publication interrupted",
        [OSError("replace failed"), KeyboardInterrupt()],
    )

    def interrupt(self, pdf: Path, output: Path, overwrite: bool = False):
        raise transaction_interrupt

    monkeypatch.setattr(cli.ExtractDocument, "run", interrupt)

    with pytest.raises(BaseExceptionGroup) as captured:
        cli.main(["manual.pdf", "--output", "out"])
    assert captured.value is transaction_interrupt


def test_cli_does_not_swallow_keyboard_interrupt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tagged_pdf_extractor import cli

    def interrupt(self, pdf: Path, output: Path, overwrite: bool = False):
        raise KeyboardInterrupt

    monkeypatch.setattr(cli.ExtractDocument, "run", interrupt)

    with pytest.raises(KeyboardInterrupt):
        cli.main(["manual.pdf", "--output", "out"])


def test_build_use_case_accepts_injected_profile_mapping_path(tmp_path: Path) -> None:
    from tagged_pdf_extractor import cli
    from tagged_pdf_extractor.infrastructure.json_profile_repository import (
        JsonProfileRepository,
    )

    mapping = tmp_path / "profiles.json"
    mapping.write_text(
        json.dumps(
            [
                {
                    "source_token": "XX_ENG",
                    "languages": "ENG",
                    "doc_type": "A3",
                    "language_count": 1,
                }
            ]
        ),
        encoding="utf-8",
    )

    use_case = cli._build_use_case(mapping)

    assert isinstance(use_case.profile_repository, JsonProfileRepository)
    assert use_case.profile_repository._mapping_path == mapping


def test_profile_mapping_search_uses_only_module_ancestors(tmp_path: Path) -> None:
    from tagged_pdf_extractor import cli

    repository_root = tmp_path / "repository"
    module_file = repository_root / "package" / "src" / "cli.py"
    module_file.parent.mkdir(parents=True)
    module_file.write_text("", encoding="utf-8")
    mapping = (
        repository_root
        / "metadata"
        / "pdf_profile_mapping"
        / "pdf_profile_mapping.json"
    )
    mapping.parent.mkdir(parents=True)
    mapping.write_text("[]", encoding="utf-8")
    misleading = tmp_path / "misleading" / "metadata" / "pdf_profile_mapping"
    misleading.mkdir(parents=True)
    (misleading / "pdf_profile_mapping.json").write_text("[]", encoding="utf-8")

    assert cli._resolve_profile_mapping_path(module_file=module_file) == mapping


def test_profile_mapping_search_accepts_explicit_repository_root(
    tmp_path: Path,
) -> None:
    from tagged_pdf_extractor import cli

    repository_root = tmp_path / "repository"
    mapping = (
        repository_root
        / "metadata"
        / "pdf_profile_mapping"
        / "pdf_profile_mapping.json"
    )
    mapping.parent.mkdir(parents=True)
    mapping.write_text("[]", encoding="utf-8")

    assert (
        cli._resolve_profile_mapping_path(repository_root=repository_root)
        == mapping
    )


def test_profile_mapping_search_reports_stable_missing_error(tmp_path: Path) -> None:
    from tagged_pdf_extractor import cli
    from tagged_pdf_extractor.ports.profile_repository import ProfileMappingFileError

    module_file = tmp_path / "repository" / "package" / "cli.py"
    module_file.parent.mkdir(parents=True)
    module_file.write_text("", encoding="utf-8")

    with pytest.raises(
        ProfileMappingFileError,
        match=(
            "Canonical PDF profile mapping was not found in module ancestors: "
            "metadata/pdf_profile_mapping/pdf_profile_mapping.json"
        ),
    ):
        cli._resolve_profile_mapping_path(module_file=module_file)


def test_profile_mapping_search_reports_stable_ambiguous_error(tmp_path: Path) -> None:
    from tagged_pdf_extractor import cli
    from tagged_pdf_extractor.ports.profile_repository import ProfileMappingFileError

    repository_root = tmp_path / "repository"
    package_root = repository_root / "package"
    module_file = package_root / "src" / "cli.py"
    module_file.parent.mkdir(parents=True)
    module_file.write_text("", encoding="utf-8")
    for root in (repository_root, package_root):
        mapping = root / "metadata" / "pdf_profile_mapping"
        mapping.mkdir(parents=True)
        (mapping / "pdf_profile_mapping.json").write_text("[]", encoding="utf-8")

    with pytest.raises(
        ProfileMappingFileError,
        match=(
            "Canonical PDF profile mapping is ambiguous across module ancestors: "
            "metadata/pdf_profile_mapping/pdf_profile_mapping.json"
        ),
    ):
        cli._resolve_profile_mapping_path(module_file=module_file)


@pytest.mark.parametrize("kind", ["unknown", "malformed"])
def test_cli_returns_two_for_typed_profile_lookup_errors(
    kind: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from tagged_pdf_extractor import cli
    from tagged_pdf_extractor.ports.profile_repository import (
        InvalidPdfFilenameError,
        UnknownSourceTokenError,
    )

    error = (
        UnknownSourceTokenError("No canonical PDF profile for source_token 'XX_L02'")
        if kind == "unknown"
        else InvalidPdfFilenameError(
            "Cannot derive valid source_token from PDF filename 'manual.pdf'"
        )
    )

    class FailingUseCase:
        def run(self, pdf: Path, output: Path, overwrite: bool = False):
            raise error

    monkeypatch.setattr(cli, "_build_use_case", lambda: FailingUseCase())

    assert cli.main(["manual.pdf", "--output", "out"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == f"error: {error}\n"
