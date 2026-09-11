"""Observe the bounded CHK-002 item draft against a current ReviewDocument.

The service verifies master provenance and extraction gates. This pure operation
rebuilds source slices and searches the supplied document; author text is inert.
"""
from copy import deepcopy
from dataclasses import asdict

from src.checklist_item_master import EDITABLE_FIELDS
from src.checklist_item_proposal import ItemSlice, build_item_proposal, observe_item_proposal


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def observe_item_master(document, master: dict) -> dict:
    _require(master.get('schema_version') == 'checklist-item-master-draft/1'
             and master.get('activation_status') == 'draft_only', 'unsupported or activated item master')
    parent, source_items = master['parent'], master['items']
    _require(parent['check_id'] == 'CHK-002-ZC-ENG' and parent['language'] == 'ENG'
             and len(source_items) == 14, 'CHK-002 ENG fourteen-item pilot required')
    proposal = build_item_proposal(parent, tuple(ItemSlice(i['item_key'], i['start'], i['end'])
                                                for i in source_items))
    originals = {i['item_key']: i for i in source_items}
    for item in proposal['items']:
        source = originals[item['item_key']]
        _require(all(source[k] == item[k] for k in ('source_check_id', 'common_id', 'required_text',
                    'language', 'scope', 'exclude_scope', 'start', 'end')), 'source item changed')
        _require(source['model_applicability'] == 'unknown' and source['condition_state'] == 'unverified',
                 'item applicability cannot be activated')
        _require(all(isinstance(source[k], str) for k in EDITABLE_FIELDS), 'author proposal must be text')
    observed = observe_item_proposal(document, proposal)
    scope = observed['scope_observation']
    anchor = scope['heading']
    examined = bool(scope['parent_status'] == 'needs_review' and anchor
                    and anchor['usable_for_observation'] and anchor['language'] == 'ENG' and scope['end'])
    items = []
    descriptions = {
        'not_examined': '제목 또는 언어·적용 범위를 확인하지 못해 항목 문구를 조사하지 않았습니다. 누락 판정은 아닙니다.',
        'not_found': '확인한 제목 범위의 목록에서 항목 전체 문구를 찾지 못했습니다. 모델 적용 여부와 누락 여부는 검토가 필요합니다.',
        'ambiguous': '항목 전체 문구가 여러 목록 위치에서 발견되었습니다. 대응 위치와 모델 적용 여부를 검토해야 합니다.',
        'found': '항목 전체 문구를 한 목록 위치에서 찾았습니다. 모델 적용 여부는 미확정입니다.',
    }
    for item in observed['items']:
        count = len(item['candidates'])
        state = 'not_examined' if not examined else 'ambiguous' if count > 1 else 'found' if count else 'not_found'
        description = descriptions[state]
        if item['condition_candidates']:
            description += ' 별표 조건 안내는 연결 후보이며 조건 관계는 미검증입니다.'
        items.append({**deepcopy(item), 'observation': state, 'description': description,
                      'model_applicability': 'unknown',
                      'author_proposal': {k: originals[item['item_key']][k] for k in EDITABLE_FIELDS}})
    return {'schema_version': 'checklist-item-observation/1', 'decision_status': 'not_evaluated',
            'activation_status': 'draft_only', 'context': asdict(document.context),
            'parent_check_id': parent['check_id'], 'parent': deepcopy(parent),
            'scope_observation': scope, 'items': items,
            'summary': {'item_count': len(items),
                        **{state: sum(i['observation'] == state for i in items)
                           for state in ('found', 'ambiguous', 'not_found', 'not_examined')},
                        'needs_review': len(items),
                        'condition_candidate_items': sum(bool(i['condition_candidates']) for i in items)},
            'master_source': deepcopy(master['source']), 'comparison_policy': observed['comparison_policy']}
