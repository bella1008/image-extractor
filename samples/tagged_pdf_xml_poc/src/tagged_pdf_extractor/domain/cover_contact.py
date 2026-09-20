from __future__ import annotations

from dataclasses import replace
import re

from tagged_pdf_extractor.domain.models import (
    ContentFragment,
    StructureElement,
    TaggedDocument,
    TextDisplayHint,
)
from tagged_pdf_extractor.domain.paragraph_eligibility import (
    is_nonempty_inline_paragraph,
)
from tagged_pdf_extractor.domain.typography import typography_evidence


_URL = re.compile(r"(?:https?://)?(?:www\.)?samsung\.com(?:/|\b)", re.IGNORECASE)
_CONTACT_NUMBER = re.compile(r"(?:\*\s*)?\d(?:[\d\s()+*.-]*\d){1,}")
_CELL_ROLES = frozenset({"table_cell", "table_header"})


def apply_cover_contact_formatting(document: TaggedDocument) -> TaggedDocument:
    """Annotate structurally proven cover contact sections without wording maps."""

    hints = list(document.text_display_hints)
    occupied_paths = {hint.child_path for hint in hints}
    changed = False

    def visit(
        node: StructureElement | ContentFragment,
        path: tuple[int, ...],
    ) -> StructureElement | ContentFragment:
        nonlocal changed
        if isinstance(node, ContentFragment):
            return node

        children = tuple(visit(child, (*path, index)) for index, child in enumerate(node.children))
        result = replace(node, children=children) if children != node.children else node
        contact = _contact_parts(result)
        if contact is None:
            return result

        title, explanation, wrapper, table = contact
        table_index = wrapper.children.index(table)
        marked_table = replace(
            table,
            attributes=_set_attributes(
                table.attributes,
                ("review-table", "source-spans"),
                ("review-table-kind", "cover-contact"),
            ),
        )
        marked_wrapper = replace(
            wrapper,
            children=tuple(
                marked_table if index == table_index else child
                for index, child in enumerate(wrapper.children)
            ),
        )
        wrapper_index = result.children.index(wrapper)
        result = replace(
            result,
            children=tuple(
                marked_wrapper if index == wrapper_index else child
                for index, child in enumerate(result.children)
            ),
        )
        changed = True

        title_path = (*path, result.children.index(title))
        if title_path not in occupied_paths:
            title_evidence = typography_evidence(title)
            body_evidence = typography_evidence(explanation)
            if (
                title_evidence is not None
                and body_evidence is not None
                and title_evidence.font_size is not None
                and body_evidence.font_size is not None
                and title_evidence.font_weight > body_evidence.font_weight
                and title_evidence.font_size >= body_evidence.font_size
            ):
                hints.append(
                    TextDisplayHint(
                        child_path=title_path,
                        display_role="strong_label",
                        font_weight=title_evidence.font_weight,
                        font_size=title_evidence.font_size,
                        comparison_body_font_weight=body_evidence.font_weight,
                        comparison_body_font_size=body_evidence.font_size,
                        reason="cover_contact_title_stronger_than_explanation",
                    )
                )
                occupied_paths.add(title_path)
        return result

    children = tuple(visit(child, (index,)) for index, child in enumerate(document.children))
    ordered_hints = tuple(sorted(hints, key=lambda hint: hint.child_path))
    if not changed and ordered_hints == document.text_display_hints:
        return document
    return replace(document, children=children, text_display_hints=ordered_hints)


def _contact_parts(
    section: StructureElement,
) -> tuple[StructureElement, StructureElement, StructureElement, StructureElement] | None:
    if section.semantic_role != "section" or len(section.children) != 3:
        return None
    title, explanation, wrapper = section.children
    if not all(isinstance(value, StructureElement) for value in (title, explanation, wrapper)):
        return None
    assert isinstance(title, StructureElement)
    assert isinstance(explanation, StructureElement)
    assert isinstance(wrapper, StructureElement)
    if not is_nonempty_inline_paragraph(title) or not is_nonempty_inline_paragraph(explanation):
        return None
    wrapper_children = tuple(child for child in wrapper.children if isinstance(child, StructureElement))
    if (
        wrapper.semantic_role != "paragraph"
        or len(wrapper.children) != 1
        or len(wrapper_children) != 1
        or wrapper_children[0].semantic_role != "table"
    ):
        return None
    table = wrapper_children[0]
    if not _is_contact_table(table):
        return None
    return title, explanation, wrapper, table


def _is_contact_table(table: StructureElement) -> bool:
    rows = tuple(
        child
        for child in table.children
        if isinstance(child, StructureElement) and child.semantic_role == "table_row"
    )
    if len(rows) < 2 or len(rows) != len(table.children):
        return False
    header_cells = _cells(rows[0])
    if len(header_cells) not in {2, 3}:
        return False
    if any(not _valid_contact_row(row) for row in rows):
        return False

    body_cells = tuple(cell for row in rows[1:] for cell in _cells(row))
    texts = tuple(_text(cell) for cell in body_cells)
    has_url = any(_URL.search(text) for text in texts)
    has_contact_number = any(
        _URL.search(text) is None and _CONTACT_NUMBER.search(text)
        for text in texts
    )
    return has_url and has_contact_number


def _valid_contact_row(row: StructureElement) -> bool:
    cells = _cells(row)
    if not cells or len(cells) != len(row.children):
        return False
    return all(
        cell.semantic_role in _CELL_ROLES
        and cell.children
        and all(
            isinstance(child, StructureElement)
            and is_nonempty_inline_paragraph(child)
            for child in cell.children
        )
        for cell in cells
    )


def _cells(row: StructureElement) -> tuple[StructureElement, ...]:
    return tuple(
        child
        for child in row.children
        if isinstance(child, StructureElement) and child.semantic_role in _CELL_ROLES
    )


def _text(element: StructureElement) -> str:
    parts: list[str] = []
    stack = list(reversed(element.children))
    while stack:
        child = stack.pop()
        if isinstance(child, ContentFragment):
            parts.extend(child.text_parts)
        else:
            stack.extend(reversed(child.children))
    return " ".join("".join(parts).split())


def _set_attributes(
    attributes: tuple[tuple[str, str], ...],
    *updates: tuple[str, str],
) -> tuple[tuple[str, str], ...]:
    values = dict(attributes)
    values.update(updates)
    return tuple(values.items())
