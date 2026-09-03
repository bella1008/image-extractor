from __future__ import annotations

import os
import re
import tempfile
from collections.abc import Iterable
from pathlib import Path
from xml.etree import ElementTree as ET

from tagged_pdf_extractor.domain.models import QualityReport
from tagged_pdf_extractor.domain.text_joining import join_text_parts
from tagged_pdf_extractor.infrastructure.xml_writer import decode_data_element


_WHITESPACE = re.compile(r"\s+")
_MARKDOWN_LINE_PREFIX = re.compile(r"^(#{1,6}\s|>|[-+*]\s|\d+[.)]\s)")
_CELL_TAGS = frozenset({"table_header", "table_cell"})


class MarkdownDocumentWriter:
    def write(
        self,
        semantic_xml: Path,
        report: QualityReport,
        output: Path,
        *,
        source_name: str,
    ) -> None:
        root = ET.parse(semantic_xml).getroot()
        path_index = self._build_path_index(root)
        promoted: dict[ET.Element, dict[str, object]] = {}
        for entry in report.heading_hierarchy:
            if entry.get("classification") != "source_role_candidate":
                continue
            path = entry.get("structure_path")
            element = path_index.get(path) if isinstance(path, str) else None
            if element is None:
                raise ValueError(f"unresolved heading candidate path {path}")
            promoted[element] = entry

        header = [
            "# Semantic XML 문서 검토",
            "",
            f"- 원본 파일: {source_name}",
            "- 목적: PDF 태그 구조와 추출 텍스트 검토",
            "- 주의: 아래 제목은 검증된 표준 PDF 제목이 아니라 PDF 원본 역할 후보입니다.",
        ]
        blocks = self._render_children(root, promoted)
        markdown = "\n".join(header)
        if blocks:
            markdown += "\n\n" + "\n\n".join(blocks)
        markdown += "\n"
        self._write_atomic(output, markdown)

    @classmethod
    def _build_path_index(cls, root: ET.Element) -> dict[str, ET.Element]:
        indexed: dict[str, ET.Element] = {}

        def walk(parent: ET.Element, parent_path: str) -> None:
            absolute_index = 0
            for child in parent:
                if child.tag == "attributes":
                    continue
                path = f"{parent_path}/{child.tag}[{absolute_index}]"
                indexed[path] = child
                walk(child, path)
                absolute_index += 1

        walk(root, "")
        return indexed

    @classmethod
    def _render_children(
        cls,
        parent: ET.Element,
        promoted: dict[ET.Element, dict[str, object]],
    ) -> list[str]:
        blocks: list[str] = []
        for child in parent:
            if child.tag == "attributes":
                continue
            blocks.extend(cls._render_element(child, promoted))
        return blocks

    @classmethod
    def _render_element(
        cls,
        element: ET.Element,
        promoted: dict[ET.Element, dict[str, object]],
    ) -> list[str]:
        heading = promoted.get(element)
        if heading is not None:
            source_level = heading.get("level")
            if source_level is None:
                source_level = 1
            level = max(1, int(source_level))
            prefix = "#" * min(level + 1, 6)
            return [f"{prefix} {cls._element_text(element)}"]

        if element.tag in {"paragraph", "heading", "caption", "label"}:
            text = cls._element_text(element)
            return [cls._escape_line_prefix(text)] if text else []
        if element.tag == "text":
            text = cls._text_value(element)
            return [cls._escape_line_prefix(text)] if text else []
        if element.tag == "list":
            lines = cls._render_list(element, depth=0)
            return ["\n".join(lines)] if lines else []
        if element.tag == "table":
            return [cls._render_table(element)]
        if element.tag == "figure":
            text = cls._element_text(element)
            return [cls._escape_line_prefix(text) if text else "[그림: 텍스트 없음]"]
        return cls._render_children(element, promoted)

    @classmethod
    def _render_list(cls, element: ET.Element, *, depth: int) -> list[str]:
        lines: list[str] = []
        for item in cls._structural_children(element):
            if item.tag != "list_item":
                lines.extend(cls._render_list_descendants(item, depth=depth))
                continue
            text_parts: list[str] = []
            nested_lists: list[ET.Element] = []
            cls._collect_list_item(item, text_parts, nested_lists)
            item_text = cls._join_text_parts(text_parts)
            lines.append(f"{'  ' * depth}- {item_text}".rstrip())
            for nested in nested_lists:
                lines.extend(cls._render_list(nested, depth=depth + 1))
        return lines

    @classmethod
    def _render_list_descendants(
        cls, element: ET.Element, *, depth: int
    ) -> list[str]:
        if element.tag == "list":
            return cls._render_list(element, depth=depth)
        lines: list[str] = []
        for child in cls._structural_children(element):
            lines.extend(cls._render_list_descendants(child, depth=depth))
        return lines

    @classmethod
    def _collect_list_item(
        cls,
        element: ET.Element,
        text_parts: list[str],
        nested_lists: list[ET.Element],
    ) -> None:
        for child in cls._structural_children(element):
            if child.tag == "list":
                nested_lists.append(child)
            elif child.tag == "text":
                text_parts.append(cls._visible_text(child))
            else:
                cls._collect_list_item(child, text_parts, nested_lists)

    @classmethod
    def _render_table(cls, table: ET.Element) -> str:
        table_children = cls._structural_children(table)
        rows = [
            child
            for child in table_children
            if child.tag == "table_row"
        ]
        cells = [
            [child for child in cls._structural_children(row) if child.tag in _CELL_TAGS]
            for row in rows
        ]
        has_nested_table = any(
            descendant is not table and descendant.tag == "table"
            for descendant in table.iter()
        )
        rectangular = (
            bool(cells)
            and bool(cells[0])
            and len(rows) == len(table_children)
            and all(len(row_cells) == len(cells[0]) for row_cells in cells)
            and all(
                len(row_cells) == len(cls._structural_children(row))
                for row, row_cells in zip(rows, cells, strict=True)
            )
            and not has_nested_table
        )
        if rectangular:
            rendered_rows = [
                "| "
                + " | ".join(
                    cls._element_text(cell).replace("|", r"\|")
                    for cell in row_cells
                )
                + " |"
                for row_cells in cells
            ]
            separator = "| " + " | ".join("---" for _ in cells[0]) + " |"
            return "\n".join((rendered_rows[0], separator, *rendered_rows[1:]))

        lines: list[str] = []
        row_index = 0
        for child in table_children:
            text = cls._element_text(child)
            if not text:
                continue
            if child.tag == "table_row":
                row_index += 1
                lines.append(f"- 행 {row_index}: {text}")
            else:
                lines.append(f"- {text}")
        if not lines:
            text = cls._element_text(table)
            lines.append(f"- 행 1: {text}".rstrip())
        return "\n".join(lines)

    @staticmethod
    def _structural_children(element: ET.Element) -> list[ET.Element]:
        return [child for child in element if child.tag != "attributes"]

    @classmethod
    def _element_text(cls, element: ET.Element) -> str:
        return cls._join_text_parts(
            cls._visible_text(descendant) for descendant in element.iter("text")
        )

    @classmethod
    def _join_text_parts(cls, parts: Iterable[str]) -> str:
        normalized = [
            _WHITESPACE.sub(" ", part)
            for part in parts
            if part and part.strip()
        ]
        joined, _ = join_text_parts(tuple(normalized))
        return joined.strip()

    @classmethod
    def _text_value(cls, element: ET.Element) -> str:
        return cls._normalize_whitespace(cls._visible_text(element))

    @classmethod
    def _visible_text(cls, element: ET.Element) -> str:
        decoded = decode_data_element(element)
        return "".join(
            character
            if cls._is_xml_character(character)
            else f"[CONTROL U+{ord(character):04X}]"
            for character in decoded
        )

    @staticmethod
    def _normalize_whitespace(value: str) -> str:
        return _WHITESPACE.sub(" ", value).strip()

    @staticmethod
    def _is_xml_character(character: str) -> bool:
        code_point = ord(character)
        return (
            code_point in {0x09, 0x0A, 0x0D}
            or 0x20 <= code_point <= 0xD7FF
            or 0xE000 <= code_point <= 0xFFFD
            or 0x10000 <= code_point <= 0x10FFFF
        )

    @staticmethod
    def _escape_line_prefix(value: str) -> str:
        if _MARKDOWN_LINE_PREFIX.match(value):
            return f"\\{value}"
        return value

    @staticmethod
    def _write_atomic(output: Path, markdown: str) -> None:
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="\n",
                dir=output.parent,
                prefix=f".{output.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
                temporary.write(markdown)
            os.replace(temporary_path, output)
            temporary_path = None
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
