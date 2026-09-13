"""Conservative semantic view of observed, whole-word, pure RTL source lines."""
from collections import Counter, defaultdict
from dataclasses import replace
import unicodedata as ud

from tagged_pdf_extractor.domain.models import ContentFragment, Diagnostic


def pure_rtl_line(line):
    runs = line["runs"]
    text = "".join(g for r in runs for g in r["glyphs"])
    return (bool(text) and not line["pending_mark"]
            and all(r["mcid"] is not None and not r["actual_text"] and r["axis_aligned"] for r in runs)
            and any(ud.bidirectional(c) == "AL" for c in text)
            and all(ud.bidirectional(c) in {"AL", "NSM", "WS"}
                    or c.isspace() or c in ".،؛!؟:-" for c in text))


def restore_rtl_glyph_lines(children, diagnostics):
    """Keep Raw nodes intact; accept only complete MCIDs with equal character bags.

    Cross-MCID reordering is limited to contiguous direct fragments under one
    paragraph, with PDF-observed whitespace at every reordered word boundary.
    """
    source = {}
    duplicates = set()
    def inventory(node):
        if isinstance(node, ContentFragment):
            key = (node.page_index, node.mcid)
            if key in source:
                duplicates.add(key)
            source[key] = node
        else:
            for child in node.children:
                inventory(child)
    for child in children:
        inventory(child)
    candidates = defaultdict(list)
    line_orders = []
    proof = []
    for diagnostic in diagnostics:
        if diagnostic.code != "africa_rtl_glyph_source":
            continue
        page = diagnostic.context["page_index"]
        for line in diagnostic.context["lines"]:
            if not pure_rtl_line(line):
                continue
            tokens = [(r["mcid"], g) for r in line["runs"] for g in r["glyphs"]]
            groups = []
            for mcid, glyph in reversed(tokens):
                if groups and groups[-1][0] == mcid:
                    groups[-1][1] += glyph
                else:
                    groups.append([mcid, glyph])
            ids = [mcid for mcid, _ in groups]
            if len(ids) != len(set(ids)):
                continue
            if any(not (left[-1:].isspace() or right[:1].isspace())
                   for (_, left), (_, right) in zip(groups, groups[1:])):
                continue
            for mcid, value in groups:
                candidates[page, mcid].append(value)
            line_orders.append([(page, mcid) for mcid in ids])
            proof.append({"page_index": page, "source_runs": line["runs"], "logical_mcids": ids})
    def letters(text):
        return Counter(c for c in text if not c.isspace())
    def glyph_styles(fragment):
        return {style for part, style in zip(fragment.text_parts, fragment.text_styles)
                if part.strip("\r\n")}
    replacements = {}
    for key, parts in candidates.items():
        fragment = source.get(key)
        # Multiple baselines or resets under a single MCID require another rule.
        if fragment is None or key in duplicates or len(parts) != 1:
            continue
        text = parts[0]
        if letters(text) == letters(fragment.text) and len(glyph_styles(fragment)) <= 1:
            replacements[key] = text
    changes = []
    reorders = []
    def visit(node):
        if isinstance(node, ContentFragment):
            key = (node.page_index, node.mcid)
            value = replacements.get(key)
            styles = glyph_styles(node)
            if value is None or len(styles) > 1 or value == node.text:
                return node
            changes.append({"page_index": key[0], "mcid": key[1],
                            "before": node.text, "after": value})
            return replace(node, text_parts=(value,),
                text_styles=(next(iter(styles)),) if styles else (),
                text_bboxes=(node.bbox,))
        updated = [visit(child) for child in node.children]
        if node.semantic_role == "paragraph" and node.language == "ARA":
            indexes = {(child.page_index, child.mcid): i for i, child in enumerate(updated)
                       if isinstance(child, ContentFragment)}
            for order in line_orders:
                if len(order) < 2 or not all(k in indexes and k in replacements for k in order):
                    continue
                positions = sorted(indexes[k] for k in order)
                if positions != list(range(positions[0], positions[-1] + 1)):
                    continue
                target = [updated[indexes[k]] for k in order]
                if updated[positions[0]:positions[-1]+1] != target:
                    updated[positions[0]:positions[-1]+1] = target
                    reorders.append({"source_structure_path": node.source_structure_path,
                                     "page_index": order[0][0], "logical_mcids": [k[1] for k in order]})
        return replace(node, children=tuple(updated))
    result = tuple(visit(child) for child in children)
    evidence = Diagnostic("warning", "africa_rtl_glyph_restored",
        "Pure RTL glyph lines restored in Semantic view; mixed/ambiguous lines remain source text.",
        {"changes": changes, "reorders": reorders, "source_glyph_lines": proof})
    return result, evidence
