import json
from dataclasses import asdict, replace

import pytest

from src.checklist_migration import SOURCE_HEADERS, draft_rows
from src.checklist_observation import observe_checklist
from src.review_document import DocumentContext, ReviewDocument, ReviewNode, SourceEvidence


def node(key, kind, *content, lang="ENG", attrs=()):
    return ReviewNode(key, kind, tuple(content), language=lang, attributes=attrs,
                      evidence=(SourceEvidence('/' + key, page_index=0),))


def heading(key="h", text="Topic", lang="ENG", candidate=False):
    kind = "paragraph" if candidate else "heading"
    evidence = dict(structure_path='/' + key, joined_text=text, source_role="H2",
                    classification="source_role_candidate" if candidate else "heading", level=2)
    return replace(node(key, kind, text, lang=lang, attrs=(("review:heading-evidence", json.dumps(evidence)),)), source_role="H2")


def document(*content):
    return ReviewDocument(DocumentContext("test", "ZC_L02", "ZC", ("ZC",), "A2", ("ENG", "C-FRA")),
                          (node("section", "section", *content),))


def rule(**changes):
    source = dict.fromkeys(SOURCE_HEADERS, "")
    source.update(common_id="TEST-001", check_id="TEST-001-ZC-ENG", status="approved", scope="WW",
                  language="ENG", doc_type="A2", section_heading="Topic", block_type="body",
                  expected_result="required_present", required_text="Required words.", match_method="presence")
    source.update(changes)
    return draft_rows([source])[0]


def observation(doc, **changes):
    return observe_checklist(doc, [rule(**changes)])["rows"][0]


def test_bounded_match_keeps_exact_text_and_never_becomes_pass():
    doc = document(heading(), node("p", "paragraph", "  Required\nwords.  "))
    before = asdict(doc)
    row = observation(doc)
    assert row["status"] == "needs_review"
    assert row["migration_status"] == "pending"
    assert row["observation"] == "evidence_found"
    assert row["matches"][0]["text"] == "  Required\nwords.  "
    assert row["heading"]["node_id"] == "h"
    assert asdict(doc) == before


def test_source_candidate_is_not_promoted():
    row = observation(document(heading(candidate=True), node("p", "paragraph", "Required words.")))
    assert row["observation"] == "evidence_found"
    assert row["status"] == "needs_review"
    assert row["heading"]["classification"] == "source_role_candidate"


@pytest.mark.parametrize("change", [{"source_token": "OTHER_L02"}, {"source_token": ""}])
def test_db_provenance_never_restricts_applicability(change):
    row = observation(document(heading(), node("p", "paragraph", "Required words.")), **change)
    assert row["observation"] == "evidence_found"


@pytest.mark.parametrize("change", [{"exclude_scope": "ZC"}, {"scope": "ZA"}, {"language": "C-FRA"}, {"doc_type": "BOOK"}])
def test_metadata_boundaries_remain_not_applicable(change):
    assert observation(document(heading()), **change)["status"] == "not_applicable"


@pytest.mark.parametrize("status", ["review", "deprecated"])
def test_unapproved_rules_are_retained_not_evaluated(status):
    row = observation(document(heading()), status=status)
    assert row["status"] == "excluded"
    assert row["approval_status"] == status


def test_missing_and_duplicate_heading_do_not_fall_back_to_global_search():
    assert observation(document(node("p", "paragraph", "Topic Required words.")))["reason"] == "heading_not_found"
    result = observation(document(heading(), node("p", "paragraph", "Required words."), heading("h2")))
    assert result["reason"] == "ambiguous_heading"
    assert result["matches"] == []


def test_other_heading_ends_scope_even_when_it_is_a_candidate():
    row = observation(document(heading(), heading("next", "Other", candidate=True), node("p", "paragraph", "Required words.")))
    assert row["observation"] == "not_found_in_selected_units"
    assert row["scope_end"]["node_id"] == "next"


def test_never_joins_two_paragraphs_or_searches_a_table():
    row = observation(document(heading(), node("p1", "paragraph", "Required"), node("p2", "paragraph", "words."),
        node("tbl", "table", node("tr", "table_row", node("cell", "table_cell", node("tp", "paragraph", "Required words."))))))
    assert row["matches"] == []
    assert any(x["reason"] == "table_requires_dedicated_selector" for x in row["rejected_units"])


def test_bullet_matches_only_list_body_under_list_item():
    row = observation(document(heading(), node("p", "paragraph", "Required words."),
        node("list", "list", node("item", "list_item", node("body", "list_body", "Required words.")))), block_type="bullet")
    assert [m["owner_id"] for m in row["matches"]] == ["body"]


def test_language_transition_stops_scope_even_if_english_returns():
    row = observation(document(heading(), node("fra", "paragraph", "French", lang="C-FRA"), node("p", "paragraph", "Required words.")))
    assert row["matches"] == []
    assert row["scope_end"]["reason"] == "language_boundary"


def test_section_end_stops_scope():
    doc = document(node("sub", "section", heading()), node("p", "paragraph", "Required words."))
    assert observation(doc)["matches"] == []


@pytest.mark.parametrize("change", [{"block_type": "regulatory_note"}, {"block_type": "safety_symbol_table", "match_method": "table_row"}])
def test_unsupported_structures_stay_visible_not_not_applicable(change):
    row = observation(document(heading()), **change)
    assert row["status"] == "needs_review"
    assert row["reason"] == "unsupported_selector"


@pytest.mark.parametrize("text", ["required words.", "Required words!", "Re-quired words.", "UnRequired words."])
def test_pilot_does_not_erase_case_punctuation_or_word_boundaries(text):
    assert observation(document(heading(), node("p", "paragraph", text)))["matches"] == []


def test_unsafe_figure_and_heading_are_not_positive_matches():
    row = observation(document(heading(), node("p", "paragraph", "Required", node("f", "figure"), " words.")))
    assert row["matches"] == []
    assert row["rejected_units"][0]["issues"] == ["visual_content_requires_review"]


def test_heading_self_selector_preserves_legacy_heading_constraint():
    doc = document(heading(text="Topic"))
    assert observation(doc, block_type="heading", required_text="Topic")["observation"] == "evidence_found"
    assert observation(doc, block_type="heading", section_heading="Other", required_text="Topic")["matches"] == []


def test_other_profile_is_not_implicitly_rolled_out():
    doc = document(heading())
    with pytest.raises(ValueError, match="pilot"):
        observe_checklist(replace(doc, context=replace(doc.context, source_token="XU_ENG", region="XU", doc_type="A3")), [rule()])


def test_unsafe_heading_with_nested_block_cannot_define_a_positive_scope():
    anchor = heading(text="TopicHidden")
    anchor = replace(anchor, content=("Topic", node("nested", "paragraph", "Hidden")))
    row = observation(document(anchor, node("p", "paragraph", "Required words.")), section_heading="TopicHidden")
    assert row["reason"] == "unsafe_heading"
    assert row["matches"] == []


def test_wrong_heading_evidence_path_is_not_trusted():
    anchor = heading()
    proof = json.loads(dict(anchor.attributes)["review:heading-evidence"])
    proof["structure_path"] = "/not-the-heading"
    anchor = replace(anchor, attributes=(("review:heading-evidence", json.dumps(proof)),))
    assert observation(document(anchor, node("p", "paragraph", "Required words.")))["reason"] == "unsafe_heading"


def test_same_heading_in_french_is_not_an_english_duplicate():
    row = observation(document(heading(), node("p", "paragraph", "Required words."), heading("fr", lang="C-FRA")))
    assert row["observation"] == "evidence_found"


@pytest.mark.parametrize("kind", ["mystery", "table", "paragraph"])
def test_empty_structural_descendant_cannot_hide_inside_heading(kind):
    anchor = replace(heading(), content=("Topic", node("hidden", kind)))
    assert observation(document(anchor, node("p", "paragraph", "Required words.")))["reason"] == "unsafe_heading"


def test_supplemental_paragraph_candidate_does_not_change_strict_match():
    row = observation(document(heading(), node('a', 'paragraph', 'Required'), node('b', 'paragraph', 'words.')))
    assert row['matches'] == []
    assert row['observation'] == 'not_found_in_selected_units'
    assert row['candidate_matches'][0]['method'] == 'adjacent_paragraphs'
    assert row['candidate_matches'][0]['text'] == 'Required\nwords.'
    assert row['status'] == 'needs_review'


def test_supplemental_candidate_does_not_cross_heading_boundary():
    row = observation(document(heading(), node('a', 'paragraph', 'Required'), heading('h2', 'Other'), node('b', 'paragraph', 'words.')))
    assert row['candidate_matches'] == []


def test_candidate_label_body_and_structure_difference_are_audited():
    row = observation(document(heading(), node('ls', 'list', node('i', 'list_item', node('l', 'label', '\u2013 '), node('b', 'list_body', 'Required words.')))), block_type='bullet', required_text='\u2013 Required words.')
    assert row['matches'] == []
    assert row['candidate_matches'][0]['method'] == 'list_item_label_body'
    row = observation(document(heading(), node('p', 'paragraph', 'Required words.')), block_type='bullet')
    assert row['candidate_matches'][0]['owner_ids'] == ('p',)
    assert 'legacy_structure_not_certified' in row['candidate_matches'][0]['caveats']


def test_visual_candidate_never_bridges_an_icon():
    doc = document(heading(), node('p', 'paragraph', 'Required', node('icon', 'figure'), ' words.'))
    assert observation(doc)['candidate_matches'] == []
    row = observation(doc, required_text='Required')
    assert row['matches'] == []
    assert row['candidate_matches'][0]['visual_node_ids'] == ('icon',)


def test_unsupported_legacy_role_gets_separate_literal_candidate_not_approval():
    row = observation(document(heading(), node('p', 'paragraph', 'Required words.')), block_type='regulatory_note')
    assert row['reason'] == 'unsupported_selector'
    assert row['observation'] == 'not_examined'
    assert row['candidate_matches'][0]['text'] == 'Required words.'


@pytest.mark.parametrize('changes', [{'status': 'review'}, {'exclude_scope': 'ZC'}, {'section_heading': 'Missing'}])
def test_candidates_never_bypass_scope_or_approval(changes):
    assert observation(document(heading(), node('p', 'paragraph', 'Required words.')), **changes)['candidate_matches'] == []


@pytest.mark.parametrize('middle', [node('sub', 'section', node('a', 'paragraph', 'Required'), node('b', 'paragraph', 'words.')),
                                  node('sub', 'section', lang='C-FRA')])
def test_candidates_stop_at_entered_section_and_empty_foreign_container(middle):
    row = observation(document(heading(), middle, node('c', 'paragraph', 'Required'), node('d', 'paragraph', 'words.')))
    assert row['candidate_matches'] == []


def test_distributed_fragments_record_separate_evidence_never_whole_match():
    row = observation(document(heading(), node('p', 'paragraph', 'First.'),
        node('t', 'table', node('r', 'table_row', node('c', 'table_cell', 'Second.')))), required_text='First.\nSecond.')
    assert row['matches'] == [] and row['candidate_matches'] == []
    assert row['fragment_observations']['status'] == 'all_fragments_located_not_whole_match'
    assert [x['required_text'] for x in row['fragment_observations']['fragments']] == ['First.', 'Second.']
    assert all(x['candidates'] for x in row['fragment_observations']['fragments'])


def test_fragment_diagnostics_do_not_cross_scope_or_hide_absent_fragment():
    row = observation(document(heading(), node('p', 'paragraph', 'First.'), heading('h2','Other'), node('q','paragraph','Second.')), required_text='First.\nSecond.')
    assert row['fragment_observations']['status'] == 'partial_fragments_located'
    assert row['fragment_observations']['fragments'][1]['candidates'] == []
