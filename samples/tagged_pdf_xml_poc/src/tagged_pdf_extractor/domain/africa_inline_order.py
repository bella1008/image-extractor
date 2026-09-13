"""RTL inline source ordering from glyph advances and original figure rectangles."""
from dataclasses import replace
import unicodedata as ud

from tagged_pdf_extractor.domain.models import ContentFragment, Diagnostic
from tagged_pdf_extractor.domain.inline_icon_policy import parse_unambiguous_bbox


def restore_inline_order(children, diagnostics):
    runs = {}
    for diagnostic in diagnostics:
        if diagnostic.code == "africa_rtl_glyph_source":
            page = diagnostic.context["page_index"]
            for line in diagnostic.context["lines"]:
                for run in line["runs"]:
                    runs.setdefault((page, run["mcid"]), []).append(run)

    def fragments(node):
        if isinstance(node, ContentFragment):
            yield node
        else:
            for child in node.children:
                yield from fragments(child)

    def placement(node):
        leaves = tuple(fragments(node))
        pages = {leaf.page_index for leaf in leaves}
        if len(pages) != 1:
            return None
        if not isinstance(node, ContentFragment) and node.semantic_role == "figure":
            box = parse_unambiguous_bbox(node.attributes)
            return (next(iter(pages)), box, None, True) if box else None
        source = [run for leaf in leaves for run in runs.get((leaf.page_index, leaf.mcid), [])]
        if not source or any(not run.get("glyph_boxes") for run in source):
            return None
        # Combining-only excursions are part of the same base-glyph line.
        base = [run for run in source if any(ud.bidirectional(c) != "NSM"
                for glyph in run["glyphs"] for c in glyph)]
        if not base:
            return None
        baselines = [r["baseline_y"] for r in base]
        if max(baselines) - min(baselines) > 0.05:
            return None
        boxes = [box for run in source for box in run["glyph_boxes"]]
        box = (min(b[0] for b in boxes), min(b[1] for b in boxes),
               max(b[2] for b in boxes), max(b[3] for b in boxes))
        return next(iter(pages)), box, sum(baselines)/len(baselines), False

    changes, skipped = [], []
    def visit(node):
        if isinstance(node, ContentFragment):
            return node
        updated = tuple(visit(child) for child in node.children)
        node = replace(node, children=updated)
        if node.language != "ARA" or node.semantic_role not in {"paragraph", "span", "list_body"} or len(updated) < 2:
            return node
        if not any(ud.bidirectional(c) == "AL" or c == "\u200f" for f in fragments(node) for c in f.text):
            return node
        # Never cross lists, cells, tables, paragraphs or other block boundaries.
        if any(not isinstance(c, ContentFragment) and c.semantic_role not in {"span", "figure", "link"} for c in updated):
            return node
        places = [placement(c) for c in updated]
        if any(p is None for p in places) or len({p[0] for p in places if p}) != 1:
            skipped.append({"source_structure_path":node.source_structure_path, "reason":"incomplete_or_multiline_inline_geometry"})
            return node
        lines = []
        for i, (_, box, baseline, figure) in enumerate(places):
            if figure:
                continue
            match = next((line for line in lines if abs(line["baseline"] - baseline) <= 0.05), None)
            if match is None:
                match = {"baseline":baseline, "height":box[3]-baseline, "indices":[]}
                lines.append(match)
            match["indices"].append(i)
        for i, (_, box, baseline, figure) in enumerate(places):
            if not figure:
                continue
            center_y = (box[1]+box[3])/2
            matches = [line for line in lines if line["baseline"] <= center_y <= line["baseline"]+line["height"]
                       and box[3]-box[1] <= 2.5*line["height"] and box[2]-box[0] <= 5*line["height"]]
            if len(matches) != 1:
                skipped.append({"source_structure_path":node.source_structure_path, "reason":"figure_is_not_unambiguous_inline_icon"})
                return node
            matches[0]["indices"].append(i)
        order = []
        for line in sorted(lines, key=lambda item: -item["baseline"]):
            spatial = sorted(line["indices"], key=lambda i: places[i][1][0])
            # A period is an RTL sentence boundary, except when the source
            # places it directly between two ASCII digit runs on this baseline.
            decimal_points = set()
            for position in range(1, len(spatial) - 1):
                left, point, right = spatial[position - 1:position + 2]
                values = ["".join(f.text for f in fragments(updated[i])).strip()
                          for i in (left, point, right)]
                if (values[1] == "." and all(v and v.isascii() and v.isdecimal()
                        for v in (values[0], values[2]))
                        and abs(places[point][1][0] - places[left][1][2]) <= 0.05 * line["height"]
                        and abs(places[right][1][0] - places[point][1][2]) <= 0.05 * line["height"]):
                    decimal_points.add(point)
            rtl_slashes = set()
            for position in range(len(spatial) - 1):
                slash, following = spatial[position:position + 2]
                value = "".join(f.text for f in fragments(updated[slash])).strip()
                mark = "".join(f.text for f in fragments(updated[following]))
                if (value == "/" and "\u200f" in mark
                        and all(c.isspace() or ud.category(c) == "Cf" for c in mark)
                        and abs(places[following][1][0] - places[slash][1][2]) <= 0.05 * line["height"]):
                    rtl_slashes.add(slash)
            groups = []
            def ltr_candidate(index):
                value = "".join(f.text for f in fragments(updated[index]))
                visible = "".join(c for c in value if ud.category(c) != "Cf").strip()
                return (not places[index][3] and bool(value)
                        and "\u200f" not in value
                        and not (visible == "." and index not in decimal_points)
                        and index not in rtl_slashes
                        and not (any(c in ':;()[]"<>' for c in visible)
                                 and not any(c.isalnum() for c in visible))
                        and visible != "-"
                        and not any(ud.bidirectional(c) in {"AL", "R", "AN"} or c in "<>" for c in visible))
            for i in spatial:
                if (groups and ltr_candidate(i) and all(ltr_candidate(j) for j in groups[-1])
                        and places[i][1][0] - places[groups[-1][-1]][1][2] <= line["height"]):
                    groups[-1].append(i)
                else:
                    groups.append([i])
            for group in reversed(groups):
                # Latin islands read left-to-right inside the surrounding RTL
                # line. Arabic words, UI arrows, figures and wide gaps split them.
                has_latin = any(ud.bidirectional(c) in {"L", "EN"} for i in group
                                for f in fragments(updated[i]) for c in f.text)
                order.extend(group if has_latin else reversed(group))
        if sorted(order) != list(range(len(updated))):
            return node
        if order != list(range(len(updated))):
            changes.append({"source_structure_path":node.source_structure_path,
                "source_children":list(range(len(updated))), "logical_children":order,
                "placements":[{"pdf_page":p[0]+1,"bbox":p[1],"baseline":p[2],"figure":p[3]} for p in places]})
            return replace(node, children=tuple(updated[i] for i in order))
        return node

    result = tuple(visit(child) for child in children)
    return result, Diagnostic("warning", "africa_rtl_inline_order", "RTL inline order follows original PDF glyph and figure placement.",
        {"changes":changes, "skipped":skipped})
