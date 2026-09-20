from pathlib import Path

from tagged_pdf_extractor.domain.cover_contact import apply_cover_contact_formatting
from tagged_pdf_extractor.domain.display_hint_validation import (
    validate_review_formatting_hints,
)
from tagged_pdf_extractor.domain.models import (
    ContentFragment,
    StructureElement,
    TaggedDocument,
    TextStyle,
)


def fragment(text: str, *, weight: int = 400, mcid: int = 1) -> ContentFragment:
    return ContentFragment(
        page_index=0,
        mcid=mcid,
        text_parts=(text,),
        text_styles=(TextStyle(f"SamsungOne-{weight}", 7.0),),
    )


def element(role: str, *children, attributes=()) -> StructureElement:
    return StructureElement(role, role, children=children, attributes=attributes)


def paragraph(text: str, *, weight: int = 400, mcid: int = 1) -> StructureElement:
    return element("paragraph", fragment(text, weight=weight, mcid=mcid))


def contact_section(*, title_weight: int = 600, extra_child: bool = False) -> StructureElement:
    header = element(
        "table_row",
        element("table_cell", paragraph("Country/Region", mcid=10)),
        element("table_cell", paragraph("Samsung Service Centre", mcid=11)),
        element("table_cell", paragraph("Website", mcid=12)),
    )
    row = element(
        "table_row",
        element("table_cell", paragraph("COUNTRY", mcid=13)),
        element(
            "table_cell",
            paragraph("123 456", mcid=14),
            paragraph("WhatsApp 789", mcid=15),
        ),
        element("table_cell", paragraph("www.samsung.com/support", mcid=16)),
    )
    table = element("table", header, row)
    children = [
        paragraph("Contact title", weight=title_weight, mcid=2),
        paragraph("Contact explanation", weight=400, mcid=3),
        element("paragraph", table),
    ]
    if extra_child:
        children.append(paragraph("Unrelated", mcid=4))
    return element("section", *children)


def document(section: StructureElement) -> TaggedDocument:
    return TaggedDocument(Path("manual.pdf"), True, None, (), (section,))


def test_marks_only_the_structurally_proven_contact_table_and_strong_title() -> None:
    result = apply_cover_contact_formatting(document(contact_section()))
    section = result.children[0]
    assert isinstance(section, StructureElement)
    wrapper = section.children[2]
    assert isinstance(wrapper, StructureElement)
    table = wrapper.children[0]
    assert isinstance(table, StructureElement)

    assert dict(table.attributes) == {
        "review-table": "source-spans",
        "review-table-kind": "cover-contact",
    }
    assert [(hint.child_path, hint.display_role) for hint in result.text_display_hints] == [
        ((0, 0), "strong_label")
    ]
    assert validate_review_formatting_hints(result).text_display_by_path[(0, 0)]


def test_contact_table_classification_does_not_require_a_bold_title() -> None:
    result = apply_cover_contact_formatting(document(contact_section(title_weight=400)))
    section = result.children[0]
    assert isinstance(section, StructureElement)
    wrapper = section.children[2]
    assert isinstance(wrapper, StructureElement)
    table = wrapper.children[0]
    assert isinstance(table, StructureElement)

    assert dict(table.attributes)["review-table-kind"] == "cover-contact"
    assert result.text_display_hints == ()


def test_ignores_a_trailing_empty_source_paragraph_in_contact_section() -> None:
    section = contact_section()
    source = document(
        StructureElement(
            section.source_role,
            section.semantic_role,
            children=(*section.children, element("paragraph")),
        )
    )

    result = apply_cover_contact_formatting(source)
    result_section = result.children[0]
    assert isinstance(result_section, StructureElement)
    wrapper = result_section.children[2]
    assert isinstance(wrapper, StructureElement)
    table = wrapper.children[0]
    assert isinstance(table, StructureElement)

    assert dict(table.attributes)["review-table-kind"] == "cover-contact"
    assert [(hint.child_path, hint.display_role) for hint in result.text_display_hints] == [
        ((0, 0), "strong_label")
    ]


def test_rejects_nearby_non_contact_topology() -> None:
    source = document(contact_section(extra_child=True))

    assert apply_cover_contact_formatting(source) is source


def test_rejects_table_without_contact_data_evidence() -> None:
    section = contact_section()
    wrapper = section.children[2]
    assert isinstance(wrapper, StructureElement)
    table = wrapper.children[0]
    assert isinstance(table, StructureElement)
    rows = list(table.children)
    data = rows[1]
    assert isinstance(data, StructureElement)
    cells = list(data.children)
    cells[2] = element("table_cell", paragraph("No website", mcid=20))
    rows[1] = StructureElement(
        data.source_role,
        data.semantic_role,
        children=tuple(cells),
    )
    replacement = StructureElement(
        table.source_role,
        table.semantic_role,
        children=tuple(rows),
    )
    changed = StructureElement(
        section.source_role,
        section.semantic_role,
        children=(*section.children[:2], element("paragraph", replacement)),
    )
    source = document(changed)

    assert apply_cover_contact_formatting(source) is source
