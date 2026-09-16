"""Source-proven overprint removal; raw fragments remain in raw_structure.xml."""
from dataclasses import replace
import re
from collections import Counter

from tagged_pdf_extractor.domain.models import ContentFragment, Diagnostic

SOURCE_SHA = '37e8ef8c16b250463c4a57f5efc199a0f65bd8f9a1e10eacc5562b727f82e99f'

def restore_zw_text(children, diagnostics):
    records = [r for d in diagnostics if d.code == 'zw_source_operations'
               and d.context.get('sha256') == SOURCE_SHA
               for r in d.context['fragments']]
    runs = {(r['page_index'],r['mcid']):r['runs'] for r in records}
    source_fragments = {}
    def collect(n):
        if isinstance(n,ContentFragment):
            source_fragments[n.page_index,n.mcid] = n
        else:
            for c in n.children: collect(c)
    for c in children: collect(c)
    def signature(rs):
        fields = ('glyphs','glyph_boxes','font_name','font_size','raw_hex','text_matrix','current_matrix')
        return tuple(tuple(repr(r.get(f)) for f in fields) for r in rs)
    removed = {}
    overprints = []
    ordered = sorted(records,key=lambda r:(r['page_index'],r['runs'][0]['operation_index']))
    for a,b in zip(ordered,ordered[1:]):
        # A numbered label may include an author-supplied whitespace ActualText
        # run. It has no visible glyph to overpaint; compare visible runs only.
        ar,br = (tuple(r for r in record['runs'] if ''.join(r['glyphs']).strip()) for record in (a,b))
        ak,bk = (a['page_index'],a['mcid']), (b['page_index'],b['mcid'])
        if (not ar or not br or ak[0] != bk[0] or not all(r.get('render_mode')==1 for r in ar)
            or not all(r.get('render_mode')==0 for r in br)
            or any(r.get('actual_text') or not r.get('glyph_boxes') for r in (*ar,*br))
            or signature(ar)!=signature(br) or ak not in source_fragments or bk not in source_fragments):
            continue
        value = ''.join(''.join(r['glyphs']) for r in ar)
        if any(re.sub(r'\s','',source_fragments[k].text)!=re.sub(r'\s','',value) for k in (ak,bk)):
            continue
        removed[bk] = ak
        overprints.append({'page_index':ak[0],'retained_mcid':ak[1],'removed_mcid':bk[1],
                           'text':value,'stroke_operations':[r['operation_index'] for r in ar],
                           'fill_operations':[r['operation_index'] for r in br]})
    def visit(n):
        if not isinstance(n,ContentFragment):
            return replace(n,children=tuple(visit(c) for c in n.children))
        if (n.page_index,n.mcid) in removed:
            return replace(n,text_parts=(),text_styles=(),text_bboxes=())
        return n
    return tuple(visit(c) for c in children), Diagnostic('warning','zw_source_text',
        'Collapsed only coincident stroke/fill glyph copies; original MCIDs and raw text retained.',
        {'overprints':overprints})

def verified_zw_special_counts(document, baseline, characters):
    """Account for baseline overpainting, never waive missing symbols.

    The independent baseline must equal the untouched raw symbol inventory.
    Recompute stroke/fill pairs from original operations instead of trusting a
    reported removal count. Unknown revisions retain the normal quality gate.
    """
    if document.source_sha256 != SOURCE_SHA or document.raw_children is None:
        return None
    restored, proof = restore_zw_text(document.raw_children, document.diagnostics)
    if not proof.context['overprints']:
        return None
    def counts(nodes):
        result = Counter()
        for n in nodes:
            if isinstance(n,ContentFragment): result.update(n.text)
            else: result.update(counts(n.children))
        return result
    raw, unique = counts(document.raw_children), counts(restored)
    if any(raw[c] != baseline.count(c) for c in characters):
        return None
    return {c:unique[c] for c in characters}
