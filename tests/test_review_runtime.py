import sys

import pytest

from src.review_service import validate_extraction_environment


def test_wrong_pdf_library_version_is_rejected_before_extraction(monkeypatch):
    import src.review_service as service
    monkeypatch.setattr(service, 'package_version', lambda name: '6.10.0')
    with pytest.raises(ValueError, match='6.16.2'):
        validate_extraction_environment()


def test_pinned_pdf_library_version_is_accepted(monkeypatch):
    import src.review_service as service
    monkeypatch.setattr(service, 'package_version', lambda name: '6.16.2')
    validate_extraction_environment()


def test_cli_reports_extractor_errors_without_a_false_success(monkeypatch, capsys):
    from scripts import run_review_v2 as command
    monkeypatch.setattr(sys, 'argv', ['run_review_v2', 'sample.pdf', '--output', 'fresh'])
    def fail(request):
        raise RuntimeError('PDF decoder fixture failure')
    monkeypatch.setattr(command, 'run_review', fail)
    with pytest.raises(SystemExit) as error:
        command.main()
    assert error.value.code == 1
    assert 'no business decision issued' in capsys.readouterr().err
