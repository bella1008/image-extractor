from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
import os
import re
import tempfile
from pathlib import Path
from xml.etree import ElementTree as ET

from tagged_pdf_extractor.domain.models import QualityReport
from tagged_pdf_extractor.domain.text_joining import join_text_parts
from tagged_pdf_extractor.infrastructure.xml_writer import decode_data_element


_WHITESPACE = re.compile(r"\s+")
_MARKDOWN_LINE_PREFIX = re.compile(r"^(#{1,6}\s|>|[-+*]\s|\d+[.)]\s)")
_FENCED_CODE_PREFIX = re.compile(r"^(?:`{3,}|~{3,})")
_THEMATIC_BREAK = re.compile(r"^(?:(?:\*\s*){3,}|(?:-\s*){3,}|(?:_\s*){3,})$")
_RAW_HTML_BLOCK_PREFIX = re.compile(
    r"^<(?:!--|[!?]|/?[A-Za-z][A-Za-z0-9-]*(?=[\s/>]))"
)
_REFERENCE_DEFINITION_PREFIX = re.compile(r"^\[[^\]\r\n]+\]:")
_LEADING_CLOSING_PUNCTUATION = re.compile(r"^([.,:;?!)]+)(.*)$")
_CELL_TAGS = frozenset({"table_header", "table_cell"})
_NESTED_TABLE_BLOCK_TAGS = frozenset(
    {"paragraph", "heading", "caption", "label", "list", "table", "figure"}
)
_SPAN_ATTRIBUTE_NAMES = frozenset({"rowspan", "colspan"})


class MarkdownDocumentWriter:
    def write(
        self,
        semantic_xml: Path,
        report: QualityReport,
        output: Path,
        *,
        source_name: str,
    ) -> None:
        markdown = self.render_text(
            semantic_xml,
            report,
            source_name=source_name,
        )
        self._write_atomic(output, markdown)

    @classmethod
    def render_text(
        cls,
        semantic_xml: Path,
        report: QualityReport,
        *,
        source_name: str,
    ) -> str:
        root = ET.parse(semantic_xml).getroot()
        promoted = cls._resolve_heading_candidates(root, report)

        header = [
            "# Semantic XML 문서 검토",
            "",
            f"- 원본 파일: {source_name}",
            "- 목적: PDF 태그 구조와 추출 텍스트 검토",
            "- 주의: 아래 제목은 검증된 표준 PDF 제목이 아니라 PDF 원본 역할 후보입니다.",
        ]
        blocks = cls._render_children(root, promoted)
        markdown = "\n".join(header)
        if blocks:
            markdown += "\n\n" + "\n\n".join(blocks)
        markdown += "\n"
        return markdown

    @classmethod
    def candidate_heading_lines(
        cls,
        semantic_xml: Path,
        report: QualityReport,
    ) -> Counter[str]:
        root = ET.parse(semantic_xml).getroot()
        promoted = cls._resolve_heading_candidates(root, report)
        rendered: Counter[str] = Counter()
        for element, entry in promoted.items():
            rendered.update(cls._render_element(element, {element: entry}))
        return rendered

    @classmethod
    def _resolve_heading_candidates(
        cls,
        root: ET.Element,
        report: QualityReport,
    ) -> dict[ET.Element, dict[str, object]]:
        path_index = cls._build_path_index(root)
        promoted: dict[ET.Element, dict[str, object]] = {}
        candidate_paths: set[str] = set()
        for entry in report.heading_hierarchy:
            if entry.get("classification") != "source_role_candidate":
                continue
            path = entry.get("structure_path")
            if isinstance(path, str) and path in candidate_paths:
                raise ValueError(f"duplicate heading candidate path {path}")
            if isinstance(path, str):
                for other_path in candidate_paths:
                    if path.startswith(f"{other_path}/"):
                        raise ValueError(
                            "overlapping heading candidate paths "
                            f"{other_path} and {path}"
                        )
                    if other_path.startswith(f"{path}/"):
                        raise ValueError(
                            "overlapping heading candidate paths "
                            f"{path} and {other_path}"
                        )
                candidate_paths.add(path)
            element = path_index.get(path) if isinstance(path, str) else None
            if element is None:
                raise ValueError(f"unresolved heading candidate path {path}")
            promoted[element] = entry
        return promoted

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

        atomic_tags = {"paragraph", "heading", "caption", "label", "figure"}
        if element.tag in atomic_tags and cls._has_mixed_content_descendant(
            element, promoted
        ):
            return cls._render_mixed_content(element, promoted)
        if element.tag in atomic_tags - {"figure"}:
            text = cls._element_text(element)
            return [cls._escape_line_prefix(text)] if text else []
        if element.tag == "text":
            text = cls._text_value(element)
            return [cls._escape_line_prefix(text)] if text else []
        if element.tag == "list":
            lines = cls._render_list(element, promoted, depth=0)
            return ["\n".join(lines)] if lines else []
        if element.tag == "table":
            return [cls._render_table(element, promoted)]
        if element.tag == "figure":
            text = cls._element_text(element)
            return [cls._escape_line_prefix(text) if text else "[그림: 텍스트 없음]"]
        return cls._render_children(element, promoted)

    @classmethod
    def _render_list(
        cls,
        element: ET.Element,
        promoted: dict[ET.Element, dict[str, object]],
        *,
        depth: int,
    ) -> list[str]:
        lines: list[str] = []
        text_parts: list[str] = []

        def flush_text() -> None:
            text = cls._join_text_parts(text_parts)
            if text:
                lines.append(cls._escape_line_prefix(text))
            text_parts.clear()

        for kind, value in cls._list_events(element, promoted):
            if kind == "text":
                text_parts.append(cls._visible_text(value))
            elif kind == "list_item":
                flush_text()
                lines.extend(cls._render_list_item(value, promoted, depth=depth))
            else:
                flush_text()
                lines.extend(cls._render_list_block(value, promoted, depth=depth + 1))
        flush_text()
        return lines

    @classmethod
    def _render_list_item(
        cls,
        item: ET.Element,
        promoted: dict[ET.Element, dict[str, object]],
        *,
        depth: int,
    ) -> list[str]:
        lines: list[str] = []
        text_parts: list[str] = []
        has_content = False
        marker_emitted = False

        def flush_text() -> None:
            nonlocal has_content, marker_emitted
            text = cls._join_text_parts(text_parts)
            if text:
                escaped = cls._escape_line_prefix(text)
                if marker_emitted:
                    lines.append(f"{'  ' * (depth + 1)}{escaped}")
                else:
                    lines.append(f"{'  ' * depth}- {escaped}")
                    marker_emitted = True
                has_content = True
            text_parts.clear()

        def ensure_marker() -> None:
            nonlocal has_content, marker_emitted
            if not marker_emitted:
                lines.append(f"{'  ' * depth}-")
                marker_emitted = True
                has_content = True

        for kind, value in cls._list_events(item, promoted):
            if kind == "text":
                text_parts.append(cls._visible_text(value))
            else:
                flush_text()
                ensure_marker()
                lines.extend(cls._render_list_block(value, promoted, depth=depth + 1))
                has_content = True
        flush_text()
        if not has_content:
            lines.append(f"{'  ' * depth}-")
        return lines

    @classmethod
    def _list_events(
        cls,
        element: ET.Element,
        promoted: dict[ET.Element, dict[str, object]],
    ) -> Iterable[tuple[str, ET.Element]]:
        for child in cls._structural_children(element):
            if child in promoted:
                yield "block", child
            elif child.tag == "list_item":
                yield "list_item", child
            elif child.tag in {"list", "table", "figure"}:
                yield "block", child
            elif child.tag == "text":
                yield "text", child
            else:
                yield from cls._list_events(child, promoted)

    @classmethod
    def _render_list_block(
        cls,
        element: ET.Element,
        promoted: dict[ET.Element, dict[str, object]],
        *,
        depth: int,
    ) -> list[str]:
        if element.tag == "list":
            return cls._render_list(element, promoted, depth=depth)
        indentation = "  " * depth
        return [
            f"{indentation}{line}"
            for block in cls._render_element(element, promoted)
            for line in block.splitlines()
        ]

    @classmethod
    def _render_table(
        cls,
        table: ET.Element,
        promoted: dict[ET.Element, dict[str, object]],
    ) -> str:
        if any(element in promoted for element in table.iter()):
            return cls._render_table_with_promotions(table, promoted)

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
        safe_pipe_table = (
            len(cells) >= 2
            and bool(cells[0])
            and len(rows) == len(table_children)
            and all(len(row_cells) == len(cells[0]) for row_cells in cells)
            and all(
                len(row_cells) == len(cls._structural_children(row))
                for row, row_cells in zip(rows, cells, strict=True)
            )
            and all(cell.tag == "table_header" for cell in cells[0])
            and all(
                cell.tag == "table_cell"
                for row_cells in cells[1:]
                for cell in row_cells
            )
            and all(cls._is_simple_table_cell(cell) for row_cells in cells for cell in row_cells)
        )
        if safe_pipe_table:
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

    @classmethod
    def _is_simple_table_cell(cls, cell: ET.Element) -> bool:
        if any(
            descendant is not cell and descendant.tag in _NESTED_TABLE_BLOCK_TAGS
            for descendant in cell.iter()
        ):
            return False

        spans: dict[str, list[str | None]] = {
            name: [] for name in _SPAN_ATTRIBUTE_NAMES
        }
        for attributes in cell.findall("attributes"):
            for attribute in attributes.findall("attribute"):
                name = attribute.get("name", "").lstrip("/").casefold()
                if name in spans:
                    spans[name].append(attribute.get("value"))
        return all(
            not values or (len(values) == 1 and values[0] is not None and values[0].strip() == "1")
            for values in spans.values()
        )

    @classmethod
    def _render_table_with_promotions(
        cls,
        table: ET.Element,
        promoted: dict[ET.Element, dict[str, object]],
    ) -> str:
        lines: list[str] = []
        row_index = 0
        for child in cls._structural_children(table):
            if child in promoted:
                lines.extend(
                    line
                    for block in cls._render_element(child, promoted)
                    for line in block.splitlines()
                )
                continue
            if child.tag == "table_row":
                row_index += 1
                prefix = f"- 행 {row_index}: "
            else:
                prefix = "- "
            lines.extend(cls._render_table_sequence(child, promoted, prefix=prefix))
        return "\n".join(lines)

    @classmethod
    def _render_table_sequence(
        cls,
        element: ET.Element,
        promoted: dict[ET.Element, dict[str, object]],
        *,
        prefix: str,
    ) -> list[str]:
        lines: list[str] = []
        text_parts: list[str] = []

        def flush_text() -> None:
            text = cls._join_text_parts(text_parts)
            if text:
                lines.append(f"{prefix}{text}")
            text_parts.clear()

        for kind, value in cls._mixed_content_events(element, promoted):
            if kind == "text":
                text_parts.append(cls._visible_text(value))
                continue
            flush_text()
            lines.extend(
                line
                for block in cls._render_element(value, promoted)
                for line in block.splitlines()
            )
        flush_text()
        return lines

    @classmethod
    def _mixed_content_events(
        cls,
        element: ET.Element,
        promoted: dict[ET.Element, dict[str, object]],
    ) -> Iterable[tuple[str, ET.Element]]:
        for child in cls._structural_children(element):
            if child in promoted or child.tag in {"list", "table", "figure"}:
                yield "block", child
            elif child.tag == "text":
                yield "text", child
            else:
                yield from cls._mixed_content_events(child, promoted)

    @staticmethod
    def _has_mixed_content_descendant(
        element: ET.Element,
        promoted: dict[ET.Element, dict[str, object]],
    ) -> bool:
        return any(
            descendant is not element
            and (
                descendant in promoted
                or descendant.tag in {"list", "table", "figure"}
            )
            for descendant in element.iter()
        )

    @classmethod
    def _render_mixed_content(
        cls,
        element: ET.Element,
        promoted: dict[ET.Element, dict[str, object]],
    ) -> list[str]:
        blocks: list[str] = []
        text_parts: list[str] = []
        deferred_empty_figures = 0

        def flush_text() -> None:
            text = cls._join_text_parts(text_parts)
            if text:
                blocks.append(cls._escape_line_prefix(text))
            text_parts.clear()

        def flush_deferred_figures() -> None:
            nonlocal deferred_empty_figures
            blocks.extend(
                "[그림: 텍스트 없음]" for _ in range(deferred_empty_figures)
            )
            deferred_empty_figures = 0

        for kind, value in cls._mixed_content_events(element, promoted):
            if kind == "text":
                text_parts.append(cls._visible_text(value))
                continue
            if value.tag == "figure" and cls._is_explicit_empty_text_figure(value):
                deferred_empty_figures += 1
                continue
            flush_text()
            flush_deferred_figures()
            blocks.extend(cls._render_element(value, promoted))
        flush_text()
        flush_deferred_figures()
        return blocks

    @classmethod
    def _is_explicit_empty_text_figure(cls, figure: ET.Element) -> bool:
        text_nodes = list(figure.iter("text"))
        return bool(text_nodes) and all(
            not cls._visible_text(text).strip() for text in text_nodes
        )

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
        for index in range(1, len(normalized)):
            previous = normalized[index - 1]
            if not previous[-1].isspace():
                continue
            match = _LEADING_CLOSING_PUNCTUATION.match(normalized[index].lstrip())
            if match is None:
                continue
            punctuation, remainder = match.groups()
            normalized[index - 1] = previous.rstrip()
            normalized[index] = (
                f"{punctuation} {remainder.lstrip()}" if remainder else f"{punctuation} "
            )
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
        if (
            _MARKDOWN_LINE_PREFIX.match(value)
            or _FENCED_CODE_PREFIX.match(value)
            or _THEMATIC_BREAK.match(value)
            or _RAW_HTML_BLOCK_PREFIX.match(value)
            or _REFERENCE_DEFINITION_PREFIX.match(value)
        ):
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
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    pass
