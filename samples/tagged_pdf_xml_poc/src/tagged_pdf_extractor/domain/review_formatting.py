from __future__ import annotations

from dataclasses import replace

from tagged_pdf_extractor.domain.models import (
    ContentFragment,
    LineBreakHint,
    StructureElement,
    TaggedDocument,
)
from tagged_pdf_extractor.domain.profile_scope import review_formatting_scope


_INLINE_ROLES = frozenset({"span", "link"})


def apply_profile_review_formatting(document: TaggedDocument) -> TaggedDocument:
    if not review_formatting_scope(document.source_path).enabled:
        return document
    return replace(
        document,
        line_break_hints=detect_rf_line_break_hints(document.children),
    )


def detect_rf_line_break_hints(
    children: tuple[StructureElement | ContentFragment, ...],
) -> tuple[LineBreakHint, ...]:
    hints: list[LineBreakHint] = []

    def visit(
        siblings: tuple[StructureElement | ContentFragment, ...],
        parent_path: tuple[int, ...],
        inside_table_cell: bool,
    ) -> None:
        for index, child in enumerate(siblings):
            if not isinstance(child, StructureElement):
                continue
            child_path = (*parent_path, index)
            if child.semantic_role == "paragraph":
                if inside_table_cell:
                    hints.extend(_paragraph_hints(child, child_path))
                for nested_index, nested_child in enumerate(child.children):
                    if (
                        isinstance(nested_child, StructureElement)
                        and nested_child.semantic_role == "table"
                    ):
                        nested_path = (*child_path, nested_index)
                        visit(
                            nested_child.children,
                            nested_path,
                            inside_table_cell,
                        )
                continue
            visit(
                child.children,
                child_path,
                inside_table_cell or child.semantic_role == "table_cell",
            )

    visit(children, (), False)
    return tuple(hints)


def _paragraph_hints(
    paragraph: StructureElement,
    paragraph_path: tuple[int, ...],
) -> tuple[LineBreakHint, ...]:
    segments: list[tuple[tuple[int, ...], str, bool]] = []

    def collect_inline(
        siblings: tuple[StructureElement | ContentFragment, ...],
        parent_path: tuple[int, ...],
    ) -> None:
        for index, child in enumerate(siblings):
            child_path = (*parent_path, index)
            if isinstance(child, ContentFragment):
                segments.append((child_path, child.text, False))
            elif child.semantic_role in _INLINE_ROLES:
                if child.actual_text is not None:
                    segments.append((child_path, child.actual_text, True))
                else:
                    collect_inline(child.children, child_path)

    collect_inline(paragraph.children, paragraph_path)
    hints: list[LineBreakHint] = []
    for index, (child_path, text, is_actual_text) in enumerate(segments):
        if not is_actual_text or text != "\n":
            continue
        if index == 0 or index == len(segments) - 1:
            continue
        previous_text = segments[index - 1][1]
        following_text = segments[index + 1][1]
        if not previous_text.strip() or not following_text.strip():
            continue
        if not previous_text.rstrip().endswith(","):
            continue
        hints.append(LineBreakHint(child_path=child_path))
    return tuple(hints)
