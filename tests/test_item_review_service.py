from copy import deepcopy
import hashlib
import importlib
import json
from pathlib import Path
import shutil

import pytest

from tests.test_item_review import MASTER
from tests.test_checklist_item_master import xlsx


def implementation():
    assert importlib.util.find_spec('src.item_review_service'), 'checked item service implementation missing'
    return importlib.import_module('src.item_review_service')


def copied_master(tmp_path):
    folder = tmp_path / 'master'
    shutil.copytree(MASTER, folder)
    return folder


def test_checked_master_reproduces_full_export_from_pinned_seed(tmp_path):
    folder = copied_master(tmp_path)
    assert implementation().load_checked_item_master(folder) == json.loads((folder / 'checklist_item_master.json').read_bytes())


@pytest.mark.parametrize('mutation', ['wording', 'unknown', 'duplicate', 'activation', 'source', 'provenance', 'proposal'])
def test_json_mutation_is_not_trusted_even_if_schema_and_provenance_look_valid(tmp_path, mutation):
    folder = copied_master(tmp_path)
    path = folder / 'checklist_item_master.json'
    data = json.loads(path.read_bytes())
    if mutation == 'wording': data['items'][0]['required_text'] = 'Edited'
    elif mutation == 'unknown': data['unexpected'] = 'ignored?'
    elif mutation == 'duplicate': data['items'][1] = deepcopy(data['items'][0])
    elif mutation == 'activation': data['activation_status'] = 'approved'
    elif mutation == 'source': data['source']['pdf_filename'] = 'edited.pdf'
    elif mutation == 'provenance': data['provenance']['excel_sha256'] = '0' * 64
    else: data['items'][0]['reviewer_note'] = 'not exported from Excel'
    path.write_text(json.dumps(data), encoding='utf-8')
    with pytest.raises(ValueError, match='differ|changed'):
        implementation().load_checked_item_master(folder)


def test_seed_hash_is_external_not_taken_from_input_provenance(tmp_path):
    folder = copied_master(tmp_path)
    seed = folder / 'master_seed.json'
    seed.write_bytes(seed.read_bytes() + b'\n')
    path = folder / 'checklist_item_master.json'
    data = json.loads(path.read_bytes())
    data['provenance']['seed_sha256'] = hashlib.sha256(seed.read_bytes()).hexdigest()
    path.write_text(json.dumps(data), encoding='utf-8')
    with pytest.raises(ValueError, match='seed SHA-256'):
        implementation().load_checked_item_master(folder)


def test_valid_author_proposals_export_and_load_without_activation(tmp_path):
    from src.checklist_item_master import export_item_master
    folder = copied_master(tmp_path)
    seed = folder / 'master_seed.json'
    sheets = json.loads(seed.read_bytes())['sheets']
    cols = sheets[0]['headers']
    sheets[0]['rows'][0][cols.index('proposed_model_rule')] = 'Applicable: every model (author proposal only)'
    sheets[0]['rows'][0][cols.index('reviewer_note')] = '<b>Check</b>'
    excel = folder / 'checklist_item_master.xlsx'
    xlsx(excel, sheets)
    output = folder / 'checklist_item_master.json'
    output.unlink()
    export_item_master(excel, seed, output, expected_seed_sha256=hashlib.sha256((MASTER / 'master_seed.json').read_bytes()).hexdigest())
    result = implementation().load_checked_item_master(folder)
    assert result['items'][0]['model_applicability'] == 'unknown'
    assert result['items'][0]['reviewer_note'] == '<b>Check</b>'


def test_stale_excel_export_is_rejected(tmp_path):
    folder = copied_master(tmp_path)
    excel = folder / 'checklist_item_master.xlsx'
    excel.write_bytes(excel.read_bytes() + b'changed')
    with pytest.raises(ValueError, match='differ|changed'):
        implementation().load_checked_item_master(folder)


@pytest.mark.parametrize('mutation', ['numeric_type', 'duplicate_json_key'])
def test_stored_json_requires_exact_value_types_and_unambiguous_keys(tmp_path, mutation):
    folder = copied_master(tmp_path)
    path = folder / 'checklist_item_master.json'
    text = path.read_text(encoding='utf-8')
    if mutation == 'numeric_type': text = text.replace('"start": 0,', '"start": false,', 1)
    else: text = text.replace('"activation_status": "draft_only",', '"activation_status": "active", "activation_status": "draft_only",', 1)
    path.write_text(text, encoding='utf-8')
    with pytest.raises(ValueError): implementation().load_checked_item_master(folder)


@pytest.fixture
def checked_bundle(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(MASTER.parents[3] / 'samples/tagged_pdf_xml_poc/src'))
    from tests.xml_v2.test_xml_adapter import bundle
    result = bundle.__wrapped__(tmp_path)
    (result[0] / 'review_run.json').write_text(json.dumps(result[1]), encoding='utf-8')
    return result


def request_for(tmp_path, checked_bundle):
    service = implementation()
    folder, _, pdf, *_ = checked_bundle
    return service.ItemReviewRequest(pdf, tmp_path / 'run', bundle=folder,
                                     master_dir=copied_master(tmp_path))


def test_service_publishes_only_fourteen_children_with_separate_current_and_historical_sources(tmp_path, checked_bundle):
    service = implementation()
    request = request_for(tmp_path, checked_bundle)
    receipt = service.run_item_review(request)
    report = service.read_completed_item_review(request.output_dir)
    assert set(receipt['artifacts']) == {'item_observation.json'}
    assert receipt['schema_version'] == 'checklist-item-observation-run/2'
    assert receipt['status'] == 'ready_for_human_review' and receipt['activation_status'] == 'draft_only'
    assert report['summary']['not_examined'] == 14
    assert report['target_source']['pdf_sha256'] == hashlib.sha256(request.pdf.read_bytes()).hexdigest()
    assert report['master_source']['pdf_sha256'] != report['target_source']['pdf_sha256']
    assert report['inputs']['master_seed_sha256'] == service.EXPECTED_SEED_SHA256
    assert report['inputs']['master_json'] == str((request.master_dir / 'checklist_item_master.json').resolve())
    assert not (request.output_dir / 'item_review_failed.json').exists()
    with pytest.raises(FileExistsError): service.run_item_review(request)


@pytest.mark.parametrize('target', ['pdf', 'mapping', 'master_json', 'master_excel', 'master_seed', 'receipt', 'artifact'])
def test_input_changes_during_validation_never_complete(tmp_path, checked_bundle, monkeypatch, target):
    from dataclasses import replace
    service = implementation()
    request = request_for(tmp_path, checked_bundle)
    mapping = tmp_path / 'mapping.json'
    shutil.copyfile(request.mapping, mapping)
    request = replace(request, mapping=mapping)
    paths = {'pdf': request.pdf, 'mapping': mapping,
             'master_json': request.master_dir / 'checklist_item_master.json',
             'master_excel': request.master_dir / 'checklist_item_master.xlsx',
             'master_seed': request.master_dir / 'master_seed.json',
             'receipt': request.bundle / 'review_run.json', 'artifact': request.bundle / 'semantic_document.md'}
    original = service._validate_report
    def tamper(report):
        result = original(report)
        path = paths[target]
        path.write_bytes(path.read_bytes() + b'\n')
        return result
    monkeypatch.setattr(service, '_validate_report', tamper)
    with pytest.raises(ValueError, match='changed'):
        service.run_item_review(request)
    assert not (request.output_dir / 'item_review_complete.json').exists()
    assert (request.output_dir / 'item_review_failed.json').exists()


@pytest.mark.parametrize('phase', ['json', 'pending', 'link'])
@pytest.mark.parametrize('target', ['item_observation.json', 'master_json'])
def test_output_and_input_changes_at_publication_boundaries_fail_closed(tmp_path, checked_bundle, monkeypatch, phase, target):
    service = implementation()
    request = request_for(tmp_path, checked_bundle)
    def tamper():
        path = request.master_dir / 'checklist_item_master.json' if target == 'master_json' else request.output_dir / target
        path.write_bytes(path.read_bytes() + b' ')
    if phase == 'link':
        real_link = service.os.link
        def link(source, destination, **kwargs):
            result = real_link(source, destination, **kwargs)
            if Path(destination).name == 'item_review_complete.json': tamper()
            return result
        monkeypatch.setattr(service.os, 'link', link)
    else:
        real_write = service._write_new
        def write(path, content):
            result = real_write(path, content)
            if Path(path).name == ('item_observation.json' if phase == 'json' else 'item_review_complete.pending.json'):
                tamper()
            return result
        monkeypatch.setattr(service, '_write_new', write)
    with pytest.raises(ValueError, match='changed'):
        service.run_item_review(request)
    assert (request.output_dir / 'item_review_failed.json').exists()
    with pytest.raises(ValueError, match='failed'):
        service.read_completed_item_review(request.output_dir)


@pytest.mark.parametrize('mutation', ['json', 'failure', 'receipt', 'summary', 'state', 'duplicate'])
def test_completed_reader_rejects_mutation_and_invalid_completed_state(tmp_path, checked_bundle, mutation):
    service = implementation()
    request = request_for(tmp_path, checked_bundle)
    service.run_item_review(request)
    output = request.output_dir
    if mutation == 'json':
        path = output / 'item_observation.json'
        path.write_bytes(path.read_bytes() + b' ')
    elif mutation == 'failure':
        (output / 'item_review_failed.json').write_text('{}')
    else:
        receipt_path = output / 'item_review_complete.json'
        receipt = json.loads(receipt_path.read_bytes())
        if mutation == 'receipt': receipt['artifacts']['../extra'] = '0' * 64
        else:
            path = output / 'item_observation.json'
            report = json.loads(path.read_bytes())
            if mutation == 'summary':
                report['summary']['found'] = 14
                receipt['summary'] = report['summary']
            elif mutation == 'state': report['items'][0]['result'] = 'pass'
            else: report['items'][1] = deepcopy(report['items'][0])
            path.write_text(json.dumps(report), encoding='utf-8')
            receipt['artifacts'][path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
        receipt_path.write_text(json.dumps(receipt), encoding='utf-8')
    with pytest.raises(ValueError): service.read_completed_item_review(output)


def test_completed_reader_archives_without_requiring_current_input_files(tmp_path, checked_bundle):
    service = implementation()
    request = request_for(tmp_path, checked_bundle)
    service.run_item_review(request)
    request.pdf.unlink()
    (request.master_dir / 'checklist_item_master.json').unlink()
    assert service.read_completed_item_review(request.output_dir)['summary']['item_count'] == 14


def test_completed_reader_detects_changes_during_its_own_validation(tmp_path, checked_bundle, monkeypatch):
    service = implementation()
    request = request_for(tmp_path, checked_bundle)
    service.run_item_review(request)
    original = service.json.loads
    def tamper(data, *args, **kwargs):
        value = original(data, *args, **kwargs)
        if isinstance(value, dict) and value.get('schema_version') == 'checklist-item-observation/1':
            path = request.output_dir / 'item_observation.json'
            path.write_bytes(path.read_bytes() + b' ')
        return value
    monkeypatch.setattr(service.json, 'loads', tamper)
    with pytest.raises(ValueError, match='changed'):
        service.read_completed_item_review(request.output_dir)


def test_fresh_pdf_path_uses_environment_check_and_existing_extractor(tmp_path, checked_bundle, monkeypatch):
    from dataclasses import replace
    import src.xml_review_run as extraction
    service = implementation()
    request = replace(request_for(tmp_path, checked_bundle), bundle=None)
    called = []
    monkeypatch.setattr(service, 'validate_extraction_environment', lambda: called.append('environment'))
    def extract(pdf, output, mapping):
        assert called == ['environment']
        called.append('extract')
        shutil.copytree(checked_bundle[0], output)
    monkeypatch.setattr(extraction, 'extract_review_document', extract)
    service.run_item_review(request)
    assert called == ['environment', 'extract']
    assert service.read_completed_item_review(request.output_dir)['target_source']['bundle_path'] == str((request.output_dir / 'extraction').resolve())


@pytest.mark.parametrize('failure', ['validation', 'publication', 'environment', 'missing_receipt', 'in_memory_mutation'])
def test_failed_preparation_never_exposes_a_valid_completion(tmp_path, checked_bundle, monkeypatch, failure):
    from dataclasses import replace
    service = implementation()
    request = request_for(tmp_path, checked_bundle)
    def fail(*args, **kwargs): raise ValueError('forced failure')
    if failure == 'validation': monkeypatch.setattr(service, '_validate_report', fail)
    elif failure == 'publication':
        real_link = service.os.link
        def link(source, destination, **kwargs):
            if Path(destination).name == 'item_review_complete.json': raise OSError('cannot publish')
            return real_link(source, destination, **kwargs)
        monkeypatch.setattr(service.os, 'link', link)
    elif failure == 'environment':
        request = replace(request, bundle=None)
        monkeypatch.setattr(service, 'validate_extraction_environment', fail)
    elif failure == 'missing_receipt': (request.bundle / 'review_run.json').unlink()
    else:
        real_render = service._validate_report
        def render(report):
            html = real_render(report)
            report['summary']['found'] = 900
            return html
        monkeypatch.setattr(service, '_validate_report', render)
    with pytest.raises((ValueError, OSError)): service.run_item_review(request)
    assert not (request.output_dir / 'item_review_complete.json').exists()
    assert (request.output_dir / 'item_review_failed.json').exists()


def test_cli_passes_bounded_request_and_reports_output(tmp_path, monkeypatch, capsys):
    import sys
    assert importlib.util.find_spec('scripts.run_item_review_v2'), 'item CLI implementation missing'
    command = importlib.import_module('scripts.run_item_review_v2')
    seen = []
    def run(request):
        seen.append(request)
        return {'status': 'ready_for_human_review', 'decision_status': 'not_evaluated'}
    monkeypatch.setattr(command, 'run_item_review', run)
    monkeypatch.setattr(sys, 'argv', ['run_item_review_v2', 'new.pdf', '--output', 'out', '--bundle', 'bundle',
                                    '--master-dir', 'master', '--mapping', 'mapping.json'])
    assert command.main() == 0
    assert seen[0] == implementation().ItemReviewRequest(Path('new.pdf'), Path('out'), bundle=Path('bundle'),
                                                        master_dir=Path('master'), mapping=Path('mapping.json'))
    assert 'item_observation.json' in capsys.readouterr().out


def test_cli_failure_is_nonzero_without_business_decision(monkeypatch, capsys):
    import sys
    assert importlib.util.find_spec('scripts.run_item_review_v2'), 'item CLI implementation missing'
    command = importlib.import_module('scripts.run_item_review_v2')
    def fail(request): raise ValueError('bad master')
    monkeypatch.setattr(command, 'run_item_review', fail)
    monkeypatch.setattr(sys, 'argv', ['run_item_review_v2', 'new.pdf', '--output', 'out'])
    with pytest.raises(SystemExit) as exc: command.main()
    assert exc.value.code == 1 and 'no business decision' in capsys.readouterr().err


def test_post_publication_failure_with_unwritable_failure_marker_withdraws_own_receipt(tmp_path, checked_bundle, monkeypatch):
    service = implementation()
    request = request_for(tmp_path, checked_bundle)
    original_link, original_write = service.os.link, service._write_new
    def link(source, destination, **kwargs):
        result = original_link(source, destination, **kwargs)
        if Path(destination).name == 'item_review_complete.json':
            path = request.master_dir / 'checklist_item_master.json'
            path.write_bytes(path.read_bytes() + b' ')
        return result
    def write(path, content):
        if Path(path).name == 'item_review_failed.json': raise OSError('failure record storage unavailable')
        return original_write(path, content)
    monkeypatch.setattr(service.os, 'link', link)
    monkeypatch.setattr(service, '_write_new', write)
    with pytest.raises(ValueError, match='changed'): service.run_item_review(request)
    assert not (request.output_dir / 'item_review_complete.json').exists()
