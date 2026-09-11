"""Offline item report contract, independent of extraction and file I/O."""
from copy import deepcopy
from html import escape
import importlib
import re

import pytest


def report():
    evidence = {'text': ' *Power Box\n  원문 공백', 'owner_ids': ['current:item'],
                'structure_types': ['list_body'], 'parts': [
                    {'node_id': 'current:text', 'evidence': [
                        {'page_index': 0, 'xml_path': '/document/list/body/text', 'mcid': '4', 'object_ref': None}]}]}
    return {'schema_version': 'checklist-item-observation/1', 'decision_status': 'not_evaluated',
            'activation_status': 'draft_only', 'context': {'source_token': 'ZC_L02'},
            'parent_check_id': 'CHK-002-ZC-ENG', 'scope_observation': {},
            'summary': {'item_count': 1, 'found': 1, 'ambiguous': 0, 'not_found': 0,
                        'not_examined': 0, 'needs_review': 1, 'condition_candidate_items': 1},
            'target_source': {'pdf_filename': 'current.pdf', 'pdf_sha256': 'a'*64,
                              'semantic_xml_sha256': 'b'*64, 'bundle_path': 'target/bundle',
                              'receipt_ref': 'target/review_run.json', 'receipt_sha256': 'c'*64},
            'master_source': {'pdf_filename': 'historical.pdf', 'pdf_sha256': 'd'*64,
                              'semantic_xml_sha256': 'e'*64},
            'items': [{'source_check_id': 'CHK-002-ZC-ENG', 'item_key': 'power_box',
                       'required_text': 'Power Box', 'observation': 'found', 'result': 'needs_review',
                       'description': '문구 근거는 찾았지만 모델 적용 여부는 미확정입니다.',
                       'model_applicability': 'unknown', 'condition_state': 'unverified',
                       'source_marker': '*', 'candidates': [evidence],
                       'condition_candidates': [{**evidence, 'text': '*: Model-dependent.',
                                                 'owner_ids': ['current:condition']}],
                       'author_proposal': {'proposed_model_rule': '확인 전 제안',
                                           'proposal_evidence': '내부 자료', 'reviewer_note': '의견'}}]}


def render(payload):
    assert importlib.util.find_spec('src.item_review_report'), 'item report renderer missing'
    return importlib.import_module('src.item_review_report').render_item_review_html(payload)


def test_report_has_current_evidence_and_separate_historical_source():
    data = report()
    original = deepcopy(data)
    html = render(data)
    assert data == original
    for value in ('current.pdf', 'historical.pdf', 'current:item', 'current:condition',
                  'list_body', '/document/list/body/text', 'CHK-002-ZC-ENG', 'power_box',
                  '검토 판정', '설명', '검토 필요', '검토 대상 PDF', '원장 작성 당시 출처',
                  '담당자 제안', '자동 실행하지 않습니다', '*: Model-dependent.'):
        assert value in html
    assert ' *Power Box\n  원문 공백' in html
    assert 'white-space:pre-wrap' in html
    assert html.count('current.pdf') == 1
    assert 'PDF 페이지: 1' in html


def test_source_text_and_proposals_are_escaped_and_never_linked_or_executed():
    data = report()
    attack = '<script>alert("x")</script><img src="https://example.com/a">'
    data['items'][0]['description'] = attack
    data['items'][0]['candidates'][0]['text'] = attack
    data['items'][0]['author_proposal']['reviewer_note'] = attack
    data['target_source']['pdf_filename'] = attack
    html = render(data)
    assert escape(attack) in html
    assert '<script' not in html and '<img' not in html
    assert not re.search(r'<[^>]*\s(?:src|href)=', html)


@pytest.mark.parametrize('state', ['not_found', 'not_examined', 'ambiguous'])
def test_unresolved_rows_keep_their_distinct_explanation(state):
    data = report()
    data['items'][0].update(observation=state, candidates=[], condition_candidates=[],
                            description='scope message: ' + state)
    data['summary'].update(found=0, condition_candidate_items=0)
    data['summary'][state] = 1
    html = render(data)
    assert 'scope message: ' + state in html
    assert '검토 필요' in html
    assert '연결된 원문 근거 없음' in html


@pytest.mark.parametrize('change', ['schema', 'decision', 'activation', 'item_result', 'model', 'condition', 'summary'])
def test_renderer_rejects_wrong_or_activated_reports(change):
    data = report()
    if change == 'schema': data['schema_version'] = 'other/1'
    elif change == 'decision': data['decision_status'] = 'approved'
    elif change == 'activation': data['activation_status'] = 'active'
    elif change == 'item_result': data['items'][0]['result'] = 'pass'
    elif change == 'model': data['items'][0]['model_applicability'] = 'applicable'
    elif change == 'condition': data['items'][0]['condition_state'] = 'approved'
    elif change == 'summary': data['summary']['item_count'] = 2
    with pytest.raises(ValueError):
        render(data)
