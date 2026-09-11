"""Explicit, reversible checklist item proposals; never an active runtime DB."""
from copy import deepcopy
from dataclasses import asdict, dataclass
import re

from src.checklist_migration import restore_source_rows, validate_rows
from src.checklist_observation import comparison_text, observe_checklist, _locations
from src.review_evidence_windows import build_evidence_windows


@dataclass(frozen=True)
class ItemSlice:
    item_key: str
    start: int
    end: int


def build_item_proposal(parent: dict, slices: tuple[ItemSlice, ...]) -> dict:
    """The caller supplies boundaries and keys; line breaks are not requirements."""
    validate_rows(restore_source_rows([parent]))
    text = parent['required_text']
    seen, cursor, items, segments = set(), 0, [], []
    if not slices:
        raise ValueError('item definitions required')
    for item in sorted(slices, key=lambda x: x.start):
        if (not isinstance(item.item_key, str) or not re.fullmatch(r'[a-z][a-z0-9_]*', item.item_key)
                or item.item_key in seen or type(item.start) is not int or type(item.end) is not int
                or not 0 <= cursor <= item.start < item.end <= len(text)):
            raise ValueError('invalid or overlapping item definition')
        gap = text[cursor:item.start]
        if gap.strip() or not text[item.start:item.end].strip():
            raise ValueError('unassigned wording or empty item')
        if gap:
            segments.append({'kind': 'separator', 'text': gap})
        wording = text[item.start:item.end]
        segments.append({'kind': 'item', 'item_key': item.item_key, 'text': wording})
        items.append({**asdict(item), 'source_check_id': parent['check_id'], 'common_id': parent['common_id'],
                      'required_text': wording, 'language': parent['language'], 'scope': parent['scope'],
                      'exclude_scope': parent['exclude_scope'], 'proposal_state': 'pending',
                      'condition_state': 'unverified'})
        seen.add(item.item_key)
        cursor = item.end
    if text[cursor:].strip():
        raise ValueError('unassigned wording')
    if text[cursor:]:
        segments.append({'kind': 'separator', 'text': text[cursor:]})
    return {'schema_version': 'checklist-item-proposal/1', 'decision_status': 'not_evaluated',
            'activation_status': 'proposal_only', 'source_rule': deepcopy(parent),
            'source_segments': segments, 'items': items}


def observe_item_proposal(document, proposal: dict) -> dict:
    """Locate complete item wording in bounded XML list bodies, not substrings.

    A PDF-observed leading * can be a condition marker. It is kept in evidence;
    locating nearby *: notes only proposes an association, never applicability.
    """
    rebuilt = build_item_proposal(proposal['source_rule'], tuple(
        ItemSlice(i['item_key'], i['start'], i['end']) for i in proposal['items']))
    if proposal != rebuilt:
        raise ValueError('item proposal changed or activated')
    result = deepcopy(proposal)
    row = observe_checklist(document, [proposal['source_rule']])['rows'][0]
    anchor, boundary = row['heading'], row['candidate_scope_end']
    starts, ends, *_ = _locations(document)
    nodes = {n.node_id: n for n in document.iter_nodes()}
    windows = []
    if (row['status'] == 'needs_review' and anchor and anchor['usable_for_observation'] and boundary
            and anchor['language'] == proposal['source_rule']['language']):
        windows = [w for w in build_evidence_windows(document)
                   if w.method == 'atomic_text' and w.language == anchor['language']
                   and all(anchor['end'] < starts[k] and ends[k] < boundary['position'] for k in w.owner_ids)]

    def view(window):
        return {**asdict(window), 'owner_ids': list(window.owner_ids), 'text': window.text,
                'parts': [asdict(p) for p in window.parts],
                'structure_types': [nodes[k].structure_type for k in window.owner_ids]}

    notes = [view(w) for w in windows if all(nodes[k].structure_type == 'paragraph' for k in w.owner_ids)
             and comparison_text(w.text).startswith('*:')]
    for item in result['items']:
        needle = comparison_text(item['required_text'])
        matches = [w for w in windows if all(nodes[k].structure_type == 'list_body' for k in w.owner_ids)
                   and comparison_text(w.text) in (needle, '*' + needle, '* ' + needle)]
        starred = any(comparison_text(w.text).startswith('*') for w in matches)
        item.update(candidates=[view(w) for w in matches], source_marker='*' if starred else '',
                    condition_candidates=deepcopy(notes) if starred else [],
                    result='needs_review', description=(
                        '항목 원문과 별표를 찾았습니다. 모델 조건 안내와의 관계 및 적용 여부는 미확정입니다.' if starred else
                        '항목 문구를 찾았습니다. 조건과 적용 여부는 미확정입니다.' if matches else
                        '확인된 제목 범위의 목록 항목에서 전체 문구를 연결하지 못했습니다. 누락 판정은 아닙니다.'))
    result['scope_observation'] = {'heading': anchor, 'end': boundary, 'parent_status': row['status']}
    result['comparison_policy'] = 'whole-list-body/whitespace-only/optional-leading-source-asterisk; no applicability approval'
    return result


def classify_migration_units(rules: list[dict]) -> list[dict]:
    """Mechanical triage only. It does not infer conditions from prose."""
    validate_rows(restore_source_rows(rules))
    result = []
    for rule in rules:
        kind, method = rule['legacy_block_type'], rule['match_method']
        category = ('item_split_candidate' if kind == 'item_list' else
                    'table_relation_review' if 'table' in kind or method in ('table_row', 'table_header') else
                    'retain_or_define')
        result.append({'check_id': rule['check_id'], 'common_id': rule['common_id'], 'language': rule['language'],
                       'legacy_block_type': kind, 'match_method': method, 'category': category,
                       'approval_status': rule['approval_status'], 'definition_state': 'pending',
                       'condition_state': 'not_inferred', 'required_text': rule['required_text']})
    return result
