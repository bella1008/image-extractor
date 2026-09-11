"""Provisional evidence compositions. Never rewrite source units or approve rules."""
from __future__ import annotations

from dataclasses import dataclass

from src.review_document import ReviewDocument, ReviewNode
from src.review_text_units import TextPart, build_text_unit_index

MAX_PARAGRAPHS = 4
_INLINE = frozenset(('text', 'span', 'label', 'figure'))
_STRUCTURED = frozenset(('list_item', 'table', 'table_row', 'table_cell'))


@dataclass(frozen=True)
class EvidenceWindow:
    method: str
    owner_ids: tuple[str, ...]
    groups: tuple[tuple[TextPart, ...], ...]
    separator: str
    language: str
    container_ids: tuple[str, ...]
    visual_node_ids: tuple[str, ...] = ()
    caveats: tuple[str, ...] = ('provisional_evidence_not_selector_approval',)

    @property
    def parts(self) -> tuple[TextPart, ...]:
        return tuple(p for group in self.groups for p in group)

    @property
    def text(self) -> str:
        return self.separator.join(''.join(p.text for p in group) for group in self.groups)


def build_evidence_windows(document: ReviewDocument) -> tuple[EvidenceWindow, ...]:
    """Bounded alternatives, including table ancestry but no row/cell flattening.

    An uninterrupted text run may be observed beside a figure; neither the
    figure nor the whole unit becomes text-safe. Paragraph composition is a
    candidate association, not a claim that XML paragraphs are one paragraph.
    """
    units = build_text_unit_index(document).units
    nodes = {n.node_id: n for n in document.iter_nodes()}
    parents = {child.node_id: n.node_id for n in nodes.values()
               for child in n.content if isinstance(child, ReviewNode)}
    part_map = {(p.node_id, p.content_index): p for u in units for p in u.parts}

    def lineage(key):
        result = []
        while key in parents:
            key = parents[key]
            result.append(key)
        return tuple(reversed(result))

    def inline_events(owner):
        # Validate even empty descendants, which a text-only scan would miss.
        pending = [owner]
        while pending:
            current = pending.pop()
            if current is not owner and current.structure_type not in _INLINE:
                return None
            if current.language != owner.language or not current.evidence:
                return None
            pending.extend(c for c in current.content if isinstance(c, ReviewNode))
        result = []
        pending = [(owner, None)]
        while pending:
            current, index = pending.pop()
            if index is not None:
                result.append(part_map[(current.node_id, index)])
            elif current.structure_type == 'figure':
                result.append(current.node_id)
            else:
                pending.extend((current, i) if isinstance(c, str) else (c, None)
                               for i, c in reversed(list(enumerate(current.content))))
        return result

    def make(method, owners, groups, separator='', visuals=()):
        lineage_ids = (*lineage(owners[0]), owners[0])
        containers = tuple(key for key in lineage_ids if nodes[key].structure_type in _STRUCTURED)
        caveats = ['provisional_evidence_not_selector_approval']
        if any(nodes[key].structure_type == 'table' for key in containers):
            caveats.append('table_structure_requires_review')
        if visuals:
            caveats.append('visual_context_requires_review')
        return EvidenceWindow(method, tuple(owners), tuple(tuple(g) for g in groups), separator,
                              nodes[owners[0]].language, containers, tuple(visuals), tuple(caveats))

    windows, atomic = [], {}
    for unit in units:
        owner = nodes[unit.owner_id]
        if (owner.structure_type not in ('paragraph', 'list_body', 'table_cell')
                or 'review:heading-evidence' in dict(owner.attributes)
                or not unit.parts or not unit.text.strip()
                or set(unit.issues) - {'visual_content_requires_review'}):
            continue
        events = inline_events(owner)
        if events is None:
            continue
        all_parts = [event for event in events if isinstance(event, TextPart)]
        # Only a whole atomic owner; no partial ownership across nested blocks.
        owner_parts = [p for u in units if u.owner_id == owner.node_id for p in u.parts]
        if not unit.visual_node_ids and all_parts != owner_parts:
            continue
        if unit.visual_node_ids:
            group = []
            for event in [*events, None]:
                if isinstance(event, TextPart):
                    group.append(event)
                else:
                    if any(p.text.strip() for p in group):
                        windows.append(make('text_beside_visual', (owner.node_id,), (group,), visuals=unit.visual_node_ids))
                    group = []
        else:
            candidate = make('atomic_text', (owner.node_id,), (unit.parts,))
            windows.append(candidate)
            atomic[owner.node_id] = candidate

    for parent in nodes.values():
        if not parent.evidence:
            continue
        children = parent.content
        if parent.structure_type in ('section', 'article', 'document', 'table_cell'):
            for start in range(len(children)):
                group = []
                for child in children[start:start + MAX_PARAGRAPHS]:
                    if (not isinstance(child, ReviewNode) or child.structure_type != 'paragraph'
                            or child.node_id not in atomic):
                        break
                    candidate = atomic[child.node_id]
                    if group and candidate.language != group[0].language:
                        break
                    group.append(candidate)
                    if len(group) > 1:
                        windows.append(make('adjacent_paragraphs', tuple(w.owner_ids[0] for w in group),
                                            tuple(w.parts for w in group), '\n'))
        if (parent.structure_type == 'list_item' and len(children) == 2
                and all(isinstance(c, ReviewNode) for c in children)):
            label, body = children
            if (label.structure_type != 'label' or body.structure_type != 'list_body'
                    or body.node_id not in atomic or label.language != body.language
                    or parent.language != body.language):
                continue
            events = inline_events(label)
            if not events or not all(isinstance(e, TextPart) for e in events):
                continue
            windows.append(make('list_item_label_body', (label.node_id, body.node_id), (events, atomic[body.node_id].parts)))
    return tuple(windows)
