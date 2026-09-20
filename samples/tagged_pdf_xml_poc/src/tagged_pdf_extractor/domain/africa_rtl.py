"""Conservative semantic view of observed, whole-word, pure RTL source lines."""
from collections import Counter, defaultdict
from dataclasses import replace
import unicodedata as ud
import math

from tagged_pdf_extractor.domain.models import ContentFragment, Diagnostic


def pure_rtl_line(line, *, rtl_classes=frozenset({'AL'})):
    runs = line["runs"]
    text = "".join(g for r in runs for g in r["glyphs"])
    return (bool(text) and not line["pending_mark"]
            and all(r["mcid"] is not None and not r["actual_text"] and r["axis_aligned"] for r in runs)
            and any(ud.bidirectional(c) in rtl_classes for c in text)
            and all(ud.bidirectional(c) in rtl_classes | {"NSM", "WS"}
                    or c.isspace() or c in ".،؛!؟:-" for c in text))


def fragment_direction(line, *, rtl_classes=frozenset({'AL'})):
    """Additional punctuation is safe within one complete MCID, never across it."""
    runs = line["runs"]
    text = "".join(g for r in runs for g in r["glyphs"])
    if (line["pending_mark"] or not text
            or any(r["mcid"] is None or r["actual_text"] or not r["axis_aligned"] for r in runs)):
        return None
    if text in {"http://", "https://"}:
        return "ltr"
    if (any(ud.bidirectional(c) in rtl_classes for c in text)
            and all(ud.bidirectional(c) in rtl_classes | {"NSM", "WS"} or c.isspace()
                    or c in '.،؛!؟:-%()"' for c in text)):
        return "rtl"
    return None


def restore_rtl_glyph_lines(children, diagnostics, *, rtl_classes=frozenset({'AL'}), languages=('ARA',)):
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
    reset_candidates = {}
    for diagnostic in diagnostics:
        if diagnostic.code != "africa_rtl_glyph_source":
            continue
        page = diagnostic.context["page_index"]
        reset_candidates.update({(page, mcid): value for mcid, value in
                                 _contiguous_mcid_resets(diagnostic.context["lines"]).items()})
        eligible_lines = []
        for line in diagnostic.context["lines"]:
            if pure_rtl_line(line, rtl_classes=rtl_classes):
                eligible_lines.append((line, "rtl"))
            else:
                # A Latin neighbour must not prevent recovery inside a pure
                # Arabic MCID. Mixed lines never authorize cross-MCID reversal.
                groups = []
                for run in line["runs"]:
                    if groups and groups[-1][-1]["mcid"] == run["mcid"]:
                        groups[-1].append(run)
                    else:
                        groups.append([run])
                for runs in groups:
                    candidate = {"runs": runs, "pending_mark": line["pending_mark"]}
                    if direction := fragment_direction(candidate, rtl_classes=rtl_classes):
                        eligible_lines.append((candidate, direction))
        for line, direction in eligible_lines:
            tokens = [(r["mcid"], g) for r in line["runs"] for g in r["glyphs"]]
            groups = []
            for mcid, glyph in (reversed(tokens) if direction == "rtl" else tokens):
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
            proof.append({"page_index": page, "source_runs": line["runs"], "logical_mcids": ids,
                          "direction": direction})
    def letters(text):
        return Counter(c for c in text if not c.isspace())
    def glyph_styles(fragment, *, reset_proven=False):
        return {style for part, style in zip(fragment.text_parts, fragment.text_styles)
                if part.strip("\r\n") and not (reset_proven and style.font_name is None
                    and style.font_size is None and all(ud.category(c).startswith('M') for c in part))}
    replacements = {}
    for key, parts in candidates.items():
        fragment = source.get(key)
        # Multiple baselines or resets under a single MCID require another rule.
        if fragment is None or key in duplicates or len(parts) != 1:
            continue
        text = parts[0]
        if letters(text) == letters(fragment.text) and len(glyph_styles(fragment)) <= 1:
            replacements[key] = text
    reset_proof = []
    reset_keys = set()
    for key, (text, runs) in reset_candidates.items():
        fragment = source.get(key)
        if (key in replacements or key in duplicates or fragment is None
                or letters(text) != letters(fragment.text) or len(glyph_styles(fragment,reset_proven=True)) > 1):
            continue
        replacements[key] = text
        reset_keys.add(key)
        reset_proof.append({"page_index": key[0], "mcid": key[1], "source_runs": runs})
    changes = []
    reorders = []
    def visit(node):
        if isinstance(node, ContentFragment):
            key = (node.page_index, node.mcid)
            value = replacements.get(key)
            styles = glyph_styles(node, reset_proven=key in reset_keys)
            if value is None or len(styles) > 1 or value == node.text:
                return node
            changes.append({"page_index": key[0], "mcid": key[1],
                            "before": node.text, "after": value})
            return replace(node, text_parts=(value,),
                text_styles=(next(iter(styles)),) if styles else (),
                text_bboxes=(node.bbox,))
        updated = [visit(child) for child in node.children]
        if node.semantic_role == "paragraph" and node.language in languages:
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
        {"changes": changes, "reorders": reorders, "source_glyph_lines": proof,
         "contiguous_mcid_resets": reset_proof})
    return result, evidence


def _contiguous_mcid_resets(lines):
    """Recover one complete MCID split by tiny PDF text-position resets.

    Evidence must be one physical baseline, one font and contiguous forward
    glyph advances. Never join distinct columns, MCIDs or actual source lines.
    Keep each PDF glyph's internal codepoints (ligatures/marks) together.
    """
    flattened = [(i, line, run) for i, line in enumerate(lines) for run in line['runs']]
    groups = defaultdict(list)
    for index, (line_id, line, run) in enumerate(flattened):
        groups[run['mcid']].append((index, line_id, line, run))
    result = {}
    for mcid, items in groups.items():
        # One MCID can be split either by a text-position reset or by an
        # author-supplied ActualText combining-mark run on the same baseline.
        # Both cases need at least two contiguous source runs; the geometry and
        # exact character-inventory checks below remain the authority.
        if mcid is None or len(items) < 2:
            continue
        if [i[0] for i in items] != list(range(items[0][0], items[-1][0]+1)):
            continue
        runs = [i[3] for i in items]
        # ActualText around a combining glyph is a PDF shaping aid here.
        # It may not authorize letters; whole-MCID character equality below
        # still checks that no source mark is added or removed.
        direction_runs = [{**r, 'actual_text': False} if r.get('actual_text')
                          and all(ud.category(c).startswith('M') for g in r['glyphs'] for c in g)
                          else r for r in runs]
        if (any(i[2]['pending_mark'] for i in items)
                or len({r.get('font_name') for r in runs}) != 1
                or fragment_direction({'runs': direction_runs, 'pending_mark': False}) != 'rtl'):
            continue
        glyphs = []
        for run in runs:
            boxes = run.get('glyph_boxes')
            if (not boxes or len(boxes) != len(run['glyphs'])
                    or any(len(b)!=4 or not all(math.isfinite(v) for v in b) for b in boxes)):
                break
            glyphs.extend(zip(run['glyphs'], boxes))
        else:
            bases = [(g,b) for g,b in glyphs if not all(ud.category(c).startswith('M') for c in g)]
            if not bases:
                continue
            height = min(b[3]-b[1] for _,b in bases)
            if height <= 0 or max(b[1] for _,b in bases)-min(b[1] for _,b in bases) > height*0.01:
                continue
            if any(right[0] <= left[0] or not -height*0.2 <= right[0]-left[2] <= height*0.2
                   for (_,left),(_,right) in zip(bases,bases[1:])):
                continue
            if not _marks_anchor_to_following_base(glyphs, height):
                continue
            result[mcid] = (''.join(g for g,_ in reversed(glyphs)), runs)
    return result


def _marks_anchor_to_following_base(glyphs, height):
    for index, (glyph, box) in enumerate(glyphs):
        if not all(ud.category(c).startswith('M') for c in glyph):
            continue
        following = next(((g,b) for g,b in glyphs[index+1:]
                          if not all(ud.category(c).startswith('M') for c in g)), None)
        if following is None:
            return False
        base, anchor = following
        if (not all(ud.bidirectional(c)=='AL' for c in base)
                or abs(box[2]-box[0]) > height*0.01
                or not anchor[0]-height*0.05 <= box[0] <= anchor[2]+height*0.05
                or abs(box[1]-anchor[1]) > height*0.3
                or abs((box[3]-box[1])-height) > height*0.01):
            return False
    return True
