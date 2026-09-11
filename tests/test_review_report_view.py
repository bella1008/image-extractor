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
    assert view['checklist'][0]['diagnostic']['category'] == 'structure_candidate'
    assert view['evidence'][0]['evidence_kind'] == 'candidate'
    assert view['evidence'][0]['composition_method'] == 'adjacent_paragraphs'


def test_fragment_evidence_is_not_a_full_candidate_excerpt():
    report = observe_checklist(document(heading(), node('p', 'paragraph', 'First.'),
        node('t', 'table', node('r', 'table_row', node('c', 'table_cell', 'Second.')))), [rule(required_text='First.\nSecond.')])
    view = build_report_view(report)
    assert view['checklist'][0]['diagnostic']['category'] == 'distributed_fragments'
    assert view['checklist'][0]['evidence_excerpt'] == ''
    assert {r['evidence_kind'] for r in view['evidence']} == {'fragment'}


def test_unknown_status_and_business_decisions_fail_closed():
    report = observe_checklist(document(heading()), [rule()])
    for field, value in [('status', 'pass'), ('migration_status', 'verified')]:
        bad = deepcopy(report); bad['rows'][0][field] = value
        with pytest.raises(ValueError):
            build_report_view(bad)


def test_concise_columns_and_diagnostics_preserve_distinctions():
    doc = document(heading(), node('p', 'paragraph', 'Required words.'))
    report = observe_checklist(doc, [rule()])
    view = build_report_view(report)
    assert view['schema_version'] == 'review-report-view/2'
    assert 'description' in view['columns']['checklist']
    assert not {'observation', 'reason'} & set(view['columns']['checklist'])
    row = view['checklist'][0]
    assert row['description'] == '문구는 찾았지만 적용 조건과 구조 역할은 아직 검사하지 않았습니다.'
    assert row['diagnostic']['observation'] == report['rows'][0]['observation']
    assert row['diagnostic']['reason'] == report['rows'][0]['reason']
    assert view['source']['availability'] == 'unavailable'
    assert not view['source'].get('pdf_filename')


def test_unsupported_and_unlocated_descriptions_do_not_claim_absence():
    doc = document(heading())
    unsupported = build_report_view(observe_checklist(doc, [rule(block_type='table')]))['checklist'][0]
    unlocated = build_report_view(observe_checklist(doc, [rule()]))['checklist'][0]
    assert '지원하지 않아' in unsupported['description']
    assert '찾지 못' in unlocated['description']
    assert unsupported['description'] != unlocated['description']
    assert all('누락' not in r['description'] and r['result'] == 'needs_review' for r in (unsupported, unlocated))


def test_document_enrichment_keeps_real_tags_and_pdf_references():
    from dataclasses import replace
    from src.review_document import SourceEvidence
    p = replace(node('p', 'paragraph', 'Required words.'),
                evidence=(SourceEvidence('/p', page_index=0, mcid=0, object_ref='10 0 R'),))
    doc = document(heading(), p)
    report = observe_checklist(doc, [rule()])
    before = deepcopy(report)
    view = build_report_view(report, document=doc)
    proof = view['evidence'][0]
    assert proof['source_node_ids'] == 'p'
    assert 'p: paragraph' in proof['structure_types']
    assert proof['mcids'] == 'p: 0'
    assert proof['object_refs'] == 'p: 10 0 R'
    assert proof['visual_node_ids'] == ''
    assert view['checklist'][0]['source_node_ids'] == 'p'
    assert report == before


@pytest.mark.parametrize('field', ['node_id', 'visual_node_ids', 'owner_id'])
def test_unknown_document_reference_is_an_error(field):
    doc = document(heading(), node('p', 'paragraph', 'Required words.'))
    report = observe_checklist(doc, [rule()])
    item = report['rows'][0]['matches'][0]
    if field == 'node_id':
        item['parts'][0][field] = 'missing'
    else:
        item[field] = ['missing'] if field.endswith('_ids') else 'missing'
    with pytest.raises(ValueError, match='unknown.*node'):
        build_report_view(report, document=doc)


def test_known_node_with_wrong_xml_reference_fails_closed():
    doc = document(heading(), node('p', 'paragraph', 'Required words.'))
    report = observe_checklist(doc, [rule()])
    report['rows'][0]['matches'][0]['parts'][0]['evidence'][0]['xml_path'] = '/not-p'
    with pytest.raises(ValueError, match='source evidence'):
        build_report_view(report, document=doc)


def test_visual_reference_is_preserved_with_exact_type_and_candidate_status():
    doc = document(heading(), node('p', 'paragraph', 'Required words.', node('fig', 'figure')))
    report = observe_checklist(doc, [rule()])
    view = build_report_view(report, document=doc)
    assert view['evidence'][0]['visual_node_ids'] == 'fig'
    assert 'fig: figure' in view['evidence'][0]['structure_types']
    assert view['checklist'][0]['diagnostic']['category'] == 'structure_candidate'
    assert view['checklist'][0]['result'] == 'needs_review'


def test_source_identity_differs_for_same_filename_and_does_not_alias_input():
    report = observe_checklist(document(heading()), [rule()])
    first = {'availability': 'verified_archive', 'pdf_filename': 'same.pdf', 'pdf_sha256': 'a' * 64,
             'semantic_xml_sha256': 'b' * 64}
    second = {**first, 'pdf_sha256': 'c' * 64, 'semantic_xml_sha256': 'd' * 64}
    view = build_report_view(report, source=first)
    other = build_report_view(report, source=second)
    assert view['source'] != other['source']
    view['source']['pdf_filename'] = 'edited'
    assert first['pdf_filename'] == 'same.pdf'


def test_main_checklist_prefers_owners_and_visuals_detail_retains_text_nodes():
    doc = document(heading(), node('p', 'paragraph', node('text', 'text', 'Required words.'), node('fig', 'figure')))
    view = build_report_view(observe_checklist(doc, [rule()]), document=doc)
    main, detail = view['checklist'][0], view['evidence'][0]
    assert main['source_node_ids'] == 'p\nfig'
    assert main['structure_types'] == 'p: paragraph\nfig: figure'
    assert detail['source_node_ids'] == 'text'
    assert 'text: text' in detail['structure_types']


def test_partial_fragment_status_stays_distinct_from_all_fragments_found():
    report = observe_checklist(document(heading(), node('p', 'paragraph', 'First.')),
                               [rule(required_text='First.\nSecond.')])
    row = build_report_view(report)['checklist'][0]
    assert row['diagnostic']['fragment_status'] == 'partial_fragments_located'
    assert row['description'].startswith('일부 문구')
    assert row['evidence_excerpt'] == ''
    assert row['result'] == 'needs_review'


@pytest.mark.parametrize('field,replacement', [('owner_id', 'q'), ('ancestor_ids', ['q']),
                                              ('visual_node_ids', ['other_fig']),
                                              ('visual_node_ids', ['text'])])
def test_existing_but_unrelated_owner_ancestor_or_visual_is_rejected(field, replacement):
    doc = document(heading(), node('p', 'paragraph', node('text', 'text', 'Required words.')),
                   node('q', 'paragraph', 'Other', node('other_fig', 'figure')))
    report = observe_checklist(doc, [rule()])
    report['rows'][0]['matches'][0][field] = replacement
    with pytest.raises(ValueError, match='relationship'):
        build_report_view(report, document=doc)


def test_candidate_groups_must_correspond_to_their_actual_owner():
    doc = document(heading(), node('p', 'paragraph', 'First.'), node('q', 'paragraph', 'Second.'))
    report = observe_checklist(doc, [rule(required_text='First.\nSecond.')])
    item = report['rows'][0]['candidate_matches'][0]
    item['owner_ids'] = tuple(reversed(item['owner_ids']))
    with pytest.raises(ValueError, match='relationship'):
        build_report_view(report, document=doc)


def test_candidate_container_must_be_the_actual_structural_ancestor():
    doc = document(heading(), node('t', 'table', node('r', 'table_row', node('c', 'table_cell',
        node('p', 'paragraph', 'Required words.')))), node('other_table', 'table'))
    report = observe_checklist(doc, [rule()])
    item = report['rows'][0]['candidate_matches'][0]
    item['container_ids'] = ['other_table']
    with pytest.raises(ValueError, match='relationship'):
        build_report_view(report, document=doc)
