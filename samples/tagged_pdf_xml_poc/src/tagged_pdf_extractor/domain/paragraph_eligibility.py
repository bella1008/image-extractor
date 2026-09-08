from __future__ import annotations

from tagged_pdf_extractor.domain.models import ContentFragment, StructureElement
from tagged_pdf_extractor.domain.role_mapping import is_heading_candidate


_INLINE_ROLES = frozenset({"span", "link"})
_SENTENCE_FLOW_CONTAINERS = frozenset({"list_body", "table_cell"})
_SENTENCE_FLOW_BARRIERS = frozenset(
    {"list", "table", "heading", "caption", "label", "figure"}
)
_SENTENCE_DISPLAY_ROLES = frozenset(
    {"subtitle", "strong_label", "strong-label", "section_heading", "section-heading"}
)


def is_nonempty_inline_paragraph(element: StructureElement) -> bool:
    """Return whether a paragraph contains text through inline wrappers only."""

    if element.semantic_role != "paragraph":
        return False
    text_parts: list[str] = []
    stack = list(element.children)
    while stack:
        child = stack.pop()
        if isinstance(child, ContentFragment):
            text_parts.extend(child.text_parts)
            continue
        if child.semantic_role not in _INLINE_ROLES:
            return False
        if child.actual_text is not None:
            text_parts.append(child.actual_text)
        stack.extend(child.children)
    return bool("".join(text_parts).strip())


def is_sentence_break_eligible_paragraph(
    *,
    semantic_role: str | None,
    source_role: str | None,
    ancestor_roles: tuple[str, ...],
    is_nonempty_inline_leaf: bool,
    ancestor_source_roles: tuple[str | None, ...] = (),
    display_role: str | None = None,
    heading_conflict: bool = False,
) -> bool:
    """Return whether a paragraph may carry sentence-break evidence."""

    if (
        semantic_role != "paragraph"
        or not is_nonempty_inline_leaf
        or heading_conflict
        or any(
            role is not None and is_heading_candidate(role)
            for role in (source_role, *ancestor_source_roles)
        )
        or display_role in _SENTENCE_DISPLAY_ROLES
    ):
        return False
    for role in reversed(ancestor_roles):
        if role in _SENTENCE_FLOW_CONTAINERS:
            return True
        if role in _SENTENCE_FLOW_BARRIERS:
            return False
    return True
