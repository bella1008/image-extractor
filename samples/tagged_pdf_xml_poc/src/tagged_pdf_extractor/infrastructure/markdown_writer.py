from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
import math
import os
import re
import tempfile
from pathlib import Path
from xml.etree import ElementTree as ET

from tagged_pdf_extractor.domain.models import QualityReport
from tagged_pdf_extractor.domain.readability_formatting import (
    sentence_start_offsets,
)
from tagged_pdf_extractor.domain.text_joining import join_text_parts
from tagged_pdf_extractor.infrastructure.xml_writer import decode_data_element


_WHITESPACE = re.compile(r"\s+")
_NATIVE_DECIMAL_MARKER = re.compile(r"^[0-9]{1,9}[.)]$")
_DECIMAL_SOURCE_LABEL = re.compile(r"^\d{1,9}[.)]$")
_PARENTHESIZED_NUMERIC_LABEL = re.compile(r"^\(\d{1,9}\)$")
_BARE_NUMERIC_LABEL = re.compile(r"^\d{1,9}$")
_ALPHABETIC_LABEL = re.compile(r"^[A-Za-z][.)]$")
_ROMAN_LABEL = re.compile(
    r"^(?=[MDCLXVI]+[.)]$)"
    r"M{0,3}(?:CM|CD|D?C{0,3})(?:XC|XL|L?X{0,3})"
    r"(?:IX|IV|V?I{0,3})[.)]$",
    re.IGNORECASE,
)
_MARKDOWN_LINE_PREFIX = re.compile(r"^(#{1,6}\s|>|[-+*]\s)")
_DECIMAL_LINE_PREFIX = re.compile(r"^([0-9]{1,9})([.)])(?=\s)")
_FENCED_CODE_PREFIX = re.compile(r"^(?:`{3,}|~{3,})")
_THEMATIC_BREAK = re.compile(r"^(?:(?:\*\s*){3,}|(?:-\s*){3,}|(?:_\s*){3,})$")
_RAW_HTML_BLOCK_PREFIX = re.compile(
    r"^<(?:!--|[!?]|/?[A-Za-z][A-Za-z0-9-]*(?=[\s/>]))"
)
_LEADING_CLOSING_PUNCTUATION = re.compile(r"^([.,:;?!)]+)(.*)$")
_CELL_TAGS = frozenset({"table_header", "table_cell"})
_NESTED_TABLE_BLOCK_TAGS = frozenset(
    {"paragraph", "heading", "caption", "label", "list", "table", "figure"}
)
_SPAN_ATTRIBUTE_NAMES = frozenset({"rowspan", "colspan"})
_PRESERVED_LINE_BREAK = "\x00preserved-markdown-line-break\x00"
_SENTENCE_BREAK = "\x00sentence-markdown-line-break\x00"
_SENTENCE_BREAK_OFFSETS = re.compile(
    r"(?:0|[1-9][0-9]*)(?:,(?:0|[1-9][0-9]*))*"
)
_SENTENCE_BREAK_ATTRIBUTE_NAMES = frozenset(
    {"sentence-break-offsets", "sentence-break-reason"}
)
_SENTENCE_BREAK_REASON = "conservative_sentence_terminal_in_review_container"
_INLINE_ICON_ATTRIBUTE_NAMES = frozenset(
    {
        "icon-reason",
        "reference-font-size",
        "width-font-ratio",
        "height-font-ratio",
    }
)
_INLINE_ICON_TOKEN = "[아이콘]"
_SENTENCE_INLINE_TAGS = frozenset({"span", "link"})
_SENTENCE_FLOW_CONTAINERS = frozenset({"list_body", "table_cell"})
_SENTENCE_FLOW_BARRIERS = frozenset(
    {"list", "table", "heading", "caption", "label", "figure"}
)
_SENTENCE_HEADING_DISPLAY_ROLES = frozenset(
    {"subtitle", "strong-label", "section-heading"}
)
_SENTENCE_SOURCE_BOUNDARY = object()
_SENTENCE_BLOCK_BOUNDARY = object()


@dataclass(frozen=True)
class _SemanticTextFragment:
    element: ET.Element
    text: str


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
        cls._validate_display_evidence(root, promoted)

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
        if _SENTENCE_BREAK in markdown:
            raise AssertionError("internal sentence sentinel leaked into Markdown")
        return markdown

    @classmethod
    def candidate_heading_lines(
        cls,
        semantic_xml: Path,
        report: QualityReport,
    ) -> Counter[str]:
        root = ET.parse(semantic_xml).getroot()
        promoted = cls._resolve_heading_candidates(root, report)
        cls._validate_display_evidence(root, promoted)
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
        display_role = element.get("display-role")
        if (
            element.tag == "paragraph"
            and display_role == "section-heading"
            and element.get("display-level") == "2"
        ):
            text = cls._element_text(element)
            return [f"## {text}"] if text else []
        if element.tag == "paragraph" and display_role == "strong-label":
            text = cls._element_text(element)
            return [f"**{cls._escape_emphasis_text(text)}**"] if text else []

        heading = promoted.get(element)
        if heading is not None:
            source_level = heading.get("level")
            if source_level is None:
                source_level = 1
            level = max(1, int(source_level))
            prefix = "#" * min(level + 1, 6)
            return [f"{prefix} {cls._element_text(element)}"]

        if element.tag == "heading" and cls._has_mixed_content_descendant(
            element, promoted
        ):
            return cls._render_mixed_heading(element, promoted)
        if element.tag == "heading":
            level = max(1, min(int(element.get("level", "1")), 6))
            text = cls._element_text(element)
            return [f"{'#' * level} {text}"] if text else []

        if (
            element.tag == "paragraph"
            and element.get("display-role") == "subtitle"
        ):
            text = cls._element_text(element)
            return [f"**{cls._escape_emphasis_text(text)}**"] if text else []

        atomic_tags = {"paragraph", "heading", "caption", "label", "figure"}
        if element.tag in atomic_tags and cls._has_mixed_content_descendant(
            element, promoted
        ):
            return cls._render_mixed_content(element, promoted)
        if element.tag in atomic_tags - {"figure"}:
            text = cls._element_text(element)
            return [cls._escape_physical_lines(text)] if text else []
        if element.tag == "text":
            text = cls._text_value(element)
            return [cls._escape_physical_lines(text)] if text else []
        if element.tag == "list":
            lines = cls._render_list(element, promoted, indent="")
            return ["\n".join(lines)] if lines else []
        if element.tag == "table":
            return [cls._render_table(element, promoted)]
        if element.tag == "figure":
            if cls._is_inline_icon(element):
                return [_INLINE_ICON_TOKEN]
            text = cls._element_text(element)
            return [cls._escape_physical_lines(text) if text else "[그림: 텍스트 없음]"]
        return cls._render_children(element, promoted)

    @staticmethod
    def _escape_emphasis_text(text: str) -> str:
        return text.replace("\\", r"\\").replace("*", r"\*").replace("_", r"\_")

    @classmethod
    def _render_list(
        cls,
        element: ET.Element,
        promoted: dict[ET.Element, dict[str, object]],
        *,
        indent: str,
    ) -> list[str]:
        lines: list[str] = []
        text_parts: list[str] = []

        def flush_text() -> None:
            text = cls._join_text_parts(text_parts)
            if text:
                lines.extend(
                    f"{indent}{line}"
                    for line in cls._escape_physical_lines(text).splitlines()
                )
            text_parts.clear()

        for kind, value in cls._list_events(element, promoted):
            if kind == "text":
                text_parts.append(cls._event_text_part(value))
            elif kind == "list_item":
                flush_text()
                lines.extend(cls._render_list_item(value, promoted, indent=indent))
            else:
                flush_text()
                lines.extend(
                    cls._render_list_block(value, promoted, indent=f"{indent}  ")
                )
        flush_text()
        return lines

    @classmethod
    def _render_list_item(
        cls,
        item: ET.Element,
        promoted: dict[ET.Element, dict[str, object]],
        *,
        indent: str,
    ) -> list[str]:
        lines: list[str] = []
        has_content = False
        marker_emitted = False
        direct_labels = tuple(
            child
            for child in cls._structural_children(item)
            if child.tag == "label"
        )
        marker, source_labels = cls._analyze_list_labels(direct_labels)
        content_labels = (
            source_labels[1:]
            if source_labels and marker == source_labels[0]
            else source_labels
        )
        text_parts = [f"{' '.join(content_labels)} "] if content_labels else []
        content_indent = f"{indent}{' ' * (len(marker) + 1)}"

        def flush_text() -> None:
            nonlocal has_content, marker_emitted
            text = cls._join_text_parts(text_parts)
            if text:
                escaped_lines = cls._escape_physical_lines(text).splitlines()
                if marker_emitted:
                    lines.extend(
                        f"{content_indent}{line}" for line in escaped_lines
                    )
                else:
                    lines.append(f"{indent}{marker} {escaped_lines[0]}")
                    lines.extend(
                        f"{content_indent}{line}"
                        for line in escaped_lines[1:]
                    )
                    marker_emitted = True
                has_content = True
            text_parts.clear()

        def ensure_marker() -> None:
            nonlocal has_content, marker_emitted
            if not marker_emitted:
                lines.append(f"{indent}{marker}")
                marker_emitted = True
                has_content = True

        for kind, value in cls._list_events(
            item, promoted, excluded=frozenset(direct_labels)
        ):
            if kind == "text":
                text_parts.append(cls._event_text_part(value))
            else:
                flush_text()
                ensure_marker()
                lines.extend(
                    cls._render_list_block(
                        value, promoted, indent=content_indent
                    )
                )
                has_content = True
        flush_text()
        if not has_content:
            lines.append(f"{indent}{marker}")
        return lines

    @classmethod
    def _list_events(
        cls,
        element: ET.Element,
        promoted: dict[ET.Element, dict[str, object]],
        *,
        excluded: frozenset[ET.Element] = frozenset(),
    ) -> Iterable[tuple[str, ET.Element]]:
        for child in cls._structural_children(element):
            if child in excluded:
                continue
            if child.tag == "figure" and cls._is_inline_icon(child):
                yield "text", child
            elif child in promoted:
                yield "block", child
            elif child.tag == "list_item":
                yield "list_item", child
            elif child.tag in {"heading", "list", "table", "figure"}:
                yield "block", child
            elif child.tag == "text" or cls._is_preserved_line_break(child):
                yield "text", child
            else:
                yield from cls._list_events(child, promoted, excluded=excluded)

    @classmethod
    def _list_marker(cls, label_text: str) -> str:
        normalized = cls._normalize_whitespace(label_text)
        ordered = any(
            pattern.fullmatch(normalized)
            for pattern in (
                _NATIVE_DECIMAL_MARKER,
                _DECIMAL_SOURCE_LABEL,
                _PARENTHESIZED_NUMERIC_LABEL,
                _BARE_NUMERIC_LABEL,
                _ALPHABETIC_LABEL,
                _ROMAN_LABEL,
            )
        )
        return normalized if ordered else "-"

    @classmethod
    def _analyze_list_labels(
        cls, labels: Iterable[ET.Element]
    ) -> tuple[str, tuple[str, ...]]:
        source_labels = tuple(
            marker
            for label in labels
            if (marker := cls._list_marker(cls._element_text(label))) != "-"
        )
        marker = (
            source_labels[0]
            if source_labels and _NATIVE_DECIMAL_MARKER.fullmatch(source_labels[0])
            else "-"
        )
        return marker, source_labels

    @classmethod
    def _render_list_block(
        cls,
        element: ET.Element,
        promoted: dict[ET.Element, dict[str, object]],
        *,
        indent: str,
    ) -> list[str]:
        if element.tag == "list":
            return cls._render_list(element, promoted, indent=indent)
        if element.tag == "heading":
            indent = ""
        return [
            f"{indent}{line}"
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
                    cls._element_text(cell)
                    .replace(_SENTENCE_BREAK, "<br>")
                    .replace("|", r"\|")
                    for cell in row_cells
                )
                + " |"
                for row_cells in cells
            ]
            separator = "| " + " | ".join("---" for _ in cells[0]) + " |"
            return "\n".join((rendered_rows[0], separator, *rendered_rows[1:]))

        return cls._render_complex_table(table_children, promoted)

    @classmethod
    def _render_complex_table(
        cls,
        table_children: list[ET.Element],
        promoted: dict[ET.Element, dict[str, object]],
    ) -> str:
        lines: list[str] = []
        row_index = 0
        for child in table_children:
            if child in promoted:
                cls._append_indented_blocks(
                    lines,
                    cls._render_element(child, promoted),
                    indent="",
                )
                continue
            if child.tag != "table_row":
                blocks = cls._render_element(child, promoted)
                cls._append_indented_blocks(lines, blocks, indent="- ")
                continue

            row_index += 1
            lines.append(f"- 행 {row_index}:")
            row_children = cls._structural_children(child)
            cells = [value for value in row_children if value.tag in _CELL_TAGS]
            if len(cells) <= 1:
                for value in row_children:
                    if value.tag in _CELL_TAGS:
                        cls._append_table_cell(
                            lines, value, promoted, indent="  "
                        )
                    else:
                        cls._append_indented_blocks(
                            lines,
                            cls._render_element(value, promoted),
                            indent="  ",
                        )
                continue

            cell_index = 0
            for value in row_children:
                if value.tag in _CELL_TAGS:
                    cell_index += 1
                    lines.append(f"  - 열 {cell_index}:")
                    cls._append_table_cell(
                        lines, value, promoted, indent="    "
                    )
                else:
                    cls._append_indented_blocks(
                        lines,
                        cls._render_element(value, promoted),
                        indent="  ",
                    )
        if not lines:
            lines.append("- 행 1:")
        return "\n".join(lines)

    @classmethod
    def _append_table_cell(
        cls,
        lines: list[str],
        cell: ET.Element,
        promoted: dict[ET.Element, dict[str, object]],
        *,
        indent: str,
    ) -> None:
        blocks = (
            cls._render_element(cell, promoted)
            if cell in promoted
            else cls._render_children(cell, promoted)
        )
        if not blocks:
            lines.append(f"{indent}[빈 셀]")
            return
        cls._append_indented_blocks(lines, blocks, indent=indent)

    @staticmethod
    def _append_indented_blocks(
        lines: list[str],
        blocks: list[str],
        *,
        indent: str,
    ) -> None:
        for block_index, block in enumerate(blocks):
            if block_index and lines and lines[-1] != "":
                lines.append("")
            block_lines = block.splitlines() or [""]
            lines.extend(f"{indent}{line}" if line else "" for line in block_lines)

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
        return cls._render_complex_table(cls._structural_children(table), promoted)

    @classmethod
    def _mixed_content_events(
        cls,
        element: ET.Element,
        promoted: dict[ET.Element, dict[str, object]],
    ) -> Iterable[tuple[str, ET.Element]]:
        for child in cls._structural_children(element):
            if child.tag == "figure" and cls._is_inline_icon(child):
                yield "text", child
            elif child in promoted or child.tag in {"list", "table", "figure"}:
                yield "block", child
            elif child.tag == "text" or cls._is_preserved_line_break(child):
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
                blocks.append(cls._escape_physical_lines(text))
            text_parts.clear()

        def flush_deferred_figures() -> None:
            nonlocal deferred_empty_figures
            blocks.extend(
                "[그림: 텍스트 없음]" for _ in range(deferred_empty_figures)
            )
            deferred_empty_figures = 0

        for kind, value in cls._mixed_content_events(element, promoted):
            if kind == "text":
                text_parts.append(cls._event_text_part(value))
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
    def _render_mixed_heading(
        cls,
        element: ET.Element,
        promoted: dict[ET.Element, dict[str, object]],
    ) -> list[str]:
        title_containers = cls._numbered_heading_title_containers(element)
        if title_containers is not None:
            return cls._render_numbered_mixed_heading(
                element, promoted, title_containers
            )

        blocks: list[str] = []
        text_parts: list[str] = []
        heading_emitted = False
        level = max(1, min(int(element.get("level", "1")), 6))

        def flush_text() -> None:
            nonlocal heading_emitted
            text = cls._join_text_parts(text_parts)
            if text:
                if heading_emitted:
                    blocks.append(cls._escape_physical_lines(text))
                else:
                    escaped_lines = cls._escape_physical_lines(text).splitlines()
                    blocks.append(
                        "\n".join(
                            (f"{'#' * level} {escaped_lines[0]}", *escaped_lines[1:])
                        )
                    )
                    heading_emitted = True
            text_parts.clear()

        for kind, value in cls._mixed_content_events(element, promoted):
            if kind == "text":
                text_parts.append(cls._event_text_part(value))
                continue
            flush_text()
            blocks.extend(cls._render_element(value, promoted))
        flush_text()
        return blocks

    @classmethod
    def _numbered_heading_title_containers(
        cls, element: ET.Element
    ) -> frozenset[ET.Element] | None:
        children = cls._structural_children(element)
        labels = [child for child in children if child.tag == "label"]
        bodies = [child for child in children if child.tag == "list_body"]
        if len(labels) != 1 or len(bodies) != 1:
            return None
        return frozenset((*labels, *bodies))

    @classmethod
    def _numbered_heading_events(
        cls,
        element: ET.Element,
        promoted: dict[ET.Element, dict[str, object]],
        title_containers: frozenset[ET.Element],
        *,
        title_text: bool = False,
    ) -> Iterable[tuple[str, ET.Element]]:
        for child in cls._structural_children(element):
            if child in promoted or child.tag in {"list", "table", "figure"}:
                yield "block", child
            elif child.tag == "text" or cls._is_preserved_line_break(child):
                yield "title_text" if title_text else "text", child
            else:
                yield from cls._numbered_heading_events(
                    child,
                    promoted,
                    title_containers,
                    title_text=title_text or child in title_containers,
                )

    @classmethod
    def _render_numbered_mixed_heading(
        cls,
        element: ET.Element,
        promoted: dict[ET.Element, dict[str, object]],
        title_containers: frozenset[ET.Element],
    ) -> list[str]:
        events = tuple(
            cls._numbered_heading_events(element, promoted, title_containers)
        )
        title = cls._join_text_parts(
            cls._event_text_part(value)
            for kind, value in events
            if kind == "title_text"
        )
        level = max(1, min(int(element.get("level", "1")), 6))
        blocks = [f"{'#' * level} {title}"] if title else []
        text_parts: list[str] = []

        def flush_text() -> None:
            text = cls._join_text_parts(text_parts)
            if text:
                blocks.append(cls._escape_physical_lines(text))
            text_parts.clear()

        for kind, value in events:
            if kind == "title_text":
                continue
            if kind == "text":
                text_parts.append(cls._event_text_part(value))
                continue
            flush_text()
            blocks.extend(cls._render_element(value, promoted))
        flush_text()
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
        return cls._join_text_parts(cls._element_text_parts(element))

    @classmethod
    def _element_text_parts(cls, element: ET.Element) -> Iterable[str]:
        if cls._is_preserved_line_break(element):
            yield _PRESERVED_LINE_BREAK
            return
        if cls._is_inline_icon(element):
            yield f" {_INLINE_ICON_TOKEN} "
            return
        if element.tag == "text":
            yield cls._text_with_sentence_breaks(element)
            return

        direct_labels = (
            tuple(
                child
                for child in cls._structural_children(element)
                if child.tag == "label"
            )
            if element.tag == "list_item"
            else ()
        )
        if direct_labels:
            _, source_labels = cls._analyze_list_labels(direct_labels)
            if source_labels:
                yield f"{' '.join(source_labels)} "

        excluded = frozenset(direct_labels)
        for child in cls._structural_children(element):
            if child in excluded:
                continue
            yield from cls._element_text_parts(child)

    @classmethod
    def _join_text_parts(cls, parts: Iterable[str]) -> str:
        normalized: list[str] = []
        for part in parts:
            if part == _PRESERVED_LINE_BREAK:
                normalized.append(part)
                continue
            chunks = part.split(_SENTENCE_BREAK)
            for index, chunk in enumerate(chunks):
                if chunk and chunk.strip():
                    normalized.append(_WHITESPACE.sub(" ", chunk))
                if index < len(chunks) - 1:
                    normalized.append(_SENTENCE_BREAK)

        source_break_normalized: list[str] = []
        for part in normalized:
            if part == _PRESERVED_LINE_BREAK:
                if (
                    source_break_normalized
                    and source_break_normalized[-1] == _SENTENCE_BREAK
                ):
                    source_break_normalized.pop()
                source_break_normalized.append(part)
                continue
            if (
                part == _SENTENCE_BREAK
                and source_break_normalized
                and source_break_normalized[-1] == _PRESERVED_LINE_BREAK
            ):
                continue
            source_break_normalized.append(part)
        normalized = source_break_normalized

        if _PRESERVED_LINE_BREAK in normalized:
            segments: list[list[str]] = [[]]
            for part in normalized:
                if part == _PRESERVED_LINE_BREAK:
                    segments.append([])
                else:
                    segments[-1].append(part)
            return "\n".join(
                cls._join_text_parts(segment) for segment in segments
            ).strip()
        if _SENTENCE_BREAK in normalized:
            segments = [[]]
            for part in normalized:
                if part == _SENTENCE_BREAK:
                    segments.append([])
                else:
                    segments[-1].append(part)
            return _SENTENCE_BREAK.join(
                cls._join_text_parts(segment) for segment in segments
            ).strip()
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
        return cls._join_text_parts((cls._text_with_sentence_breaks(element),))

    @classmethod
    def _event_text_part(cls, element: ET.Element) -> str:
        if cls._is_preserved_line_break(element):
            return _PRESERVED_LINE_BREAK
        if cls._is_inline_icon(element):
            return f" {_INLINE_ICON_TOKEN} "
        if element.tag == "text":
            return cls._text_with_sentence_breaks(element)
        return cls._visible_text(element)

    @staticmethod
    def _is_inline_icon(element: ET.Element) -> bool:
        return (
            element.tag == "figure"
            and element.get("display-role") == "inline-icon"
        )

    @classmethod
    def _text_with_sentence_breaks(cls, element: ET.Element) -> str:
        source = decode_data_element(element)
        if element.get("display-role") != "sentence-break-source":
            return cls._visible_source_text(source)
        offsets = cls._sentence_break_offsets(element, source)
        parts: list[str] = []
        previous = 0
        for offset in offsets:
            parts.append(cls._visible_source_text(source[previous:offset]))
            parts.append(_SENTENCE_BREAK)
            previous = offset
        parts.append(cls._visible_source_text(source[previous:]))
        return "".join(parts)

    @classmethod
    def _sentence_break_offsets(
        cls,
        element: ET.Element,
        source: str,
    ) -> tuple[int, ...]:
        value = element.get("sentence-break-offsets")
        if value is None:
            raise ValueError("missing sentence-break-offsets")
        if _SENTENCE_BREAK_OFFSETS.fullmatch(value) is None:
            raise ValueError("invalid sentence-break-offsets")
        offsets = tuple(int(item) for item in value.split(","))
        if offsets != tuple(sorted(set(offsets))):
            raise ValueError("sentence-break-offsets must be sorted unique integers")
        if any(offset >= len(source) for offset in offsets):
            raise ValueError("sentence-break-offset out of bounds")
        reason = element.get("sentence-break-reason")
        if reason is None or not reason.strip():
            raise ValueError("missing sentence-break-reason")
        if reason != _SENTENCE_BREAK_REASON:
            raise ValueError("invalid sentence-break-reason")
        return offsets

    @classmethod
    def _validate_display_evidence(
        cls,
        root: ET.Element,
        promoted: dict[ET.Element, dict[str, object]],
    ) -> None:
        sentence_offsets_by_element: dict[ET.Element, tuple[int, ...]] = {}
        for element in root.iter():
            display_role = element.get("display-role")
            has_sentence_attributes = any(
                name in element.attrib for name in _SENTENCE_BREAK_ATTRIBUTE_NAMES
            )
            if display_role == "sentence-break-source":
                if element.tag != "text":
                    raise ValueError("sentence-break-source must target text")
                sentence_offsets_by_element[element] = cls._sentence_break_offsets(
                    element,
                    decode_data_element(element),
                )
            elif has_sentence_attributes:
                raise ValueError(
                    "sentence-break attributes without sentence-break-source"
                )

            has_icon_attributes = any(
                name in element.attrib for name in _INLINE_ICON_ATTRIBUTE_NAMES
            )
            if display_role == "inline-icon":
                cls._validate_inline_icon_evidence(element)
            elif has_icon_attributes:
                raise ValueError(
                    "inline-icon attributes without inline-icon display role"
                )
        cls._validate_sentence_boundaries(
            root,
            sentence_offsets_by_element,
            promoted,
        )

    @classmethod
    def _validate_sentence_boundaries(
        cls,
        root: ET.Element,
        offsets_by_element: dict[ET.Element, tuple[int, ...]],
        promoted: dict[ET.Element, dict[str, object]],
    ) -> None:
        if not offsets_by_element:
            return
        cls._reject_sentence_heading_overlaps(
            root,
            offsets_by_element,
            promoted,
        )
        eligible_offsets = cls._eligible_sentence_offsets(root)
        for element, offsets in offsets_by_element.items():
            expected = eligible_offsets.get(element)
            if expected is None:
                raise ValueError("ineligible sentence-break-source structure")
            if any(offset not in expected for offset in offsets):
                raise ValueError(
                    "sentence-break offset is not an eligible sentence-start boundary"
                )

    @classmethod
    def _reject_sentence_heading_overlaps(
        cls,
        root: ET.Element,
        offsets_by_element: dict[ET.Element, tuple[int, ...]],
        promoted: dict[ET.Element, dict[str, object]],
    ) -> None:
        parents = {
            child: parent
            for parent in root.iter()
            for child in cls._structural_children(parent)
        }
        for element in offsets_by_element:
            ancestor: ET.Element | None = element
            while ancestor is not None:
                if ancestor in promoted:
                    raise ValueError(
                        "sentence-break-source overlaps report-promoted heading"
                    )
                if ancestor.tag == "heading":
                    raise ValueError("sentence-break-source overlaps source heading")
                display_role = ancestor.get("display-role")
                if display_role in _SENTENCE_HEADING_DISPLAY_ROLES:
                    raise ValueError(
                        "sentence-break-source overlaps "
                        f"{display_role} display role"
                    )
                ancestor = parents.get(ancestor)

    @classmethod
    def _eligible_sentence_offsets(
        cls,
        root: ET.Element,
    ) -> dict[ET.Element, frozenset[int]]:
        flows: list[tuple[_SemanticTextFragment, ...]] = []

        def visit(parent: ET.Element, ancestors: tuple[str, ...]) -> None:
            for child in cls._structural_children(parent):
                if child.tag == "list_body":
                    flows.extend(cls._direct_sentence_flows(child))
                if (
                    child.tag == "paragraph"
                    and cls._eligible_sentence_paragraph_context(ancestors)
                ):
                    flows.extend(cls._leaf_sentence_paragraph_flows(child))
                visit(child, (*ancestors, child.tag))

        visit(root, ())
        offsets: dict[ET.Element, set[int]] = {}
        for flow in flows:
            text, locations = cls._join_sentence_flow(flow)
            for fragment in flow:
                offsets.setdefault(fragment.element, set())
            for start in sentence_start_offsets(text):
                location = locations[start]
                if location is None:
                    continue
                element, local_offset = location
                offsets.setdefault(element, set()).add(local_offset)
        return {
            element: frozenset(values)
            for element, values in offsets.items()
        }

    @staticmethod
    def _eligible_sentence_paragraph_context(
        ancestors: tuple[str, ...],
    ) -> bool:
        for tag in reversed(ancestors):
            if tag in _SENTENCE_FLOW_CONTAINERS:
                return True
            if tag in _SENTENCE_FLOW_BARRIERS:
                return False
        return False

    @classmethod
    def _direct_sentence_flows(
        cls,
        container: ET.Element,
    ) -> tuple[tuple[_SemanticTextFragment, ...], ...]:
        return cls._sentence_segments(cls._sentence_inline_tokens(container))

    @classmethod
    def _leaf_sentence_paragraph_flows(
        cls,
        paragraph: ET.Element,
    ) -> tuple[tuple[_SemanticTextFragment, ...], ...]:
        tokens = cls._sentence_inline_tokens(paragraph)
        if _SENTENCE_BLOCK_BOUNDARY in tokens:
            return ()
        return cls._sentence_segments(tokens)

    @classmethod
    def _sentence_inline_tokens(
        cls,
        parent: ET.Element,
    ) -> tuple[_SemanticTextFragment | object, ...]:
        tokens: list[_SemanticTextFragment | object] = []
        for child in cls._structural_children(parent):
            if child.tag == "text":
                source = decode_data_element(child)
                if source:
                    tokens.append(_SemanticTextFragment(child, source))
            elif cls._is_preserved_line_break(child):
                tokens.append(_SENTENCE_SOURCE_BOUNDARY)
            elif child.tag in _SENTENCE_INLINE_TAGS:
                tokens.extend(cls._sentence_inline_tokens(child))
            else:
                tokens.append(_SENTENCE_BLOCK_BOUNDARY)
        return tuple(tokens)

    @staticmethod
    def _sentence_segments(
        tokens: tuple[_SemanticTextFragment | object, ...],
    ) -> tuple[tuple[_SemanticTextFragment, ...], ...]:
        segments: list[tuple[_SemanticTextFragment, ...]] = []
        current: list[_SemanticTextFragment] = []
        for token in tokens:
            if isinstance(token, _SemanticTextFragment):
                current.append(token)
            elif current:
                segments.append(tuple(current))
                current = []
        if current:
            segments.append(tuple(current))
        return tuple(segments)

    @staticmethod
    def _join_sentence_flow(
        fragments: tuple[_SemanticTextFragment, ...],
    ) -> tuple[str, tuple[tuple[ET.Element, int] | None, ...]]:
        characters: list[str] = []
        locations: list[tuple[ET.Element, int] | None] = []
        for fragment in fragments:
            if characters and fragment.text:
                _, decisions = join_text_parts(
                    (characters[-1], fragment.text[0])
                )
                if decisions[0]["action"] == "insert_space":
                    characters.append(" ")
                    locations.append(None)
            characters.extend(fragment.text)
            locations.extend(
                (fragment.element, offset)
                for offset in range(len(fragment.text))
            )
        return "".join(characters), tuple(locations)

    @staticmethod
    def _validate_inline_icon_evidence(element: ET.Element) -> None:
        if element.tag != "figure":
            raise ValueError("inline-icon must target figure")
        page_index = element.get("page-index")
        if (
            page_index is None
            or re.fullmatch(r"0|[1-9][0-9]*", page_index) is None
        ):
            raise ValueError("invalid inline-icon page-index")
        reason = element.get("icon-reason")
        if reason is None or not reason.strip():
            raise ValueError("missing inline-icon icon-reason")
        for name in (
            "reference-font-size",
            "width-font-ratio",
            "height-font-ratio",
        ):
            value = element.get(name)
            try:
                number = float(value) if value is not None else math.nan
            except ValueError as error:
                raise ValueError(f"invalid inline-icon {name}") from error
            if not math.isfinite(number) or number <= 0:
                raise ValueError(f"invalid inline-icon {name}")

    @staticmethod
    def _is_preserved_line_break(element: ET.Element) -> bool:
        return (
            element.tag in {"span", "link"}
            and element.get("display-role") == "preserved-line-break"
            and element.get("actual-text") == "\n"
        )

    @classmethod
    def _visible_text(cls, element: ET.Element) -> str:
        return cls._visible_source_text(decode_data_element(element))

    @classmethod
    def _visible_source_text(cls, decoded: str) -> str:
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

    @classmethod
    def _escape_line_prefix(cls, value: str) -> str:
        decimal = _DECIMAL_LINE_PREFIX.match(value)
        if decimal is not None:
            return (
                f"{decimal.group(1)}\\{decimal.group(2)}"
                f"{value[decimal.end():]}"
            )
        if (
            _MARKDOWN_LINE_PREFIX.match(value)
            or _FENCED_CODE_PREFIX.match(value)
            or _THEMATIC_BREAK.match(value)
            or _RAW_HTML_BLOCK_PREFIX.match(value)
            or cls._starts_reference_definition(value)
        ):
            return f"\\{value}"
        return value

    @classmethod
    def _escape_physical_lines(cls, value: str) -> str:
        value = value.replace(_SENTENCE_BREAK, "<br>\n")
        return "\n".join(
            cls._escape_line_prefix(line) for line in value.split("\n")
        )

    @staticmethod
    def _starts_reference_definition(value: str) -> bool:
        if not value.startswith("["):
            return False
        index = 1
        while index < len(value):
            character = value[index]
            if character in "\r\n":
                return False
            if character == "\\":
                index += 2
                continue
            if character == "]":
                return index > 1 and value[index + 1 : index + 2] == ":"
            index += 1
        return False

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
