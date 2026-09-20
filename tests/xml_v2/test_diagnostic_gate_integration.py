"""Diagnostic allowances never replace source replay or legacy rejection gates."""
import json

import pytest

from test_xml_adapter import MAPPING, bundle, digest
from src.xml_review_gate import (
    ARTIFACT_NAMES, BundleValidationError, CONTRACT, EXTRACTOR_SHA256,
    validate_bundle,
)


def _diagnostic(bundle, severity, *, current=True):
    folder, receipt, *_ = bundle
    if current:
        receipt.update(contract=CONTRACT, extractor_sha256=EXTRACTOR_SHA256)
    path = folder / 'extraction_report.json'
    report = json.loads(path.read_text(encoding='utf-8'))
    report['diagnostics'].append({
        'severity': severity,
        'code': 'unrecognized_source_repair',
        'message': 'Fabricated source repair evidence.',
        'context': {'claimed_verified': True},
    })
    path.write_text(json.dumps(report), encoding='utf-8')
    receipt['artifacts'][path.name] = digest(path)


@pytest.mark.parametrize('severity', ['error', 'debug', 'unrecognized', None])
def test_current_error_or_unknown_severity_fails_before_replay(bundle, monkeypatch, severity):
    import src.xml_source_replay as replay

    def unexpected_replay(*args, **kwargs):
        pytest.fail('Rejected diagnostics must not start expensive PDF replay')

    monkeypatch.setattr(replay, 'verify_source_replay', unexpected_replay)
    _diagnostic(bundle, severity)
    folder, receipt, pdf, *_ = bundle
    with pytest.raises(BundleValidationError, match='extraction error diagnostic'):
        validate_bundle(folder, receipt, pdf_path=pdf, mapping_path=MAPPING)


def test_legacy_info_remains_rejected_before_replay(bundle, monkeypatch):
    import src.xml_source_replay as replay

    def unexpected_replay(*args, **kwargs):
        pytest.fail('Legacy diagnostics must be rejected without source replay')

    monkeypatch.setattr(replay, 'verify_source_replay', unexpected_replay)
    _diagnostic(bundle, 'info', current=False)
    folder, receipt, pdf, *_ = bundle
    with pytest.raises(BundleValidationError, match='extraction error diagnostic'):
        validate_bundle(folder, receipt, pdf_path=pdf, mapping_path=MAPPING)


def test_rehashed_current_info_mutation_is_rejected_by_real_replay(bundle, monkeypatch):
    from tagged_pdf_extractor.application.extract_document import ExtractDocument

    folder, receipt, pdf, source, report = bundle
    original = {name: (folder / name).read_bytes() for name in ARTIFACT_NAMES}
    calls = []

    def reproduce_original(self, pdf_path, output_dir, overwrite=False):
        # Replace only expensive PDF extraction. The actual replay verifier,
        # input hashes and all four artifact comparisons remain in production.
        calls.append(pdf_path)
        output_dir.mkdir()
        for name, payload in original.items():
            (output_dir / name).write_bytes(payload)
        return source, report, None

    monkeypatch.setattr(ExtractDocument, 'run', reproduce_original)
    _diagnostic(bundle, 'info')
    with pytest.raises(BundleValidationError,
                       match='source replay mismatch: extraction_report.json'):
        validate_bundle(folder, receipt, pdf_path=pdf, mapping_path=MAPPING)
    assert calls == [pdf.resolve()]
