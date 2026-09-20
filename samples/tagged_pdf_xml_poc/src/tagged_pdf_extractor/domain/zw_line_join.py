"""Join only operation-proven Taiwan line breaks; preserve source whitespace."""
from dataclasses import replace
import re
import unicodedata
from tagged_pdf_extractor.domain.models import ContentFragment, Diagnostic

SOURCE_SHA = '37e8ef8c16b250463c4a57f5efc199a0f65bd8f9a1e10eacc5562b727f82e99f'

def _cjk(character):
    return bool(character) and unicodedata.east_asian_width(character) in {'W','F'}

def restore_zw_line_join(children, diagnostics):
    records = [r for d in diagnostics if d.code == 'zw_source_operations'
               and d.context.get('sha256') == SOURCE_SHA
               for r in d.context.get('fragments', ())]
    runs = {(r['page_index'], r['mcid']): r['runs'] for r in records}
    changes = []

    def source(fragment):
        values = runs.get((fragment.page_index, fragment.mcid), ())
        if not values or any(r.get('actual_text') or r.get('operation_index') is None for r in values):
            return None
        value = ''.join(''.join(r['glyphs']) for r in values)
        return value if value and '\ufffd' not in value else None

    def repair_fragment(fragment):
        observed = source(fragment)
        if observed is None:
            return fragment
        # Only CJK-to-CJK internal whitespace is a candidate. Full operation
        # equality prevents deletion of any real source space or source glyph.
        removed = set()
        text = fragment.text
        for match in re.finditer(r'(?<=\S)\s+(?=\S)', text):
            if _cjk(text[match.start()-1]) and _cjk(text[match.end()]):
                removed.update(range(match.start(), match.end()))
        parts = []
        offset = 0
        for part in fragment.text_parts:
            parts.append(''.join(c for i,c in enumerate(part, offset) if i not in removed))
            offset += len(part)
        parts = tuple(parts)
        if parts != fragment.text_parts and ''.join(parts).lstrip() == observed:
            changes.append({'kind':'internal_operation_spacing','page_index':fragment.page_index,
                'mcid':fragment.mcid,'source_parts':fragment.text_parts,'parts':parts})
            return replace(fragment, text_parts=parts)
        return fragment

    def visit(node):
        if isinstance(node, ContentFragment):
            return repair_fragment(node)
        result = [visit(child) for child in node.children]
        def inline_leaves(items):
            for item in items:
                if isinstance(item, ContentFragment):
                    yield item
                elif item.semantic_role in {'span', 'link'}:
                    yield from inline_leaves(item.children)
                else:
                    yield None  # paragraph/cell/list/figure is a hard boundary
        replacements = {}
        previous = None
        for child in inline_leaves(result):
            if child is None:
                previous = None
                continue
            if not child.text:
                continue  # dedup retains empty source MCID owners
            if previous is not None and child.page_index == previous.page_index:
                a, b = source(previous), source(child)
                if (a and b and not a[-1].isspace() and not b[0].isspace()
                        and previous.text.lstrip() == a
                        and child.text.lstrip() == b):
                    chinese = _cjk(a[-1]) and _cjk(b[0])
                    url = a.endswith('www.') and b.startswith('samsung.com')
                    if chinese or url:
                        replacements[id(child)] = replace(child, join_previous=True)
                        if not child.join_previous:
                            changes.append({'kind':'source_fragment_boundary','page_index':child.page_index,
                            'previous_mcid':previous.mcid,'mcid':child.mcid,
                            'reason':'cjk_source_boundary' if chinese else 'source_url_boundary'})
            previous = child
        def substitute(item):
            if isinstance(item, ContentFragment):
                return replacements.get(id(item), item)
            if item.semantic_role in {'span', 'link'}:
                return replace(item, children=tuple(substitute(c) for c in item.children))
            return item
        return replace(node, children=tuple(substitute(c) for c in result))

    return tuple(visit(child) for child in children), Diagnostic('warning','zw_line_join',
        'Joined only source-proven CJK and URL boundaries; source spaces and MCID owners retained.',
        {'changes':changes})
