import pytest

from tagged_pdf_extractor.domain.models import ContentFragment, StructureElement
from tagged_pdf_extractor.domain.role_mapping import (
    heading_candidate_level,
    is_heading_candidate,
    map_role,
)


@pytest.mark.parametrize(
    ("source_role", "expected_candidate", "expected_level"),
    (
        ("Heading", True, None),
        ("Heading2_0_2", True, 2),
        ("Cover_Title", True, None),
        ("cover-title", True, None),
        ("NotHeading", True, None),
        ("Heading20", False, None),
        ("Subtitle", False, None),
        ("P", False, None),
    ),
)
def test_heading_candidate_helpers_preserve_quality_evaluator_policy(
    source_role: str, expected_candidate: bool, expected_level: int | None
) -> None:
    assert is_heading_candidate(source_role) is expected_candidate
    assert heading_candidate_level(source_role) == expected_level


def test_maps_headings_and_preserves_unknown_source_role() -> None:
    assert map_role("H2", {}) == ("heading", 2)
    assert map_role("CustomHeading", {"CustomHeading": "H3"}) == ("heading", 3)
    assert map_role("SamsungBox", {}) == ("unknown", None)


def test_unicode_numeric_heading_suffix_is_unknown() -> None:
    assert map_role("H²", {}) == ("unknown", None)


def test_maps_generic_heading_and_title() -> None:
    assert map_role("H", {}) == ("heading", None)
    assert map_role("Title", {}) == ("heading", 1)


@pytest.mark.parametrize("source_role", ["H0", "H7", "H8", "H9"])
def test_nonstandard_numbered_headings_are_unknown(source_role: str) -> None:
    assert map_role(source_role, {}) == ("unknown", None)


@pytest.mark.parametrize("mapped_role", ["H0", "H7", "H8", "H9"])
def test_role_map_cannot_promote_nonstandard_numbered_headings(
    mapped_role: str,
) -> None:
    assert map_role("CustomHeading", {"CustomHeading": mapped_role}) == (
        "unknown",
        None,
    )


@pytest.mark.parametrize(
    ("source_role", "semantic_role"),
    [
        ("Document", "document"),
        ("Part", "part"),
        ("Art", "article"),
        ("Sect", "section"),
        ("Div", "division"),
        ("P", "paragraph"),
        ("L", "list"),
        ("LI", "list_item"),
        ("Lbl", "label"),
        ("LBody", "list_body"),
        ("Table", "table"),
        ("TR", "table_row"),
        ("TH", "table_header"),
        ("TD", "table_cell"),
        ("Figure", "figure"),
        ("Caption", "caption"),
        ("Span", "span"),
        ("Link", "link"),
    ],
)
def test_maps_standard_source_roles(source_role: str, semantic_role: str) -> None:
    assert map_role(source_role, {}) == (semantic_role, None)


def test_lowercase_semantic_role_is_unknown() -> None:
    assert map_role("document", {}) == ("unknown", None)


def test_structure_element_preserves_mixed_child_order() -> None:
    first = ContentFragment(page_index=0, mcid=3, text_parts=("A",))
    nested = StructureElement(source_role="Span", semantic_role="span")
    last = ContentFragment(page_index=0, mcid=4, text_parts=("B",))
    element = StructureElement(
        source_role="P", semantic_role="paragraph", children=(first, nested, last)
    )
    assert element.children == (first, nested, last)
