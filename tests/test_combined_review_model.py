from copy import deepcopy
import importlib
import json
import hashlib

import pytest

from tests.test_item_review_service import checked_bundle, request_for


def api():
    assert importlib.util.find_spec('src.combined_review_model'), 'combined model is missing'
    return importlib.import_module('src.combined_review_model')


def rebind_sources(report):
    """Reach domain validation rather than only the outer snapshot hash gate."""
    for kind, key, receipt_name, data_name in (
        ('checklist','checklist','review_complete.json','observation.json'),
        ('items','items','item_review_complete.json','item_observation.json')):
        files=report['source_runs'][kind]
        files[data_name]=json.dumps(report[key],ensure_ascii=True)
        receipt=json.loads(files[receipt_name])
        receipt['summary']=report[key]['summary']
        receipt['artifacts'][data_name]=hashlib.sha256(files[data_name].encode()).hexdigest()
        files[receipt_name]=json.dumps(receipt)


@pytest.fixture
def combined_inputs(tmp_path, checked_bundle):
    from src.item_review_service import run_item_review, read_completed_item_review
    from src.review_service import ReviewRequest, run_review, read_completed_observation
    request = request_for(tmp_path, checked_bundle)
    run_item_review(request)
    left = tmp_path / 'checklist'
    run_review(ReviewRequest(request.pdf, left, bundle=request.bundle))
    checklist = read_completed_observation(left)
    items = read_completed_item_review(request.output_dir)
    folder = request.bundle
    archive = {name: (folder / name).read_text(encoding='utf-8') for name in
               ('review_run.json', 'semantic_document.xml', 'extraction_report.json')}
    runs = {'checklist': {p.name: p.read_text(encoding='utf-8') for p in left.iterdir() if p.is_file()},
            'items': {p.name: p.read_text(encoding='utf-8') for p in request.output_dir.iterdir() if p.is_file()}}
    return checklist, items, archive, runs


def test_combined_model_preserves_parents_children_and_originals(combined_inputs):
    before = deepcopy(combined_inputs)
    report = api().build_combined_report(*combined_inputs)
    assert report['summary']['parent_check_count'] == 59
    assert report['summary']['child_item_count'] == 14
    assert report['summary']['rule_count'] == 547
    assert report['summary']['excluded_count'] == 488
    assert 'total_review_count' not in report['summary']
    assert report['checklist'] == before[0] and report['items'] == before[1]
    assert combined_inputs == before
    report['items']['items'][0]['description'] = 'changed copy'
    assert combined_inputs == before


@pytest.mark.parametrize('fault', ['pdf','xml','receipt','context','parent_missing','parent_duplicate',
    'parent_excluded','child_key','child_text','decision','source_node','archive','summary','duplicate_json'])
def test_combined_model_rejects_invalid_or_mixed_inputs(combined_inputs, fault):
    report = api().build_combined_report(*combined_inputs)
    a,b = report['checklist'],report['items']
    parent = next(r for r in a['rows'] if r['check_id']==b['parent_check_id'])
    if fault in ('pdf','xml','receipt'):
        field={'pdf':'pdf_sha256','xml':'semantic_xml_sha256','receipt':'receipt_sha256'}[fault]
        b['target_source'][field]='0'*64
    elif fault=='context': b['context']['source_token']='ZX_L02'
    elif fault=='parent_missing': a['rows'].remove(parent)
    elif fault=='parent_duplicate': a['rows'].append(deepcopy(parent))
    elif fault=='parent_excluded': parent['status']='not_applicable'
    elif fault=='child_key': b['items'][0]['item_key']='invented_key'
    elif fault=='child_text': b['items'][0]['required_text']='changed wording'
    elif fault=='decision': b['items'][0]['result']='pass'
    elif fault=='source_node': parent['matches']=[{'node_id':'xml:999999'}]
    elif fault=='archive': report['source_archive']['semantic_document.xml']+=' '
    elif fault=='summary': report['summary']['parent_check_count']=73
    else: report['source_runs']['items']['item_observation.json']='{"a":1,"a":2}'
    if fault!='duplicate_json': rebind_sources(report)
    with pytest.raises((ValueError,KeyError)):
        api().validate_combined_report(report)


@pytest.mark.parametrize('fault',['aggregate_text','empty_evidence','missing_content_index','missing_owner','proposal_approved','observation_pass'])
def test_domain_checks_reject_coherently_rebound_bad_evidence(combined_inputs,checked_bundle,fault):
    from dataclasses import asdict
    from src.semantic_xml_reader import read_review_bundle
    from src.review_text_units import build_text_unit_index
    from src.review_service import DEFAULT_MAPPING
    report=api().build_combined_report(*combined_inputs)
    folder,receipt,pdf,*_=checked_bundle
    doc=read_review_bundle(folder,receipt,pdf_path=pdf,mapping_path=DEFAULT_MAPPING)
    unit=build_text_unit_index(doc).units[0]
    proof=json.loads(json.dumps({**asdict(unit),'text':unit.text}))
    proof.update(owner_ids=[unit.owner_id],structure_types=[unit.structure_type],
                 groups=[deepcopy(proof['parts'])],separator='')
    report['items']['items'][0]['condition_candidates']=[proof]
    report['items']['summary']['condition_candidate_items']=1
    report['summary']['item_evidence_count']=1
    rebind_sources(report)
    api().validate_combined_report(report)
    if fault=='aggregate_text': proof['text']='FORGED DISPLAY TEXT'
    elif fault=='missing_owner':
        proof.pop('owner_id')
        proof.pop('owner_ids')
        proof['text']='FORGED DISPLAY TEXT'
    elif fault=='empty_evidence':
        for part in proof['parts']: part['evidence']=[]
        proof['groups']=[deepcopy(proof['parts'])]
    elif fault=='missing_content_index':
        for part in proof['parts']:
            part.pop('content_index')
            part['text']='FORGED DISPLAY TEXT'
            part['evidence']=[]
        proof['groups']=[deepcopy(proof['parts'])]
        proof['text']=''.join(p['text'] for p in proof['parts'])
    elif fault=='proposal_approved': report['items']['items'][0]['proposal_state']='approved'
    else: report['checklist']['rows'][0]['observation']='pass'
    rebind_sources(report)
    with pytest.raises(ValueError): api().validate_combined_report(report)


def test_archived_source_parser_and_compatibility_import(combined_inputs):
    assert importlib.util.find_spec('src.review_source_archive'), 'pure archive parser is missing'
    from src.review_source_archive import parse_archived_source, load_archived_source
    from scripts.prepare_review_report import load_archived_source as compatibility
    a,_,archive,_=combined_inputs
    nodes,source=parse_archived_source(a,*(archive[n].encode() for n in
        ('review_run.json','semantic_document.xml','extraction_report.json')))
    assert nodes and source['pdf_filename'].endswith('.pdf')
    assert compatibility is load_archived_source
    assert load_archived_source(a)[:2]==(nodes,source)


def test_model_revalidates_after_historical_inputs_are_removed(combined_inputs, tmp_path):
    import shutil
    report=api().build_combined_report(*combined_inputs)
    for name in ('bundle','master','run','checklist'):
        shutil.rmtree(tmp_path/name)
    assert len(api().validate_combined_report(report)['checklist'])==59
