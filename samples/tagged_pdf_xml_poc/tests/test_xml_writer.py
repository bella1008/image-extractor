import base64
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from tagged_pdf_extractor.domain.models import (
    ContentFragment,
    StructureElement,
    TaggedDocument,
)
from tagged_pdf_extractor.infrastructure import xml_writer as xml_writer_module
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
            "fragment_child_index": 0,
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


def test_raw_preserves_cr_crlf_and_literal_character_reference_text(
    tmp_path: Path,
) -> None:
    parts = ("\r", "\r\n", "literal &#13; remains text")
    fragment = ContentFragment(page_index=3, mcid=6, text_parts=parts)
    document = TaggedDocument(Path("carriage-return.pdf"), True, None, (), (fragment,))
    raw_path = tmp_path / "raw.xml"

    XmlDocumentWriter().write_raw(document, raw_path)

    raw_fragment = ET.parse(raw_path).getroot().find("fragment")
    assert raw_fragment is not None
    assert [part.text for part in raw_fragment.findall("part")] == list(parts)
    assert "".join(raw_fragment.itertext()) == fragment.text
    serialized = raw_path.read_bytes()
    assert b"&#13;" in serialized
    assert b"literal &amp;#13; remains text" in serialized


def test_semantic_preserves_carriage_returns_in_serialized_text(tmp_path: Path) -> None:
    source_text = "first\rsecond\r\nthird"
    fragment = ContentFragment(page_index=4, mcid=7, text_parts=(source_text,))
    document = TaggedDocument(Path("semantic-cr.pdf"), True, None, (), (fragment,))
    semantic_path = tmp_path / "semantic.xml"

    XmlDocumentWriter().write_semantic(document, semantic_path)

    semantic = ET.parse(semantic_path).getroot()
    semantic_text = semantic.find("text")
    assert semantic_text is not None
    assert semantic_text.text == source_text
    assert "".join(semantic.itertext()) == source_text


def test_control_nodes_preserve_forbidden_xml_characters_in_raw_and_semantic(
    tmp_path: Path,
) -> None:
    source_text = "A\x01B\x02C\x07D\x0eE\x00F"
    fragment = ContentFragment(page_index=5, mcid=9, text_parts=(source_text, "tail"))
    document = TaggedDocument(Path("controls.pdf"), True, None, (), (fragment,))
    raw_path = tmp_path / "raw.xml"
    semantic_path = tmp_path / "semantic.xml"

    writer = XmlDocumentWriter()
    writer.write_raw(document, raw_path)
    writer.write_semantic(document, semantic_path)

    raw_parts = ET.parse(raw_path).getroot().findall("fragment/part")
    semantic_text = ET.parse(semantic_path).getroot().find("text")
    assert len(raw_parts) == 2
    assert semantic_text is not None
    expected_codes = ["0001", "0002", "0007", "000E", "0000"]
    assert [node.attrib["code"] for node in raw_parts[0].findall("control")] == expected_codes
    assert [node.attrib["code"] for node in semantic_text.findall("control")] == expected_codes
    assert [xml_writer_module.decode_data_element(part) for part in raw_parts] == [
        source_text,
        "tail",
    ]
    assert xml_writer_module.decode_data_element(semantic_text) == f"{source_text} tail"


def test_invalid_metadata_and_source_attributes_use_reversible_base64(
    tmp_path: Path,
) -> None:
    source_role = "P\x01"
    title = "Title\x02"
    attribute_name = "Key\x07"
    attribute_value = "Value\x0e"
    element = StructureElement(
        source_role=source_role,
        semantic_role="paragraph",
        title=title,
        attributes=((attribute_name, attribute_value),),
    )
    document = TaggedDocument(
        Path("source.pdf"),
        True,
        "en\x00US",
        (("Role\x01", "P\x02"),),
        (element,),
    )
    raw_path = tmp_path / "raw.xml"
    semantic_path = tmp_path / "semantic.xml"

    writer = XmlDocumentWriter()
    writer.write_raw(document, raw_path)
    writer.write_semantic(document, semantic_path)

    raw = ET.parse(raw_path).getroot()
    assert raw.attrib["language-encoding"] == "base64-utf8"
    assert base64.b64decode(raw.attrib["language"]).decode("utf-8") == "en\x00US"
    raw_element = raw.find("element")
    assert raw_element is not None
    assert raw_element.attrib["source-role-encoding"] == "base64-utf8"
    assert base64.b64decode(raw_element.attrib["source-role"]).decode("utf-8") == source_role
    assert raw_element.attrib["title-encoding"] == "base64-utf8"
    assert base64.b64decode(raw_element.attrib["title"]).decode("utf-8") == title
    source_attribute = raw_element.find("attributes/attribute")
    assert source_attribute is not None
    assert source_attribute.attrib["name-encoding"] == "base64-utf8"
    assert source_attribute.attrib["value-encoding"] == "base64-utf8"
    assert base64.b64decode(source_attribute.attrib["name"]).decode("utf-8") == attribute_name
    assert base64.b64decode(source_attribute.attrib["value"]).decode("utf-8") == attribute_value


def test_failed_structural_validation_is_atomic_and_preserves_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fragment = ContentFragment(page_index=0, mcid=1, text_parts=("A", "B"))
    document = TaggedDocument(Path("boundaries.pdf"), True, None, (), (fragment,))
    raw_path = tmp_path / "raw.xml"
    raw_path.write_text("existing destination", encoding="utf-8")
    original_tostring = xml_writer_module.ET.tostring

    def collapse_part_boundary(*args: object, **kwargs: object) -> bytes:
        serialized = original_tostring(*args, **kwargs)
        return serialized.replace(b"<part>A</part><part>B</part>", b"<part>AB</part>")

    monkeypatch.setattr(xml_writer_module.ET, "tostring", collapse_part_boundary)

    with pytest.raises(ValueError, match="structural round trip mismatch"):
        XmlDocumentWriter().write_raw(document, raw_path)

    assert raw_path.read_text(encoding="utf-8") == "existing destination"
    assert list(tmp_path.glob(".raw.xml.*.tmp")) == []


def test_join_decisions_distinguish_sibling_fragments_with_null_mcids(
    tmp_path: Path,
) -> None:
    first = ContentFragment(0, None, ("first", "fragment"))
    second = ContentFragment(0, None, ("second", "fragment"))
    paragraph = StructureElement("P", "paragraph", children=(first, second))
    document = TaggedDocument(Path("decisions.pdf"), True, None, (), (paragraph,))

    decisions = XmlDocumentWriter().write_semantic(document, tmp_path / "semantic.xml")

    assert [decision["fragment_child_index"] for decision in decisions] == [0, 1]
    assert [decision["element_path"] for decision in decisions] == [
        "/paragraph[0]",
        "/paragraph[0]",
    ]
    assert [decision["mcid"] for decision in decisions] == [None, None]


def test_raw_preserves_whitespace_only_tail_after_control(tmp_path: Path) -> None:
    source_text = "A\x01 "
    fragment = ContentFragment(0, 1, (source_text,))
    document = TaggedDocument(Path("raw-tail.pdf"), True, None, (), (fragment,))
    raw_path = tmp_path / "raw.xml"

    XmlDocumentWriter().write_raw(document, raw_path)

    raw_part = ET.parse(raw_path).getroot().find("fragment/part")
    assert raw_part is not None
    assert xml_writer_module.decode_data_element(raw_part) == source_text
    control = raw_part.find("control")
    assert control is not None and control.tail == " "


def test_semantic_preserves_newline_tail_after_control(tmp_path: Path) -> None:
    source_text = "A\x01\n"
    fragment = ContentFragment(0, 2, (source_text,))
    document = TaggedDocument(
        Path("semantic-tail.pdf"), True, None, (), (fragment,)
    )
    semantic_path = tmp_path / "semantic.xml"

    XmlDocumentWriter().write_semantic(document, semantic_path)

    semantic_text = ET.parse(semantic_path).getroot().find("text")
    assert semantic_text is not None
    assert xml_writer_module.decode_data_element(semantic_text) == source_text
    control = semantic_text.find("control")
    assert control is not None and control.tail == "\n"


def test_lone_surrogate_metadata_round_trips_with_explicit_encoding(
    tmp_path: Path,
) -> None:
    title = "before\ud800after"
    element = StructureElement("P", "paragraph", title=title)
    document = TaggedDocument(Path("surrogate.pdf"), True, None, (), (element,))
    raw_path = tmp_path / "raw.xml"
    semantic_path = tmp_path / "semantic.xml"

    writer = XmlDocumentWriter()
    writer.write_raw(document, raw_path)
    writer.write_semantic(document, semantic_path)

    raw_element = ET.parse(raw_path).getroot().find("element")
    semantic_element = ET.parse(semantic_path).getroot().find("paragraph")
    assert raw_element is not None
    assert semantic_element is not None
    for serialized_element in (raw_element, semantic_element):
        assert (
            serialized_element.attrib["title-encoding"]
            == "base64-utf8-surrogatepass"
        )
        encoded = base64.b64decode(serialized_element.attrib["title"])
        assert encoded.decode("utf-8", errors="surrogatepass") == title
