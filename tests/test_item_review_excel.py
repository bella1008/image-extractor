from copy import deepcopy
import importlib
import json
import hashlib
import os
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile
import xml.etree.ElementTree as ET

import pytest

from src.item_review import observe_item_master
from tests.test_item_review import master, target, node
from tests.test_item_review_service import checked_bundle, request_for


def workbook_fixture(path, view):
    """Minimal OOXML fixture, not the production writer."""
    from tests.test_checklist_item_master import xlsx
    text_sheets = deepcopy(view['sheets'])
    for sheet in text_sheets:
        sheet['rows'] = [[str(v) for v in row] for row in sheet['rows']]
    xlsx(path, text_sheets)
    ns = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    with ZipFile(path) as archive:
        parts = {n: archive.read(n) for n in archive.namelist()}
    for i, sheet in enumerate(view['sheets'], 1):
        key = f'xl/worksheets/sheet{i}.xml'
        tree = ET.fromstring(parts[key])
        views = ET.Element(f'{{{ns}}}sheetViews')
        sv = ET.SubElement(views, f'{{{ns}}}sheetView', workbookViewId='0')
        ET.SubElement(sv, f'{{{ns}}}pane', ySplit='1', topLeftCell=sheet['freeze'], state='frozen')
        tree.insert(0, views)
        from openpyxl.utils import get_column_letter
        ET.SubElement(tree, f'{{{ns}}}autoFilter', ref=f'A1:{get_column_letter(len(sheet["headers"]))}{len(sheet["rows"])+1}')
        for row, values in zip(tree.find(f'{{{ns}}}sheetData'), [sheet['headers'], *sheet['rows']], strict=True):
            for cell, value in zip(row, values, strict=True):
                if type(value) is int:
                    cell.remove(cell[0])
                    cell.set('t', 'n')
                    ET.SubElement(cell, f'{{{ns}}}v').text = str(value)
        parts[key] = ET.tostring(tree)
    with ZipFile(path, 'w') as archive:
        for name, content in parts.items(): archive.writestr(name, content)


@pytest.fixture
def completed_run(tmp_path, checked_bundle):
    from src.item_review_service import run_item_review
    request = request_for(tmp_path, checked_bundle)
    run_item_review(request)
    return request.output_dir


def fake_builder(view_path, output_dir, node_executable, node_modules):
    workbook_fixture(output_dir / 'item_review.xlsx', json.loads(view_path.read_bytes()))


def test_export_publishes_validated_workbook_and_consumer_returns_exact_bytes(tmp_path, completed_run, monkeypatch):
    api = implementation()
    monkeypatch.setattr(api, '_run_builder', fake_builder)
    output = tmp_path / 'excel'
    completion = api.export_item_review_excel(completed_run, output, Path('node'), Path('modules'))
    assert completion['status'] == 'ready_for_human_review'
    assert completion['decision_status'] == 'not_evaluated'
    assert api.read_completed_item_excel(output, completed_run) == (output / 'item_review.xlsx').read_bytes()
    assert completion['source_completion_sha256'] == hashlib.sha256((completed_run / 'item_review_complete.json').read_bytes()).hexdigest()
    with pytest.raises(FileExistsError):
        api.export_item_review_excel(completed_run, output, Path('node'), Path('modules'))


@pytest.mark.parametrize('mutation', ['source', 'view', 'workbook', 'builder_failure'])
def test_export_failure_never_publishes_completion(tmp_path, completed_run, monkeypatch, mutation):
    api = implementation()
    def corrupt(view_path, output_dir, *args):
        fake_builder(view_path, output_dir, *args)
        if mutation == 'builder_failure': raise RuntimeError('authoring failed')
        if mutation == 'source': path = completed_run / 'item_observation.json'
        elif mutation == 'view': path = view_path
        else: path = output_dir / 'item_review.xlsx'
        path.write_bytes(b'changed')
    monkeypatch.setattr(api, '_run_builder', corrupt)
    output = tmp_path / 'excel'
    with pytest.raises(Exception): api.export_item_review_excel(completed_run, output, Path('node'), Path('modules'))
    assert not (output / 'item_excel_complete.json').exists()
    assert (output / 'item_excel_failed.json').exists()


@pytest.mark.parametrize('mutation', ['xlsx', 'view', 'source', 'failure', 'incomplete'])
def test_consumer_rejects_changed_or_failed_export(tmp_path, completed_run, monkeypatch, mutation):
    api = implementation()
    monkeypatch.setattr(api, '_run_builder', fake_builder)
    output = tmp_path / 'excel'
    api.export_item_review_excel(completed_run, output, Path('node'), Path('modules'))
    paths = {'xlsx': output / 'item_review.xlsx', 'view': output / 'item_excel_view.json',
             'source': completed_run / 'item_review_complete.json', 'failure': output / 'item_excel_failed.json'}
    if mutation == 'incomplete': (output / 'item_excel_complete.json').unlink()
    else: paths[mutation].write_bytes(b'changed')
    with pytest.raises(Exception): api.read_completed_item_excel(output, completed_run)


@pytest.mark.parametrize('kind', ['source', 'excel'])
@pytest.mark.parametrize('content', ['[]', 'null'])
def test_malformed_receipt_shape_is_a_validation_error(tmp_path, completed_run, monkeypatch, kind, content):
    api = implementation()
    monkeypatch.setattr(api, '_run_builder', fake_builder)
    output = tmp_path / 'excel'
    api.export_item_review_excel(completed_run, output, Path('node'), Path('modules'))
    path = completed_run / 'item_review_complete.json' if kind == 'source' else output / 'item_excel_complete.json'
    path.write_text(content)
    with pytest.raises(ValueError): api.read_completed_item_excel(output, completed_run)


def test_saved_workbook_contract_rejects_formula_and_unexpected_cell(tmp_path):
    api = implementation()
    view = api.build_item_excel_view(report())
    path = tmp_path / 'fixture.xlsx'
    workbook_fixture(path, view)
    api.validate_item_workbook(path.read_bytes(), view)
    with ZipFile(path) as archive: parts = {n: archive.read(n) for n in archive.namelist()}
    key = 'xl/worksheets/sheet1.xml'
    tree = ET.fromstring(parts[key])
    ns = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    cell = tree.find(f'.//{{{ns}}}c')
    ET.SubElement(cell, f'{{{ns}}}f').text = '1+1'
    parts[key] = ET.tostring(tree)
    buf = BytesIO()
    with ZipFile(buf, 'w') as archive:
        for name, content in parts.items(): archive.writestr(name, content)
    with pytest.raises(ValueError): api.validate_item_workbook(buf.getvalue(), view)


@pytest.mark.parametrize('when', ['pending', 'published'])
def test_completion_race_never_leaves_usable_receipt(tmp_path, completed_run, monkeypatch, when):
    api = implementation()
    monkeypatch.setattr(api, '_run_builder', fake_builder)
    original_write, original_link = api._write_new, api.os.link
    output = tmp_path / 'excel'
    def write(path, text):
        original_write(path, text)
        if when == 'pending' and path.name == 'item_excel_complete.pending.json':
            path.write_bytes(b'partial')
    def link(source, target):
        original_link(source, target)
        if when == 'published':
            (completed_run / 'item_review_failed.json').write_text('{}')
    monkeypatch.setattr(api, '_write_new', write)
    monkeypatch.setattr(api.os, 'link', link)
    with pytest.raises(ValueError): api.export_item_review_excel(completed_run, output, Path('node'), Path('modules'))
    assert not (output / 'item_excel_complete.json').exists()


@pytest.mark.parametrize('empty', [False, True], ids=['literal-text', 'empty-evidence'])
def test_real_artifact_backend_roundtrip(tmp_path, empty):
    node_exe = os.environ.get('ITEM_REVIEW_NODE')
    modules = os.environ.get('ITEM_REVIEW_NODE_MODULES')
    if not node_exe or not modules:
        pytest.skip('explicit Artifact Tool runtime required for real workbook integration')
    api = implementation()
    data = report() if not empty else observe_item_master(target(), master())
    data['target_source'] = report()['target_source']
    for item, text in zip(data['items'], ['=1+1', "'literal", '+cmd', '@SUM(A1)', '<script>x</script>']):
        item['author_proposal']['reviewer_note'] = text
    from src.item_review_report import render_item_review_html
    run = tmp_path / 'run'
    run.mkdir()
    contents = {'item_observation.json': json.dumps(data).encode(), 'item_review.html': render_item_review_html(data).encode()}
    for name, content in contents.items(): (run / name).write_bytes(content)
    (run / 'item_review_complete.json').write_text(json.dumps({'schema_version':'checklist-item-observation-run/1',
        'status':'ready_for_human_review', 'decision_status':'not_evaluated', 'activation_status':'draft_only',
        'summary':data['summary'], 'artifacts':{n:hashlib.sha256(b).hexdigest() for n,b in contents.items()}}))
    output = tmp_path / 'excel'
    api.export_item_review_excel(run, output, Path(node_exe), Path(modules))
    assert api.read_completed_item_excel(output, run) == (output / 'item_review.xlsx').read_bytes()


def implementation():
    assert importlib.util.find_spec('src.item_review_excel'), 'Excel display contract missing'
    return importlib.import_module('src.item_review_excel')


def test_public_builder_and_cli_are_available():
    root = Path(__file__).resolve().parents[1]
    assert (root / 'scripts/build_item_review_excel.mjs').is_file()
    assert importlib.util.find_spec('scripts.export_item_review_excel')


def report():
    original = master()
    result = observe_item_master(target(*(node('current_' + str(i), 'list_body',
        ('*' if i >= 2 else '') + item['required_text']) for i, item in enumerate(original['items'])),
        node('current_note', 'paragraph', '*: Depends on model.')), original)
    result['target_source'] = dict(pdf_filename='current.pdf', pdf_sha256='1' * 64,
        semantic_xml_sha256='2' * 64, receipt_ref='current/review_run.json',
        receipt_sha256='3' * 64, bundle_path='current')
    return result


def test_three_sheets_preserve_fourteen_items_and_twenty_six_current_associations():
    data = report()
    before = deepcopy(data)
    view = implementation().build_item_excel_view(data)
    summary, items, evidence = view['sheets']
    assert [s['name'] for s in view['sheets']] == ['Summary', 'Item Results', 'Source Evidence']
    assert len(items['rows']) == 14 and len(evidence['rows']) == 26
    assert items['rows'][0][1] == data['items'][0]['required_text']
    assert all(row[2] == '검토 필요' and row[6] == '' for row in items['rows'])
    assert 'observation' not in items['headers'] and 'reason' not in items['headers']
    assert [r[2] for r in summary['rows'] if r[:2] == ['집계', '하위 항목']] == [14]
    assert any(r[:2] == ['검토 대상', 'PDF 파일'] and r[2] == 'current.pdf' for r in summary['rows'])
    assert any(r[0] == '원장 작성 당시' and r[1] == 'PDF 파일' for r in summary['rows'])
    for r in evidence['rows']:
        assert 'current_' in r[4]
        assert r[2] in ('항목 문구', '조건 안내 후보')
        assert json.loads(r[8])['text'] == r[3]
    assert data == before


@pytest.mark.parametrize('value', ['=1+1', "'literal", '<script>x</script>', '+cmd', '@SUM(A1)'])
def test_literals_and_author_proposals_remain_data(value):
    data = report()
    data['items'][0]['author_proposal']['reviewer_note'] = value
    view = implementation().build_item_excel_view(data)
    assert view['sheets'][1]['rows'][0][-1] == value
    assert view['sheets'][1]['rows'][0][2] == '검토 필요'


@pytest.mark.parametrize('value', ['x' * 32768, '\x00bad', '\ud800', '\ufffe'],
                         ids=['too-long', 'control', 'surrogate', 'noncharacter'])
def test_excel_unrepresentable_text_rejected_without_truncation(value):
    data = report()
    data['items'][0]['description'] = value
    with pytest.raises(ValueError, match='Excel'):
        implementation().build_item_excel_view(data)


def test_decision_and_summary_mutations_rejected():
    data = report()
    data['items'][0]['result'] = 'pass'
    with pytest.raises(ValueError): implementation().build_item_excel_view(data)
    data = report()
    data['summary']['found'] = 15
    with pytest.raises(ValueError): implementation().build_item_excel_view(data)


def test_missing_and_ambiguous_evidence_not_coalesced():
    data = report()
    data['items'][0]['candidates'].append(deepcopy(data['items'][0]['candidates'][0]))
    data['items'][0]['observation'] = 'ambiguous'
    data['summary'].update(found=13, ambiguous=1)
    view = implementation().build_item_excel_view(data)
    refs = view['sheets'][1]['rows'][0][4].split('\n')
    assert len(refs) == 2 and refs[0] != refs[1]
    assert len(view['sheets'][2]['rows']) == 27
