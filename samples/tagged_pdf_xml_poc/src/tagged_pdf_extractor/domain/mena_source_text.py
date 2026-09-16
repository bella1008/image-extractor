"""Source-proven MENA Arabic boundaries, called inside the SHA gate.

No words or model codes are inferred. The one transferred star has an explicit
glyph/MCID ownership audit; raw_children remains the original source inventory.
"""
from collections import Counter
from dataclasses import replace
import math
import unicodedata

from tagged_pdf_extractor.domain.models import ContentFragment, Diagnostic


def repair_mena_source(children, diagnostics):
    runs = {}
    for diagnostic in diagnostics:
        if diagnostic.code == 'africa_rtl_glyph_source' and diagnostic.context.get('page_index') == 1:
            for line in diagnostic.context.get('lines', ()):
                for run in line['runs']:
                    runs.setdefault(run['mcid'], []).append(run)
    changes = []

    def visible(value):
        return ''.join(c for c in value if not c.isspace() and unicodedata.category(c) != 'Cf')

    def source(mcid):
        result = []
        for run in runs.get(mcid, ()):
            glyphs = run.get('glyphs', ())
            # Author-supplied whitespace/RLM cannot supply or relocate a glyph.
            if run.get('actual_text'):
                if visible(''.join(glyphs)):
                    return ()
                continue
            boxes = run.get('glyph_boxes')
            if not boxes or len(boxes) != len(glyphs) or run.get('operation_index') is None:
                return ()
            for glyph, box in zip(glyphs, boxes):
                if len(box) != 4 or not all(math.isfinite(v) for v in box):
                    return ()
                result.append({'glyph': glyph, 'box': box, 'operation_index': run['operation_index'],
                               'font_name': run.get('font_name'), 'font_size': run.get('font_size')})
        return tuple(result)

    def same_line(*groups):
        boxes = [g['box'] for group in groups for g in group]
        return bool(boxes) and max(b[1] for b in boxes)-min(b[1] for b in boxes) <= .05

    def adjacent(left, right):
        return abs(left['box'][2]-right['box'][0]) <= .35

    def update(fragment, value, glyph_evidence=()):
        # These observed owners have uniform source typography. Do not collapse
        # unexpectedly mixed styles into an invented single style.
        styles = [style for part, style in zip(fragment.text_parts, fragment.text_styles) if visible(part)]
        if len(set(styles)) > 1:
            return None
        chosen = styles[0] if styles else None
        # pypdf's synthetic newline may have font size 1. Ignore its style only
        # if it has no visible glyph and no source rectangle.
        if chosen is not None and any(style != chosen and (visible(part) or box is not None)
                for part, style, box in zip(fragment.text_parts, fragment.text_styles,
                                            fragment.text_bboxes or (None,)*len(fragment.text_parts))):
            return None
        box = fragment.bbox
        if glyph_evidence:
            boxes = [g['box'] for g in glyph_evidence]
            box = (min(b[0] for b in boxes), min(b[1] for b in boxes),
                   max(b[2] for b in boxes), max(b[3] for b in boxes))
        return replace(fragment, text_parts=(value,),
                       text_styles=(chosen,) if chosen else (), text_bboxes=(box,) if box else ())

    def visit(node):
        if isinstance(node, ContentFragment):
            return node
        node = replace(node, children=tuple(visit(c) for c in node.children))
        if node.language != 'ARA' or node.object_ref not in {'174 0 R', '517 0 R', '553 0 R', '119 0 R'}:
            return node
        fs = [c for c in node.children if isinstance(c, ContentFragment) and c.page_index == 1]
        by_id = {f.mcid: f for f in fs}
        if len(by_id) != len(fs):
            return node
        replacements = {}
        if node.object_ref == '119 0 R' and 943 in by_id:
            fragment = by_id[943]
            glyphs = source(943)
            if (glyphs and visible(fragment.text) == 'عام©حقوقالنشر'
                    and ''.join(g['glyph'] for g in glyphs) == ' ماع © رشنلا قوقح'
                    and all(len(g['glyph']) == 1 for g in glyphs) and same_line(glyphs)
                    and all(a['box'][0] < b['box'][0] for a, b in zip(glyphs, glyphs[1:]))):
                # This single source line contains Arabic plus the copyright
                # symbol, no Latin/numeric island or combining glyph. Original
                # physical positions prove its logical right-to-left sequence.
                ordered = sorted(glyphs, key=lambda g: -g['box'][0])
                value = ''.join(g['glyph'] for g in ordered)
                if Counter(visible(value)) != Counter(visible(fragment.text)):
                    raise ValueError('MENA copyright source glyph inventory changed')
                candidate = update(fragment, value, glyphs)
                if candidate is not None:
                    changes.append({'kind': 'copyright_source_glyph_order', 'page_index': 1,
                        'object_ref': node.object_ref, 'source_structure_path': node.source_structure_path,
                        'source_glyphs': {'943': glyphs},
                        'logical_glyph_x': [g['box'][0] for g in ordered],
                        'source_whitespace_restored': sum(c.isspace() for c in value)-sum(c.isspace() for c in fragment.text),
                        'fragment_changes': [{'mcid': 943, 'before': fragment.text, 'after': value}]})
                    return replace(node, children=tuple(candidate if c is fragment else c for c in node.children))
        if node.object_ref == '174 0 R' and {1083, 1084, 1085} <= by_id.keys():
            model, separator, previous = (by_id[k] for k in (1083, 1084, 1085))
            a, b, c = (source(k) for k in (1083, 1084, 1085))
            if (a and b and c and visible(model.text) == 'LS03H' and visible(separator.text) == '*/'
                    and visible(previous.text) == 'U9***H'
                    and ''.join(x['glyph'] for x in a) == 'LS03H'
                    and ''.join(x['glyph'] for x in b) == '*/'
                    and ''.join(x['glyph'] for x in c) == 'U9***H'
                    and len(b) == 2 and same_line(a, b, c) and adjacent(a[-1], b[0])
                    and adjacent(b[0], b[1]) and 0 <= c[0]['box'][0]-b[-1]['box'][2] <= 2):
                # A trailing star is visibly adjacent to LS03H, to the left of
                # the separator and the preceding RTL model U9***H.
                values = {1083: model.text + '*', 1084: separator.text.replace('*', '', 1)}
                candidate = {1083: update(model, values[1083], (*a, b[0])),
                             1084: update(separator, values[1084], b[1:])}
                if all(v is not None for v in candidate.values()):
                    replacements = candidate
                    changes.append({'kind': 'model_suffix_source_ownership', 'page_index': 1,
                        'object_ref': node.object_ref, 'source_structure_path': node.source_structure_path,
                        'from_mcid': 1084, 'to_mcid': 1083, 'glyph': '*', 'glyph_box': b[0]['box'],
                        'operation_index': b[0]['operation_index'], 'source_glyphs': {'1083': a, '1084': b, '1085': c},
                        'fragment_changes': [{'mcid': k, 'before': by_id[k].text, 'after': v} for k, v in values.items()]})
        elif node.object_ref == '517 0 R' and {1729, 1730} <= by_id.keys():
            slash, model = by_id[1729], by_id[1730]
            a, b = source(1729), source(1730)
            indices = [node.children.index(x) for x in (slash, model)]
            if (a and b and visible(slash.text) == '/' and visible(model.text) == 'QN1EH'
                    and ''.join(x['glyph'] for x in a) == '/' and ''.join(x['glyph'] for x in b) == 'QN1EH'
                    and same_line(a, b) and adjacent(a[-1], b[0]) and indices[1] == indices[0]+1):
                cs = list(node.children)
                cs[indices[0]], cs[indices[1]] = model, slash
                changes.append({'kind': 'sound_model_boundary_slash', 'page_index': 1,
                    'object_ref': node.object_ref, 'source_structure_path': node.source_structure_path,
                    'source_mcids': [1729, 1730], 'logical_mcids': [1730, 1729],
                    'source_glyphs': {'1729': a, '1730': b}, 'fragment_changes': []})
                return replace(node, children=tuple(cs))
        elif node.object_ref == '553 0 R' and {1889, 1881} <= by_id.keys():
            first, last = by_id[1889], by_id[1881]
            a, b = source(1889), source(1881)
            if (a and b and visible(first.text) == 'احتياطاتاستخدامشبكة['
                    and visible(last.text) == '])جيجاهرتز'
                    and a[-1]['glyph'] == '[' and b[0]['glyph'] == ']' and b[-1]['glyph'] == ')'
                    and same_line(a, b)
                    and a[-1]['box'][0] == max(g['box'][0] for g in a)
                    and b[0]['box'][0] == min(g['box'][0] for g in b)
                    and Counter(visible(''.join(g['glyph'] for g in a))) == Counter(visible(first.text))
                    and Counter(visible(''.join(g['glyph'] for g in b))) == Counter(visible(last.text))):
                prefix = len(first.text)-len(first.text.lstrip())
                value = first.text[:prefix]+'['+first.text[prefix:].replace('[', '', 1)
                end = len(last.text.rstrip())
                tail = last.text[:end].replace(']', '', 1)+']'+last.text[end:]
                candidate = {1889: update(first, value), 1881: update(last, tail)}
                if all(v is not None for v in candidate.values()):
                    replacements = candidate
                    changes.append({'kind': 'wifi_source_bracket_order', 'page_index': 1,
                        'object_ref': node.object_ref, 'source_structure_path': node.source_structure_path,
                        'source_glyphs': {'1889': a, '1881': b},
                        'fragment_changes': [{'mcid': k, 'before': by_id[k].text, 'after': v.text} for k, v in candidate.items()]})
        if replacements:
            before = ''.join(by_id[k].text for k in replacements)
            after = ''.join(f.text for f in replacements.values())
            if Counter(before) != Counter(after):
                raise ValueError('MENA source punctuation repair changed character inventory')
            return replace(node, children=tuple(replacements.get(c.mcid, c) if isinstance(c, ContentFragment) else c for c in node.children))
        return node

    return tuple(visit(c) for c in children), Diagnostic('warning', 'mena_source_text',
        'MENA source glyph geometry proves model separators and bracket ownership; original MCID changes are audited.',
        {'changes': changes})
