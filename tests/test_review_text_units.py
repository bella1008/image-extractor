from dataclasses import asdict

import pytest

from src.review_document import DocumentContext, ReviewDocument, ReviewNode, SourceEvidence
from src.review_text_units import build_text_unit_index


def node(key, kind, *content, language="ENG", evidence=True):
    return ReviewNode(key, kind, tuple(content), language=language,
                      evidence=(SourceEvidence('/' + key, page_index=0),) if evidence else ())


def doc(*roots):
    return ReviewDocument(DocumentContext("BN68-test", "ZC_L02", "ZC", ("ZC",), "A2", ("ENG", "C-FRA")), tuple(roots))


def test_inline_order_unicode_and_empty_strings_preserved_without_normalization():
    source = doc(node("p", "paragraph", " é ", node("s", "span", node("t", "text", "中文\n")), "", "fin."))
    before = asdict(source)
    index = build_text_unit_index(source)
    assert len(index.units) == 1
    unit = index.units[0]
    assert unit.text == " é 中文\nfin."
    assert [(p.node_id, p.content_index, p.text) for p in unit.parts] == [("p", 0, " é "), ("t", 0, "中文\n"), ("p", 2, ""), ("p", 3, "fin.")]
    assert unit.ready_for_text_match
    assert asdict(source) == before


def test_nested_table_and_sibling_paragraphs_are_not_one_search_window():
    table = node("table", "table", node("row", "table_row",
        node("a", "table_cell", node("p1", "paragraph", "cell one")),
        node("b", "table_cell", node("p2", "paragraph", "cell two"))))
    index = build_text_unit_index(doc(node("p", "paragraph", "before", table, "after"), node("p3", "paragraph", "last")))
    assert [u.text for u in index.units] == ["before", "cell one", "cell two", "after", "last"]
    assert index.units[1].ancestor_ids == ("p", "table", "row", "a")
    assert [u.segment_index for u in index.units if u.owner_id == "p"] == [0, 1]


def test_list_items_and_their_labels_are_not_collapsed():
    index = build_text_unit_index(doc(node("list", "list",
        node("i1", "list_item", node("label", "label", "1."), node("body1", "list_body", "alpha")),
        node("i2", "list_item", node("body2", "list_body", "beta")))))
    assert [u.text for u in index.units] == ["1.", "alpha", "beta"]
    assert [u.ready_for_text_match for u in index.units] == [False, True, True]


def test_heading_composes_only_inline_label_and_body():
    index = build_text_unit_index(doc(node("h", "heading", node("l", "label", "01 "), node("b", "list_body", "Contents"))))
    assert [u.text for u in index.units] == ["01 Contents"]
    assert index.units[0].ready_for_text_match


@pytest.mark.parametrize("wrapper", ["list_body", "span", "label"])
def test_heading_never_flattens_a_nested_list_body(wrapper):
    index = build_text_unit_index(doc(node("h", "heading", node("outer", wrapper,
        "before", node("inner", "list_body", "inner"), "after"))))
    assert [unit.text for unit in index.units] == ["before", "inner", "after"]


@pytest.mark.parametrize("kind", ["paragraph", "list_body", "table_cell"])
def test_structural_children_inside_inline_wrapper_break_the_window(kind):
    index = build_text_unit_index(doc(node("p", "paragraph", "before", node("s", "span", node("inner", kind, "inner")), "after")))
    assert [u.text for u in index.units] == ["before", "inner", "after"]
    assert "unsupported_inline_structure" in index.units[1].issues


@pytest.mark.parametrize("content", [(), ("",), ("icon label",)])
def test_figures_are_never_silently_removed_from_search(content):
    index = build_text_unit_index(doc(node("p", "paragraph", "alpha", node("f", "figure", *content), "beta")))
    assert len(index.units) == 1
    assert "visual_content_requires_review" in index.units[0].issues
    assert not index.units[0].ready_for_text_match
    assert "f" in index.units[0].visual_node_ids


def test_empty_standalone_figure_stays_in_inventory():
    unit = build_text_unit_index(doc(node("f", "figure"))).units[0]
    assert unit.visual_node_ids == ("f",)
    assert not unit.ready_for_text_match


@pytest.mark.parametrize("lang,issue", [(None, "unassigned_language"), ("C-FRA", "mixed_language"), ("DEU", "unexpected_language")])
def test_language_conflicts_are_not_guessed(lang, issue):
    unit = build_text_unit_index(doc(node("p", "paragraph", "ENG", node("t", "text", "text", language=lang)))).units[0]
    assert issue in unit.issues
    assert not unit.ready_for_text_match


def test_missing_part_evidence_is_not_replaced_with_parent_evidence():
    unit = build_text_unit_index(doc(node("p", "paragraph", node("t", "text", "word", evidence=False)))).units[0]
    assert "missing_text_evidence" in unit.issues
    assert not unit.ready_for_text_match


def test_unknown_container_is_retained_and_blocks_descendant_matching():
    units = build_text_unit_index(doc(node("u", "mystery", "raw", node("p", "paragraph", "known")))).units
    assert [u.text for u in units] == ["raw", "known"]
    assert all("unsupported_structure" in u.issues for u in units)


def test_known_structural_container_direct_text_is_not_silently_accepted():
    unit = build_text_unit_index(doc(node("row", "table_row", "raw row"))).units[0]
    assert "unsupported_text_owner" in unit.issues


def test_owner_language_disagreement_and_no_text_are_not_ready():
    unit = build_text_unit_index(doc(node("p", "paragraph", node("t", "text", "word", language="C-FRA")))).units[0]
    assert "mixed_language" in unit.issues
    assert not unit.ready_for_text_match
    empty = build_text_unit_index(doc(node("p", "paragraph", ""))).units[0]
    assert not empty.ready_for_text_match


def test_deep_nesting_does_not_use_python_recursion():
    root = node("p", "paragraph", "deep")
    for i in range(1100):
        root = node(f"s{i}", "section", root)
    index = build_text_unit_index(doc(root))
    assert index.units[0].text == "deep"
    assert len(index.units[0].ancestor_ids) == 1100
