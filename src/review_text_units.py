"""Source-bounded text inventory, not a checklist evaluator or quality gate."""
from __future__ import annotations

from dataclasses import dataclass, field

from src.review_document import ReviewDocument, ReviewNode, SourceEvidence

_OWNERS = frozenset(("paragraph", "heading", "list_body", "table_cell"))
_INLINE = frozenset(("text", "span", "label", "figure"))
_CONTAINERS = frozenset(("document", "article", "section", "list", "list_item", "table", "table_row"))


@dataclass(frozen=True)
class TextPart:
    node_id: str
    content_index: int
    text: str
    language: str | None
    evidence: tuple[SourceEvidence, ...]


@dataclass(frozen=True)
class ReviewTextUnit:
    owner_id: str
    structure_type: str
    segment_index: int
    ancestor_ids: tuple[str, ...]
    language: str | None
    parts: tuple[TextPart, ...]
    visual_node_ids: tuple[str, ...]
    evidence: tuple[SourceEvidence, ...]
    issues: tuple[str, ...]

    @property
    def text(self) -> str:
        return "".join(part.text for part in self.parts)

    @property
    def ready_for_text_match(self) -> bool:
        """Structural preconditions only; never means a rule passed."""
        return bool(self.text.strip()) and not self.issues


@dataclass(frozen=True)
class TextUnitIndex:
    units: tuple[ReviewTextUnit, ...]
    schema_version: str = "review-text-units/1"
    decision_status: str = "not_evaluated"


@dataclass
class _Segment:
    owner: ReviewNode
    ancestors: tuple[str, ...]
    inherited_issues: tuple[str, ...]
    number: int = 0
    parts: list[TextPart] = field(default_factory=list)
    visuals: list[str] = field(default_factory=list)
    nodes: list[ReviewNode] = field(default_factory=list)


def build_text_unit_index(document: ReviewDocument) -> TextUnitIndex:
    """Partition every source string occurrence exactly once, in source order.

    Unknown containers are retained and block their descendant units. Tables and
    lists supply ancestry, not flattened text windows. This function does not
    certify its input; application callers must use the checked bundle reader.
    """
    if not isinstance(document, ReviewDocument):
        raise TypeError("expected ReviewDocument")
    # Postorder calculation keeps deeply nested input independent of recursion limits.
    all_nodes = list(document.iter_nodes())
    inline, heading_inline = {}, {}
    for node in reversed(all_nodes):
        children = [item for item in node.content if isinstance(item, ReviewNode)]
        inline[node.node_id] = node.structure_type in _INLINE and all(inline[c.node_id] for c in children)
        # Only a heading's direct list_body child may compose its title. A body
        # below another body/span/label is still a structural boundary.
        heading_inline[node.node_id] = (node.structure_type in _INLINE | {"list_body"}
                                        and all(inline[c.node_id] for c in children))
    units = []
    expected = [(node.node_id, i) for node in all_nodes for i, item in enumerate(node.content) if isinstance(item, str)]

    def add_node(segment, node):
        segment.nodes.append(node)
        if node.structure_type == "figure":
            segment.visuals.append(node.node_id)

    def add_text(segment, node, index):
        segment.parts.append(TextPart(node.node_id, index, node.content[index], node.language, node.evidence))

    def flush(segment):
        if not segment.parts and not segment.visuals:
            return
        issues = set(segment.inherited_issues)
        if segment.owner.structure_type not in _OWNERS:
            issues.add("unsupported_text_owner")
        nodes = [segment.owner, *segment.nodes]
        languages = {node.language for node in nodes}
        languages.update(part.language for part in segment.parts)
        if None in languages:
            issues.add("unassigned_language")
        known_languages = languages - {None}
        if len(known_languages) > 1:
            issues.add("mixed_language")
        if known_languages - set(document.context.expected_languages):
            issues.add("unexpected_language")
        if any(not part.evidence for part in segment.parts):
            issues.add("missing_text_evidence")
        if segment.visuals:
            issues.add("visual_content_requires_review")
        if not any(part.text.strip() for part in segment.parts):
            issues.add("empty_text")
        evidence = tuple(dict.fromkeys(e for node in nodes for e in node.evidence))
        units.append(ReviewTextUnit(segment.owner.node_id, segment.owner.structure_type, segment.number,
                                    segment.ancestors, next(iter(languages)) if len(languages) == 1 else None,
                                    tuple(segment.parts), tuple(segment.visuals), evidence, tuple(sorted(issues))))
        segment.number += 1
        segment.parts.clear()
        segment.visuals.clear()
        segment.nodes.clear()

    actions = [("block", root, (), ()) for root in reversed(document.roots)]
    while actions:
        event, *args = actions.pop()
        if event == "flush":
            flush(args[0])
        elif event == "text":
            add_text(*args)
        elif event == "inline":
            segment, node = args
            add_node(segment, node)
            for i in reversed(range(len(node.content))):
                item = node.content[i]
                actions.append(("text", segment, node, i) if isinstance(item, str) else ("inline", segment, item))
        else:
            node, ancestors, inherited = args
            issues = set(inherited)
            if node.structure_type not in _OWNERS | _INLINE | _CONTAINERS:
                issues.add("unsupported_structure")
            if node.structure_type in _INLINE and not inline[node.node_id]:
                issues.add("unsupported_inline_structure")
            if node.structure_type == "figure":
                issues.add("visual_content_requires_review")
            segment = _Segment(node, ancestors, tuple(sorted(issues)))
            if node.structure_type == "figure":
                add_node(segment, node)
            events = []
            for i, item in enumerate(node.content):
                if isinstance(item, str):
                    events.append(("text", segment, node, i))
                elif (heading_inline if node.structure_type == "heading" else inline)[item.node_id]:
                    events.append(("inline", segment, item))
                else:
                    events.extend((("flush", segment), ("block", item, ancestors + (node.node_id,), tuple(sorted(issues)))))
            events.append(("flush", segment))
            actions.extend(reversed(events))

    actual = [(part.node_id, part.content_index) for unit in units for part in unit.parts]
    if len(actual) != len(expected) or set(actual) != set(expected):
        raise ValueError("text partition lost or duplicated source occurrences")
    # Preorder node inventory does not encode text-child-tail order; compare using
    # an independent mixed-content traversal instead.
    source_order = []
    pending = [(root, None) for root in reversed(document.roots)]
    while pending:
        node, index = pending.pop()
        if index is not None:
            source_order.append((node.node_id, index))
        else:
            pending.extend((node, i) if isinstance(node.content[i], str) else (node.content[i], None)
                           for i in reversed(range(len(node.content))))
    if actual != source_order:
        raise ValueError("text partition changed source order")
    return TextUnitIndex(tuple(units))
