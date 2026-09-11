from copy import deepcopy

import pytest

from src import checklist_item_proposal as proposal
from tests.test_checklist_observation import rule, document, heading, node


def test_explicit_items_preserve_parent_and_exact_slices_including_conditions():
    parent = rule(required_text='  Guide\r\nAdapter x 2 (some models)\n')
    before = deepcopy(parent)
    specs = (proposal.ItemSlice('guide', 2, 7), proposal.ItemSlice('adapter', 9, 34))
    result = proposal.build_item_proposal(parent, specs)
    assert result['source_rule'] == before == parent
    assert [r['required_text'] for r in result['items']] == ['Guide', 'Adapter x 2 (some models)']
    assert ''.join(p['text'] for p in result['source_segments']) == parent['required_text']
    assert all(r['proposal_state'] == 'pending' and r['condition_state'] == 'unverified' for r in result['items'])
    assert all(r['source_check_id'] == parent['check_id'] for r in result['items'])


def test_item_keys_do_not_depend_on_manifest_order():
    parent = rule(required_text='First\nSecond')
    specs = (proposal.ItemSlice('first', 0, 5), proposal.ItemSlice('second', 6, 12))
    assert proposal.build_item_proposal(parent, specs) == proposal.build_item_proposal(parent, tuple(reversed(specs)))


@pytest.mark.parametrize('specs', [
    [('a', 0, 5)], [('a', 0, 5), ('a', 6, 12)],
    [('a', 0, 7), ('b', 6, 12)], [('a', -1, 5), ('b', 6, 12)],
    [('a', 0, 5), ('b', 6, 13)], [('a', 0, 5), ('', 6, 12)],
])
def test_missing_overlap_duplicate_or_invalid_slices_rejected(specs):
    with pytest.raises(ValueError):
        proposal.build_item_proposal(rule(required_text='First\nSecond'), tuple(proposal.ItemSlice(*s) for s in specs))


def test_exact_item_search_does_not_match_longer_item_and_keeps_source_marker():
    parent = rule(required_text='Power Box\nPower Box Cable x 2', block_type='item_list')
    draft = proposal.build_item_proposal(parent, (proposal.ItemSlice('box', 0, 9), proposal.ItemSlice('cable', 10, 29)))
    doc = document(heading(), node('list', 'list',
        node('i1', 'list_item', node('b1', 'list_body', ' *Power Box')),
        node('i2', 'list_item', node('b2', 'list_body', ' *Power Box Cable x 2'))),
        node('condition', 'paragraph', '*: Some items depend on the model.'))
    result = proposal.observe_item_proposal(doc, draft)
    assert len(result['items'][0]['candidates']) == 1
    assert result['items'][0]['candidates'][0]['owner_ids'] == ['b1']
    assert result['items'][0]['candidates'][0]['text'] == ' *Power Box'
    assert result['items'][0]['source_marker'] == '*'
    assert result['items'][0]['condition_candidates'][0]['owner_ids'] == ['condition']
    assert result['decision_status'] == 'not_evaluated'
    assert result['items'][0]['condition_state'] == 'unverified'
    assert 'candidates' not in draft['items'][0]


def test_item_search_stops_at_next_heading_and_does_not_invent_missing_conditions():
    parent = rule(required_text='Guide', block_type='item_list')
    draft = proposal.build_item_proposal(parent, (proposal.ItemSlice('guide', 0, 5),))
    doc = document(heading(), heading('other', 'Other heading'), node('item', 'list_body', 'Guide'))
    result = proposal.observe_item_proposal(doc, draft)
    assert not result['items'][0]['candidates']
    assert not result['items'][0]['condition_candidates']


def test_modified_or_approved_proposal_is_rejected_before_observation():
    draft = proposal.build_item_proposal(rule(required_text='Guide'), (proposal.ItemSlice('guide', 0, 5),))
    for field, value in [('required_text', 'Changed'), ('proposal_state', 'approved')]:
        bad = deepcopy(draft)
        bad['items'][0][field] = value
        with pytest.raises(ValueError):
            proposal.observe_item_proposal(document(heading()), bad)


def test_triage_preserves_all_rules_and_does_not_classify_newlines_as_items():
    rules = [rule(check_id='T-1', required_text='One\nTwo'), rule(check_id='T-2', block_type='item_list'),
             rule(check_id='T-3', match_method='table_row', block_type='spec_table')]
    before = deepcopy(rules)
    inventory = proposal.classify_migration_units(rules)
    assert [r['check_id'] for r in inventory] == ['T-1', 'T-2', 'T-3']
    assert inventory[0]['category'] == 'retain_or_define'
    assert inventory[1]['category'] == 'item_split_candidate'
    assert inventory[2]['category'] == 'table_relation_review'
    assert rules == before


def test_zc_manifest_requires_exact_frozen_wording_and_retains_fourteen_keys():
    from scripts.prepare_item_proposal import zc_item_slices, ZC_ITEMS
    parent = rule(check_id='CHK-002-ZC-ENG', required_text='\n'.join(text for _, text in ZC_ITEMS))
    result = proposal.build_item_proposal(parent, zc_item_slices(parent))
    assert len(result['items']) == 14
    assert len({i['item_key'] for i in result['items']}) == 14
    parent['required_text'] = parent['required_text'].replace(' x 2', ' x 3')
    with pytest.raises(ValueError):
        zc_item_slices(parent)


def test_actual_checked_zc_proposal_is_non_active_and_all_items_have_source(tmp_path, monkeypatch):
    from pathlib import Path
    from scripts.prepare_item_proposal import prepare_proposal
    run_dir = Path(__file__).resolve().parents[1] / 'outputs/review_service_zc_20260911_r2'
    pdf = Path(__file__).resolve().parents[1] / 'samples/SUG_RAW/TV_ZC/BN68-25100B-00_SUG_Y26 TV ALL_ZC_L02_260122.0.pdf'
    if not run_dir.exists() or not pdf.exists():
        pytest.skip('local checked ZC bundle required')
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / 'samples/tagged_pdf_xml_poc/src'))
    output = tmp_path / 'proposal.json'
    result = prepare_proposal(run_dir, pdf, output)
    assert output.exists()
    assert len(result['inventory']) == 547
    assert len(result['items']) == 14
    assert all(len(i['candidates']) == 1 for i in result['items'])
    assert sum(i['source_marker'] == '*' for i in result['items']) == 12
    assert sum(bool(i['condition_candidates']) for i in result['items']) == 12
    assert result['activation_status'] == 'proposal_only'
    with pytest.raises(FileExistsError):
        prepare_proposal(run_dir, pdf, output)


def test_mixed_language_and_empty_unknown_structures_never_form_item_candidates():
    parent = rule(required_text='Guide', block_type='item_list')
    draft = proposal.build_item_proposal(parent, (proposal.ItemSlice('guide', 0, 5),))
    for content in [node('foreign', 'list_body', 'Guide', lang='C-FRA'),
                    node('unsafe', 'list_body', 'Guide', node('unknown', 'unknown'))]:
        result = proposal.observe_item_proposal(document(heading(), content), draft)
        assert not result['items'][0]['candidates']


@pytest.mark.parametrize('when', ['before', 'during'])
def test_proposal_cli_rejects_changed_draft_without_publishing(tmp_path, monkeypatch, when):
    import hashlib
    import json
    from pathlib import Path
    import shutil
    from scripts import prepare_item_proposal as cli
    root = Path(__file__).resolve().parents[1]
    original = root / 'outputs/review_service_zc_20260911_r2'
    pdf = root / 'samples/SUG_RAW/TV_ZC/BN68-25100B-00_SUG_Y26 TV ALL_ZC_L02_260122.0.pdf'
    if not original.exists() or not pdf.exists():
        pytest.skip('local checked ZC bundle required')
    monkeypatch.syspath_prepend(str(root / 'samples/tagged_pdf_xml_poc/src'))
    run_dir = tmp_path / 'copied_run'
    shutil.copytree(original, run_dir)
    report = json.loads((run_dir / 'observation.json').read_text())
    for key in ('draft_json', 'draft_excel'):
        target = run_dir / Path(report['inputs'][key]).name
        shutil.copy2(report['inputs'][key], target)
        report['inputs'][key] = str(target)
    report['inputs']['receipt'] = str(run_dir / 'extraction/review_run.json')
    report_bytes = json.dumps(report).encode()
    (run_dir / 'observation.json').write_bytes(report_bytes)
    receipt = json.loads((run_dir / 'review_complete.json').read_text())
    receipt['artifacts']['observation.json'] = hashlib.sha256(report_bytes).hexdigest()
    (run_dir / 'review_complete.json').write_text(json.dumps(receipt))
    draft_path = Path(report['inputs']['draft_json'])
    def alter():
        draft_path.write_bytes(draft_path.read_bytes() + b'\n')
    if when == 'before':
        alter()
    else:
        real = cli.observe_item_proposal
        def during(*args):
            result = real(*args)
            alter()
            return result
        monkeypatch.setattr(cli, 'observe_item_proposal', during)
    output = tmp_path / 'proposal.json'
    with pytest.raises(ValueError, match='changed'):
        cli.prepare_proposal(run_dir, pdf, output)
    assert not output.exists()
