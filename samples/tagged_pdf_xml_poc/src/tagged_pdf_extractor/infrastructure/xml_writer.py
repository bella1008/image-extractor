from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree as ET

from tagged_pdf_extractor.domain.models import (
    ContentFragment,
    StructureElement,
    TaggedDocument,
)
from tagged_pdf_extractor.domain.text_joining import join_text_parts


_SAFE_SEMANTIC_TAGS = frozenset(
    {
        "document",
        "part",
        "article",
        "section",
        "division",
        "paragraph",
        "list",
        "list_item",
        "label",
        "list_body",
        "table",
        "table_row",
        "table_header",
        "table_cell",
        "figure",
        "caption",
        "span",
        "link",
        "heading",
    }
)


class XmlDocumentWriter:
    def write_raw(self, document: TaggedDocument, path: Path) -> None:
        root_attributes = {
            "source": str(document.source_path),
            "marked": "true" if document.marked else "false",
        }
        if document.language is not None:
            root_attributes["language"] = document.language
        root = ET.Element("tagged-document", root_attributes)

        if document.role_map:
            role_map = ET.SubElement(root, "role-map")
            for source_role, mapped_role in document.role_map:
                ET.SubElement(
                    role_map,
                    "role",
                    {"source-role": source_role, "mapped-role": mapped_role},
                )

        for child in document.children:
            self._append_raw_child(root, child)

        self._write_and_verify(
            root,
            path,
            expected_text=self._raw_text(document.children),
            output_name="raw",
        )

    def write_semantic(
        self, document: TaggedDocument, path: Path
    ) -> tuple[dict[str, object], ...]:
        root = ET.Element("document")
        expected_parts: list[str] = []
        decisions: list[dict[str, object]] = []

        for index, child in enumerate(document.children):
            self._append_semantic_child(
                root,
                child,
                parent_path="",
                child_index=index,
                expected_parts=expected_parts,
                decisions=decisions,
            )

        self._write_and_verify(
            root,
            path,
            expected_text="".join(expected_parts),
            output_name="semantic",
        )
        return tuple(decisions)

    def _append_raw_child(
        self,
        parent: ET.Element,
        child: StructureElement | ContentFragment,
    ) -> None:
        if isinstance(child, ContentFragment):
            fragment = ET.SubElement(parent, "fragment", self._fragment_attributes(child))
            for part in child.text_parts:
                ET.SubElement(fragment, "part").text = part
            return

        element = ET.SubElement(parent, "element", self._raw_element_attributes(child))
        self._append_source_attributes(element, child.attributes)
        for nested_child in child.children:
            self._append_raw_child(element, nested_child)

    def _append_semantic_child(
        self,
        parent: ET.Element,
        child: StructureElement | ContentFragment,
        *,
        parent_path: str,
        child_index: int,
        expected_parts: list[str],
        decisions: list[dict[str, object]],
    ) -> None:
        if isinstance(child, ContentFragment):
            text, fragment_decisions = join_text_parts(child.text_parts)
            ET.SubElement(parent, "text", self._fragment_attributes(child)).text = text or None
            expected_parts.append(text)
            element_path = parent_path or "/"
            for decision in fragment_decisions:
                decisions.append(
                    {
                        "page_index": child.page_index,
                        "mcid": child.mcid,
                        "element_path": element_path,
                        **decision,
                    }
                )
            return

        tag = (
            child.semantic_role
            if child.semantic_role in _SAFE_SEMANTIC_TAGS
            else "unknown"
        )
        element_path = f"{parent_path}/{tag}[{child_index}]"
        element = ET.SubElement(parent, tag, self._semantic_element_attributes(child, tag))
        self._append_source_attributes(element, child.attributes)
        for index, nested_child in enumerate(child.children):
            self._append_semantic_child(
                element,
                nested_child,
                parent_path=element_path,
                child_index=index,
                expected_parts=expected_parts,
                decisions=decisions,
            )

    @staticmethod
    def _fragment_attributes(fragment: ContentFragment) -> dict[str, str]:
        attributes = {"page-index": str(fragment.page_index)}
        if fragment.mcid is not None:
            attributes["mcid"] = str(fragment.mcid)
        if fragment.object_ref is not None:
            attributes["object-ref"] = fragment.object_ref
        return attributes

    @staticmethod
    def _raw_element_attributes(element: StructureElement) -> dict[str, str]:
        attributes = {
            "source-role": element.source_role,
            "semantic-role": element.semantic_role,
        }
        XmlDocumentWriter._append_optional_element_attributes(attributes, element)
        return attributes

    @staticmethod
    def _semantic_element_attributes(
        element: StructureElement, tag: str
    ) -> dict[str, str]:
        attributes: dict[str, str] = {}
        if tag == "unknown":
            attributes["source-role"] = element.source_role
        if element.heading_level is not None:
            attributes["level"] = str(element.heading_level)
        XmlDocumentWriter._append_optional_element_attributes(
            attributes, element, include_heading_level=False
        )
        return attributes

    @staticmethod
    def _append_optional_element_attributes(
        attributes: dict[str, str],
        element: StructureElement,
        *,
        include_heading_level: bool = True,
    ) -> None:
        optional_values = (
            ("heading-level", element.heading_level if include_heading_level else None),
            ("object-ref", element.object_ref),
            ("page-index", element.page_index),
            ("title", element.title),
            ("language", element.language),
            ("alternate-text", element.alternate_text),
            ("actual-text", element.actual_text),
        )
        for name, value in optional_values:
            if value is not None:
                attributes[name] = str(value)

    @staticmethod
    def _append_source_attributes(
        parent: ET.Element, attributes: tuple[tuple[str, str], ...]
    ) -> None:
        if not attributes:
            return
        container = ET.SubElement(parent, "attributes")
        for name, value in attributes:
            ET.SubElement(container, "attribute", {"name": name, "value": value})

    @classmethod
    def _raw_text(
        cls, children: tuple[StructureElement | ContentFragment, ...]
    ) -> str:
        text_parts: list[str] = []
        for child in children:
            if isinstance(child, ContentFragment):
                text_parts.append(child.text)
            else:
                text_parts.append(cls._raw_text(child.children))
        return "".join(text_parts)

    @staticmethod
    def _write_and_verify(
        root: ET.Element,
        path: Path,
        *,
        expected_text: str,
        output_name: str,
    ) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tree = ET.ElementTree(root)
        ET.indent(tree, space="  ")
        XmlDocumentWriter._remove_indentation_text(root)
        tree.write(path, encoding="utf-8", xml_declaration=True)

        parsed_root = ET.parse(path).getroot()
        parsed_text = "".join(parsed_root.itertext())
        if parsed_text != expected_text:
            raise ValueError(
                f"{output_name} XML text round trip mismatch: "
                f"expected {expected_text!r}, parsed {parsed_text!r}"
            )

    @classmethod
    def _remove_indentation_text(cls, element: ET.Element) -> None:
        if element.text is not None and not element.text.strip():
            element.text = None
        for child in element:
            cls._remove_indentation_text(child)
            if child.tail is not None and not child.tail.strip():
                child.tail = None
