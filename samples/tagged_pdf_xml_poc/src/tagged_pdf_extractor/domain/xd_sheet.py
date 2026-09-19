"""Exact-source XD Indonesian A3 repairs, with original tree retained."""
from dataclasses import replace
import math
from tagged_pdf_extractor.domain.models import ContentFragment, Diagnostic, StructureElement

SOURCE_SHA = 'f332cca0f65ea88a6b00489d076173a6a5eaf859bc4a1773c05a3153c97dad56'

def xd_scope(profile):
    return profile is not None and (profile.source_token,profile.doc_type,profile.languages) == ('XD_INS','A3',('INS',))

def fragments(node):
    if isinstance(node,ContentFragment):
        yield node
    else:
        for child in node.children:
            yield from fragments(child)

def _text(node):
    return ' '.join(''.join(f.text for f in fragments(node)).split())

def prepare_xd_sheet(document,profile):
    if not xd_scope(profile): return document
    if document.source_sha256 != SOURCE_SHA: raise ValueError('XD source revision needs review')
    if document.raw_children is not None: raise ValueError('XD sheet already prepared')
    evidence = [d.context for d in document.diagnostics if d.code == 'xd_source_operations' and d.context.get('sha256') == SOURCE_SHA]
    if len(evidence) != 1: raise ValueError('XD source operation evidence needs review')
    runs = evidence[0]['runs']
    changes = []

    def visit(node,path,address=False):
        if isinstance(node,ContentFragment):
            key = (node.page_index,node.mcid)
            corrections = {
                (0,447): ('https:/ /www.samsung.com/id/support/servicelocation','https://www.samsung.com/id/support/servicelocation'),
                (1,1076): ('[Peringatan penggunaan Wi-Fi 5,925 - 7 ,125 (atau 6.425) GHz]','[Peringatan penggunaan Wi-Fi 5,925 - 7,125 (atau 6.425) GHz]'),
            }
            if key not in corrections: return node
            before,after = corrections[key]
            proof = [r for r in runs if (r['page_index'],r['mcid']) == key]
            if (node.text.strip() != before or not proof or any(r.get('actual_text') is not False for r in proof)
                or {r.get('operation_index') for r in proof} != {{(0,447):6464,(1,1076):8667}[key]}
                or ''.join(''.join(r['glyphs']) for r in proof) != after):
                raise ValueError('XD source operation evidence needs review')
            changes.append({'kind':'operation_spacing','page_index':key[0],'mcid':key[1],'source_parts':node.text_parts,'operation_index':proof[0]['operation_index']})
            return replace(node,text_parts=tuple(p.replace(before,after) for p in node.text_parts))
        address = address or node.object_ref in {'512 0 R','790 0 R'}
        children = tuple(visit(c,(*path,i),address) for i,c in enumerate(node.children))
        attrs = node.attributes
        if ((address and node.semantic_role == 'paragraph') or node.object_ref in {'391 0 R','771 0 R','768 0 R'}):
            attrs = (*attrs,('review-sentence-breaks','preserve-source'))
        if node.object_ref in {'512 0 R','653 0 R'}:
            expected_rows,header = {'512 0 R':(45,'Kota Alamat'),'653 0 R':(15,'Jenis Barang Waktu Jaminan(Keterangan)')}[node.object_ref]
            if node.semantic_role != 'table' or len(children) != expected_rows or _text(children[0]) != header:
                raise ValueError('XD source table topology needs review')
            if node.object_ref == '512 0 R' and (_text(children[12].children[0]) != 'Jakarta' or dict(children[12].children[0].attributes).get('/RowSpan') != '2'):
                raise ValueError('XD Jakarta source span needs review')
            attrs = (*attrs,('review-table','source-spans'))
            changes.append({'kind':'source_spans','object_ref':node.object_ref,'rows':len(children)})
        if node.object_ref == '495 0 R':
            if len(children) != 80 or any(c.semantic_role != 'paragraph' for c in children):
                raise ValueError('XD cover model source topology needs review')
            boxes = []
            for child in children:
                fs = tuple(fragments(child))
                if len(fs) != 1 or fs[0].page_index != 0: raise ValueError('XD model fragment topology needs review')
                proof = [r for r in runs if r['page_index'] == 0 and r['mcid'] == fs[0].mcid]
                if not proof or ''.join(''.join(r['glyphs']) for r in proof) != _text(child) or any(r.get('actual_text') is not False or r.get('axis_aligned') is not True for r in proof):
                    raise ValueError('XD model operation evidence needs review')
                glyph_boxes = [b for r in proof for b in r['glyph_boxes']]
                if not glyph_boxes or any(len(b)!=4 or any(not isinstance(v,(int,float)) or not math.isfinite(v) for v in b) for b in glyph_boxes):
                    raise ValueError('XD model geometry missing or nonfinite')
                boxes.append((min(b[0] for b in glyph_boxes),min(b[1] for b in glyph_boxes)))
            # Source is column-major. Five aligned x positions and sixteen y positions
            # prove the visually checked matrix; no model names are synthesized.
            for col in range(5):
                column = boxes[col*16:(col+1)*16]
                if any(abs(b[0]-column[0][0]) > 1 for b in column): raise ValueError('XD model column geometry needs review')
                if any(column[i][1] <= column[i+1][1] for i in range(15)): raise ValueError('XD model row order needs review')
                if col and column[0][0] <= boxes[(col-1)*16][0]: raise ValueError('XD model column order needs review')
                if any(abs(column[i][1]-boxes[i][1]) > 1 for i in range(16)): raise ValueError('XD model row alignment needs review')
            rows = tuple(StructureElement('TR','table_row',language='INS',children=tuple(
                StructureElement('TD','table_cell',language='INS',children=(children[col*16+row],)) for col in range(5))) for row in range(16))
            children = (StructureElement('Table','table',language='INS',attributes=(('review-table','source-spans'),('review-table-kind','xd-cover-models')),children=rows),)
            changes.append({'kind':'cover_model_matrix','rows':16,'columns':5,'source_path':path})
        if node.object_ref == '491 0 R':
            preceding,continuation = children[8:10]
            if (preceding.object_ref != '1505 0 R' or preceding.semantic_role != 'list'
                or continuation.object_ref != '1506 0 R'
                or _text(continuation) != 'Lihat bagian spesifikasi daya dalam buku panduan atau label catu daya pada produk untuk informasi tentang tegangan dan arus listrik.'):
                raise ValueError('XD power continuation source topology needs review')
            item = preceding.children[-1]
            body = item.children[-1]
            if body.object_ref != '1986 0 R' or body.semantic_role != 'list_body': raise ValueError('XD power list ownership needs review')
            body = replace(body,children=(*body.children,replace(continuation,semantic_role='span')))
            item = replace(item,children=(*item.children[:-1],body))
            preceding = replace(preceding,children=(*preceding.children[:-1],item))
            children = (*children[:8],preceding,*children[10:])
            changes.append({'kind':'power_continuation','source_path':continuation.source_structure_path})
        if node.source_role == 'Article':
            if tuple(c.object_ref for c in children) != tuple(f'{n} 0 R' for n in range(490,510)) + ('488 0 R',):
                raise ValueError('XD article source order needs review')
            order = (0,2,4,5,7,8,9,10,1,3,6,11,12,13,14,15,16,17,18,19,20)
            children = tuple(children[i] for i in order)
            changes.append({'kind':'cover_order','original_indexes':order})
        return replace(node,children=children,attributes=attrs,source_structure_path=path,language='INS')

    children = tuple(visit(c,(i,)) for i,c in enumerate(document.children))
    if CounterKinds(changes) != {'operation_spacing':2,'source_spans':2,'cover_model_matrix':1,'cover_order':1,'power_continuation':1}:
        raise ValueError('XD source structures missing')
    return replace(document,children=children,raw_children=document.children,readability_profile=profile,
        diagnostics=(*document.diagnostics,Diagnostic('warning','xd_source_structure',
        'Restored source-verified XD cover order/model matrix, merged cells and operation spacing.',
        {'sha256':SOURCE_SHA,'source_token':'XD_INS','doc_type':'A3','language':'INS','changes':changes})))

def CounterKinds(changes):
    from collections import Counter
    return dict(Counter(c['kind'] for c in changes))

def sentence_preservation_paths(document):
    """Exact reviewed addresses and company abbreviations, never language-wide."""
    if document.source_sha256 != SOURCE_SHA or not xd_scope(document.readability_profile): return frozenset()
    if not any(d.code == 'xd_source_structure' and d.context.get('sha256') == SOURCE_SHA for d in document.diagnostics): return frozenset()
    found = set()
    def visit(node,path):
        if isinstance(node,ContentFragment): return
        if dict(node.attributes).get('review-sentence-breaks') == 'preserve-source':
            source = node.source_structure_path
            allowed = (source is not None and (source[:5] in {(0,0,18,1,0),(0,0,8,3,0)}
                or (node.object_ref,source) in {('391 0 R',(0,0,15,9)),('771 0 R',(0,0,12,1,0,1)),('768 0 R',(0,0,12,1,1,1))}))
            if node.language != 'INS' or not allowed: raise ValueError('XD sentence preservation source needs review')
            found.add(path)
        for i,c in enumerate(node.children): visit(c,(*path,i))
    for i,c in enumerate(document.children): visit(c,(i,))
    return frozenset(found)
