from pathlib import Path
from xml.etree import ElementTree as ET

from tagged_pdf_extractor.domain.models import (
    ContentFragment,
    StructureElement,
    TaggedDocument,
)
from tagged_pdf_extractor.infrastructure.xml_writer import XmlDocumentWriter


def test_xml_round_trip_preserves_hierarchy_and_exact_unicode_osd_path(
    tmp_path: Path,
) -> None:
    fragment = ContentFragment(
        page_index=0,
        mcid=8,
        text_parts=("Settings > General", " → Accessibility & Help"),
    )
    heading = StructureElement(
        source_role="H2",
        semantic_role="heading",
        heading_level=2,
        children=(fragment,),
    )
    document = TaggedDocument(
        source_path=tmp_path / "sample.pdf",
        marked=True,
        language="en",
        role_map=(),
        children=(heading,),
    )
    raw_path = tmp_path / "nested" / "raw.xml"
    semantic_path = tmp_path / "nested" / "semantic.xml"

    writer = XmlDocumentWriter()
    writer.write_raw(document, raw_path)
    decisions = writer.write_semantic(document, semantic_path)

    raw = ET.parse(raw_path).getroot()
    assert "".join(raw.itertext()) == fragment.text
    assert [part.text for part in raw.findall("./element/fragment/part")] == list(
        fragment.text_parts
    )

    semantic = ET.parse(semantic_path).getroot()
    heading_xml = semantic.find("heading")
    assert heading_xml is not None
    assert heading_xml.attrib["level"] == "2"
    assert "".join(semantic.itertext()) == "Settings > General → Accessibility & Help"
    assert decisions == (
        {
            "page_index": 0,
            "mcid": 8,
            "element_path": "/heading[0]",
            "boundary": 0,
            "action": "trim_left",
        },
    )


def test_preserves_mixed_interleaved_order_and_unknown_source_role(
    tmp_path: Path,
) -> None:
    first = ContentFragment(2, 3, ("before",), object_ref="10 0 R")
    nested_fragment = ContentFragment(2, 4, ("inside",), object_ref="11 0 R")
    unknown = StructureElement(
        source_role="Samsung:Box & Panel",
        semantic_role="unknown",
        object_ref="12 0 R",
        children=(nested_fragment,),
    )
    last = ContentFragment(2, 5, ("after",), object_ref="13 0 R")
    paragraph = StructureElement(
        source_role="P",
        semantic_role="paragraph",
        children=(first, unknown, last),
    )
    document = TaggedDocument(Path("manual.pdf"), True, None, (), (paragraph,))
    raw_path = tmp_path / "raw.xml"
    semantic_path = tmp_path / "semantic.xml"

    writer = XmlDocumentWriter()
    writer.write_raw(document, raw_path)
    writer.write_semantic(document, semantic_path)

    raw_paragraph = ET.parse(raw_path).getroot().find("element")
    assert raw_paragraph is not None
    assert [child.tag for child in raw_paragraph] == ["fragment", "element", "fragment"]
    assert raw_paragraph[0].attrib == {
        "page-index": "2",
        "mcid": "3",
        "object-ref": "10 0 R",
    }
    assert raw_paragraph[1].attrib["object-ref"] == "12 0 R"
    assert raw_paragraph[1][0].attrib["object-ref"] == "11 0 R"

    semantic_paragraph = ET.parse(semantic_path).getroot().find("paragraph")
    assert semantic_paragraph is not None
    assert [child.tag for child in semantic_paragraph] == ["text", "unknown", "text"]
    assert semantic_paragraph[1].attrib["source-role"] == "Samsung:Box & Panel"
    assert "".join(semantic_paragraph.itertext()) == "beforeinsideafter"


def test_raw_preserves_document_role_map_and_all_element_metadata(
    tmp_path: Path,
) -> None:
    element = StructureElement(
        source_role="Figure",
        semantic_role="figure",
        heading_level=4,
        object_ref="81 0 R",
        page_index=7,
        title="Controls <Overview>",
        language="ko-KR",
        alternate_text='Use "A&B"',
        actual_text="실제 → 텍스트",
        attributes=(("Placement", "Block"), ("Placement", "Inline & <safe>")),
    )
    document = TaggedDocument(
        source_path=Path("manual & <review>.pdf"),
        marked=False,
        language="en-US",
        role_map=(("Custom&H", "H2"), ("Box", "Div")),
        children=(element,),
    )
    raw_path = tmp_path / "raw.xml"

    XmlDocumentWriter().write_raw(document, raw_path)

    root = ET.parse(raw_path).getroot()
    assert root.attrib == {
        "source": "manual & <review>.pdf",
        "marked": "false",
        "language": "en-US",
    }
    assert [role.attrib for role in root.findall("./role-map/role")] == [
        {"source-role": "Custom&H", "mapped-role": "H2"},
        {"source-role": "Box", "mapped-role": "Div"},
    ]
    element_xml = root.find("element")
    assert element_xml is not None
    assert element_xml.attrib == {
        "source-role": "Figure",
        "semantic-role": "figure",
        "heading-level": "4",
        "object-ref": "81 0 R",
        "page-index": "7",
        "title": "Controls <Overview>",
        "language": "ko-KR",
        "alternate-text": 'Use "A&B"',
        "actual-text": "실제 → 텍스트",
    }
    assert [item.attrib for item in element_xml.findall("./attributes/attribute")] == [
        {"name": "Placement", "value": "Block"},
        {"name": "Placement", "value": "Inline & <safe>"},
    ]
    assert "".join(root.itertext()) == ""


def test_empty_fragment_and_null_identifiers_round_trip(tmp_path: Path) -> None:
    fragment = ContentFragment(page_index=9, mcid=None, text_parts=())
    document = TaggedDocument(Path("empty.pdf"), False, None, (), (fragment,))
    raw_path = tmp_path / "raw.xml"
    semantic_path = tmp_path / "semantic.xml"

    writer = XmlDocumentWriter()
    writer.write_raw(document, raw_path)
    assert writer.write_semantic(document, semantic_path) == ()

    raw_fragment = ET.parse(raw_path).getroot().find("fragment")
    semantic_text = ET.parse(semantic_path).getroot().find("text")
    assert raw_fragment is not None and raw_fragment.attrib == {"page-index": "9"}
    assert list(raw_fragment) == []
    assert semantic_text is not None and semantic_text.attrib == {"page-index": "9"}
    assert semantic_text.text is None


def test_xml_reserved_characters_round_trip_without_source_normalization(
    tmp_path: Path,
) -> None:
    parts = ("<&", " > © ‘설정’ \"도움말\"")
    fragment = ContentFragment(0, 1, parts, object_ref="7 & 0 <R>")
    document = TaggedDocument(Path("reserved.pdf"), True, None, (), (fragment,))
    raw_path = tmp_path / "raw.xml"
    semantic_path = tmp_path / "semantic.xml"

    writer = XmlDocumentWriter()
    writer.write_raw(document, raw_path)
    writer.write_semantic(document, semantic_path)

    raw_fragment = ET.parse(raw_path).getroot().find("fragment")
    semantic_text = ET.parse(semantic_path).getroot().find("text")
    assert raw_fragment is not None
    assert [part.text for part in raw_fragment.findall("part")] == list(parts)
    assert raw_fragment.attrib["object-ref"] == "7 & 0 <R>"
    assert "".join(raw_fragment.itertext()) == fragment.text
    assert semantic_text is not None
    assert semantic_text.text == "<& > © ‘설정’ \"도움말\""


def test_raw_preserves_whitespace_only_parts_exactly(tmp_path: Path) -> None:
    parts = (" ", "\n", "\t")
    fragment = ContentFragment(page_index=0, mcid=8, text_parts=parts)
    document = TaggedDocument(Path("whitespace.pdf"), True, None, (), (fragment,))
    raw_path = tmp_path / "raw.xml"

    XmlDocumentWriter().write_raw(document, raw_path)

    raw_fragment = ET.parse(raw_path).getroot().find("fragment")
    assert raw_fragment is not None
    assert [part.text for part in raw_fragment.findall("part")] == list(parts)
    assert "".join(raw_fragment.itertext()) == fragment.text


def test_semantic_structural_part_removes_indentation_from_itertext(
    tmp_path: Path,
) -> None:
    fragment = ContentFragment(page_index=1, mcid=4, text_parts=("Nested content",))
    structural_part = StructureElement(
        source_role="Part",
        semantic_role="part",
        children=(fragment,),
    )
    document = TaggedDocument(
        Path("semantic-part.pdf"), True, None, (), (structural_part,)
    )
    semantic_path = tmp_path / "semantic.xml"

    XmlDocumentWriter().write_semantic(document, semantic_path)

    semantic = ET.parse(semantic_path).getroot()
    assert semantic.find("part/text") is not None
    assert "".join(semantic.itertext()) == fragment.text
