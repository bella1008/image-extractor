"""Thin presentation mapping for report formats, independent of XLSX libraries."""
from collections import Counter
from copy import deepcopy
from dataclasses import asdict
import json

CHECKLIST_COLUMNS = ('scope', 'exclude_scope', 'common_id', 'check_id', 'section_heading', 'language',
                     'required_text', 'evidence_excerpt', 'result', 'description', 'pdf_pages',
                     'source_node_ids', 'structure_types', 'evidence_ids', 'reviewer_note')
EVIDENCE_COLUMNS = ('evidence_id', 'check_id', 'evidence_kind', 'composition_method', 'language',
                    'pdf_pages', 'required_fragment', 'text', 'source_node_ids', 'structure_types',
                    'xml_paths', 'mcids', 'object_refs', 'visual_node_ids', 'caveats')
EXCLUDED_COLUMNS = ('check_id', 'common_id', 'language', 'scope', 'exclude_scope', 'approval_status', 'status', 'reason')


def _description(row, category):
    if category == 'strict_evidence':
        return '문구는 찾았지만 적용 조건과 구조 역할은 아직 검사하지 않았습니다.'
    if category == 'structure_candidate':
        method = row['candidate_matches'][0].get('method')
        if method == 'adjacent_paragraphs':
            return '서로 다른 XML 문단에 나뉜 전체 문구 후보를 찾았으며 적용 조건과 구조 역할은 검토가 필요합니다.'
        return 'XML 구조에서 전체 문구 후보를 찾았으며 적용 조건과 구조 역할은 검토가 필요합니다.'
    if category == 'distributed_fragments':
        partial = row['fragment_observations']['status'] == 'partial_fragments_located'
        return ('일부 문구의 분산 근거를 찾았으며 전체 요구사항은 확인하지 못했습니다.' if partial else
                '여러 XML 구조에 나뉜 문구 근거를 찾았지만 전체 요구사항의 순서·수량·적용 조건은 확인하지 못했습니다.')
    if row.get('reason') == 'unsupported_selector' or row.get('candidate_reason') == 'unsupported_match_method':
        return '이 항목의 구조 또는 검사 방식을 지원하지 않아 확인하지 못했습니다.'
    reason = row.get('candidate_reason') or row.get('reason')
    return {'heading_not_found': '검토할 제목 범위를 찾지 못해 문구를 확인하지 못했습니다.',
            'ambiguous_heading': '검토할 제목 범위가 여러 곳이어서 문구를 확인하지 못했습니다.',
            'unsafe_heading': '제목 범위의 구조 근거가 불확실하여 문구를 확인하지 못했습니다.'}.get(
                reason, '선택한 XML 범위에서 문구 근거를 찾지 못했으며 원문 확인이 필요합니다.')


def _node_metadata(document):
    if document is None:
        return None
    if isinstance(document, dict):
        return document
    parents = {child.node_id: node.node_id for node in document.iter_nodes()
               for child in node.content if not isinstance(child, str)}
    return {node.node_id: {'structure_type': node.structure_type,
                          'parent_id': parents.get(node.node_id),
                          'evidence': [asdict(e) for e in node.evidence]}
            for node in document.iter_nodes()}


def _node_lineages(nodes):
    lineages = {}
    for key in nodes:
        pending, current = [], key
        seen = set()
        while current is not None and current not in lineages:
            if current in seen or current not in nodes or 'parent_id' not in nodes[current]:
                raise ValueError(f'invalid source parent relationship: {current}')
            seen.add(current)
            pending.append(current)
            current = nodes[current]['parent_id']
        lineage = (*lineages[current], current) if current is not None else ()
        for child in reversed(pending):
            lineages[child] = lineage
            lineage = (*lineage, child)
    return lineages


def _validate_relationships(item, nodes, lineages):
    if 'parts' not in item or not ('owner_id' in item or 'owner_ids' in item):
        return
    owners = tuple(item.get('owner_ids', (item['owner_id'],) if 'owner_id' in item else ()))
    if not owners or len(set(owners)) != len(owners):
        raise ValueError('invalid source owner relationship')
    if 'owner_id' in item and owners != (item['owner_id'],):
        raise ValueError('conflicting source owner relationship')

    def belongs_to(key, owner):
        # Ownership stops at a nested block even when that block is a descendant.
        while key != owner:
            if owner not in lineages[key]:
                return False
            kind, parent = nodes[key]['structure_type'], nodes[key]['parent_id']
            heading_body = kind == 'list_body' and parent == owner and nodes[owner]['structure_type'] == 'heading'
            if kind not in ('text', 'span', 'label', 'figure') and not heading_body:
                return False
            key = parent
        return True

    groups = item.get('groups', (item['parts'],))
    if len(groups) != len(owners) or [p for group in groups for p in group] != list(item['parts']):
        raise ValueError('source group/owner relationship differs')
    for owner, group in zip(owners, groups):
        if any(not belongs_to(part['node_id'], owner) for part in group):
            raise ValueError('source part/owner relationship differs')
    if 'structure_type' in item and item['structure_type'] != nodes[owners[0]]['structure_type']:
        raise ValueError('source owner type relationship differs')
    if 'ancestor_ids' in item and tuple(item['ancestor_ids']) != lineages[owners[0]]:
        raise ValueError('source ancestor relationship differs')
    if 'container_ids' in item:
        containers = tuple(key for key in (*lineages[owners[0]], owners[0])
                           if nodes[key]['structure_type'] in ('list_item', 'table', 'table_row', 'table_cell'))
        if tuple(item['container_ids']) != containers or any(
                container not in (*lineages[owner], owner) for container in containers for owner in owners):
            raise ValueError('source container relationship differs')
    for visual in item.get('visual_node_ids', ()):
        if nodes[visual]['structure_type'] != 'figure' or not any(belongs_to(visual, owner) for owner in owners):
            raise ValueError('source visual relationship differs')


def _validate_references(value, nodes, lineages):
    if isinstance(value, dict):
        if value.get('node_id') in nodes:
            supplied = value.get('evidence', value.get('source_evidence', ()))
            expected = {json.dumps(e, sort_keys=True) for e in nodes[value['node_id']]['evidence']}
            if any(json.dumps(e, sort_keys=True) not in expected for e in supplied):
                raise ValueError(f"source evidence differs for node: {value['node_id']}")
        for key, item in value.items():
            if key in ('node_id', 'owner_id'):
                refs = () if item is None else (item,)
            elif key in ('owner_ids', 'ancestor_ids', 'container_ids', 'visual_node_ids'):
                refs = item
            else:
                refs = ()
            for ref in refs:
                if ref not in nodes:
                    raise ValueError(f'unknown source node: {ref}')
            _validate_references(item, nodes, lineages)
        _validate_relationships(value, nodes, lineages)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _validate_references(item, nodes, lineages)


def build_report_view(report: dict, *, document=None, source=None) -> dict:
    """Map an observation without evaluating it; optional document supplies node metadata.

    document accepts ReviewDocument or an archived node-id/metadata mapping.
    The production command verifies archived metadata bytes before calling here.
    """
    if report.get('schema_version') != 'checklist-observation/2' or report.get('decision_status') != 'not_evaluated':
        raise ValueError('expected an unevaluated observation schema 2')
    checklist, evidence, excluded = [], [], []
    nodes = _node_metadata(document)
    if nodes is not None:
        _validate_references(report['rows'], nodes, _node_lineages(nodes))
    source_panel = deepcopy(source) if source is not None else {'availability': 'unavailable'}
    for row in report['rows']:
        if row['status'] not in ('needs_review', 'not_applicable', 'excluded') or row['migration_status'] not in ('pending', 'excluded'):
            raise ValueError('unexpected business decision or migration activation')
        source = row['source_rule']
        if row['status'] != 'needs_review':
            excluded.append({key: row.get(key, source.get(key, '')) for key in EXCLUDED_COLUMNS})
            continue
        refs, pages, row_nodes, row_types = [], set(), [], []

        def add_evidence(item, kind, fragment=''):
            ref = f"{row['check_id']}:{len(refs)+1}"
            item_pages = sorted({e['page_index'] + 1 for p in item['parts'] for e in p['evidence'] if type(e.get('page_index')) is int})
            pages.update(item_pages)
            refs.append(ref)
            part_ids = list(dict.fromkeys(p['node_id'] for p in item['parts']))
            owners = item.get('owner_ids', [item['owner_id']] if item.get('owner_id') else [])
            visual_ids = item.get('visual_node_ids', [])
            all_ids = list(dict.fromkeys([*part_ids, *owners, *item.get('container_ids', []), *visual_ids]))
            details = []
            for key in all_ids:
                if nodes is not None:
                    details.append({'node_id': key, **deepcopy(nodes[key])})
                else:
                    details.append({'node_id': key, 'structure_type': None,
                                    'evidence': [deepcopy(e) for p in item['parts'] if p['node_id'] == key for e in p['evidence']]})
            types = [f"{d['node_id']}: {d['structure_type']}" for d in details if d['structure_type']]
            primary_ids = list(dict.fromkeys([*(owners or part_ids), *visual_ids]))
            row_nodes.extend(primary_ids)
            row_types.extend(f"{key}: {nodes[key]['structure_type']}" for key in primary_ids
                             if nodes is not None and nodes[key]['structure_type'])
            evidence.append({'evidence_id': ref, 'check_id': row['check_id'], 'evidence_kind': kind,
                             'composition_method': item.get('method', 'strict_unit'), 'language': item['language'],
                             'pdf_pages': ', '.join(map(str, item_pages)), 'required_fragment': fragment,
                             'text': item['text'], 'source_node_ids': '\n'.join(dict.fromkeys(p['node_id'] for p in item['parts'])),
                             'structure_types': '\n'.join(types), 'node_details': details,
                             'mcids': '\n'.join(dict.fromkeys(f"{d['node_id']}: {e['mcid']}" for d in details for e in d['evidence'] if e.get('mcid') is not None)),
                             'object_refs': '\n'.join(dict.fromkeys(f"{d['node_id']}: {e['object_ref']}" for d in details for e in d['evidence'] if e.get('object_ref') is not None)),
                             'visual_node_ids': '\n'.join(visual_ids),
                             'xml_paths': '\n'.join(dict.fromkeys(e['xml_path'] for p in item['parts'] for e in p['evidence'])),
                             'caveats': '; '.join(item.get('caveats', ['provisional_scope_and_role_require_review']))})
        for item in row['matches']:
            add_evidence(item, 'strict')
        for item in row['candidate_matches']:
            add_evidence(item, 'candidate')
        fragments = row.get('fragment_observations')
        if fragments:
            for fragment in fragments['fragments']:
                for item in fragment['candidates']:
                    add_evidence(item, 'fragment', fragment['required_text'])
        observation = ('strict_evidence' if row['matches'] else 'structure_candidate' if row['candidate_matches']
                       else 'distributed_fragments' if refs else 'unresolved')
        whole = row['matches'] or row['candidate_matches']
        checklist.append({'scope': source['scope'], 'exclude_scope': source['exclude_scope'],
                          'common_id': row['common_id'], 'check_id': row['check_id'],
                          'section_heading': source['legacy_section_heading'], 'language': source['language'],
                          'required_text': source['required_text'],
                          'evidence_excerpt': '\n\n'.join(item['text'] for item in whole),
                          'result': 'needs_review', 'description': _description(row, observation),
                          'diagnostic': {'category': observation, 'observation': row['observation'],
                                         'reason': row['reason'], 'candidate_reason': row['candidate_reason'],
                                         'fragment_status': fragments['status'] if fragments else None},
                          'source_node_ids': '\n'.join(dict.fromkeys(row_nodes)),
                          'structure_types': '\n'.join(dict.fromkeys(row_types)),
                          'pdf_pages': ', '.join(map(str, sorted(pages))), 'evidence_ids': '\n'.join(refs), 'reviewer_note': ''})
    return {'schema_version': 'review-report-view/2', 'decision_status': 'not_evaluated', 'context': deepcopy(report['context']),
            'source': source_panel,
            'summary': {'rule_count': len(report['rows']), 'applicable_count': len(checklist), 'excluded_count': len(excluded),
                        'evidence_count': len(evidence), 'by_observation': dict(Counter(r['diagnostic']['category'] for r in checklist))},
            'columns': {'checklist': CHECKLIST_COLUMNS, 'evidence': EVIDENCE_COLUMNS, 'excluded': EXCLUDED_COLUMNS},
            'checklist': checklist, 'evidence': evidence, 'excluded': excluded}
