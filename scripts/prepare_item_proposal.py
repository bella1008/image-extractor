"""Produce a checked, non-active CHK-002 item migration proposal."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from src.checklist_item_proposal import ItemSlice, build_item_proposal, observe_item_proposal, classify_migration_units
from src.checklist_migration import read_excel_rows
from src.review_service import DEFAULT_MAPPING, FROZEN_DRAFT_JSON_SHA256, read_completed_observation

ZC_ITEMS = (
    ('simple_user_guide', 'Simple User Guide'),
    ('warranty_regulatory_guide', 'Warranty Card / Regulatory Guide (Not available in some locations)'),
    ('samsung_smart_remote', 'Samsung Smart Remote'),
    ('remote_control', 'Remote Control'),
    ('standard_remote_control', 'Standard Remote Control'),
    ('batteries', 'Batteries'),
    ('tv_power_cord', 'TV Power Cord'),
    ('wall_mount_adapter', 'Wall Mount Adapter x 2'),
    ('slim_power_cord', 'Slim Power Cord'),
    ('power_box', 'Power Box'),
    ('power_box_cable', 'Power Box Cable x 2'),
    ('c_type_power_adapter', 'C-type Power Adapter'),
    ('c_to_c_cable', 'C to C Cable'),
    ('wireless_one_connect_box', 'Wireless One Connect Box'),
)


def zc_item_slices(parent):
    if parent['check_id'] != 'CHK-002-ZC-ENG' or parent['required_text'] != '\n'.join(t for _, t in ZC_ITEMS):
        raise ValueError('explicit ZC proposal no longer matches frozen parent wording')
    offset, result = 0, []
    for key, text in ZC_ITEMS:
        result.append(ItemSlice(key, offset, offset + len(text)))
        offset += len(text) + 1
    return tuple(result)


def prepare_proposal(run_dir: Path, pdf: Path, output: Path, mapping: Path = DEFAULT_MAPPING) -> dict:
    from src.semantic_xml_reader import read_review_bundle
    from src.xml_review_gate import require, validate_bundle
    if output.exists():
        raise FileExistsError(f'use a fresh proposal file: {output}')
    completion = run_dir / 'review_complete.json'
    before_completion = completion.read_bytes()
    report = read_completed_observation(run_dir)
    inputs = report['inputs']
    paths = {key: Path(inputs[key]) for key in ('receipt', 'draft_json', 'draft_excel')}
    before = {key: path.read_bytes() for key, path in paths.items()}
    for key, data in before.items():
        require(hashlib.sha256(data).hexdigest() == inputs[key + '_sha256'], f'changed {key}')
    require(hashlib.sha256(before['draft_json']).hexdigest() == FROZEN_DRAFT_JSON_SHA256, 'unfrozen draft')
    payload = json.loads(before['draft_json'])
    require(payload['activation_status'] == 'blocked_pending_contract_review', 'active draft not permitted')
    require(payload['master_sha256'] == inputs['draft_excel_sha256'], 'Excel hash mismatch')
    rules = read_excel_rows(paths['draft_excel'], draft=True)
    require(rules == payload['rules'] == [r['source_rule'] for r in report['rows']], 'source rules differ')
    receipt = json.loads(before['receipt'])
    require(receipt == inputs['source_bundle'], 'source receipt differs')
    bundle = paths['receipt'].parent
    document = read_review_bundle(bundle, receipt, pdf_path=pdf, mapping_path=mapping)
    parent = next(r for r in rules if r['check_id'] == 'CHK-002-ZC-ENG')
    result = observe_item_proposal(document, build_item_proposal(parent, zc_item_slices(parent)))
    result['inventory'] = classify_migration_units(rules)
    result['inventory_summary'] = dict(Counter(r['category'] for r in result['inventory']))
    result['source'] = {'pdf_filename': pdf.name, 'pdf_sha256': receipt['pdf_sha256'],
                        'semantic_xml_sha256': receipt['artifacts']['semantic_document.xml'],
                        'bundle_path': str(bundle.resolve()), 'receipt_ref': str(paths['receipt'].resolve()),
                        'receipt_sha256': inputs['receipt_sha256'], 'draft_excel_sha256': inputs['draft_excel_sha256'],
                        'source_completion_sha256': hashlib.sha256(before_completion).hexdigest()}
    validate_bundle(bundle, receipt, pdf_path=pdf, mapping_path=mapping)
    require(all(path.read_bytes() == before[key] for key, path in paths.items()), 'source changed during proposal')
    require(read_completed_observation(run_dir) == report and completion.read_bytes() == before_completion,
            'completed snapshot changed during proposal')
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(result, stream, ensure_ascii=True, indent=2)
        stream.write('\n')
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('run_dir', type=Path)
    parser.add_argument('pdf', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    prepare_proposal(args.run_dir, args.pdf, args.output)


if __name__ == '__main__':
    main()
