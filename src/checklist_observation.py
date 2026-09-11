"""Provisional ZC ENG checklist evidence observations; never business Pass/Fail."""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import asdict

from src.checklist_migration import metadata_applies, restore_source_rows, validate_rows
from src.review_document import ReviewDocument, ReviewNode
from src.review_evidence_windows import MAX_PARAGRAPHS, build_evidence_windows
from src.review_text_units import build_text_unit_index

NORMALIZATION = "unicode-whitespace-only/case-and-punctuation-preserved/1"


def comparison_text(text: str) -> str:
    return " ".join(text.split())


def _locations(document):
    starts, ends, ancestors, parts, nodes = {}, {}, {}, {}, {}
    events = [("enter", root, ()) for root in reversed(document.roots)]
    clock = 0
    while events:
        kind, node, value = events.pop()
        if kind == "leave":
            ends[node.node_id] = clock
        elif kind == "text":
            parts[(node.node_id, value)] = clock
        else:
            starts[node.node_id] = clock
            ancestors[node.node_id] = value
            nodes[node.node_id] = node
            events.append(("leave", node, None))
            events.extend(("text", node, i) if isinstance(node.content[i], str)
                          else ("enter", node.content[i], value + (node.node_id,))
                          for i in reversed(range(len(node.content))))
        clock += 1
    return starts, ends, ancestors, parts, nodes


def _unit_view(unit):
    return {**asdict(unit), "text": unit.text, "issues": list(unit.issues)}


def _atomic_anchor(node, unit):
    """The entire heading, including empty descendants, must fit one unit."""
    expected = set()
    pending = [(node, None)]
    while pending:
        current, parent_id = pending.pop()
        if current is not node:
            ordinary_inline = current.structure_type in ("text", "span", "label", "figure")
            direct_heading_body = (node.structure_type == "heading" and parent_id == node.node_id
                                   and current.structure_type == "list_body")
            if not (ordinary_inline or direct_heading_body):
                return False
        for i, item in enumerate(current.content):
            if isinstance(item, str):
                expected.add((current.node_id, i))
            else:
                pending.append((item, current.node_id))
    return (expected == {(p.node_id, p.content_index) for p in unit.parts}
            and unit.text == node.text_content)


def _anchors(document, units, starts, ends):
    owned = defaultdict(list)
    for unit in units:
        owned[unit.owner_id].append(unit)
    anchors = []
    for node in document.iter_nodes():
        raw = dict(node.attributes).get("review:heading-evidence")
        if raw is None and node.structure_type != "heading":
            continue
        proof = json.loads(raw) if raw is not None else {}
        if not isinstance(proof, dict):
            raise ValueError("invalid heading evidence object")
        valid = (
            proof.get("classification") in ("heading", "numbered_chapter_promotion", "source_role_candidate")
            and isinstance(proof.get("joined_text"), str)
            and comparison_text(proof["joined_text"]) == comparison_text(node.text_content)
            and proof.get("structure_path") in {e.xml_path for e in node.evidence}
            and proof.get("source_role") == node.source_role
            and len(owned[node.node_id]) == 1
            and owned[node.node_id][0].ready_for_text_match
            and _atomic_anchor(node, owned[node.node_id][0])
        )
        anchors.append({"node_id": node.node_id, "text": node.text_content, "language": node.language,
                        "classification": proof.get("classification", "unverified_heading"),
                        "source_role": node.source_role, "source_evidence": [asdict(e) for e in node.evidence],
                        "reader_evidence": proof, "usable_for_observation": bool(valid),
                        "start": starts[node.node_id], "end": ends[node.node_id]})
    return anchors


def _literal_match(expected, actual, method):
    needle, haystack = comparison_text(expected), comparison_text(actual)
    if not needle:
        return False
    if method == "normalized_exact":
        return needle == haystack
    left = r"(?<!\w)" if needle[0].isalnum() or needle[0] == "_" else ""
    right = r"(?!\w)" if needle[-1].isalnum() or needle[-1] == "_" else ""
    return re.search(left + re.escape(needle) + right, haystack) is not None


def _candidate_views(windows, source, language, anchor, boundary, starts, ends):
    matches = []
    for window in windows:
        if (window.language != language
                or any(starts[key] <= anchor['end'] or ends[key] >= boundary['position'] for key in window.owner_ids)
                or not _literal_match(source['required_text'], window.text, source['match_method'])):
            continue
        matches.append(window)
    # Prefer the smallest complete source span; do not pad evidence with nearby text.
    keys = [{(p.node_id, p.content_index) for p in w.parts} for w in matches]
    return [{**asdict(w), 'text': w.text, 'parts': [asdict(p) for p in w.parts],
             'caveats': [*w.caveats, 'legacy_structure_not_certified']}
            for i, w in enumerate(matches) if not any(other < keys[i] for other in keys)]


def _candidate_boundary(anchor, boundary, nodes, starts, language):
    result = dict(boundary)
    for key, node in nodes.items():
        if anchor['end'] < starts[key] < result['position']:
            if node.structure_type in ('section', 'article', 'document'):
                result = {'position': starts[key], 'node_id': key, 'reason': 'entered_structure_boundary'}
            elif node.language != language:
                result = {'position': starts[key], 'node_id': key, 'reason': 'candidate_language_boundary'}
    return result


def _fragment_observations(windows, source, language, anchor, boundary, starts, ends):
    fragments = []
    for index, line in enumerate(source['required_text'].splitlines()):
        if not line.strip():
            continue
        fragment_rule = {**source, 'required_text': line, 'match_method': 'presence'}
        fragments.append({'required_line_index': index, 'required_text': line,
                          'candidates': _candidate_views(windows, fragment_rule, language, anchor, boundary, starts, ends)})
    found = sum(bool(f['candidates']) for f in fragments)
    return {'status': ('all_fragments_located_not_whole_match' if fragments and found == len(fragments)
                       else 'partial_fragments_located' if found else 'no_fragments_located'),
            'policy': 'source_DB_line_diagnostics_only; no order, multiplicity, role or whole-rule approval',
            'fragments': fragments}


def observe_checklist(document: ReviewDocument, rules: list[dict[str, str]], *, language: str = "ENG") -> dict:
    """Inspect a draft's literal evidence, retaining all rules and pending states.

    Caller must load a checked XML bundle and verify the draft Excel/JSON source.
    Provisional structural selectors do not approve legacy-role equivalence.
    """
    if (document.context.source_token, document.context.doc_type, language) != ("ZC_L02", "A2", "ENG"):
        raise ValueError("unsupported profile/language for this pilot")
    if language not in document.context.expected_languages:
        raise ValueError("pilot language absent from profile")
    source_rows = restore_source_rows(rules)
    validate_rows(source_rows)
    units = build_text_unit_index(document).units
    starts, ends, ancestors, parts, nodes = _locations(document)
    anchors = _anchors(document, units, starts, ends)
    windows = build_evidence_windows(document)
    context = {"source_token": document.context.source_token, "region": document.context.region,
               "language": language, "doc_type": document.context.doc_type}
    rows = []
    for source, draft in zip(source_rows, rules, strict=True):
        row = {"check_id": source["check_id"], "common_id": source["common_id"],
               "source_rule": dict(draft), "approval_status": source["status"],
               "status": "needs_review", "migration_status": "pending", "observation": "not_examined",
               "reason": "", "selector_status": "provisional", "heading": None, "scope_end": None,
               "selected_units": [], "rejected_units": [], "matches": [], "candidate_matches": [],
               "candidate_reason": "not_examined", "candidate_scope_end": None,
               "fragment_observations": None}
        rows.append(row)
        if source["status"] != "approved":
            row.update(status="excluded", migration_status="excluded", reason="not_approved")
            continue
        if not metadata_applies(source, context):
            row.update(status="not_applicable", reason="metadata_scope")
            continue
        kind = source["block_type"]
        supported = kind in ("heading", "body", "bullet")
        if not supported or source["match_method"] not in ("presence", "normalized_exact"):
            row["reason"] = "unsupported_selector"
        if source["match_method"] not in ("presence", "normalized_exact"):
            row['candidate_reason'] = 'unsupported_match_method'
            continue
        targets = [a for a in anchors if a["language"] in (language, None)
                   and comparison_text(a["text"]) == comparison_text(source["section_heading"])]
        if len(targets) != 1:
            row['candidate_reason'] = "ambiguous_heading" if targets else "heading_not_found"
            if supported:
                row["reason"] = row['candidate_reason']
            continue
        anchor = targets[0]
        row["heading"] = anchor
        if not anchor["usable_for_observation"] or anchor["language"] != language:
            row['candidate_reason'] = 'unsafe_heading'
            if supported:
                row["reason"] = "unsafe_heading"
            continue
        enclosing = next((key for key in reversed(ancestors[anchor["node_id"]])
                          if nodes[key].structure_type in ("section", "article", "document")), None)
        boundary = {"position": ends[enclosing] if enclosing else max(ends.values()),
                    "node_id": enclosing, "reason": "enclosing_structure_end"}
        for other in anchors:
            if anchor["end"] < other["start"] < boundary["position"]:
                boundary = {"position": other["start"], "node_id": other["node_id"], "reason": "next_heading"}
        for (key, _), position in parts.items():
            if anchor["end"] < position < boundary["position"] and nodes[key].language != language:
                boundary = {"position": position, "node_id": key, "reason": "language_boundary"}
        row["scope_end"] = boundary
        candidate_boundary = _candidate_boundary(anchor, boundary, nodes, starts, language)
        row['candidate_scope_end'] = candidate_boundary
        if not supported:
            row['candidate_matches'] = _candidate_views(windows, source, language, anchor, candidate_boundary, starts, ends)
            row['candidate_reason'] = 'provisional_candidate_found' if row['candidate_matches'] else 'no_bounded_candidate'
            continue
        for unit in units:
            if kind == "heading":
                if unit.owner_id != anchor["node_id"]:
                    continue
            else:
                positions = [parts[(part.node_id, part.content_index)] for part in unit.parts]
                positions.extend(starts[key] for key in unit.visual_node_ids)
                if not positions or max(positions) <= anchor["end"] or min(positions) >= boundary["position"]:
                    continue
                if min(positions) <= anchor["end"] or max(positions) >= boundary["position"]:
                    row["rejected_units"].append({**_unit_view(unit), "reason": "crosses_scope_boundary"})
                    continue
            lineage = [nodes[key].structure_type for key in (*unit.ancestor_ids, unit.owner_id)]
            reason = None
            if any(t in ("table", "table_row", "table_cell") for t in lineage):
                reason = "table_requires_dedicated_selector"
            elif unit.language != language or not unit.ready_for_text_match:
                reason = "unsafe_text_unit"
            elif kind == "body" and unit.structure_type != "paragraph":
                reason = "different_structure"
            elif kind == "bullet" and (unit.structure_type != "list_body" or "list_item" not in lineage):
                reason = "different_structure"
            if reason:
                row["rejected_units"].append({**_unit_view(unit), "reason": reason})
                continue
            view = _unit_view(unit)
            row["selected_units"].append(view)
            if _literal_match(source["required_text"], unit.text, source["match_method"]):
                row["matches"].append(view)
        row["observation"] = "evidence_found" if row["matches"] else "not_found_in_selected_units"
        row["reason"] = "provisional_scope_and_role_require_review"
        if not row['matches'] and kind != 'heading':
            row['candidate_matches'] = _candidate_views(windows, source, language, anchor, candidate_boundary, starts, ends)
            row['candidate_reason'] = 'provisional_candidate_found' if row['candidate_matches'] else 'no_bounded_candidate'
        elif row['matches']:
            row['candidate_reason'] = 'strict_evidence_already_found'
        if not row['matches'] and not row['candidate_matches'] and len(source['required_text'].splitlines()) > 1:
            row['fragment_observations'] = _fragment_observations(windows, source, language, anchor, candidate_boundary, starts, ends)
    return {"schema_version": "checklist-observation/2", "decision_status": "not_evaluated",
            "candidate_policy": {"approval": "never", "max_adjacent_paragraphs": MAX_PARAGRAPHS,
                                 "scope": "same_checked_heading_and_language", "table_rows_joined": False},
            "normalization": NORMALIZATION, "context": asdict(document.context), "language": language,
            "summary": {"rule_count": len(rows), "by_status": dict(Counter(r["status"] for r in rows)),
                        "by_observation": dict(Counter(r["observation"] for r in rows)),
                        "by_reason": dict(Counter(r["reason"] for r in rows)),
                        "rows_with_candidates": sum(bool(r['candidate_matches']) for r in rows)}, "rows": rows}
