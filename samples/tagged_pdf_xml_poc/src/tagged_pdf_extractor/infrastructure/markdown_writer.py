from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
import math
import html
import os
import re
import tempfile
from pathlib import Path
from xml.etree import ElementTree as ET

from tagged_pdf_extractor.domain.models import QualityReport
from tagged_pdf_extractor.domain.paragraph_eligibility import (
    is_sentence_break_eligible_paragraph,
    sentence_break_heading_conflict,
)
from tagged_pdf_extractor.domain.inline_icon_policy import (
    GENERIC_INLINE_ICON_REASON,
    NAVIGATION_ROUTE_INLINE_ICON_REASON,
    inline_icon_ratio_limits,
    navigation_text_evidence,
    parse_positive_finite_number,
    parse_unambiguous_bbox,
)
from tagged_pdf_extractor.domain.text_joining import join_text_parts
from tagged_pdf_extractor.infrastructure.xml_writer import decode_data_element


_WHITESPACE = re.compile(r"\s+")
_MODEL_WILDCARDS = re.compile(r"\b[A-Z][A-Z0-9]*\*+[A-Z0-9*]*")
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
_INLINE_SUBTITLE_OFFSET_ATTRIBUTES = frozenset(
    {"title-end-offset", "qualifier-start-offset"}
)
_INLINE_ICON_ATTRIBUTE_NAMES = frozenset(
    {
        "icon-reason",
        "reference-font-size",
        "width-font-ratio",
        "height-font-ratio",
        "route-separator-count",
        "route-parenthesized",
    }
)
_INLINE_ICON_UNIQUE_ATTRIBUTE_NAMES = _INLINE_ICON_ATTRIBUTE_NAMES - {
    "reference-font-size"
}
_CONTINUATION_REASON = "sibling_list_paragraph_list_geometry_typography"
_CONTINUATION_ATTRIBUTES = (
    "continuation-reason",
    "preceding-list-item-path",
    "preceding-list-body-path",
    "paragraph-bbox",
    "list-body-bbox",
    "left-delta",
    "vertical-gap",
    "reference-font-size",
    "continuation-source-role",
    "preceding-body-font-weight",
    "preceding-body-font-size",
    "preceding-body-observed-lines",
    "target-font-weight",
    "target-font-size",
    "target-observed-lines",
)
_CONTINUATION_ATTRIBUTE_NAMES = frozenset(_CONTINUATION_ATTRIBUTES)
_CONTINUATION_UNIQUE_ATTRIBUTE_NAMES = _CONTINUATION_ATTRIBUTE_NAMES - {
    "reference-font-size"
}
_CONTINUATION_PATH = re.compile(r"(?:0|[1-9][0-9]*)(?:/(?:0|[1-9][0-9]*))*")
_CONTINUATION_LINES = re.compile(
    r"(?:0|[1-9][0-9]*):(?:0|[1-9][0-9]*)(?:,(?:0|[1-9][0-9]*):(?:0|[1-9][0-9]*))*"
)
_INLINE_ICON_TOKEN = "[아이콘]"
_SEMANTIC_NOTE_MARKERS = frozenset({"※"})
_SENTENCE_INLINE_TAGS = frozenset({"span", "link"})
_SENTENCE_SOURCE_BOUNDARY = object()
_SENTENCE_BLOCK_BOUNDARY = object()


@dataclass(frozen=True)
class _SemanticTextFragment:
    element: ET.Element
    text: str


@dataclass(frozen=True)
class _SemanticInlineFigure:
    element: ET.Element


@dataclass(frozen=True)
class _SemanticInlineText:
    element: ET.Element
    text: str


@dataclass(frozen=True)
class _SemanticInlineIconEvidence:
    reason: str
    page_index: int
    bbox: tuple[float, float, float, float]
    reference_font_size: float
    width_ratio: float
    height_ratio: float
    route_separator_count: int | None = None
    route_parenthesized: bool | None = None


@dataclass(frozen=True)
class _ListLabelAnalysis:
    ordered_marker: str | None
    note_marker: str | None
    retained_content_labels: tuple[str, ...]


class _TrustedInlineHtml(str):
    """HTML emitted only after validating an explicit semantic inline marker."""


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
            if child.get("display-role") == "list-continuation":
                text = cls._element_text(child)
                if text:
                    if not blocks:
                        raise ValueError(
                            "list-continuation has no preceding list block"
                        )
                    content_indent = cls._continuation_content_indent(
                        parent, child
                    )
                    continuation = "\n".join(
                        f"{content_indent}{line}"
                        for line in cls._escape_physical_lines(text).splitlines()
                    )
                    blocks[-1] = f"{blocks[-1]}\n\n{continuation}"
                continue
            blocks.extend(cls._render_element(child, promoted))
        return blocks

    @classmethod
    def _render_element(
        cls,
        element: ET.Element,
        promoted: dict[ET.Element, dict[str, object]],
    ) -> list[str]:
        if element.get("display-direction") is not None or element.get("direction-reason") is not None:
            if (element.tag != "paragraph" or element.get("language") != "ARA"
                    or element.get("display-direction") != "rtl"
                    or element.get("direction-reason") != "source-glyph-numeric-condition"
                    or not element.get("source-structure-path")
                    or any(c.tag != "text" and not cls._has_source_space_marker(c)
                           for c in cls._structural_children(element))):
                raise ValueError("Invalid source numeric-condition direction")
            from tagged_pdf_extractor.domain.africa_rtl_conditions import is_rtl_numeric_condition
            text = cls._element_text(element)
            if not is_rtl_numeric_condition(text):
                raise ValueError("Invalid RTL numeric-condition text")
            literal = html.escape(text, quote=False).replace("*", "&#42;")
            return [f'<span dir="rtl">{literal}</span>']
        display_role = element.get("display-role")
        if (
            element.tag == "paragraph"
            and display_role == "section-heading"
            and element.get("display-level") == "2"
        ):
            text = cls._element_text(element)
            return [f"## {cls._escape_model_wildcards(text)}"] if text else []
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
            return [f"{prefix} {cls._escape_model_wildcards(cls._element_text(element))}"]

        if (element.tag == "heading" and element.get("numbered-label") is not None
                and element.get("promotion-reason") is not None):
            level = max(1, min(int(element.get("level", "1")), 6))
            compact_label = element.get("numbered-label")
            if compact_label is not None:
                children = cls._structural_children(element)
                labels = [c for c in children if c.tag == "label"]
                bodies = [c for c in children if c.tag == "list_body"]
                if (element.get("promotion-reason") != "numbered_chapter_structure_sequence_typography"
                        or len(labels) != 1 or len(bodies) != 1 or len(children) != 2
                        or re.fullmatch(r"0[1-9]", compact_label) is None
                        or "".join(cls._element_text(labels[0]).split()) != compact_label):
                    raise ValueError(f"Invalid numbered-label source evidence: {compact_label!r}; "
                                     f"{[(c.tag, cls._element_text(c)) for c in children]!r}")
                text = compact_label + " " + cls._element_text(bodies[0])
            return [f"{'#' * level} {cls._escape_model_wildcards(text)}"] if text else []

        if element.tag == "heading" and cls._has_mixed_content_descendant(
            element, promoted
        ):
            return cls._render_mixed_heading(element, promoted)
        if element.tag == "heading":
            level = max(1, min(int(element.get("level", "1")), 6))
            text = cls._element_text(element)
            return [f"{'#' * level} {cls._escape_model_wildcards(text)}"] if text else []

        if (
            element.tag == "paragraph"
            and element.get("display-role") == "subtitle"
        ):
            if any(
                name in element.attrib
                for name in _INLINE_SUBTITLE_OFFSET_ATTRIBUTES
            ):
                source, title_end, qualifier_start = cls._inline_subtitle_source(
                    element
                )
                title = cls._join_text_parts((source[:title_end],))
                qualifier = cls._join_text_parts((source[qualifier_start:],))
                return [
                    cls._escape_physical_lines(
                        f"**{cls._escape_emphasis_text(title)}**"
                        f"{_SENTENCE_BREAK}{cls._escape_model_wildcards(qualifier)}",
                        model_literals=False,
                    )
                ]
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
    def _escape_model_wildcards(text: str) -> str:
        # Source model placeholders must remain visible in CommonMark viewers.
        # This is output escaping, not a model/heading inference or PDF rewrite.
        return _MODEL_WILDCARDS.sub(
            lambda match: match.group().replace("*", r"\*"), text
        )

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
                    for line in cls._escape_event_parts(text_parts).splitlines()
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
        label_analysis = cls._analyze_list_labels(direct_labels)
        marker = cls._list_item_marker(label_analysis)
        content_labels = label_analysis.retained_content_labels
        text_parts = [f"{' '.join(content_labels)} "] if content_labels else []
        content_indent = f"{indent}{' ' * (len(marker) + 1)}"

        def flush_text() -> None:
            nonlocal has_content, marker_emitted
            text = cls._join_text_parts(text_parts)
            if text:
                escaped_lines = cls._escape_event_parts(text_parts).splitlines()
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

    @staticmethod
    def _list_item_marker(label_analysis: _ListLabelAnalysis) -> str:
        return (
            label_analysis.ordered_marker
            or label_analysis.note_marker
            or "-"
        )

    @classmethod
    def _continuation_content_indent(
        cls,
        parent: ET.Element,
        continuation: ET.Element,
    ) -> str:
        siblings = cls._structural_children(parent)
        index = siblings.index(continuation) - 1
        while index >= 0 and cls._is_ignorable_text_fragment(siblings[index]):
            index -= 1
        if index < 0 or siblings[index].tag != "list":
            raise ValueError("list-continuation predecessor is not preceding list")
        list_children = cls._structural_children(siblings[index])
        item_index = cls._final_meaningful_child_index(list_children)
        if item_index is None or list_children[item_index].tag != "list_item":
            raise ValueError("list-continuation predecessor path is not list_item")
        item = list_children[item_index]
        direct_labels = tuple(
            child
            for child in cls._structural_children(item)
            if child.tag == "label"
        )
        marker = cls._list_item_marker(cls._analyze_list_labels(direct_labels))
        return " " * (len(marker) + 1)

    @staticmethod
    def _is_ignorable_text_fragment(element: ET.Element) -> bool:
        return element.tag == "text" and not decode_data_element(element).strip()

    @classmethod
    def _final_meaningful_child_index(
        cls, children: list[ET.Element]
    ) -> int | None:
        index = len(children) - 1
        while index >= 0 and cls._is_ignorable_text_fragment(children[index]):
            index -= 1
        return index if index >= 0 else None

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
            if cls._has_ltr_model_marker(child) or cls._has_source_space_marker(child):
                yield "text", child
            elif child.tag == "figure" and cls._is_inline_icon(child):
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
    ) -> _ListLabelAnalysis:
        direct_labels = tuple(labels)
        retained_source_labels: list[str] = []
        has_note_marker = False
        for label in direct_labels:
            source_label = cls._normalize_whitespace(cls._element_text(label))
            if source_label in _SEMANTIC_NOTE_MARKERS:
                retained_source_labels.append(source_label)
                has_note_marker = True
                continue
            ordered_label = cls._list_marker(source_label)
            if ordered_label != "-":
                retained_source_labels.append(ordered_label)

        if (
            len(direct_labels) == 1
            and len(retained_source_labels) == 1
            and retained_source_labels[0] in _SEMANTIC_NOTE_MARKERS
        ):
            return _ListLabelAnalysis(
                ordered_marker=None,
                note_marker=retained_source_labels[0],
                retained_content_labels=(),
            )

        if has_note_marker:
            return _ListLabelAnalysis(
                ordered_marker=None,
                note_marker=None,
                retained_content_labels=tuple(retained_source_labels),
            )

        source_labels = tuple(retained_source_labels)
        ordered_marker = (
            source_labels[0]
            if source_labels and _NATIVE_DECIMAL_MARKER.fullmatch(source_labels[0])
            else None
        )
        content_labels = source_labels[1:] if ordered_marker else source_labels
        return _ListLabelAnalysis(
            ordered_marker=ordered_marker,
            note_marker=None,
            retained_content_labels=content_labels,
        )

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
        if any(a.get('name') == 'review-table' and a.get('value') == 'source-spans'
               for a in table.findall('attributes/attribute')):
            return cls._render_source_spans_table(table)
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
                    cls._escape_model_wildcards(cls._element_text(cell))
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
    def _render_source_spans_table(cls, table: ET.Element) -> str:
        """HTML in Markdown retains explicitly reviewed PDF merged-cell geometry."""
        allowed={'table','table_row','table_cell','table_header','paragraph','span','link','text','attributes','attribute'}
        if any(n.tag not in allowed for n in table.iter()):
            raise ValueError('source-spans table contains unreviewed nested structure')
        lines=['<table>']
        for row in cls._structural_children(table):
            if row.tag!='table_row':raise ValueError('source-spans requires rows')
            lines.append('<tr>')
            for cell in cls._structural_children(row):
                if cell.tag not in _CELL_TAGS:raise ValueError('source-spans requires cells')
                attrs=[]
                for a in cell.findall('attributes/attribute'):
                    name=a.get('name','').lstrip('/').lower()
                    if name in {'rowspan','colspan'}:
                        value=a.get('value','')
                        if not value.isdigit() or not 1<=int(value)<=1000:raise ValueError('invalid source table span')
                        attrs.append(f' {name}="{int(value)}"')
                value=html.escape(cls._element_text(cell)).replace(_SENTENCE_BREAK,'<br>')
                tag='th' if cell.tag=='table_header' else 'td'
                lines.append(f'<{tag}{"".join(attrs)}>{value}</{tag}>')
            lines.append('</tr>')
        return '\n'.join((*lines,'</table>'))

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
            if cls._has_ltr_model_marker(child) or cls._has_source_space_marker(child):
                yield "text", child
            elif child.tag == "figure" and cls._is_inline_icon(child):
                yield "text", child
            elif child in promoted or child.tag in {"list", "table", "figure"}:
                yield "block", child
            elif child.tag == "text" or cls._is_preserved_line_break(child):
                yield "text", child
            else:
                yield from cls._mixed_content_events(child, promoted)

    @classmethod
    def _has_mixed_content_descendant(
        cls,
        element: ET.Element,
        promoted: dict[ET.Element, dict[str, object]],
    ) -> bool:
        return any(
            descendant is not element
            and (
                descendant in promoted
                or descendant.tag in {"list", "table", "figure"}
                or cls._has_ltr_model_marker(descendant)
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
                blocks.append(cls._escape_event_parts(text_parts))
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
                    blocks.append(cls._escape_event_parts(text_parts))
                else:
                    escaped_lines = cls._escape_event_parts(text_parts).splitlines()
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
        blocks = [f"{'#' * level} {cls._escape_model_wildcards(title)}"] if title else []
        text_parts: list[str] = []

        def flush_text() -> None:
            text = cls._join_text_parts(text_parts)
            if text:
                blocks.append(cls._escape_event_parts(text_parts))
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
        if cls._has_source_space_marker(element):
            yield cls._source_space_text(element)
            return
        if cls._is_preserved_line_break(element):
            yield _PRESERVED_LINE_BREAK
            return
        if cls._is_inline_icon(element):
            yield f" {_INLINE_ICON_TOKEN} "
            return
        if element.tag == "text":
            if element.get('join-previous') == 'source-token':
                yield '\x00JOIN_PREVIOUS\x00'
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
            analysis = cls._analyze_list_labels(direct_labels)
            source_labels = tuple(
                label
                for label in (
                    analysis.ordered_marker,
                    analysis.note_marker,
                    *analysis.retained_content_labels,
                )
                if label is not None
            )
            if source_labels:
                yield f"{' '.join(source_labels)} "

        excluded = frozenset(direct_labels)
        for child in cls._structural_children(element):
            if child in excluded:
                continue
            yield from cls._element_text_parts(child)

    @classmethod
    def _join_text_parts(cls, parts: Iterable[str]) -> str:
        source_parts_list = []
        join_previous = False
        for part in parts:
            if part.startswith('\x00JOIN_PREVIOUS\x00'):
                join_previous = True
                part = part.removeprefix('\x00JOIN_PREVIOUS\x00')
                if not part:
                    continue
            if join_previous and source_parts_list:
                source_parts_list[-1] = source_parts_list[-1].rstrip() + part.lstrip()
            else:
                source_parts_list.append(part)
            join_previous = False
        source_parts = tuple(source_parts_list)
        normalized: list[str] = []
        for source_index, part in enumerate(source_parts):
            if part == _PRESERVED_LINE_BREAK:
                normalized.append(part)
                continue
            if (
                part
                and not part.strip()
                and cls._whitespace_fragment_touches_note_marker(
                    source_parts,
                    source_index,
                )
            ):
                normalized.append(" ")
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

    @staticmethod
    def _whitespace_fragment_touches_note_marker(
        parts: tuple[str, ...],
        index: int,
    ) -> bool:
        previous = parts[index - 1].rstrip() if index > 0 else ""
        following = parts[index + 1].lstrip() if index + 1 < len(parts) else ""
        return any(
            previous.endswith(marker) or following.startswith(marker)
            for marker in _SEMANTIC_NOTE_MARKERS
        )

    @classmethod
    def _text_value(cls, element: ET.Element) -> str:
        return cls._join_text_parts((cls._text_with_sentence_breaks(element),))

    @classmethod
    def _event_text_part(cls, element: ET.Element) -> str:
        if cls._has_source_space_marker(element):
            return cls._source_space_text(element)
        if cls._has_ltr_model_marker(element):
            return cls._ltr_model_event(element)
        if cls._is_preserved_line_break(element):
            return _PRESERVED_LINE_BREAK
        if cls._is_inline_icon(element):
            return f" {_INLINE_ICON_TOKEN} "
        if element.tag == "text":
            prefix = '\x00JOIN_PREVIOUS\x00' if element.get('join-previous') == 'source-token' else ''
            return prefix + cls._text_with_sentence_breaks(element)
        return cls._visible_text(element)

    @staticmethod
    def _has_source_space_marker(element: ET.Element) -> bool:
        return any(a.get('name') in {'review-whitespace', 'review-whitespace-source-token',
                   'review-whitespace-source-sha256'} for a in element.findall('attributes/attribute'))

    @classmethod
    def _source_space_text(cls, element: ET.Element) -> str:
        from tagged_pdf_extractor.domain.tk_arabic_source import VERIFIED_SOURCE_SHA256, VERIFIED_SPACE_BOUNDARIES
        expected = {'review-whitespace': 'source-boundary', 'review-whitespace-source-token': 'TK_ARA',
                    'review-whitespace-source-sha256': VERIFIED_SOURCE_SHA256}
        attrs = element.findall('attributes/attribute')
        children = cls._structural_children(element)
        scope = next((v for v in VERIFIED_SPACE_BOUNDARIES.values()
                      if '/'.join(map(str, v[0])) == element.get('source-structure-path')), None)
        if (element.tag != 'span' or element.get('language') != 'ARA' or element.get('page-index') != '1'
                or scope is None or len(attrs) != len(expected)
                or {a.get('name'): a.get('value') for a in attrs} != expected
                or len(children) != 3 or any(c.tag != 'text' or len(c) for c in children)
                or [(c.get('page-index'), c.get('mcid')) for c in children]
                    != [('1', str(mcid)) for mcid in scope[1:]]):
            raise ValueError('Invalid reviewed source-space boundary')
        previous, space, following = (cls._text_with_sentence_breaks(c) for c in children)
        if not previous.strip() or not following.strip() or space != ' ':
            raise ValueError('Invalid reviewed source-space text')
        return previous + space + following

    @staticmethod
    def _has_ltr_model_marker(element: ET.Element) -> bool:
        return any(a.get('name') in {'review-inline','review-source-token','review-source-sha256'}
                   for a in element.findall('attributes/attribute'))

    @classmethod
    def _ltr_model_event(cls, element: ET.Element) -> str:
        from tagged_pdf_extractor.domain.tk_arabic_source import VERIFIED_SOURCE_SHA256
        expected={'review-inline':'ltr-model-token','review-source-token':'TK_ARA',
                  'review-source-sha256':VERIFIED_SOURCE_SHA256}
        attributes=element.findall('attributes/attribute')
        children=cls._structural_children(element)
        if (element.tag!='span' or element.get('language')!='ARA'
                or element.get('page-index')!='1'
                or element.get('source-structure-path')!='0/0/1/72/0/1'
                or len(attributes)!=len(expected)
                or {a.get('name'):a.get('value') for a in attributes}!=expected
                or len(children)!=2 or any(c.tag!='text' or len(c) for c in children)
                or [(c.get('page-index'),c.get('mcid')) for c in children]!=[('1','770'),('1','771')]):
            raise ValueError('Invalid source-owned LTR model marker')
        token, wildcard = [decode_data_element(c) for c in children]
        if (re.fullmatch(r'[A-Z][A-Z0-9]+',token) is None or wildcard!='*'
                or children[1].get('join-previous')!='source-token'):
            raise ValueError('Invalid source-owned LTR model text')
        return _TrustedInlineHtml('<bdi dir="ltr">'+html.escape(token+wildcard).replace('*','&#42;')+'</bdi>')

    @classmethod
    def _escape_event_parts(cls, parts: Iterable[str]) -> str:
        parts = tuple(parts)
        if not any(isinstance(part, _TrustedInlineHtml) for part in parts):
            return cls._escape_physical_lines(cls._join_text_parts(parts))
        # Protect only generated HTML from line-prefix escaping. Pick a marker
        # absent from every source part, so source text cannot impersonate it.
        marker = '\x00trusted-inline\x00'
        while any(marker in part for part in parts):
            marker += '\x00'
        protected = (
            marker + part if isinstance(part, _TrustedInlineHtml) else part
            for part in parts
        )
        return cls._escape_physical_lines(cls._join_text_parts(protected)).replace(marker, '')

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
        inline_icons: dict[ET.Element, _SemanticInlineIconEvidence] = {}
        continuation_elements: list[ET.Element] = []
        for element in root.iter():
            display_role = element.get("display-role")
            has_inline_subtitle_offsets = any(
                name in element.attrib
                for name in _INLINE_SUBTITLE_OFFSET_ATTRIBUTES
            )
            if display_role == "subtitle" and has_inline_subtitle_offsets:
                cls._inline_subtitle_source(element)
            elif has_inline_subtitle_offsets:
                raise ValueError(
                    "inline subtitle offsets without subtitle display role"
                )
            has_continuation_attributes = any(
                name in element.attrib
                for name in _CONTINUATION_UNIQUE_ATTRIBUTE_NAMES
            )
            if display_role == "list-continuation":
                cls._validate_continuation_evidence(element)
                continuation_elements.append(element)
            elif has_continuation_attributes:
                raise ValueError(
                    "continuation attributes without list-continuation"
                )
            has_sentence_attributes = any(
                name in element.attrib for name in _SENTENCE_BREAK_ATTRIBUTE_NAMES
            )
            if display_role == "list-continuation" and has_sentence_attributes:
                raise ValueError(
                    "sentence-break evidence overlaps list-continuation"
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
                inline_icons[element] = cls._validate_inline_icon_evidence(element)
            elif display_role == "list-continuation" and any(
                name in element.attrib
                for name in _INLINE_ICON_UNIQUE_ATTRIBUTE_NAMES
            ):
                raise ValueError(
                    "inline-icon attributes overlap list-continuation"
                )
            elif has_icon_attributes and display_role != "list-continuation":
                raise ValueError(
                    "inline-icon attributes without inline-icon display role"
                )
        cls._reject_sentence_continuation_overlaps(
            sentence_offsets_by_element,
            continuation_elements,
        )
        cls._validate_sentence_boundaries(
            root,
            sentence_offsets_by_element,
            promoted,
        )
        cls._validate_inline_icon_structures(root, inline_icons)
        cls._validate_continuation_structures(root, continuation_elements)

    @classmethod
    def _inline_subtitle_source(
        cls, element: ET.Element
    ) -> tuple[str, int, int]:
        if element.tag != "paragraph":
            raise ValueError("inline subtitle must target paragraph")
        values = tuple(
            element.get(name)
            for name in ("title-end-offset", "qualifier-start-offset")
        )
        if any(
            value is None or re.fullmatch(r"0|[1-9][0-9]*", value) is None
            for value in values
        ):
            raise ValueError("invalid inline subtitle offsets")
        title_end, qualifier_start = (
            int(value) for value in values if value is not None
        )
        parts: list[str] = []
        boundaries = 0

        def visit(parent: ET.Element) -> None:
            nonlocal boundaries
            for child in cls._structural_children(parent):
                if child.tag == "text":
                    if child.get("display-role") is not None:
                        raise ValueError("inline subtitle display role conflict")
                    parts.append(decode_data_element(child))
                elif child.tag in _SENTENCE_INLINE_TAGS:
                    actual_text = child.get("actual-text")
                    if child.get("display-role") is not None:
                        raise ValueError("inline subtitle display role conflict")
                    if actual_text is not None:
                        parts.append(actual_text)
                        if actual_text == "\n":
                            boundaries += 1
                    else:
                        visit(child)
                else:
                    raise ValueError("inline subtitle role conflict")

        visit(element)
        source = "".join(parts)
        if boundaries != 1:
            raise ValueError("inline subtitle source boundary is invalid")
        if (
            qualifier_start != title_end + 1
            or title_end <= 0
            or qualifier_start >= len(source)
            or source[title_end:qualifier_start] != "\n"
            or not source[:title_end].strip()
            or not source[qualifier_start:].strip()
        ):
            raise ValueError("invalid inline subtitle offsets")
        return source, title_end, qualifier_start

    @staticmethod
    def _reject_sentence_continuation_overlaps(
        sentence_offsets_by_element: dict[ET.Element, tuple[int, ...]],
        continuation_elements: list[ET.Element],
    ) -> None:
        sentence_elements = set(sentence_offsets_by_element)
        if any(
            sentence_elements.intersection(continuation.iter())
            for continuation in continuation_elements
        ):
            raise ValueError(
                "sentence-break-source overlaps list-continuation"
            )

    @classmethod
    def _validate_continuation_evidence(cls, element: ET.Element) -> None:
        if element.tag != "paragraph":
            raise ValueError("list-continuation must target paragraph")
        for name in _CONTINUATION_ATTRIBUTES:
            if element.get(name) is None:
                raise ValueError(f"missing continuation {name}")
        if element.get("continuation-reason") != _CONTINUATION_REASON:
            raise ValueError("invalid continuation reason")
        for name in ("preceding-list-item-path", "preceding-list-body-path"):
            value = element.get(name)
            if value is None or _CONTINUATION_PATH.fullmatch(value) is None:
                raise ValueError(f"invalid continuation {name}")
        page_index = element.get("page-index")
        if page_index is None or re.fullmatch(r"0|[1-9][0-9]*", page_index) is None:
            raise ValueError("invalid continuation page-index")
        boxes: dict[str, tuple[float, float, float, float]] = {}
        for name in ("paragraph-bbox", "list-body-bbox"):
            value = element.get(name)
            try:
                parts = tuple(float(part) for part in (value or "").split(","))
            except ValueError as exc:
                raise ValueError(f"invalid continuation {name}") from exc
            if (
                len(parts) != 4
                or any(not math.isfinite(number) for number in parts)
                or parts[2] <= parts[0]
                or parts[3] <= parts[1]
            ):
                raise ValueError(f"invalid continuation {name}")
            boxes[name] = parts
        numbers: dict[str, float] = {}
        for name in (
            "left-delta",
            "vertical-gap",
            "reference-font-size",
            "preceding-body-font-size",
            "target-font-size",
        ):
            try:
                number = float(element.get(name, ""))
            except ValueError as exc:
                raise ValueError(f"invalid continuation {name}") from exc
            if not math.isfinite(number) or (
                name not in {"left-delta", "vertical-gap"} and number <= 0
            ):
                raise ValueError(f"invalid continuation {name}")
            numbers[name] = number
        for name in ("preceding-body-font-weight", "target-font-weight"):
            value = element.get(name)
            if value is None or re.fullmatch(r"[1-9][0-9]*", value) is None:
                raise ValueError(f"invalid continuation {name}")
        for name in (
            "preceding-body-observed-lines",
            "target-observed-lines",
        ):
            value = element.get(name)
            if value is None or _CONTINUATION_LINES.fullmatch(value) is None:
                raise ValueError(f"invalid continuation {name}")
            if any(item.split(":", 1)[0] != page_index for item in value.split(",")):
                raise ValueError(f"cross-page continuation {name}")
        if not element.get("continuation-source-role", "").strip():
            raise ValueError("invalid continuation continuation-source-role")
        if not math.isclose(
            boxes["paragraph-bbox"][0] - boxes["list-body-bbox"][0],
            numbers["left-delta"],
            abs_tol=5e-7,
        ):
            raise ValueError("continuation left-delta does not match BBoxes")
        if not math.isclose(
            boxes["list-body-bbox"][1] - boxes["paragraph-bbox"][3],
            numbers["vertical-gap"],
            abs_tol=5e-7,
        ):
            raise ValueError("continuation vertical-gap does not match BBoxes")
        if not (
            numbers["reference-font-size"]
            == numbers["preceding-body-font-size"]
            == numbers["target-font-size"]
            and element.get("preceding-body-font-weight")
            == element.get("target-font-weight")
        ):
            raise ValueError("continuation typography evidence mismatch")

    @classmethod
    def _validate_continuation_structures(
        cls, root: ET.Element, continuations: list[ET.Element]
    ) -> None:
        if not continuations:
            return
        indexed: dict[tuple[int, ...], ET.Element] = {}

        def visit(parent: ET.Element, parent_path: tuple[int, ...]) -> None:
            for index, child in enumerate(cls._structural_children(parent)):
                path = (*parent_path, index)
                indexed[path] = child
                visit(child, path)

        visit(root, ())
        target_paths = {element: path for path, element in indexed.items()}
        for element in continuations:
            target_path = target_paths[element]
            item_path = tuple(
                int(part)
                for part in element.attrib["preceding-list-item-path"].split("/")
            )
            body_path = tuple(
                int(part)
                for part in element.attrib["preceding-list-body-path"].split("/")
            )
            item = indexed.get(item_path)
            body = indexed.get(body_path)
            if item is None or item.tag != "list_item":
                raise ValueError("continuation predecessor path is not list_item")
            if (
                body is None
                or body.tag != "list_body"
                or body_path[: len(item_path)] != item_path
            ):
                raise ValueError("continuation predecessor body path is not list_body")
            if len(target_path) < 1 or target_path[-1] == 0:
                raise ValueError("list-continuation has no preceding sibling list")
            preceding_index = target_path[-1] - 1
            preceding_path = (*target_path[:-1], preceding_index)
            preceding = indexed.get(preceding_path)
            while (
                preceding_index >= 0
                and preceding is not None
                and cls._is_ignorable_text_fragment(preceding)
            ):
                preceding_index -= 1
                preceding_path = (*target_path[:-1], preceding_index)
                preceding = indexed.get(preceding_path)
            if (
                preceding is None
                or preceding.tag != "list"
                or item_path[: len(preceding_path)] != preceding_path
            ):
                raise ValueError("list-continuation predecessor is not preceding list")
            preceding_children = cls._structural_children(preceding)
            final_item_index = cls._final_meaningful_child_index(
                preceding_children
            )
            if final_item_index is None:
                raise ValueError(
                    "continuation predecessor path is not final meaningful list_item"
                )
            final_item = preceding_children[final_item_index]
            final_item_path = (*preceding_path, final_item_index)
            if final_item.tag != "list_item" or item_path != final_item_path:
                raise ValueError(
                    "continuation predecessor path is not final meaningful list_item"
                )
            body_candidates = [
                (*final_item_path, index)
                for index, child in enumerate(cls._structural_children(final_item))
                if child.tag == "list_body"
            ]
            if len(body_candidates) != 1 or body_path != body_candidates[0]:
                raise ValueError(
                    "continuation predecessor body path is not final item list_body"
                )
            following_index = target_path[-1] + 1
            following_path = (*target_path[:-1], following_index)
            following = indexed.get(following_path)
            while (
                following is not None
                and cls._is_ignorable_text_fragment(following)
            ):
                following_index += 1
                following_path = (*target_path[:-1], following_index)
                following = indexed.get(following_path)
            if following is None or following.tag != "list":
                raise ValueError(
                    "list-continuation following sibling is not list"
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
        eligible_elements = cls._eligible_sentence_elements(root, promoted)
        for element in offsets_by_element:
            if element not in eligible_elements:
                raise ValueError("ineligible sentence-break-source structure")

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
                conflict = sentence_break_heading_conflict(
                    semantic_role=ancestor.tag,
                    source_role=ancestor.get("source-role"),
                    display_role=ancestor.get("display-role"),
                    promoted=ancestor in promoted,
                )
                if conflict == "promoted_heading":
                    raise ValueError(
                        "sentence-break-source overlaps report-promoted heading"
                    )
                if conflict == "source_heading":
                    raise ValueError("sentence-break-source overlaps source heading")
                if conflict is not None:
                    raise ValueError(
                        "sentence-break-source overlaps "
                        f"{conflict} display role"
                    )
                ancestor = parents.get(ancestor)

    @classmethod
    def _eligible_sentence_elements(
        cls,
        root: ET.Element,
        promoted: dict[ET.Element, dict[str, object]],
    ) -> frozenset[ET.Element]:
        flows: list[tuple[_SemanticTextFragment, ...]] = []

        def visit(
            parent: ET.Element,
            ancestors: tuple[ET.Element, ...],
        ) -> None:
            for child in cls._structural_children(parent):
                if child.tag == "list_body" and not any(
                    (
                        sentence_break_heading_conflict(
                            semantic_role=element.tag,
                            source_role=element.get("source-role"),
                            display_role=element.get("display-role"),
                            promoted=element in promoted,
                        )
                        is not None
                    )
                    for element in (*ancestors, *tuple(child.iter()))
                ):
                    flows.extend(cls._direct_sentence_flows(child))
                if is_sentence_break_eligible_paragraph(
                    semantic_role=child.tag,
                    source_role=child.get("source-role"),
                    ancestor_roles=tuple(element.tag for element in ancestors),
                    is_nonempty_inline_leaf=(
                        cls._is_nonempty_inline_sentence_paragraph(child)
                    ),
                    ancestor_source_roles=tuple(
                        element.get("source-role") for element in ancestors
                    ),
                    display_role=child.get("display-role"),
                    heading_conflict=any(
                        element in promoted
                        for element in (*ancestors, *tuple(child.iter()))
                    ),
                ):
                    flows.extend(cls._leaf_sentence_paragraph_flows(child))
                visit(child, (*ancestors, child))

        visit(root, ())
        elements: set[ET.Element] = set()
        for flow in flows:
            for fragment in flow:
                elements.add(fragment.element)
        return frozenset(elements)

    @classmethod
    def _is_nonempty_inline_sentence_paragraph(
        cls,
        element: ET.Element,
    ) -> bool:
        if element.tag != "paragraph":
            return False

        has_visible_text = False

        def visit_inline(parent: ET.Element) -> bool:
            nonlocal has_visible_text
            for child in cls._structural_children(parent):
                if child.tag == "text":
                    if decode_data_element(child).strip():
                        has_visible_text = True
                elif child.tag in _SENTENCE_INLINE_TAGS:
                    if (child.get("actual-text") or "").strip():
                        has_visible_text = True
                    if not visit_inline(child):
                        return False
                elif cls._is_inline_icon(child):
                    # Geometry and route context are validated for every icon
                    # by _validate_display_evidence before rendering succeeds.
                    continue
                else:
                    return False
            return True

        return visit_inline(element) and has_visible_text

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
            elif cls._is_inline_icon(child):
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

    @classmethod
    def _validate_inline_icon_evidence(
        cls,
        element: ET.Element,
    ) -> _SemanticInlineIconEvidence:
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
        try:
            max_width_ratio, max_height_ratio = inline_icon_ratio_limits(reason)
        except ValueError as exc:
            raise ValueError("invalid inline-icon icon-reason")

        route_separator_count: int | None = None
        route_parenthesized: bool | None = None
        if reason == NAVIGATION_ROUTE_INLINE_ICON_REASON:
            raw_count = element.get("route-separator-count")
            if raw_count is None:
                raise ValueError("missing navigation route-separator-count")
            if re.fullmatch(r"[2-9]|[1-9][0-9]+", raw_count) is None:
                raise ValueError("invalid navigation route-separator-count")
            route_separator_count = int(raw_count)
            raw_parenthesized = element.get("route-parenthesized")
            if raw_parenthesized not in {"true", "false"}:
                raise ValueError("invalid navigation route-parenthesized")
            route_parenthesized = raw_parenthesized == "true"
        elif reason == GENERIC_INLINE_ICON_REASON:
            if (
                "route-separator-count" in element.attrib
                or "route-parenthesized" in element.attrib
            ):
                raise ValueError("generic inline-icon contains route evidence")

        numbers: dict[str, float] = {}
        for name in (
            "reference-font-size",
            "width-font-ratio",
            "height-font-ratio",
        ):
            number = parse_positive_finite_number(element.get(name))
            if number is None:
                raise ValueError(f"invalid inline-icon {name}")
            numbers[name] = number

        width_ratio = numbers["width-font-ratio"]
        height_ratio = numbers["height-font-ratio"]
        if width_ratio > max_width_ratio:
            raise ValueError("inline-icon width-font-ratio exceeds limit")
        if height_ratio > max_height_ratio:
            raise ValueError("inline-icon height-font-ratio exceeds limit")

        bbox = parse_unambiguous_bbox(cls._source_attribute_pairs(element))
        if bbox is None:
            raise ValueError("invalid inline-icon BBox")
        reference_font_size = numbers["reference-font-size"]
        expected_width_ratio = (bbox[2] - bbox[0]) / reference_font_size
        expected_height_ratio = (bbox[3] - bbox[1]) / reference_font_size
        if not math.isclose(width_ratio, expected_width_ratio, rel_tol=5e-7, abs_tol=5e-7):
            raise ValueError("inline-icon width-font-ratio does not match BBox")
        if not math.isclose(height_ratio, expected_height_ratio, rel_tol=5e-7, abs_tol=5e-7):
            raise ValueError("inline-icon height-font-ratio does not match BBox")
        if cls._inline_icon_has_visible_text(element):
            raise ValueError("inline-icon figure contains visible text")

        return _SemanticInlineIconEvidence(
            reason=reason,
            page_index=int(page_index),
            bbox=bbox,
            reference_font_size=reference_font_size,
            width_ratio=width_ratio,
            height_ratio=height_ratio,
            route_separator_count=route_separator_count,
            route_parenthesized=route_parenthesized,
        )

    @staticmethod
    def _source_attribute_pairs(element: ET.Element) -> tuple[tuple[object, object], ...]:
        return tuple(
            (attribute.get("name"), attribute.get("value"))
            for attributes in element.findall("attributes")
            for attribute in attributes.findall("attribute")
        )

    @classmethod
    def _inline_icon_has_visible_text(cls, element: ET.Element) -> bool:
        for descendant in element.iter():
            if (descendant.get("actual-text") or "").strip():
                return True
            if descendant.tag == "text" and decode_data_element(descendant).strip():
                return True
        return False

    @classmethod
    def _validate_inline_icon_structures(
        cls,
        root: ET.Element,
        icons: dict[ET.Element, _SemanticInlineIconEvidence],
    ) -> None:
        if not icons:
            return
        eligible: dict[ET.Element, tuple[bool, bool, bool, int, bool]] = {}
        for flow in cls._inline_icon_flows(root):
            for index, item in enumerate(flow):
                if not isinstance(item, _SemanticInlineFigure) or item.element not in icons:
                    continue
                evidence = icons[item.element]
                adjacent = tuple(
                    text
                    for text in (
                        cls._adjacent_inline_text(flow, index, -1),
                        cls._adjacent_inline_text(flow, index, 1),
                    )
                    if text is not None
                )
                same_page_segment, local_index = cls._same_page_inline_segment(
                    flow,
                    index,
                    evidence.page_index,
                )
                separator_adjacent, separator_count, parenthesized = (
                    cls._semantic_navigation_route_evidence(
                        same_page_segment,
                        local_index,
                    )
                )
                eligible[item.element] = (
                    bool(adjacent),
                    any(
                        cls._nonnegative_page_index(text.element) == evidence.page_index
                        for text in adjacent
                    ),
                    separator_adjacent,
                    separator_count,
                    parenthesized,
                )

        for element in icons:
            relationship = eligible.get(element)
            if relationship is None:
                raise ValueError("ineligible inline-icon structure")
            (
                has_adjacent,
                has_same_page,
                separator_adjacent,
                separator_count,
                parenthesized,
            ) = relationship
            if not has_adjacent:
                raise ValueError("inline-icon requires adjacent visible text")
            if not has_same_page:
                raise ValueError("inline-icon requires adjacent same-page visible text")
            evidence = icons[element]
            if evidence.reason == NAVIGATION_ROUTE_INLINE_ICON_REASON:
                if not separator_adjacent:
                    raise ValueError(
                        "navigation icon requires adjacent separator"
                    )
                if separator_count != evidence.route_separator_count:
                    raise ValueError(
                        "navigation route-separator-count does not match flow"
                    )
                if parenthesized is not evidence.route_parenthesized:
                    raise ValueError(
                        "navigation route-parenthesized does not match flow"
                    )

    @classmethod
    def _same_page_inline_segment(
        cls,
        flow: tuple[_SemanticInlineText | _SemanticInlineFigure, ...],
        candidate_index: int,
        page_index: int,
    ) -> tuple[
        tuple[_SemanticInlineText | _SemanticInlineFigure, ...],
        int,
    ]:
        start = candidate_index
        while (
            start > 0
            and cls._semantic_inline_item_page_index(flow[start - 1]) == page_index
        ):
            start -= 1
        end = candidate_index + 1
        while (
            end < len(flow)
            and cls._semantic_inline_item_page_index(flow[end]) == page_index
        ):
            end += 1
        return flow[start:end], candidate_index - start

    @classmethod
    def _semantic_inline_item_page_index(
        cls,
        item: _SemanticInlineText | _SemanticInlineFigure,
    ) -> int | None:
        return cls._nonnegative_page_index(item.element)

    @classmethod
    def _semantic_navigation_route_evidence(
        cls,
        segment: tuple[_SemanticInlineText | _SemanticInlineFigure, ...],
        candidate_index: int,
    ) -> tuple[bool, int, bool]:
        evidence = navigation_text_evidence(
            tuple(
                item.text if isinstance(item, _SemanticInlineText) else None
                for item in segment
            ),
            candidate_index,
        )
        if evidence is None:
            return False, 0, False
        return True, evidence.separator_count, evidence.parenthesized

    @classmethod
    def _inline_icon_flows(
        cls,
        root: ET.Element,
    ) -> tuple[tuple[_SemanticInlineText | _SemanticInlineFigure, ...], ...]:
        flows: list[tuple[_SemanticInlineText | _SemanticInlineFigure, ...]] = []

        def visit(parent: ET.Element) -> None:
            for child in cls._structural_children(parent):
                if child.tag in {"heading", "caption", "label", "figure"}:
                    continue
                if child.tag == "paragraph":
                    tokens = cls._inline_icon_tokens(child)
                    if _SENTENCE_BLOCK_BOUNDARY not in tokens:
                        flow = tuple(
                            token
                            for token in tokens
                            if isinstance(token, (_SemanticInlineText, _SemanticInlineFigure))
                        )
                        if flow:
                            flows.append(flow)
                elif child.tag == "list_body":
                    flows.extend(cls._inline_icon_segments(cls._inline_icon_tokens(child)))
                visit(child)

        visit(root)
        return tuple(flows)

    @classmethod
    def _inline_icon_tokens(
        cls,
        parent: ET.Element,
    ) -> tuple[_SemanticInlineText | _SemanticInlineFigure | object, ...]:
        tokens: list[_SemanticInlineText | _SemanticInlineFigure | object] = []
        for child in cls._structural_children(parent):
            if child.tag == "text":
                tokens.append(_SemanticInlineText(child, decode_data_element(child)))
            elif child.tag in _SENTENCE_INLINE_TAGS:
                tokens.extend(cls._inline_icon_tokens(child))
            elif child.tag == "figure":
                tokens.append(_SemanticInlineFigure(child))
            else:
                tokens.append(_SENTENCE_BLOCK_BOUNDARY)
        return tuple(tokens)

    @staticmethod
    def _inline_icon_segments(
        tokens: tuple[_SemanticInlineText | _SemanticInlineFigure | object, ...],
    ) -> tuple[tuple[_SemanticInlineText | _SemanticInlineFigure, ...], ...]:
        segments: list[tuple[_SemanticInlineText | _SemanticInlineFigure, ...]] = []
        current: list[_SemanticInlineText | _SemanticInlineFigure] = []
        for token in tokens:
            if isinstance(token, (_SemanticInlineText, _SemanticInlineFigure)):
                current.append(token)
            elif current:
                segments.append(tuple(current))
                current = []
        if current:
            segments.append(tuple(current))
        return tuple(segments)

    @staticmethod
    def _adjacent_inline_text(
        flow: tuple[_SemanticInlineText | _SemanticInlineFigure, ...],
        figure_index: int,
        direction: int,
    ) -> _SemanticInlineText | None:
        index = figure_index + direction
        while 0 <= index < len(flow):
            item = flow[index]
            if isinstance(item, _SemanticInlineFigure):
                return None
            if any(not character.isspace() for character in item.text):
                return item
            index += direction
        return None

    @staticmethod
    def _nonnegative_page_index(element: ET.Element) -> int | None:
        value = element.get("page-index")
        if value is None or re.fullmatch(r"0|[1-9][0-9]*", value) is None:
            return None
        return int(value)

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
    def _escape_physical_lines(cls, value: str, *, model_literals: bool = True) -> str:
        if model_literals:
            value = cls._escape_model_wildcards(value)
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
