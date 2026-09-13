from copy import deepcopy
import importlib
import json
from pathlib import Path
import shutil
import pytest

from tests.test_combined_review_model import combined_inputs
from tests.test_item_review_service import checked_bundle
from tests.test_item_review_excel import workbook_fixture


def api():
    assert importlib.util.find_spec('src.combined_review_service'), 'combined export service missing'
    return importlib.import_module('src.combined_review_service')


def builder(view_path, output, *args):
    workbook_fixture(output/'review_report.xlsx', json.loads(view_path.read_bytes()))


def export(tmp_path, monkeypatch):
    service=api()
    monkeypatch.setattr(service,'_run_builder',builder)
    output=tmp_path/'combined'
    service.export_combined_review(tmp_path/'checklist',tmp_path/'run',output,Path('node'),Path('modules'))
    return output


def test_export_and_archive_reader_preserve_exact_downloads(combined_inputs,tmp_path,monkeypatch):
    output=export(tmp_path,monkeypatch)
    before={p.name:p.read_bytes() for p in output.iterdir()}
    assert not list(output.glob('*.html'))
    for name in ('bundle','master','run','checklist'): shutil.rmtree(tmp_path/name)
    screen=api().read_completed_combined_review(output)
    assert screen['json_bytes']==before['review_report.json']
    assert screen['excel_bytes']==before['review_report.xlsx']
    assert screen['report']['summary']['parent_check_count']==59
    assert screen['report']['summary']['child_item_count']==14


def test_existing_output_is_not_overwritten(combined_inputs,tmp_path,monkeypatch):
    output=export(tmp_path,monkeypatch)
    before={p:p.read_bytes() for p in output.iterdir()}
    with pytest.raises(FileExistsError): export(tmp_path,monkeypatch)
    assert before=={p:p.read_bytes() for p in output.iterdir()}
    assert api().read_completed_combined_review(output)['report']['summary']['child_item_count']==14


@pytest.mark.parametrize('fault',['source','view','workbook','backend'])
def test_failed_build_has_no_completion(combined_inputs,tmp_path,monkeypatch,fault):
    service=api()
    def broken(view,output,*args):
        builder(view,output,*args)
        if fault=='backend': raise RuntimeError('backend failed')
        path={'source':tmp_path/'run/item_observation.json','view':view,'workbook':output/'review_report.xlsx'}[fault]
        path.write_bytes(b'changed')
    monkeypatch.setattr(service,'_run_builder',broken)
    output=tmp_path/'combined'
    with pytest.raises(Exception):
        service.export_combined_review(tmp_path/'checklist',tmp_path/'run',output,Path('node'),Path('modules'))
    assert not (output/'review_report_complete.json').exists()
    assert (output/'review_report_failed.json').exists()


@pytest.mark.parametrize('name',['review_report.json','review_report_view.json','review_report.xlsx',
                               'review_report_complete.json','review_report_failed.json'])
def test_reader_rejects_changed_or_failed_artifacts(combined_inputs,tmp_path,monkeypatch,name):
    output=export(tmp_path,monkeypatch)
    (output/name).write_bytes(b'changed')
    with pytest.raises(Exception): api().read_completed_combined_review(output)


def test_completion_publication_mutation_is_withdrawn(combined_inputs,tmp_path,monkeypatch):
    service=api()
    monkeypatch.setattr(service,'_run_builder',builder)
    original=service.os.link
    def changed(src,dst):
        original(src,dst)
        (tmp_path/'checklist/review_complete.json').write_bytes(b'changed')
    monkeypatch.setattr(service.os,'link',changed)
    output=tmp_path/'combined'
    with pytest.raises(ValueError):
        service.export_combined_review(tmp_path/'checklist',tmp_path/'run',output,Path('node'),Path('modules'))
    assert not (output/'review_report_complete.json').exists()


def test_duplicate_json_receipt_is_rejected(combined_inputs,tmp_path,monkeypatch):
    api()
    path=tmp_path/'checklist/review_complete.json'
    text=path.read_text()
    path.write_text(text.replace('"status":','"status":"bad","status":',1))
    with pytest.raises(ValueError): export(tmp_path,monkeypatch)


def test_reader_detects_mutation_during_workbook_validation(combined_inputs,tmp_path,monkeypatch):
    output=export(tmp_path,monkeypatch)
    service=api()
    original=service.validate_workbook
    def changed(data,view):
        original(data,view)
        (output/'review_report.json').write_bytes(b'changed')
    monkeypatch.setattr(service,'validate_workbook',changed)
    with pytest.raises(ValueError): service.read_completed_combined_review(output)
