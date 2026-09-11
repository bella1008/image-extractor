from dataclasses import asdict, replace

import pytest

from src.review_evidence_windows import build_evidence_windows
from tests.test_checklist_observation import document, heading, node


def windows(*content):
    return build_evidence_windows(document(*content))


def test_adjacent_paragraphs_keep_original_parts_and_explicit_separator():
    doc = document(heading(), node('p1', 'paragraph', 'First.'), node('p2', 'paragraph', 'Second.'))
    before = asdict(doc)
    grouped = [w for w in build_evidence_windows(doc) if w.method == 'adjacent_paragraphs']
    assert len(grouped) == 1
    assert grouped[0].text == 'First.\nSecond.'
    assert [p.text for p in grouped[0].parts] == ['First.', 'Second.']
    assert grouped[0].separator == '\n'
    assert asdict(doc) == before


@pytest.mark.parametrize('middle', [node('x', 'mystery'), node('x', 'figure'), node('x', 'table'), heading('x', 'Other'), node('x', 'paragraph', 'Autre', lang='C-FRA')])
def test_any_intervening_structure_or_language_stops_paragraph_composition(middle):
    assert not any(w.method == 'adjacent_paragraphs' for w in windows(node('a', 'paragraph', 'First'), middle, node('b', 'paragraph', 'Second')))


def test_same_item_label_body_preserves_en_dash():
    result = windows(node('list', 'list', node('item', 'list_item', node('label', 'label', '\u2013 '), node('body', 'list_body', 'Text.'))))
    candidate = next(w for w in result if w.method == 'list_item_label_body')
    assert candidate.text == '\u2013 Text.'
    assert [p.node_id for p in candidate.parts] == ['label', 'body']
    assert candidate.container_ids == ('item',)


def test_never_composes_across_list_items_or_table_cells():
    result = windows(node('list', 'list', node('i1', 'list_item', node('a', 'list_body', 'First')), node('i2', 'list_item', node('b', 'list_body', 'Second'))),
                     node('t', 'table', node('r', 'table_row', node('c1', 'table_cell', 'First'), node('c2', 'table_cell', 'Second'))))
    assert not any('First' in w.text and 'Second' in w.text for w in result)


def test_figure_splits_text_and_keeps_visual_context():
    result = windows(node('p', 'paragraph', 'Before', node('f', 'figure'), 'After'))
    runs = [w for w in result if w.method == 'text_beside_visual']
    assert [w.text for w in runs] == ['Before', 'After']
    assert all(w.visual_node_ids == ('f',) for w in runs)
    assert all('visual_context_requires_review' in w.caveats for w in runs)


def test_figure_text_is_not_claimed_as_an_uninterrupted_text_run():
    result = windows(node('p', 'paragraph', 'Before', node('f', 'figure', 'Icon'), 'After'))
    assert [w.text for w in result] == ['Before', 'After']


def test_missing_evidence_and_unknown_ancestry_never_become_candidates():
    bad = replace(node('p', 'paragraph', 'Text'), evidence=())
    assert not windows(bad)
    assert not windows(node('u', 'mystery', node('p', 'paragraph', 'Text')))


def test_empty_unknown_inside_paragraph_blocks_atomic_window():
    assert not windows(node('p', 'paragraph', 'Text', node('u', 'mystery')))


def test_maximum_group_is_explicitly_bounded_to_four_paragraphs():
    result = windows(*(node(str(i), 'paragraph', str(i)) for i in range(6)))
    assert max(len(w.owner_ids) for w in result) == 4


def test_table_ancestry_stays_visible_for_atomic_evidence():
    result = windows(node('t', 'table', node('r', 'table_row', node('c', 'table_cell', node('p', 'paragraph', 'Text')))))
    assert len(result) == 1
    assert result[0].container_ids == ('t', 'r', 'c')
    assert 'table_structure_requires_review' in result[0].caveats


def test_composition_requires_parent_evidence():
    item = replace(node('i', 'list_item', node('l', 'label', '\u2013 '), node('b', 'list_body', 'Text')), evidence=())
    assert not any(w.method == 'list_item_label_body' for w in windows(item))
    parent = replace(node('s', 'section', node('a', 'paragraph', 'First'), node('b', 'paragraph', 'Second')), evidence=())
    assert not any(w.method == 'adjacent_paragraphs' for w in windows(parent))
