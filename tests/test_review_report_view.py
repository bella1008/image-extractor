from copy import deepcopy

import pytest

from src.checklist_observation import observe_checklist
from src.review_report_view import build_report_view
from tests.test_checklist_observation import document, heading, node, rule


def test_view_preserves_rule_text_and_never_converts_observation_to_pass():
    report = observe_checklist(document(heading(), node('p', 'paragraph', 'Required words.')), [rule()])
    before = deepcopy(report)
    view = build_report_view(report)
    row = view['checklist'][0]
    assert row['required_text'] == 'Required words.'
    assert row['evidence_excerpt'] == 'Required words.'
    assert row['result'] == 'needs_review'
    assert row['pdf_pages'] == '1'
    assert row['reviewer_note'] == ''
    assert report == before


def test_all_excluded_rules_remain_in_a_separate_audit_view():
    report = observe_checklist(document(heading()), [rule(), rule(check_id='TEST-002-ZA-ENG', scope='ZA')])
    view = build_report_view(report)
    assert len(view['checklist']) == 1 and len(view['excluded']) == 1
    assert view['excluded'][0]['check_id'] == 'TEST-002-ZA-ENG'
    assert view['summary']['rule_count'] == 2


def test_candidate_evidence_and_fragment_evidence_are_labeled_separately():
    report = observe_checklist(document(heading(), node('a', 'paragraph', 'First.'), node('b', 'paragraph', 'Second.')),
                               [rule(required_text='First.\nSecond.')])
    view = build_report_view(report)
    assert view['checklist'][0]['observation'] == 'structure_candidate'
    assert view['evidence'][0]['evidence_kind'] == 'candidate'
    assert view['evidence'][0]['composition_method'] == 'adjacent_paragraphs'


def test_fragment_evidence_is_not_a_full_candidate_excerpt():
    report = observe_checklist(document(heading(), node('p', 'paragraph', 'First.'),
        node('t', 'table', node('r', 'table_row', node('c', 'table_cell', 'Second.')))), [rule(required_text='First.\nSecond.')])
    view = build_report_view(report)
    assert view['checklist'][0]['observation'] == 'distributed_fragments'
    assert view['checklist'][0]['evidence_excerpt'] == ''
    assert {r['evidence_kind'] for r in view['evidence']} == {'fragment'}


def test_unknown_status_and_business_decisions_fail_closed():
    report = observe_checklist(document(heading()), [rule()])
    for field, value in [('status', 'pass'), ('migration_status', 'verified')]:
        bad = deepcopy(report); bad['rows'][0][field] = value
        with pytest.raises(ValueError):
            build_report_view(bad)
