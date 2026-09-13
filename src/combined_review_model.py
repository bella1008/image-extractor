"""Self-contained, unevaluated parent/item observation composition."""
from collections import Counter
from copy import deepcopy
import hashlib
import json
from xml.etree import ElementTree as ET

from src.item_review_service import _validate_report, _unique_object, _canonical
from src.review_report_view import build_report_view, _validate_references, _node_lineages
from src.review_source_archive import parse_archived_source

SCHEMA = 'combined-review-report/1'
ARCHIVE_NAMES = ('review_run.json', 'semantic_document.xml', 'extraction_report.json')
# SHA-256 of ordered [item_key, required_text] pairs from the approved ZC_ITEMS
# definition in scripts.prepare_item_proposal (compact ASCII JSON). Not a DB lookup.
ITEM_DEFINITION_SHA256 = '9d8f16e77a0ff1e32a36c150cafb9ae1aaec26e910d355136cc0363936a799f8'


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def parse_json(data):
    return json.loads(data, object_pairs_hook=_unique_object,
                      parse_constant=lambda x: (_ for _ in ()).throw(ValueError('non-finite JSON number')))


def validate_source_run(files, report, kind):
    """Check exact original bytes embedded in the combined archive."""
    is_item = kind == 'items'
    receipt_name = 'item_review_complete.json' if is_item else 'review_complete.json'
    data_name = 'item_observation.json' if is_item else 'observation.json'
    require(isinstance(files, dict) and receipt_name in files, 'missing source completion')
    receipt = parse_json(files[receipt_name])
    require(isinstance(receipt, dict), 'invalid source completion shape')
    versions = ({'checklist-item-observation-run/1': {data_name, 'item_review.html'},
                 'checklist-item-observation-run/2': {data_name}} if is_item else
                {'review-observation-run/1': {data_name, 'review.html'},
                 'review-observation-run/2': {data_name}})
    require(receipt.get('schema_version') in versions and receipt.get('status') == 'ready_for_human_review'
            and receipt.get('decision_status') == 'not_evaluated', 'invalid source completion state')
    if is_item:
        require(receipt.get('activation_status') == 'draft_only', 'activated source completion')
    names = versions[receipt['schema_version']]
    require(set(files) == names | {receipt_name} and isinstance(receipt.get('artifacts'), dict)
            and set(receipt['artifacts']) == names, 'unexpected source artifacts')
    for name in names:
        require(isinstance(files[name], str) and digest(files[name].encode('utf-8')) == receipt['artifacts'][name],
                f'source artifact changed: {name}')
    require(_canonical(parse_json(files[data_name])) == _canonical(report), 'embedded source report differs')
    require(_canonical(receipt.get('summary')) == _canonical(report['summary']), 'source summary differs')


def _source_texts(xml):
    """Decode text nodes without importing the PDF extractor on archival reads."""
    result = {}
    def visit(element, path):
        if element.tag == 'text':
            pieces = [element.text or '']
            for child in element:
                require(child.tag == 'control' and set(child.attrib) == {'code'}, 'invalid XML text child')
                code = child.get('code')
                number = int(code, 16)
                require(0 <= number <= 0x10FFFF and code == f'{number:04X}' and
                        not (number in (9, 10, 13) or 32 <= number <= 0xD7FF or
                             0xE000 <= number <= 0xFFFD or 0x10000 <= number <= 0x10FFFF), 'invalid XML control')
                pieces.extend((chr(number), child.tail or ''))
            result['xml:' + '/'.join(map(str, path))] = ''.join(pieces)
        else:
            children = [c for c in element if c.tag not in ('attributes','role-map','multilingual-heading-audit')]
            for i, child in enumerate(children):
                visit(child, (*path, i))
    visit(ET.fromstring(xml), ())
    return result


def _validate_text_parts(value, texts, nodes):
    if isinstance(value, dict):
        if 'content_index' in value and 'node_id' in value:
            require(type(value['content_index']) is int and value['content_index'] == 0
                    and value['node_id'] in texts and value.get('text') == texts[value['node_id']],
                    'evidence text differs from XML')
            require(_canonical(value.get('evidence')) == _canonical(nodes[value['node_id']]['evidence']),
                    'evidence page or path differs from XML')
        if 'parts' in value:
            require('owner_id' in value or 'owner_ids' in value, 'missing source evidence owner')
            require(bool(value['parts']), 'empty source evidence parts')
            groups = value.get('groups', [value['parts']])
            separator = value.get('separator', '')
            require(separator in ('', '\n') and all(groups), 'invalid source composition')
            for part in [*value['parts'], *(p for group in groups for p in group)]:
                require(isinstance(part, dict) and
                        {'node_id', 'content_index', 'text', 'language', 'evidence'} <= part.keys(),
                        'missing mandatory source evidence fields')
            expected = separator.join(''.join(p['text'] for p in group) for group in groups)
            require(value.get('text') == expected, 'aggregate evidence text differs from XML parts')
        if 'owner_ids' in value and 'structure_types' in value:
            require(value['structure_types'] == [nodes[key]['structure_type'] for key in value['owner_ids']],
                    'evidence tag differs from XML')
        for child in value.values():
            _validate_text_parts(child, texts, nodes)
    elif isinstance(value, (list, tuple)):
        for child in value:
            _validate_text_parts(child, texts, nodes)


def _validated_view(report):
    require(isinstance(report, dict) and report.get('schema_version') == SCHEMA
            and report.get('decision_status') == 'not_evaluated'
            and report.get('activation_status') == 'draft_only', 'invalid combined report state')
    a, b = report['checklist'], report['items']
    _validate_report(b)
    require(set(report['source_runs']) == {'checklist', 'items'}, 'invalid source run set')
    for kind, data in (('checklist', a), ('items', b)):
        validate_source_run(report['source_runs'][kind], data, kind)
    require(a['context'] == b['context'] and a['context']['source_token'] == 'ZC_L02'
            and a['context']['doc_type'] == 'A2' and a['language'] == 'ENG', 'incompatible review context')
    require('ENG' in a['context']['expected_languages'], 'review language absent')
    archive = report['source_archive']
    require(set(archive) == set(ARCHIVE_NAMES), 'invalid source archive set')
    archive_bytes = [archive[name].encode('utf-8') for name in ARCHIVE_NAMES]
    nodes, source = parse_archived_source(a, *archive_bytes)
    item_nodes, item_source = parse_archived_source(b, *archive_bytes)
    require(nodes == item_nodes, 'different XML nodes')
    target = b['target_source']
    for key in ('pdf_filename', 'pdf_sha256', 'semantic_xml_sha256', 'receipt_sha256'):
        require(target.get(key) == source[key] == item_source[key], f'different target {key}')
    require(b['inputs']['pdf_sha256'] == source['pdf_sha256'], 'item PDF identity differs')
    ids = [row['check_id'] for row in a['rows']]
    require(all(row['observation'] in ('not_examined','evidence_found','not_found_in_selected_units')
                for row in a['rows']), 'invalid checklist observation state')
    require(len(ids) == len(set(ids)), 'duplicate checklist key')
    parent = [r for r in a['rows'] if r['check_id'] == b['parent_check_id']]
    require(len(parent) == 1 and parent[0]['status'] == 'needs_review', 'missing or inapplicable item parent')
    require(_canonical(parent[0]['source_rule']) == _canonical(b['parent']), 'item parent rule differs')
    definitions = [(i['item_key'], i['required_text']) for i in b['items']]
    require(digest(json.dumps(definitions, ensure_ascii=True, separators=(',', ':')).encode()) == ITEM_DEFINITION_SHA256,
            'fixed item definition differs')
    require(all(i['source_check_id'] == b['parent_check_id'] and i['language'] == 'ENG' and i['proposal_state'] == 'pending'
                and i['scope'] == b['parent']['scope'] and i['exclude_scope'] == b['parent']['exclude_scope']
                for i in b['items']), 'item scope or parent differs')
    view = build_report_view(a, document=nodes, source=source)
    require(a['summary']['rule_count'] == len(a['rows'])
            and a['summary']['by_status'] == dict(Counter(r['status'] for r in a['rows'])), 'checklist summary differs')
    _validate_references(b['items'], nodes, _node_lineages(nodes))
    _validate_references(b['scope_observation'], nodes, _node_lineages(nodes))
    texts = _source_texts(archive_bytes[1])
    _validate_text_parts(a['rows'], texts, nodes)
    _validate_text_parts(b['items'], texts, nodes)
    return view


def _summary(report, view):
    return {'parent_check_count': len(view['checklist']), 'child_item_count': len(report['items']['items']),
            'checklist_evidence_count': len(view['evidence']),
            'item_evidence_count': sum(len(i[k]) for i in report['items']['items'] for k in ('candidates','condition_candidates')),
            'excluded_count': len(view['excluded']), 'rule_count': len(report['checklist']['rows'])}


def build_combined_report(checklist, items, source_archive, source_runs):
    result = deepcopy({'schema_version': SCHEMA, 'decision_status': 'not_evaluated', 'activation_status': 'draft_only',
                       'checklist': checklist, 'items': items, 'source_archive': source_archive, 'source_runs': source_runs})
    view = _validated_view(result)
    result['summary'] = _summary(result, view)
    return result


def validate_combined_report(report):
    """Rebuild the checklist view and verify combined counts without old files."""
    view = _validated_view(report)
    require(_canonical(report.get('summary')) == _canonical(_summary(report, view)), 'combined summary differs')
    return view
