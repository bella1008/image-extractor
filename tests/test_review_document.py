from dataclasses import FrozenInstanceError, replace
import json
from dataclasses import asdict

import pytest

from src.review_document import (
    DocumentContext, ReviewDocument, ReviewNode, ReviewRole, SourceEvidence,
)


def context():
    return DocumentContext("MANUAL", "ZC_L02", "ZC", ("ZC",), "A2", ("ENG", "C-FRA"))


def test_inline_text_figure_and_tail_keep_source_order():
    figure = ReviewNode("icon", "figure", (), source_role="Figure")
    paragraph = ReviewNode("p", "paragraph", ("Before ", figure, " after.\n"))
    document = ReviewDocument(context(), (paragraph,))
    assert paragraph.content == ("Before ", figure, " after.\n")
    assert paragraph.text_content == "Before  after.\n"
    assert [node.node_id for node in document.iter_nodes()] == ["p", "icon"]


def test_nested_table_cell_list_and_paragraph_remain_separate_nodes():
    p = ReviewNode("p", "paragraph", ("Line one. Line two.",))
    item = ReviewNode("item", "list_item", ("• ", p))
    listing = ReviewNode("list", "list", (item,))
    cell = ReviewNode("cell", "table_cell", (listing,), attributes=(("colspan", "2"),))
    row = ReviewNode("row", "table_row", (cell,))
    table = ReviewNode("table", "table", (row,))
    doc = ReviewDocument(context(), (table,))
    assert [node.structure_type for node in doc.iter_nodes()] == [
        "table", "table_row", "table_cell", "list", "list_item", "paragraph"
    ]
    assert cell.attributes == (("colspan", "2"),)
    assert p.content == ("Line one. Line two.",)


def test_language_counts_do_not_force_equal_sentence_or_node_counts():
    eng = ReviewNode("e", "paragraph", ("One sentence.",), language="ENG")
    fra1 = ReviewNode("f1", "paragraph", ("Phrase un. Phrase deux.",), language="C-FRA")
    fra2 = ReviewNode("f2", "paragraph", ("Suite.",), language="C-FRA")
    shared = ReviewNode("common", "figure", ())
    doc = ReviewDocument(context(), (eng, fra1, fra2, shared))
    assert len(doc.roots) == 4
    assert fra1.text_content == "Phrase un. Phrase deux."
    assert shared.language is None


def test_review_role_is_optional_and_does_not_change_structure():
    node = ReviewNode("t", "table", ())
    assert node.review_roles == ()
    role = ReviewRole("specification", "verified-spec-rule-v1", ("/document/table[1]",))
    classified = replace(node, review_roles=(role,))
    assert classified.structure_type == "table"
    assert node.review_roles == ()
    assert classified.review_roles[0].rule_id == "verified-spec-rule-v1"


def test_unknown_source_structure_and_heading_candidate_are_preserved():
    node = ReviewNode("h", "source_role_candidate", ("Warranty",),
                      source_role="Heading2", attributes=(("level", "3"),))
    doc = ReviewDocument(context(), (node,))
    assert doc.roots[0].structure_type == "source_role_candidate"
    assert doc.roots[0].source_role == "Heading2"


def test_evidence_retains_zero_page_mcid_and_object_context():
    evidence = SourceEvidence("/document/paragraph[1]", 0, 0, "12 0 R", (1, 2, 3, 4))
    node = ReviewNode("p", "paragraph", ("你好。\nالعربية",), evidence=(evidence,))
    data = json.loads(json.dumps(asdict(ReviewDocument(context(), (node,))), ensure_ascii=False))
    assert data["roots"][0]["evidence"][0]["page_index"] == 0
    assert data["roots"][0]["evidence"][0]["object_ref"] == "12 0 R"
    assert data["roots"][0]["content"] == ["你好。\nالعربية"]
    assert data["schema_version"] == "review-document/1"
    assert "status" not in data


def test_missing_geometry_is_not_replaced_with_zero_bbox():
    assert SourceEvidence("/document/figure[1]").bbox is None


def test_document_rejects_duplicate_node_id_across_nested_roots():
    p = ReviewNode("same", "paragraph", ("Text",))
    wrapper = ReviewNode("wrapper", "section", (p,))
    with pytest.raises(ValueError, match="duplicate node_id"):
        ReviewDocument(context(), (p, wrapper))


def test_models_are_immutable():
    node = ReviewNode("p", "paragraph", ("Text",))
    with pytest.raises(FrozenInstanceError):
        node.language = "ENG"


@pytest.mark.parametrize("kwargs", [
    {"manual_code": " "}, {"source_token": ""}, {"region": ""},
    {"doc_type": "GRID"}, {"buyer_codes": []}, {"expected_languages": ("eng",)},
    {"expected_languages": ("ENG", "ENG")}, {"expected_languages": ()},
    {"expected_languages": ("C--FRA",)},
])
def test_invalid_context_is_rejected(kwargs):
    with pytest.raises(ValueError):
        replace(context(), **kwargs)


@pytest.mark.parametrize("kwargs", [
    {"page_index": -1}, {"page_index": True}, {"mcid": -1}, {"mcid": False},
    {"bbox": (2, 0, 1, 4)}, {"bbox": (0, 4, 1, 2)},
    {"bbox": (0, 0, float("nan"), 1)}, {"bbox": (0, 0, float("inf"), 1)},
    {"bbox": [0, 0, 1, 1]}, {"bbox": (0, 0, 1)},
    {"bbox": (False, 0, 1, 1)}, {"xml_path": ""},
])
def test_invalid_evidence_is_rejected(kwargs):
    with pytest.raises(ValueError):
        replace(SourceEvidence("/document/p[1]"), **kwargs)


@pytest.mark.parametrize("kwargs", [
    {"node_id": ""}, {"structure_type": ""}, {"content": ["Text"]},
    {"content": (123,)}, {"attributes": (("key", 3),)},
    {"attributes": (("key", "one"), ("key", "two"))},
    {"language": "fra"}, {"evidence": [SourceEvidence("/p")]},
    {"review_roles": ("specification",)},
])
def test_invalid_node_payload_is_rejected(kwargs):
    with pytest.raises(ValueError):
        replace(ReviewNode("p", "paragraph", ("Text",)), **kwargs)


@pytest.mark.parametrize("kwargs", [
    {"rule_id": ""}, {"evidence_paths": ()}, {"evidence_paths": ("",)},
])
def test_role_requires_provenance(kwargs):
    with pytest.raises(ValueError):
        replace(ReviewRole("specification", "rule1", ("/p",)), **kwargs)


@pytest.mark.parametrize("kwargs", [
    {"roots": []}, {"roots": ("text",)}, {"context": {}},
    {"schema_version": "unsupported"},
])
def test_document_rejects_invalid_container(kwargs):
    with pytest.raises(ValueError):
        replace(ReviewDocument(context(), ()), **kwargs)
