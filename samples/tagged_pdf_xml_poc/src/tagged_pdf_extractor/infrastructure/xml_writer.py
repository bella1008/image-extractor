from __future__ import annotations

import base64
import binascii
import json
import os
import tempfile
from collections.abc import Mapping
from pathlib import Path
from xml.etree import ElementTree as ET

from tagged_pdf_extractor.domain.heading_promotion_validation import (
    HeadingPromotionTracker,
)
from tagged_pdf_extractor.domain.inline_icon_policy import (
    GENERIC_INLINE_ICON_REASON,
    NAVIGATION_ROUTE_INLINE_ICON_REASON,
)
from tagged_pdf_extractor.domain.display_hint_validation import (
    validate_display_hints,
)
from tagged_pdf_extractor.domain.models import (
    ContentFragment,
    HeadingPromotion,
    InlineIconHint,
    LineBreakHint,
    SentenceBreakHint,
    StructureElement,
    SubtitleHint,
    TaggedDocument,
    TextDisplayHint,
)
from tagged_pdf_extractor.domain.subtitle_detection import (
    subtitle_target_rejection,
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
_BASE64_UTF8 = "base64-utf8"
_BASE64_UTF8_SURROGATEPASS = "base64-utf8-surrogatepass"


def decode_data_element(element: ET.Element) -> str:
    parts = [element.text or ""]
    for child in element:
        if child.tag != "control" or tuple(child.attrib) != ("code",):
            raise ValueError(f"invalid data child {child.tag!r}")
        code_text = child.attrib["code"]
        try:
            code_point = int(code_text, 16)
        except ValueError as exc:
            raise ValueError(f"invalid control code {code_text!r}") from exc
        if (
            len(code_text) < 4
            or code_text != code_text.upper()
            or code_text != f"{code_point:04X}"
            or code_point > 0x10FFFF
            or _is_xml_10_character(chr(code_point))
        ):
            raise ValueError(f"invalid control code {code_text!r}")
        parts.extend((chr(code_point), child.tail or ""))
    return "".join(parts)


def _is_xml_10_character(character: str) -> bool:
    code_point = ord(character)
    return (
        code_point in {0x09, 0x0A, 0x0D}
        or 0x20 <= code_point <= 0xD7FF
        or 0xE000 <= code_point <= 0xFFFD
        or 0x10000 <= code_point <= 0x10FFFF
    )


def _encoded_attributes(attributes: dict[str, str]) -> dict[str, str]:
    encoded: dict[str, str] = {}
    for name, value in attributes.items():
        if any(not _is_xml_10_character(character) for character in value):
            try:
                value_bytes = value.encode("utf-8")
                encoding = _BASE64_UTF8
            except UnicodeEncodeError:
                value_bytes = value.encode("utf-8", errors="surrogatepass")
                encoding = _BASE64_UTF8_SURROGATEPASS
            encoded[name] = base64.b64encode(value_bytes).decode("ascii")
            encoded[f"{name}-encoding"] = encoding
        else:
            encoded[name] = value
    return encoded


def _decoded_attributes(element: ET.Element) -> tuple[tuple[str, str], ...]:
    items = tuple(element.attrib.items())
    decoded: list[tuple[str, str]] = []
    index = 0
    while index < len(items):
        name, value = items[index]
        if name.endswith("-encoding"):
            raise ValueError(f"orphan attribute encoding marker {name!r}")
        marker_name = f"{name}-encoding"
        if index + 1 < len(items) and items[index + 1][0] == marker_name:
            marker = items[index + 1][1]
            if marker == _BASE64_UTF8:
                decode_errors = "strict"
            elif marker == _BASE64_UTF8_SURROGATEPASS:
                decode_errors = "surrogatepass"
            else:
                raise ValueError(f"unsupported attribute encoding {marker!r}")
            try:
                value = base64.b64decode(value, validate=True).decode(
                    "utf-8", errors=decode_errors
                )
            except (binascii.Error, UnicodeDecodeError) as exc:
                raise ValueError(f"invalid base64 UTF-8 attribute {name!r}") from exc
            index += 1
        decoded.append((name, value))
        index += 1
    return tuple(decoded)


def _set_data_text(element: ET.Element, value: str) -> None:
    segment: list[str] = []
    last_control: ET.Element | None = None
    for character in value:
        if _is_xml_10_character(character):
            segment.append(character)
            continue
        valid_text = "".join(segment) or None
        if last_control is None:
            element.text = valid_text
        else:
            last_control.tail = valid_text
        last_control = ET.SubElement(
            element, "control", {"code": f"{ord(character):04X}"}
        )
        segment = []
    valid_text = "".join(segment) or None
    if last_control is None:
        element.text = valid_text
    else:
        last_control.tail = valid_text


class XmlDocumentWriter:
    def write_raw(self, document: TaggedDocument, path: Path) -> None:
        validate_display_hints(document)
        root_attributes = {
            "source": str(document.source_path),
            "marked": "true" if document.marked else "false",
        }
        if document.language is not None:
            root_attributes["language"] = document.language
        root = ET.Element("tagged-document", _encoded_attributes(root_attributes))

        if document.role_map:
            role_map = ET.SubElement(root, "role-map")
            for source_role, mapped_role in document.role_map:
                ET.SubElement(
                    role_map,
                    "role",
                    _encoded_attributes(
                        {"source-role": source_role, "mapped-role": mapped_role}
                    ),
                )

        for child in document.children:
            self._append_raw_child(root, child)

        self._write_and_verify(
            root,
            path,
            expected_text=self._raw_text(document.children),
            output_name="raw",
            text_data_tags=frozenset({"part"}),
        )

    def write_semantic(
        self, document: TaggedDocument, path: Path
    ) -> tuple[dict[str, object], ...]:
        validated_display_hints = validate_display_hints(document)
        root = ET.Element("document")
        expected_parts: list[str] = []
        decisions: list[dict[str, object]] = []
        promotion_tracker = HeadingPromotionTracker(document.heading_promotions)
        subtitle_by_path = {
            hint.child_path: hint for hint in document.subtitle_hints
        }
        consumed_subtitle_paths: set[tuple[int, ...]] = set()
        consumed_line_break_paths: set[tuple[int, ...]] = set()
        consumed_text_display_paths: set[tuple[int, ...]] = set()
        consumed_sentence_break_paths: set[tuple[int, ...]] = set()
        consumed_inline_icon_paths: set[tuple[int, ...]] = set()

        for index, child in enumerate(document.children):
            self._append_semantic_child(
                root,
                child,
                parent_path="",
                parent_child_path=(),
                child_index=index,
                promotion_tracker=promotion_tracker,
                subtitle_by_path=subtitle_by_path,
                consumed_subtitle_paths=consumed_subtitle_paths,
                line_break_by_path=validated_display_hints.line_break_by_path,
                consumed_line_break_paths=consumed_line_break_paths,
                text_display_by_path=validated_display_hints.text_display_by_path,
                consumed_text_display_paths=consumed_text_display_paths,
                sentence_break_by_path=(
                    validated_display_hints.sentence_break_by_path
                ),
                consumed_sentence_break_paths=consumed_sentence_break_paths,
                inline_icon_by_path=validated_display_hints.inline_icon_by_path,
                consumed_inline_icon_paths=consumed_inline_icon_paths,
                expected_parts=expected_parts,
                decisions=decisions,
            )

        promotion_tracker.assert_all_applied()
        unresolved_subtitle_paths = set(subtitle_by_path) - consumed_subtitle_paths
        if unresolved_subtitle_paths:
            unresolved = sorted(unresolved_subtitle_paths)[0]
            raise ValueError(f"unresolved subtitle hint path {unresolved}")
        self._assert_display_hints_consumed(
            validated_display_hints.line_break_by_path,
            consumed_line_break_paths,
            "line break hint",
        )
        self._assert_display_hints_consumed(
            validated_display_hints.text_display_by_path,
            consumed_text_display_paths,
            "text display hint",
        )
        self._assert_display_hints_consumed(
            validated_display_hints.sentence_break_by_path,
            consumed_sentence_break_paths,
            "sentence break hint",
        )
        self._assert_display_hints_consumed(
            validated_display_hints.inline_icon_by_path,
            consumed_inline_icon_paths,
            "inline icon hint",
        )
        self._write_and_verify(
            root,
            path,
            expected_text="".join(expected_parts),
            output_name="semantic",
            text_data_tags=frozenset({"text"}),
        )
        return tuple(decisions)

    def _append_raw_child(
        self,
        parent: ET.Element,
        child: StructureElement | ContentFragment,
    ) -> None:
        if isinstance(child, ContentFragment):
            fragment = ET.SubElement(
                parent,
                "fragment",
                _encoded_attributes(self._fragment_attributes(child)),
            )
            for part in child.text_parts:
                _set_data_text(ET.SubElement(fragment, "part"), part)
            return

        element = ET.SubElement(
            parent,
            "element",
            _encoded_attributes(self._raw_element_attributes(child)),
        )
        self._append_source_attributes(element, child.attributes)
        for nested_child in child.children:
            self._append_raw_child(element, nested_child)

    def _append_semantic_child(
        self,
        parent: ET.Element,
        child: StructureElement | ContentFragment,
        *,
        parent_path: str,
        parent_child_path: tuple[int, ...],
        child_index: int,
        promotion_tracker: HeadingPromotionTracker,
        subtitle_by_path: dict[tuple[int, ...], SubtitleHint],
        consumed_subtitle_paths: set[tuple[int, ...]],
        line_break_by_path: Mapping[tuple[int, ...], LineBreakHint],
        consumed_line_break_paths: set[tuple[int, ...]],
        text_display_by_path: Mapping[tuple[int, ...], TextDisplayHint],
        consumed_text_display_paths: set[tuple[int, ...]],
        sentence_break_by_path: Mapping[tuple[int, ...], SentenceBreakHint],
        consumed_sentence_break_paths: set[tuple[int, ...]],
        inline_icon_by_path: Mapping[tuple[int, ...], InlineIconHint],
        consumed_inline_icon_paths: set[tuple[int, ...]],
        expected_parts: list[str],
        decisions: list[dict[str, object]],
    ) -> None:
        child_path = (*parent_child_path, child_index)
        promotion = promotion_tracker.apply(child_path, child)
        subtitle = subtitle_by_path.get(child_path)
        line_break = line_break_by_path.get(child_path)
        text_display = text_display_by_path.get(child_path)
        sentence_break = sentence_break_by_path.get(child_path)
        inline_icon = inline_icon_by_path.get(child_path)
        if subtitle is not None:
            rejection = subtitle_target_rejection(
                child, promoted=promotion is not None
            )
            if rejection == "not_unpromoted_paragraph":
                raise ValueError(
                    "subtitle hint must target an unpromoted paragraph "
                    f"StructureElement at {child_path}"
                )
            if rejection == "source_role_heading_candidate":
                raise ValueError(
                    "subtitle hint must not target a source-role heading candidate "
                    f"at {child_path}"
                )
            if rejection == "block_descendant":
                raise ValueError(
                    "subtitle paragraph must not contain block descendants "
                    f"at {child_path}"
                )
            if rejection is not None:
                raise AssertionError(f"unknown subtitle target rejection {rejection}")
            consumed_subtitle_paths.add(child_path)
        if isinstance(child, ContentFragment):
            text, fragment_decisions = join_text_parts(child.text_parts)
            attributes = self._fragment_attributes(child)
            if sentence_break is not None:
                attributes.update(self._sentence_break_attributes(sentence_break))
                consumed_sentence_break_paths.add(child_path)
            text_element = ET.SubElement(
                parent,
                "text",
                _encoded_attributes(attributes),
            )
            _set_data_text(text_element, text)
            expected_parts.append(text)
            element_path = parent_path or "/"
            for decision in fragment_decisions:
                decisions.append(
                    {
                        "page_index": child.page_index,
                        "mcid": child.mcid,
                        "element_path": element_path,
                        "fragment_child_index": child_index,
                        **decision,
                    }
                )
            return

        tag = (
            "heading"
            if promotion is not None
            else (
                child.semantic_role
                if child.semantic_role in _SAFE_SEMANTIC_TAGS
                else "unknown"
            )
        )
        element_path = f"{parent_path}/{tag}[{child_index}]"
        attributes = self._semantic_element_attributes(child, tag)
        if promotion is not None:
            attributes.update(
                self._promotion_attributes(promotion, source_role=child.source_role)
            )
        if subtitle is not None:
            attributes.update(self._subtitle_attributes(subtitle))
        if line_break is not None:
            attributes.update(self._line_break_attributes(line_break))
            consumed_line_break_paths.add(child_path)
        if text_display is not None:
            attributes.update(self._text_display_attributes(text_display))
            consumed_text_display_paths.add(child_path)
        if inline_icon is not None:
            attributes.update(self._inline_icon_attributes(inline_icon))
            consumed_inline_icon_paths.add(child_path)
        element = ET.SubElement(
            parent,
            tag,
            _encoded_attributes(attributes),
        )
        self._append_source_attributes(element, child.attributes)
        for index, nested_child in enumerate(child.children):
            self._append_semantic_child(
                element,
                nested_child,
                parent_path=element_path,
                parent_child_path=child_path,
                child_index=index,
                promotion_tracker=promotion_tracker,
                subtitle_by_path=subtitle_by_path,
                consumed_subtitle_paths=consumed_subtitle_paths,
                line_break_by_path=line_break_by_path,
                consumed_line_break_paths=consumed_line_break_paths,
                text_display_by_path=text_display_by_path,
                consumed_text_display_paths=consumed_text_display_paths,
                sentence_break_by_path=sentence_break_by_path,
                consumed_sentence_break_paths=consumed_sentence_break_paths,
                inline_icon_by_path=inline_icon_by_path,
                consumed_inline_icon_paths=consumed_inline_icon_paths,
                expected_parts=expected_parts,
                decisions=decisions,
            )

    @staticmethod
    def _subtitle_attributes(subtitle: SubtitleHint) -> dict[str, str]:
        return {
            "display-role": "subtitle",
            "subtitle-reason": subtitle.reason,
            "font-weight": str(subtitle.font_weight),
            "comparison-body-font-weight": str(
                subtitle.comparison_body_font_weight
            ),
            "observed-line-count": str(subtitle.observed_line_count),
        }

    @staticmethod
    def _line_break_attributes(hint: LineBreakHint) -> dict[str, str]:
        return {
            "display-role": "preserved-line-break",
            "line-break-reason": hint.reason,
        }

    @staticmethod
    def _text_display_attributes(hint: TextDisplayHint) -> dict[str, str]:
        attributes = {
            "display-role": hint.display_role.replace("_", "-"),
            "display-reason": hint.reason,
            "font-weight": str(hint.font_weight),
            "font-size": XmlDocumentWriter._format_number(hint.font_size),
            "comparison-body-font-weight": str(
                hint.comparison_body_font_weight
            ),
            "comparison-body-font-size": XmlDocumentWriter._format_number(
                hint.comparison_body_font_size
            ),
        }
        if hint.display_role == "section_heading":
            attributes["display-level"] = "2"
        return attributes

    @staticmethod
    def _sentence_break_attributes(hint: SentenceBreakHint) -> dict[str, str]:
        return {
            "display-role": "sentence-break-source",
            "sentence-break-offsets": ",".join(str(offset) for offset in hint.offsets),
            "sentence-break-reason": hint.reason,
        }

    @staticmethod
    def _inline_icon_attributes(hint: InlineIconHint) -> dict[str, str]:
        attributes = {
            "display-role": "inline-icon",
            "icon-reason": hint.reason,
            "reference-font-size": XmlDocumentWriter._format_number(
                hint.reference_font_size
            ),
            "width-font-ratio": XmlDocumentWriter._format_number(
                hint.width_ratio
            ),
            "height-font-ratio": XmlDocumentWriter._format_number(
                hint.height_ratio
            ),
        }
        if hint.reason == NAVIGATION_ROUTE_INLINE_ICON_REASON:
            if (
                type(hint.route_separator_count) is not int
                or hint.route_separator_count < 2
                or type(hint.route_parenthesized) is not bool
            ):
                raise ValueError("invalid navigation route icon evidence")
            attributes["route-separator-count"] = str(
                hint.route_separator_count
            )
            attributes["route-parenthesized"] = (
                "true" if hint.route_parenthesized else "false"
            )
        elif hint.reason == GENERIC_INLINE_ICON_REASON:
            if (
                hint.route_separator_count is not None
                or hint.route_parenthesized is not None
            ):
                raise ValueError("generic inline icon contains route evidence")
        else:
            raise ValueError(f"unknown inline icon reason: {hint.reason}")
        return attributes

    @staticmethod
    def _assert_display_hints_consumed(
        hints_by_path: Mapping[tuple[int, ...], object],
        consumed_paths: set[tuple[int, ...]],
        name: str,
    ) -> None:
        unresolved = set(hints_by_path) - consumed_paths
        if unresolved:
            raise ValueError(f"unresolved {name} path {sorted(unresolved)[0]}")

    @staticmethod
    def _promotion_attributes(
        promotion: HeadingPromotion, *, source_role: str
    ) -> dict[str, str]:
        return {
            "level": str(promotion.level),
            "source-role": source_role,
            "promotion-reason": promotion.promotion_reason,
            "series-index": str(promotion.series_index),
            "heading-font-size": XmlDocumentWriter._format_number(
                promotion.heading_font_size
            ),
            "body-font-size": XmlDocumentWriter._format_number(
                promotion.body_font_size
            ),
            "font-size-ratio": XmlDocumentWriter._format_number(
                promotion.font_size_ratio
            ),
            "heading-font-names": json.dumps(
                promotion.heading_font_names,
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            "body-font-names": json.dumps(
                promotion.body_font_names,
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        }

    @staticmethod
    def _format_number(value: float) -> str:
        return f"{value:.6f}".rstrip("0").rstrip(".")

    @staticmethod
    def _format_bbox_number(value: float) -> str:
        if value == 0:
            return "0"
        serialized = repr(value)
        return serialized[:-2] if serialized.endswith(".0") else serialized

    @staticmethod
    def _fragment_attributes(fragment: ContentFragment) -> dict[str, str]:
        attributes = {"page-index": str(fragment.page_index)}
        if fragment.mcid is not None:
            attributes["mcid"] = str(fragment.mcid)
        if fragment.object_ref is not None:
            attributes["object-ref"] = fragment.object_ref
        bbox = fragment.bbox
        if bbox is not None:
            attributes["bbox"] = ",".join(
                XmlDocumentWriter._format_bbox_number(value) for value in bbox
            )
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
            ET.SubElement(
                container,
                "attribute",
                _encoded_attributes({"name": name, "value": value}),
            )

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
        text_data_tags: frozenset[str],
    ) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        expected_signature = XmlDocumentWriter._canonical_signature(
            root, text_data_tags
        )
        data_state = XmlDocumentWriter._snapshot_data_text(root, text_data_tags)
        tree = ET.ElementTree(root)
        ET.indent(tree, space="  ")
        XmlDocumentWriter._restore_data_text(data_state)
        XmlDocumentWriter._remove_indentation_text(root, text_data_tags)
        serialized = ET.tostring(root, encoding="utf-8", xml_declaration=True)
        serialized = serialized.replace(b"\r", b"&#13;")

        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
                temporary.write(serialized)

            parsed_root = ET.parse(temporary_path).getroot()
            parsed_signature = XmlDocumentWriter._canonical_signature(
                parsed_root, text_data_tags
            )
            if parsed_signature != expected_signature:
                raise ValueError(f"{output_name} XML structural round trip mismatch")

            parsed_text = XmlDocumentWriter._decoded_tree_text(
                parsed_root, text_data_tags
            )
            if parsed_text != expected_text:
                raise ValueError(
                    f"{output_name} XML text round trip mismatch: "
                    f"expected {expected_text!r}, parsed {parsed_text!r}"
                )

            os.replace(temporary_path, path)
            temporary_path = None
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    @staticmethod
    def _snapshot_data_text(
        root: ET.Element, text_data_tags: frozenset[str]
    ) -> tuple[
        tuple[ET.Element, str | None, tuple[tuple[ET.Element, str | None], ...]], ...
    ]:
        return tuple(
            (
                element,
                element.text,
                tuple((child, child.tail) for child in element),
            )
            for element in root.iter()
            if element.tag in text_data_tags
        )

    @staticmethod
    def _restore_data_text(
        data_state: tuple[
            tuple[ET.Element, str | None, tuple[tuple[ET.Element, str | None], ...]],
            ...,
        ]
    ) -> None:
        for element, text, child_tails in data_state:
            element.text = text
            for child, tail in child_tails:
                child.tail = tail

    @classmethod
    def _canonical_signature(
        cls,
        element: ET.Element,
        text_data_tags: frozenset[str],
        *,
        tail_is_data: bool = False,
    ) -> tuple[object, ...]:
        is_data = element.tag in text_data_tags
        text = (
            decode_data_element(element)
            if is_data
            else cls._without_formatting(element.text)
        )
        tail = element.tail if tail_is_data else cls._without_formatting(element.tail)
        return (
            element.tag,
            _decoded_attributes(element),
            text,
            tuple(
                cls._canonical_signature(
                    child,
                    text_data_tags,
                    tail_is_data=is_data,
                )
                for child in element
            ),
            tail,
        )

    @classmethod
    def _decoded_tree_text(
        cls, element: ET.Element, text_data_tags: frozenset[str]
    ) -> str:
        if element.tag in text_data_tags:
            return decode_data_element(element)
        return "".join(
            cls._decoded_tree_text(child, text_data_tags) for child in element
        )

    @staticmethod
    def _without_formatting(value: str | None) -> str | None:
        if value is not None and value.isspace():
            return None
        return value

    @classmethod
    def _remove_indentation_text(
        cls, element: ET.Element, text_data_tags: frozenset[str]
    ) -> None:
        is_data = element.tag in text_data_tags
        if (
            not is_data
            and element.text is not None
            and not element.text.strip()
        ):
            element.text = None
        for child in element:
            cls._remove_indentation_text(child, text_data_tags)
            if not is_data and child.tail is not None and not child.tail.strip():
                child.tail = None
