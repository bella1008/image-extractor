"""User-facing output contract and archival integrity regressions."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from tests.test_item_review_service import checked_bundle, request_for
from tests.test_item_review_excel import report, fake_builder


@pytest.fixture
def run(tmp_path, checked_bundle):
    from src.item_review_service import run_item_review
    request = request_for(tmp_path, checked_bundle)
    run_item_review(request)
    return request.output_dir


def test_new_observation_requires_json_only(run):
    from src.item_review_service import read_completed_item_review
    receipt = json.loads((run / 'item_review_complete.json').read_bytes())
    assert set(receipt['artifacts']) == {'item_observation.json'}
    assert not (run / 'item_review.html').exists()
    assert read_completed_item_review(run)['summary']['item_count'] == 14


def test_legacy_receipt_still_checks_its_html(run):
    from src.item_review_service import read_completed_item_review
    html = run / 'item_review.html'
    html.write_text('archived HTML', encoding='utf-8')
    path = run / 'item_review_complete.json'
    receipt = json.loads(path.read_bytes())
    receipt['schema_version'] = 'checklist-item-observation-run/1'
    receipt['artifacts'][html.name] = hashlib.sha256(html.read_bytes()).hexdigest()
    path.write_text(json.dumps(receipt), encoding='utf-8')
    assert read_completed_item_review(run)['summary']['item_count'] == 14
    html.write_text('changed', encoding='utf-8')
    with pytest.raises(ValueError):
        read_completed_item_review(run)


def test_reduced_workbook_keeps_all_evidence_and_internal_source_data():
    from src.item_review_excel import build_item_excel_view
    data = report()
    before = deepcopy(data)
    summary, items, evidence = build_item_excel_view(data)['sheets']
    assert len(summary['rows']) == 11
    assert summary['rows'][-1] == ['검토 대상', 'PDF 파일', 'current.pdf']
    assert items['headers'] == ['고정 항목 키', '기준 문구', '검토 판정', '설명', '검토 메모',
                                '원장 모델 조건 제안', '원장 제안 근거', '원장 검토 메모']
    assert evidence['headers'] == ['고정 항목 키', '근거 종류', '현재 원문', '현재 노드 ID',
                                   '태그 종류', 'PDF 페이지', 'XML 경로', '상세 근거 JSON']
    assert len(items['rows']) == 14 and len(evidence['rows']) == 26
    actual = [(row[0], row[1], json.loads(row[-1])) for row in evidence['rows']]
    expected = [(item['item_key'], kind, window) for item in data['items']
                for field, kind in [('candidates', '항목 문구'), ('condition_candidates', '조건 안내 후보')]
                for window in item[field]]
    assert json.loads(json.dumps(actual)) == json.loads(json.dumps(expected))
    assert data == before and 'pdf_sha256' in data['target_source']


def test_same_folder_export_leaves_observation_bytes_unchanged(run, monkeypatch):
    import src.item_review_excel as api
    from src.item_review_ui import load_item_review_screen
    before = {path: path.read_bytes() for path in run.iterdir() if path.is_file()}
    monkeypatch.setattr(api, '_run_builder', fake_builder)
    api.export_item_review_excel(run, Path('node'), Path('modules'))
    content = (run / 'item_review.xlsx').read_bytes()
    assert api.read_completed_item_excel(run) == content
    screen = load_item_review_screen(run)
    assert set(screen) == {'report', 'json_bytes', 'excel_bytes'}
    assert screen['excel_bytes'] == content
    assert all(path.read_bytes() == value for path, value in before.items())
    with pytest.raises(FileExistsError):
        api.export_item_review_excel(run, Path('node'), Path('modules'))
    assert api.read_completed_item_excel(run) == content


@pytest.mark.parametrize('name', ['item_review.xlsx', 'item_excel_view.json',
                                'item_excel_complete.json', 'item_excel_failed.json',
                                'item_excel_complete.pending.json', 'item_excel.lock'])
def test_existing_excel_artifacts_are_never_overwritten(run, monkeypatch, name):
    import src.item_review_excel as api
    monkeypatch.setattr(api, '_run_builder', fake_builder)
    (run / name).write_bytes(b'existing')
    before = {path: path.read_bytes() for path in run.iterdir() if path.is_file()}
    with pytest.raises(FileExistsError):
        api.export_item_review_excel(run, Path('node'), Path('modules'))
    assert {path: path.read_bytes() for path in run.iterdir() if path.is_file()} == before


@pytest.mark.parametrize('name', ['item_review.xlsx', 'item_excel_view.json', 'item_excel_failed.json',
                                'item_excel_complete.pending.json', 'item_excel.lock'])
def test_partial_excel_is_not_silently_treated_as_absent(run, name):
    from src.item_review_ui import load_item_review_screen
    (run / name).write_bytes(b'partial')
    with pytest.raises(ValueError, match='Excel'):
        load_item_review_screen(run)


def test_single_folder_screen_has_no_html_download(run):
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'scripts/item_review_app.py'), default_timeout=15).run()
    assert len(app.text_input) == 1
    app.text_input[0].set_value(str(run))
    app.button[0].click().run()
    assert not app.exception and not app.error
    assert [button.label for button in app.get('download_button')] == ['JSON 다운로드']
    assert len(app.dataframe[0].value) == 14
