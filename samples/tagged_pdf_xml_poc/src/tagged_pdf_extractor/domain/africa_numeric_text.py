"""Join only complete, geometrically contiguous PDF ActualText decimal tokens."""
from collections import defaultdict
from dataclasses import replace
import re

from tagged_pdf_extractor.domain.models import ContentFragment, Diagnostic


def decimal_source_text(fragment, runs, replacements):
    compact = "".join(fragment.text_parts)
    if (not re.fullmatch(r"[0-9]+\.[0-9]+", compact) or not replacements
            or any(not re.fullmatch(r"[0-9]+", value) for value in replacements)
            or not runs or any(not r.get("glyph_boxes") for r in runs)):
        return None
    boxes = [b for r in runs for b in r["glyph_boxes"]]
    if (max(b[1] for b in boxes) - min(b[1] for b in boxes) > 0.05
            or any(abs(b[0]-a[2]) > 0.15*(a[3]-a[1]) for a,b in zip(boxes,boxes[1:]))):
        return None
    reconstructed, active, index = "", False, 0
    for run in runs:
        if run["actual_text"]:
            if not active:
                if index >= len(replacements):
                    return None
                reconstructed += replacements[index]
                index += 1
        else:
            reconstructed += "".join(run["glyphs"])
        active = run["actual_text"]
    styles = set(fragment.text_styles)
    if reconstructed != compact or index != len(replacements) or len(styles) > 1:
        return None
    return compact


def restore_actual_text_decimals(children, diagnostics):
    runs, replacements = defaultdict(list), defaultdict(list)
    for diagnostic in diagnostics:
        context = diagnostic.context
        if diagnostic.code == "africa_rtl_glyph_source":
            for line in context["lines"]:
                for run in line["runs"]:
                    runs[context["page_index"],run["mcid"]].append(run)
        elif diagnostic.code == "pdf_actual_text_applied":
            for item in context["replacements"]:
                replacements[context["page_index"],item["mcid"]].append(item["actual_text"])
    changes = []
    def visit(node):
        if not isinstance(node,ContentFragment):
            return replace(node,children=tuple(visit(c) for c in node.children))
        key = node.page_index,node.mcid
        text = decimal_source_text(node,runs.get(key,[]),replacements.get(key,[]))
        if text is None or node.text_parts == (text,):
            return node
        changes.append({"page_index":key[0],"mcid":key[1],"source_parts":node.text_parts,"text":text})
        return replace(node,text_parts=(text,),text_styles=node.text_styles[:1],text_bboxes=(node.bbox,))
    return tuple(visit(c) for c in children), Diagnostic("warning","africa_actual_text_decimal_join",
        "Contiguous source decimal glyphs and PDF-authored ActualText form one numeric token.",{"changes":changes})
