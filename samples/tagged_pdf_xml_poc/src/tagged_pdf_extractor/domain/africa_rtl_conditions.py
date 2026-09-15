"""Source-proven neutral punctuation in AFRICA Arabic inch/output conditions."""
from collections import Counter, defaultdict
from dataclasses import replace
import math
import re

from tagged_pdf_extractor.domain.models import ContentFragment, Diagnostic

_MODEL = r"[A-Z][A-Z0-9*]*"
_CONDITION = _MODEL + r'\("\d+(?:-"\d+)?\)'
_CLAUSE = _CONDITION + r"(?:/" + _MODEL + r")?:\d+واط"
_PATTERN = re.compile(_CLAUSE + r"(?:," + _CLAUSE + r")?")
# Wording observed in this PDF; it is never translated or substituted.
_WIFI_PATTERN = re.compile(r"\[احتياطاتاستخدامشبكةWi-Fiبتردد\d+\.\d+-\d+\.\d+\(أو\d+\.\d+\)جيجاهرتز\]")


def condition_key(text):
    return "".join(c for c in text if not c.isspace() and c not in "\u200e\u200f")


def is_rtl_numeric_condition(text):
    key = condition_key(text)
    # TK source uses U+060C between clauses. Validate its grammar without
    # replacing that source punctuation in XML or Markdown.
    return bool(_PATTERN.fullmatch(key.replace('،', ',')) or _WIFI_PATTERN.fullmatch(key))


def _visible_glyphs(runs):
    result = []
    for run in runs:
        boxes = run.get("glyph_boxes")
        if not boxes or len(run["glyphs"]) != len(boxes):
            return None
        for glyph, box in zip(run["glyphs"], boxes):
            if condition_key(glyph):
                if not all(math.isfinite(v) for v in box):
                    return None
                result.append((glyph, box))
    return result


def _ltr_neutral_glyphs(runs):
    glyphs = _visible_glyphs(runs)
    return bool(glyphs and all(len(g) == 1 for g, _ in glyphs) and all(
        b[0] >= a[0] and b[0]-a[2] <= 0.5*(a[3]-a[1])
        for (_,a),(_,b) in zip(glyphs,glyphs[1:])))


def restore_wifi_brackets(node, source_runs):
    """Move bracket glyphs from physical MCID edges to logical paragraph edges."""
    if (node.language != "ARA" or node.semantic_role != "paragraph"
            or len(node.children) < 2 or any(not isinstance(c,ContentFragment) for c in node.children)):
        return node
    first, last = node.children[0], node.children[-1]
    values = ["".join(c.text_parts) for c in node.children]
    if (not values[0].rstrip().endswith('[') or not values[-1].lstrip().startswith(']')
            or len({c.page_index for c in node.children}) != 1):
        return node
    for child, bracket, right_edge in [(first,'[',True),(last,']',False)]:
        runs = source_runs.get((child.page_index,child.mcid),[])
        glyphs = _visible_glyphs(runs)
        if not glyphs or len(set(child.text_styles)) > 1:
            return node
        source = "".join(g for g,_ in glyphs)
        if Counter(condition_key(source)) != Counter(condition_key("".join(child.text_parts))):
            return node
        brackets = [b for g,b in glyphs if g == bracket]
        if (len(brackets) != 1 or max(b[1] for _,b in glyphs)-min(b[1] for _,b in glyphs)>0.05
                or brackets[0][0] != (max if right_edge else min)(b[0] for _,b in glyphs)):
            return node
    values[0] = '[' + values[0].replace('[','',1)
    values[-1] = values[-1].replace(']','',1) + ']'
    if not _WIFI_PATTERN.fullmatch(condition_key("".join(values))):
        return node
    children = list(node.children)
    for index in [0,len(children)-1]:
        child = children[index]
        children[index] = replace(child,text_parts=(values[index],),text_styles=child.text_styles[:1],
                                  text_bboxes=(child.bbox,) if child.text_bboxes else ())
    return replace(node,children=tuple(children),display_direction="rtl")


def restore_condition_paragraph(node, source_runs):
    if (node.language != "ARA" or node.semantic_role != "paragraph"
            or not node.children or any(not isinstance(c, ContentFragment) for c in node.children)):
        return node
    original = node.children
    joined = "".join("".join(c.text_parts) for c in original)
    if '"(' not in joined or "واط" not in joined or len({c.page_index for c in original}) != 1:
        return node
    bounds = {}
    for child in original:
        if not condition_key("".join(child.text_parts)):
            continue
        runs = source_runs.get((child.page_index, child.mcid), [])
        if not runs or any(not r.get("glyph_boxes") for r in runs):
            return node
        boxes = [b for r in runs for b in r["glyph_boxes"]]
        if not all(math.isfinite(v) for b in boxes for v in b):
            return node
        bounds[child.mcid] = (min(b[0] for b in boxes), max(b[2] for b in boxes),
                              min(b[1] for b in boxes), max(b[1] for b in boxes))
    if max(b[3] for b in bounds.values()) - min(b[2] for b in bounds.values()) > 0.05:
        return node
    proposed = []
    for child in original:
        value = "".join(child.text_parts)
        key = condition_key(value)
        if key in {'"(', ':)', '"-', '/)'}:
            runs = source_runs[child.page_index, child.mcid]
            source = "".join("".join(r["glyphs"]) for r in runs)
            if ("\u200f" not in value or condition_key(source) != key or len(set(child.text_styles)) > 1
                    or not _ltr_neutral_glyphs(runs)):
                return node
            child = replace(child, text_parts=tuple(p[::-1] for p in reversed(child.text_parts)),
                            text_styles=child.text_styles[::-1], text_bboxes=child.text_bboxes[::-1])
        proposed.append(child)
    # This comma is physically right of its model; keep it outside the Latin island.
    for i in range(1, len(proposed)):
        comma, model = proposed[i], proposed[i-1]
        if (condition_key("".join(comma.text_parts)) == ","
                and re.fullmatch(_MODEL, condition_key("".join(model.text_parts)))):
            if bounds[comma.mcid][0] < bounds[model.mcid][1] - 0.02:
                return node
            source = "".join("".join(r["glyphs"]) for r in source_runs[comma.page_index,comma.mcid])
            if condition_key(source) != ",":
                return node
            proposed[i-1], proposed[i] = comma, model
    rendered = "".join("".join(c.text_parts) for c in proposed)
    if not _PATTERN.fullmatch(condition_key(rendered)) or Counter(rendered) != Counter(joined):
        return node
    return replace(node, children=tuple(proposed), display_direction="rtl")


def restore_rtl_conditions(children, diagnostics):
    source_runs = defaultdict(list)
    for diagnostic in diagnostics:
        if diagnostic.code == "africa_rtl_glyph_source":
            for line in diagnostic.context["lines"]:
                for run in line["runs"]:
                    source_runs[diagnostic.context["page_index"],run["mcid"]].append(run)
    changes = []
    def visit(node):
        if isinstance(node, ContentFragment):
            return node
        node = replace(node, children=tuple(visit(c) for c in node.children))
        restored = restore_condition_paragraph(node, source_runs)
        if restored == node:
            restored = restore_wifi_brackets(node, source_runs)
        if restored != node:
            changes.append({"source_structure_path":node.source_structure_path,
                "before":[{"mcid":c.mcid,"parts":c.text_parts} for c in node.children],
                "after":[{"mcid":c.mcid,"parts":c.text_parts} for c in restored.children]})
        return restored
    return tuple(visit(c) for c in children), Diagnostic("info", "africa_rtl_numeric_conditions",
        "Source glyphs prove neutral punctuation order and RTL numeric-condition display.", {"changes":changes})
