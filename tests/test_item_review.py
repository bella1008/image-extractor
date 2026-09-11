from copy import deepcopy
from dataclasses import replace
import importlib
import json
from pathlib import Path

import pytest

from tests.test_checklist_observation import document, heading, node

MASTER = Path(__file__).resolve().parents[1] / 'metadata/checklist_v2/item_master_drafts/20260911'


def implementation():
    assert importlib.util.find_spec('src.item_review'), 'bounded item observation implementation missing'
    return importlib.import_module('src.item_review')


def master():
    return json.loads((MASTER / 'checklist_item_master.json').read_bytes())


def target(*items, headings=True):
    return document(*([heading(text='01 Package Content')] if headings else []), *items)


def test_current_target_is_searched_without_historical_node_ids_or_conditions():
    source = master()
    source['items'][0].update(proposed_model_rule='Approved all models', proposal_evidence='<script>x</script>', reviewer_note='Check')
    before = deepcopy(source)
    doc = target(node('new_item', 'list_body', ' * Simple\nUser Guide '),
                 node('new_note', 'paragraph', '*: New target model note.'))
    report = implementation().observe_item_master(doc, source)
    row = report['items'][0]
    assert row['observation'] == 'found'
    assert row['candidates'][0]['owner_ids'] == ['new_item']
    assert row['candidates'][0]['text'] == ' * Simple\nUser Guide '
    assert row['candidates'][0]['parts'][0]['evidence'][0]['xml_path'] == '/new_item'
    assert row['condition_candidates'][0]['owner_ids'] == ['new_note']
    assert row['source_marker'] == '*'
    assert row['author_proposal'] == {k: source['items'][0][k] for k in ('proposed_model_rule', 'proposal_evidence', 'reviewer_note')}
    assert report['parent'] == source['parent'] and report['master_source'] == source['source']
    assert source == before
    assert report['summary'] == dict(item_count=14, found=1, ambiguous=0, not_found=13, not_examined=0,
                                    needs_review=14, condition_candidate_items=1)
    assert report['activation_status'] == 'draft_only' and report['decision_status'] == 'not_evaluated'
    assert all(r['result'] == 'needs_review' and r['model_applicability'] == 'unknown'
               and r['condition_state'] == 'unverified' for r in report['items'])


def test_whole_list_body_not_substring_and_duplicates_are_ambiguous():
    report = implementation().observe_item_master(target(
        node('cable', 'list_body', 'Power Box Cable x 2'),
        node('one', 'list_body', 'Simple User Guide'), node('two', 'list_body', '*Simple User Guide'),
        node('quantity', 'list_body', 'Wall Mount Adapter x 3'),
        node('parenthetical', 'list_body', 'Warranty Card / Regulatory Guide')),
        master())
    rows = {r['item_key']: r for r in report['items']}
    assert rows['simple_user_guide']['observation'] == 'ambiguous'
    assert len(rows['simple_user_guide']['candidates']) == 2
    assert rows['power_box']['observation'] == 'not_found'
    assert rows['power_box_cable']['observation'] == 'found'
    assert rows['wall_mount_adapter']['observation'] == 'not_found'
    assert rows['warranty_regulatory_guide']['observation'] == 'not_found'


@pytest.mark.parametrize('doc', [target(node('outside', 'list_body', 'Simple User Guide'), headings=False),
    target(heading('duplicate', '01 Package Content'), node('outside', 'list_body', 'Simple User Guide')),
    document(heading(text='01 Package Content', lang=None), node('outside', 'list_body', 'Simple User Guide'))])
def test_missing_ambiguous_or_unusable_heading_is_not_examined(doc):
    report = implementation().observe_item_master(doc, master())
    assert report['summary']['not_examined'] == 14 and report['summary']['not_found'] == 0
    assert all(not r['candidates'] and not r['condition_candidates'] for r in report['items'])


def test_next_heading_and_foreign_language_do_not_supply_matches():
    report = implementation().observe_item_master(target(node('foreign', 'list_body', 'Simple User Guide', lang='C-FRA'),
        heading('next', 'Another topic'), node('later', 'list_body', 'Power Box')), master())
    assert report['summary']['found'] == 0


@pytest.mark.parametrize('changes', [{'source_token': 'ZX_L02'}, {'doc_type': 'A3'}, {'expected_languages': ('C-FRA',)}])
def test_unsupported_profile_is_not_silently_generalized(changes):
    doc = target()
    doc = replace(doc, context=replace(doc.context, **changes))
    with pytest.raises(ValueError, match='profile|language'):
        implementation().observe_item_master(doc, master())


@pytest.mark.parametrize('mutation', ['activation', 'item_activation', 'duplicate', 'wording'])
def test_altered_or_activated_master_rejected_by_pure_observer(mutation):
    source = master()
    if mutation == 'activation':
        source['activation_status'] = 'approved'
    elif mutation == 'item_activation':
        source['items'][0]['model_applicability'] = 'applicable'
    elif mutation == 'duplicate':
        source['items'][1] = deepcopy(source['items'][0])
    else:
        source['items'][0]['required_text'] = 'Different'
    with pytest.raises(ValueError):
        implementation().observe_item_master(target(), source)
