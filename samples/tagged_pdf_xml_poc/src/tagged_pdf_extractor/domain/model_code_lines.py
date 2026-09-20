from __future__ import annotations

from dataclasses import replace
import re
from statistics import median

from tagged_pdf_extractor.domain.models import (
    ContentFragment,
    StructureElement,
    TaggedDocument,
)


_MODEL_TOKEN = re.compile(r"[A-Z0-9*]+(?:[-/][A-Z0-9*]+)*")
_LINE_TOLERANCE = 1.5


def annotate_model_code_lines(document: TaggedDocument) -> TaggedDocument:
    """Mark only model-only table-cell paragraphs with proven source baselines."""

    changed = False

    def visit(
        node: StructureElement | ContentFragment,
        *,
        inside_table_cell: bool,
    ) -> StructureElement | ContentFragment:
        nonlocal changed
        if isinstance(node, ContentFragment):
            return node
        children = tuple(
            visit(
                child,
                inside_table_cell=(inside_table_cell or node.semantic_role == "table_cell"),
            )
            for child in node.children
        )
        result = replace(node, children=children) if children != node.children else node
        if inside_table_cell and result.semantic_role == "paragraph":
            indexes = _line_start_indexes(result)
            if indexes:
                attributes = dict(result.attributes)
                attributes["review-line-layout"] = "model-code-rows"
                attributes["review-line-break-before-child-indexes"] = ",".join(
                    str(index) for index in indexes
                )
                result = replace(result, attributes=tuple(attributes.items()))
                changed = True
        return result

    children = tuple(visit(child, inside_table_cell=False) for child in document.children)
    return replace(document, children=children) if changed else document


def _line_start_indexes(paragraph: StructureElement) -> tuple[int, ...]:
    if len(paragraph.children) < 2 or any(
        not isinstance(child, ContentFragment) for child in paragraph.children
    ):
        return ()

    fragments = tuple(child for child in paragraph.children if isinstance(child, ContentFragment))
    positions: list[float] = []
    visible: list[str] = []
    for fragment in fragments:
        boxes = tuple(
            bbox
            for bbox in fragment.text_bboxes
            if bbox is not None and bbox[2] > bbox[0] and bbox[3] > bbox[1]
        )
        if not boxes:
            return ()
        positions.append(median((bbox[1] + bbox[3]) / 2 for bbox in boxes))
        visible.append(" ".join(fragment.text.split()))

    groups: list[list[int]] = [[0]]
    for index in range(1, len(positions)):
        if abs(positions[index] - positions[groups[-1][0]]) <= _LINE_TOLERANCE:
            groups[-1].append(index)
        else:
            groups.append([index])
    if len(groups) < 2:
        return ()

    for group in groups:
        line = " ".join(visible[index] for index in group if visible[index]).strip()
        tokens = tuple(
            cleaned
            for token in line.split()
            if (cleaned := token.strip("(),;."))
        )
        if not tokens or any(not _is_model_token(token) for token in tokens):
            return ()
    return tuple(group[0] for group in groups[1:])


def _is_model_token(token: str) -> bool:
    return (
        _MODEL_TOKEN.fullmatch(token) is not None
        and any(character.isalpha() for character in token)
        and any(character.isdigit() for character in token)
    )
