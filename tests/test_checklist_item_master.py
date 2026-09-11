"""Draft authoring contract, using minimal OOXML fixtures (no Excel writer)."""
from copy import deepcopy
import hashlib
import importlib
import json
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr
from zipfile import ZipFile

import pytest

from scripts.prepare_item_proposal import ZC_ITEMS, zc_item_slices
from src.checklist_item_proposal import build_item_proposal, observe_item_proposal
from tests.test_checklist_observation import document, heading, node, rule


def module():
    assert importlib.util.find_spec('src.checklist_item_master'), 'item master implementation missing'
    return importlib.import_module('src.checklist_item_master')


def proposal():
    parent = rule(common_id='CHK-002', check_id='CHK-002-ZC-ENG', block_type='item_list',
                  required_text='\n'.join(text for _, text in ZC_ITEMS))
    doc = document(heading(), *(node(key, 'list_body', ('*' if i >= 2 else '') + text)
                               for i, (key, text) in enumerate(ZC_ITEMS)),
                   node('condition', 'paragraph', '*: Model-dependent items.'))
    result = observe_item_proposal(doc, build_item_proposal(parent, zc_item_slices(parent)))
    result['source'] = {'pdf_filename': 'original.pdf', 'pdf_sha256': 'a' * 64,
                        'semantic_xml_sha256': 'b' * 64, 'receipt_sha256': 'c' * 64,
                        'draft_excel_sha256': 'd' * 64, 'source_completion_sha256': 'e' * 64,
                        'bundle_path': 'bundle', 'receipt_ref': 'bundle/review_run.json'}
    return result


def xlsx(path, sheets, special=None, dimension=None):
    ns = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    relns = 'http://schemas.openxmlformats.org/package/2006/relationships'
    with ZipFile(path, 'w') as archive:
        archive.writestr('[Content_Types].xml', '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                         '<Default Extension="xml" ContentType="application/xml"/>'
                         '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                         '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/></Types>')
        archive.writestr('_rels/.rels', f'<Relationships xmlns="{relns}"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        archive.writestr('xl/workbook.xml', f'<workbook xmlns="{ns}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>' + ''.join(
            f'<sheet name={quoteattr(s["name"])} sheetId="{i}" r:id="rId{i}"/>' for i, s in enumerate(sheets, 1)) + '</sheets></workbook>')
        archive.writestr('xl/_rels/workbook.xml.rels', f'<Relationships xmlns="{relns}">' + ''.join(
            f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>' for i in range(1, len(sheets) + 1)) + '</Relationships>')
        for i, sheet in enumerate(sheets, 1):
            rows = []
            for r, values in enumerate([sheet['headers'], *sheet['rows']], 1):
                cells = []
                for c, value in enumerate(values, 1):
                    col, n = '', c
                    while n:
                        n, rem = divmod(n - 1, 26)
                        col = chr(65 + rem) + col
                    address = f'{col}{r}'
                    override = (special or {}).get((sheet['name'], address))
                    cells.append(override or f'<c r="{address}" t="inlineStr"><is><t xml:space="preserve">{escape(value)}</t></is></c>')
                rows.append(f'<row r="{r}">' + ''.join(cells) + '</row>')
            hint = f'<dimension ref="{dimension}"/>' if dimension else ''
            archive.writestr(f'xl/worksheets/sheet{i}.xml', f'<worksheet xmlns="{ns}">{hint}<sheetData>' + ''.join(rows) + '</sheetData></worksheet>')


def inputs(tmp_path):
    seed = module().build_master_seed(proposal())
    seed_path = tmp_path / 'seed.json'
    seed_path.write_text(json.dumps(seed), encoding='utf-8')
    return seed, seed_path, hashlib.sha256(seed_path.read_bytes()).hexdigest(), tmp_path / 'master.xlsx', tmp_path / 'draft.json'


def test_seed_retains_parent_items_and_all_condition_evidence():
    source = proposal()
    seed = module().build_master_seed(source)
    sheets = {s['name']: s for s in seed['sheets']}
    assert list(sheets) == ['Items', 'Parent', 'Source Evidence', 'Source', 'Guide']
    assert dict(sheets['Parent']['rows']) == source['source_rule']
    items = [dict(zip(sheets['Items']['headers'], r)) for r in sheets['Items']['rows']]
    assert len(items) == 14
    assert [i['required_text'] for i in items] == [text for _, text in ZC_ITEMS]
    assert sum(bool(json.loads(i['condition_refs'])) for i in items) == 12
    assert all(i['condition_state'] == 'unverified' and i['model_applicability'] == 'unknown' for i in items)
    assert len(sheets['Source Evidence']['rows']) == 26
    assert sheets['Source Evidence']['headers'] == ['evidence_id', 'kind', 'item_key', 'text',
        'source_node_ids', 'structure_types', 'pdf_pages', 'details_json']
    assert json.loads(dict(sheets['Source']['rows'])['source_segments_json']) == source['source_segments']
    assert 'result' not in sheets['Items']['headers']


def test_roundtrip_accepts_only_editable_text_and_stable_item_reorder(tmp_path):
    seed, seed_path, digest, excel, output = inputs(tmp_path)
    edited = deepcopy(seed['sheets'])
    cols = edited[0]['headers']
    for field in ('proposed_model_rule', 'proposal_evidence', 'reviewer_note'):
        edited[0]['rows'][0][cols.index(field)] = '  제안\n원문 그대로  '
    edited[0]['rows'].reverse()
    xlsx(excel, edited)
    result = module().export_item_master(excel, seed_path, output, expected_seed_sha256=digest)
    assert result == json.loads(output.read_text(encoding='utf-8'))
    assert result['activation_status'] == 'draft_only'
    assert result['parent'] == proposal()['source_rule']
    assert result['items'][0]['item_key'] == 'simple_user_guide'
    assert result['items'][0]['reviewer_note'] == '  제안\n원문 그대로  '
    assert all(i['model_applicability'] == 'unknown' and i['condition_state'] == 'unverified' for i in result['items'])
    assert all('result' not in i and 'approved' not in i for i in result['items'])
    assert result['provenance']['seed_sha256'] == digest
    assert result['source']['pdf_filename'] == 'original.pdf'


@pytest.mark.parametrize('mutation', ['missing_item', 'duplicate_item', 'extra_item', 'missing_sheet', 'extra_sheet',
    'header', 'extra_column', 'blank_row', 'source_text', 'source_hash', 'condition_link', 'parent', 'activation', 'blank_key'])
def test_invalid_workbook_never_publishes(tmp_path, mutation):
    seed, seed_path, digest, excel, output = inputs(tmp_path)
    sheets = deepcopy(seed['sheets'])
    items = sheets[0]
    if mutation == 'missing_item': items['rows'].pop()
    elif mutation == 'duplicate_item': items['rows'][-1] = items['rows'][0][:]
    elif mutation == 'extra_item': items['rows'].append(items['rows'][0][:])
    elif mutation == 'missing_sheet': sheets.pop()
    elif mutation == 'extra_sheet': sheets.append({'name': 'Extra', 'headers': ['x'], 'rows': [['x']]})
    elif mutation == 'header': items['headers'][0] = 'wrong'
    elif mutation == 'extra_column':
        items['headers'].append('extra')
        for row in items['rows']: row.append('')
    elif mutation == 'blank_row': items['rows'][0] = [''] * len(items['headers'])
    elif mutation == 'source_text': sheets[2]['rows'][0][3] += 'changed'
    elif mutation == 'source_hash': sheets[3]['rows'][1][1] = '0' * 64
    elif mutation == 'condition_link': items['rows'][2][items['headers'].index('condition_refs')] = '[]'
    elif mutation == 'parent': sheets[1]['rows'][0][1] = 'changed'
    elif mutation == 'activation': items['rows'][0][items['headers'].index('model_applicability')] = 'applicable'
    elif mutation == 'blank_key': items['rows'][0][1] = ''
    xlsx(excel, sheets)
    with pytest.raises(ValueError):
        module().export_item_master(excel, seed_path, output, expected_seed_sha256=digest)
    assert not output.exists()


@pytest.mark.parametrize('cell', ['<c r="F2"><f>1+1</f><v>2</v></c>', '<c r="F2" t="e"><v>#VALUE!</v></c>',
                                 '<c r="F2" t="n"><v>12</v></c>'])
def test_formula_error_and_numeric_cells_rejected_even_in_editable_column(tmp_path, cell):
    seed, seed_path, digest, excel, output = inputs(tmp_path)
    xlsx(excel, seed['sheets'], {('Items', 'F2'): cell})
    with pytest.raises(ValueError, match='cell'):
        module().export_item_master(excel, seed_path, output, expected_seed_sha256=digest)
    assert not output.exists()


def test_changed_seed_and_missing_external_digest_are_rejected(tmp_path):
    seed, seed_path, digest, excel, output = inputs(tmp_path)
    xlsx(excel, seed['sheets'])
    with pytest.raises(TypeError):
        module().export_item_master(excel, seed_path, output)
    seed_path.write_bytes(seed_path.read_bytes() + b' ')
    with pytest.raises(ValueError, match='seed'):
        module().export_item_master(excel, seed_path, output, expected_seed_sha256=digest)
    assert not output.exists()


def test_formula_outside_false_dimension_is_not_silently_omitted(tmp_path):
    seed, seed_path, digest, excel, output = inputs(tmp_path)
    xlsx(excel, seed['sheets'], {('Items', 'F2'): '<c r="F2"><f>1+1</f><v>2</v></c>'}, dimension='A1:A1')
    with pytest.raises(ValueError, match='cell'):
        module().export_item_master(excel, seed_path, output, expected_seed_sha256=digest)
    assert not output.exists()


def test_failed_serialization_removes_only_own_pending_file(tmp_path, monkeypatch):
    seed, seed_path, digest, excel, output = inputs(tmp_path)
    xlsx(excel, seed['sheets'])
    unrelated = tmp_path / 'another-writer.pending'
    unrelated.write_text('preserve me')
    def fail(*args, **kwargs):
        raise OSError('disk failure')
    monkeypatch.setattr(module().json, 'dump', fail)
    with pytest.raises(OSError, match='disk failure'):
        module().export_item_master(excel, seed_path, output, expected_seed_sha256=digest)
    assert not output.exists()
    assert list(tmp_path.glob('*.pending')) == [unrelated]


def test_existing_export_is_never_replaced(tmp_path):
    seed, seed_path, digest, excel, output = inputs(tmp_path)
    output.write_text('keep existing')
    with pytest.raises(FileExistsError):
        module().export_item_master(excel, seed_path, output, expected_seed_sha256=digest)
    assert output.read_text() == 'keep existing'


@pytest.mark.parametrize('changed', ['seed', 'excel'])
def test_input_change_while_pending_is_written_blocks_publication(tmp_path, monkeypatch, changed):
    seed, seed_path, digest, excel, output = inputs(tmp_path)
    xlsx(excel, seed['sheets'])
    real_fsync = module().os.fsync
    def mutate(fd):
        real_fsync(fd)
        path = seed_path if changed == 'seed' else excel
        path.write_bytes(path.read_bytes() + b' ')
    monkeypatch.setattr(module().os, 'fsync', mutate)
    with pytest.raises(ValueError, match='changed'):
        module().export_item_master(excel, seed_path, output, expected_seed_sha256=digest)
    assert not output.exists()
    assert not list(tmp_path.glob('*.pending'))


def test_no_overwrite_including_destination_created_during_publication(tmp_path, monkeypatch):
    seed, seed_path, digest, excel, output = inputs(tmp_path)
    xlsx(excel, seed['sheets'])
    real_link = module().os.link
    def race(source, target):
        Path(target).write_text('other writer', encoding='utf-8')
        real_link(source, target)
    monkeypatch.setattr(module().os, 'link', race)
    with pytest.raises(FileExistsError):
        module().export_item_master(excel, seed_path, output, expected_seed_sha256=digest)
    assert output.read_text() == 'other writer'
    assert not list(tmp_path.glob('*.pending'))


def test_blank_optional_fields_are_preserved_and_literals_are_not_executed(tmp_path):
    seed, seed_path, digest, excel, output = inputs(tmp_path)
    seed['sheets'][0]['rows'][0][5] = '=literal proposal'
    xlsx(excel, seed['sheets'])
    result = module().export_item_master(excel, seed_path, output, expected_seed_sha256=digest)
    assert result['items'][0]['proposed_model_rule'] == '=literal proposal'
    assert result['items'][1]['reviewer_note'] == ''
    assert result['parent']['source_reference_token'] == ''


@pytest.mark.parametrize('change_during', [False, True])
def test_prepare_reuses_checked_proposal_and_checks_sources_until_publication(tmp_path, monkeypatch, change_during):
    assert importlib.util.find_spec('scripts.prepare_item_master'), 'checked master prepare missing'
    cli = importlib.import_module('scripts.prepare_item_master')
    root = Path(__file__).resolve().parents[1]
    run_dir = root / 'outputs/review_service_zc_20260911_r2'
    pdf = root / 'samples/SUG_RAW/TV_ZC/BN68-25100B-00_SUG_Y26 TV ALL_ZC_L02_260122.0.pdf'
    if not run_dir.exists() or not pdf.exists():
        pytest.skip('local checked bundle required')
    monkeypatch.syspath_prepend(str(root / 'samples/tagged_pdf_xml_poc/src'))
    copied_pdf = tmp_path / pdf.name
    copied_pdf.write_bytes(pdf.read_bytes())
    real = cli.prepare_proposal
    calls = []
    def checked(*args, **kwargs):
        calls.append(args[2])
        return real(*args, **kwargs)
    monkeypatch.setattr(cli, 'prepare_proposal', checked)
    if change_during:
        real_build = cli.build_master_seed
        def mutate(data):
            value = real_build(data)
            copied_pdf.write_bytes(copied_pdf.read_bytes() + b' ')
            return value
        monkeypatch.setattr(cli, 'build_master_seed', mutate)
    output = tmp_path / 'seed.json'
    if change_during:
        with pytest.raises(ValueError, match='changed'):
            cli.prepare_master(run_dir, copied_pdf, output)
        assert not output.exists()
    else:
        seed = cli.prepare_master(run_dir, copied_pdf, output)
        assert len(seed['sheets'][0]['rows']) == 14
        assert sum(bool(json.loads(r[-1])) for r in seed['sheets'][0]['rows']) == 12
        assert output.exists()
        with pytest.raises(FileExistsError):
            cli.prepare_master(run_dir, copied_pdf, output)
    assert len(calls) == 1
    assert not calls[0].exists()
