from tagged_pdf_extractor.domain.models import ContentFragment, StructureElement
from tagged_pdf_extractor.domain.role_mapping import map_role


def test_maps_headings_and_preserves_unknown_source_role() -> None:
    assert map_role("H2", {}) == ("heading", 2)
    assert map_role("CustomHeading", {"CustomHeading": "H3"}) == ("heading", 3)
    assert map_role("SamsungBox", {}) == ("unknown", None)


def test_structure_element_preserves_mixed_child_order() -> None:
    first = ContentFragment(page_index=0, mcid=3, text_parts=("A",))
    nested = StructureElement(source_role="Span", semantic_role="span")
    last = ContentFragment(page_index=0, mcid=4, text_parts=("B",))
    element = StructureElement(
        source_role="P", semantic_role="paragraph", children=(first, nested, last)
    )
    assert element.children == (first, nested, last)
