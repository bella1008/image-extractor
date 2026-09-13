"""One extraction shared by real observation services and one verified report."""
from dataclasses import replace
import importlib
import json
from pathlib import Path
import shutil

import pytest

from tests.test_item_review_service import checked_bundle
from tests.test_combined_review_service import builder


def api():
    assert importlib.util.find_spec('src.combined_review_run'), 'combined PDF workflow missing'
    return importlib.import_module('src.combined_review_run')


def request(tmp_path, checked_bundle, monkeypatch):
    from src import combined_review_service
    monkeypatch.setattr(combined_review_service, '_run_builder', builder)
    folder, _, pdf, *_ = checked_bundle
    return api().CombinedReviewRequest(pdf, tmp_path / 'combined', Path('node'), Path('modules'), bundle=folder)


def test_reuse_shares_one_receipt_without_extracting(tmp_path, checked_bundle, monkeypatch):
    from src import xml_review_run
    def forbidden(*args):
        pytest.fail('reuse must not extract PDF')
    monkeypatch.setattr(xml_review_run, 'extract_review_document', forbidden)
    req = request(tmp_path, checked_bundle, monkeypatch)
    api().run_combined_review(req)
    from src.combined_review_service import read_completed_combined_review
    report = read_completed_combined_review(req.output_dir)['report']
    assert report['summary']['parent_check_count'] == 59
    assert report['summary']['child_item_count'] == 14
    assert report['checklist']['inputs']['receipt_sha256'] == report['items']['inputs']['receipt_sha256']
    assert not list(req.output_dir.rglob('*.html'))
    receipt = json.loads(report['source_runs']['checklist']['review_complete.json'])
    assert receipt['schema_version'] == 'review-observation-run/2'
    assert not (req.output_dir / 'review_workflow.lock').exists()


def test_fresh_pdf_extracts_once_and_preserves_md(tmp_path, checked_bundle, monkeypatch):
    from src import xml_review_run
    req = replace(request(tmp_path, checked_bundle, monkeypatch), bundle=None)
    calls = []
    def extract(pdf, folder, mapping):
        calls.append(pdf)
        shutil.copytree(checked_bundle[0], folder)
    monkeypatch.setattr(xml_review_run, 'extract_review_document', extract)
    api().run_combined_review(req)
    assert calls == [req.pdf]
    assert (req.output_dir / '_internal/extraction/semantic_document.md').read_bytes() == (checked_bundle[0] / 'semantic_document.md').read_bytes()


def test_existing_output_is_preserved(tmp_path, checked_bundle, monkeypatch):
    req = request(tmp_path, checked_bundle, monkeypatch)
    req.output_dir.mkdir()
    sentinel = req.output_dir / 'existing.txt'
    sentinel.write_bytes(b'existing user output')
    with pytest.raises(FileExistsError):
        api().run_combined_review(req)
    assert list(req.output_dir.iterdir()) == [sentinel]
    assert sentinel.read_bytes() == b'existing user output'


@pytest.mark.parametrize('failure', ['extraction', 'items', 'changed_pdf', 'publication'])
def test_workflow_failure_never_exposes_completed_output(tmp_path, checked_bundle, monkeypatch, failure):
    from src import item_review_service, xml_review_run, combined_review_service
    req = request(tmp_path, checked_bundle, monkeypatch)
    def broken(*args):
        raise ValueError('injected failure')
    if failure == 'extraction':
        req = replace(req, bundle=None)
        monkeypatch.setattr(xml_review_run, 'extract_review_document', broken)
    elif failure == 'items':
        monkeypatch.setattr(item_review_service, 'run_item_review', broken)
    elif failure == 'changed_pdf':
        def changed(view, output, *args):
            builder(view, output, *args)
            req.pdf.write_bytes(b'changed PDF')
        monkeypatch.setattr(combined_review_service, '_run_builder', changed)
    else:
        original = combined_review_service.os.link
        def changed(src, dst):
            original(src, dst)
            if Path(dst).name == 'review_report_complete.json':
                req.pdf.write_bytes(b'changed after publication')
        monkeypatch.setattr(combined_review_service.os, 'link', changed)
    with pytest.raises(ValueError):
        api().run_combined_review(req)
    assert (req.output_dir / 'review_report_failed.json').exists()
    assert not (req.output_dir / 'review_report_complete.json').exists()
    with pytest.raises((OSError, ValueError)):
        combined_review_service.read_completed_combined_review(req.output_dir)


def test_reader_rejects_workflow_still_running(tmp_path, checked_bundle, monkeypatch):
    from src.combined_review_service import read_completed_combined_review
    req = request(tmp_path, checked_bundle, monkeypatch)
    api().run_combined_review(req)
    (req.output_dir / 'review_workflow.lock').write_text('running')
    with pytest.raises(ValueError, match='active'):
        read_completed_combined_review(req.output_dir)
