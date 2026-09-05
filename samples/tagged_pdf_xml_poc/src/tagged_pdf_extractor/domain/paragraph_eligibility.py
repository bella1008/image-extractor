from __future__ import annotations

from tagged_pdf_extractor.domain.models import ContentFragment, StructureElement


_INLINE_ROLES = frozenset({"span", "link"})


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
