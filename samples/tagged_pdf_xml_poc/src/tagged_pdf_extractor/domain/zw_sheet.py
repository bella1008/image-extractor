"""PDF-verified Taiwan sheet order, table spans and power ownership.

BN68-24973D-00, pages 1–2: original fragments and paths remain auditable.
No wording, inferred headings or translated aliases are introduced here.
"""
from dataclasses import replace
from tagged_pdf_extractor.domain.models import ContentFragment, Diagnostic, StructureElement
from tagged_pdf_extractor.domain.zw_source_text import SOURCE_SHA


def zw_scope(profile):
    return (profile is not None and profile.source_token == 'ZW_TPE'
            and profile.doc_type == 'A3' and profile.languages == ('TPE',))


def _fragments(node):
    if isinstance(node, ContentFragment):
        yield node
    else:
        for child in node.children:
            yield from _fragments(child)


def _text(node):
    return ''.join(''.join(f.text for f in _fragments(node)).split())


_POWER = '•切勿讓牆上插座、延長線超載或讓轉接器超出其電壓和容量。這可能會造成火災或電擊。'
_CONTINUATION = '有關電壓和安培資訊，請參閱手冊的規格部分或者產品上的電源供應標籤。'
_CONSUMPTION_CONTINUATION = (
    'MRA65R95HAX:300W/MRA75R95HAX:390W'
    'MRA85R95HAX:450W'
    'QA65LS03HWX:200W/QA75LS03HWX:250W'
    'QA55QN1EHAX:210W/QA65QN1EHAX:230W'
    'QA75QN1EHAX:270W'
    'UA55M1EHAX:130W/UA65M1EHAX:175W'
    'UA75M1EHAX:230W'
    'UA98U9000HX:510W'
)
_ROHS_SPANS = (
    ((1, 4), (1, 3), (1, 2)),
    ((2, 1), (1, 8)),
    ((1, 1), (1, 1), (1, 2), (1, 1), (1, 2), (1, 1)),
    *(((1, 1), (1, 1), (1, 1), (1, 2), (1, 1), (1, 2), (1, 1)),) * 6,
    ((1, 9),),
)


def prepare_zw_sheet(document, profile):
    if not zw_scope(profile):
        return document
    if document.source_sha256 != SOURCE_SHA:
        raise ValueError('ZW source revision needs review')
    if document.raw_children is not None:
        raise ValueError('ZW sheet already prepared')
    changes = []
    source_languages = []

    def annotate(node, path):
        if isinstance(node, ContentFragment):
            return node
        if node.language is not None:
            source_languages.append({'source_path': path, 'language': node.language})
        return replace(node, language='TPE', source_structure_path=path,
                       children=tuple(annotate(c, (*path, i)) for i, c in enumerate(node.children)))

    def visit(node):
        if isinstance(node, ContentFragment):
            return node
        children = tuple(visit(c) for c in node.children)
        if node.object_ref == '432 0 R':
            topology = tuple((getattr(row, 'object_ref', None),
                              tuple(getattr(c, 'object_ref', None) for c in getattr(row, 'children', ())))
                             for row in children)
            expected = tuple(zip(('433 0 R','434 0 R','435 0 R','436 0 R','437 0 R','438 0 R'),
                                 (('490 0 R',),('481 0 R',),('478 0 R',),('457 0 R',),('448 0 R',),('439 0 R',))))
            if (node.semantic_role != 'table' or topology != expected
                    or any(row.semantic_role != 'table_row' or row.children[0].semantic_role != 'table_cell'
                           for row in children)
                    or not _text(children[3]).startswith('消耗功率消耗功率QA55S85HAE:270W/')
                    or not _text(children[3]).endswith('MRA75R85HAX:280W/MRA85R85HAX:340W')
                    or _text(children[4]) != _CONSUMPTION_CONTINUATION
                    or {f.page_index for row in children[3:5] for f in _fragments(row)} != {1}):
                raise ValueError('ZW consumption source topology needs review')
            first, second = children[3].children[0], children[4].children[0]
            continuation = replace(second, semantic_role='section')
            merged = replace(first, children=(*first.children, continuation))
            changes.append({'kind': 'consumption_continuation',
                            'source_row_refs': [children[3].object_ref, children[4].object_ref],
                            'source_cell_refs': [first.object_ref, second.object_ref],
                            'source_row_paths': [children[3].source_structure_path, children[4].source_structure_path],
                            'source_cell_paths': [first.source_structure_path, second.source_structure_path]})
            children = (*children[:3], replace(children[3], children=(merged,)), children[5])
        if node.semantic_role == 'table' and 'Equipmentname' in _text(node):
            valid = all(isinstance(row, StructureElement) and row.semantic_role == 'table_row'
                        and all(isinstance(cell, StructureElement) and cell.semantic_role in {'table_cell','table_header'}
                                for cell in row.children) for row in children)
            spans = tuple(tuple((dict(cell.attributes).get('/RowSpan', '1'),
                                 dict(cell.attributes).get('/ColSpan', '1'))
                                for cell in row.children) for row in children) if valid else ()
            expected = tuple(tuple((str(r), str(c)) for r, c in row) for row in _ROHS_SPANS)
            if spans == expected:
                node = replace(node, attributes=(*node.attributes, ('review-table', 'source-spans')))
                changes.append({'kind': 'rohs_source_spans', 'source_path': node.source_structure_path})
        repaired = []
        for index, child in enumerate(children):
            following = children[index + 1] if index + 1 < len(children) else None
            if (isinstance(child, StructureElement) and child.source_role == 'UnorderList_1-Bullet'
                    and _text(child) == _CONTINUATION and repaired
                    and isinstance(repaired[-1], StructureElement) and repaired[-1].semantic_role == 'list'
                    and _text(repaired[-1]) == _POWER
                    and isinstance(following, StructureElement) and following.semantic_role == 'list'):
                preceding = repaired[-1]
                item = preceding.children[-1]
                body = item.children[-1] if isinstance(item, StructureElement) else None
                if (isinstance(body, StructureElement) and body.semantic_role == 'list_body'
                        and {f.page_index for n in (preceding, child) for f in _fragments(n)} == {0}):
                    body = replace(body, children=(*body.children, child))
                    item = replace(item, children=(*item.children[:-1], body))
                    repaired[-1] = replace(preceding, children=(*preceding.children[:-1], item))
                    changes.append({'kind': 'power_continuation', 'source_path': child.source_structure_path})
                    continue
            repaired.append(child)
        children = tuple(repaired)
        if node.source_role == 'Article':
            roles = tuple(getattr(c, 'source_role', None) for c in children)
            covers = [c for c in children if any(getattr(x, 'source_role', None) == 'Cover_Title'
                       for x in getattr(c, 'children', ()))]
            if (roles != ('Story', 'Figure', 'Story', 'Story', 'Story', 'Story', 'Story')
                    or len(covers) != 1 or covers[0] is not children[2]
                    or {f.page_index for c in children[1:] for f in _fragments(c)} != {0}
                    or {f.page_index for f in _fragments(children[0])} != {0, 1}):
                raise ValueError('ZW cover/body source layout needs review')
            children = (*children[1:], children[0])
            changes.append({'kind': 'cover_order', 'body_source_path': children[-1].source_structure_path})
        return replace(node, children=children)

    children = tuple(visit(annotate(c, (i,))) for i, c in enumerate(document.children))
    return replace(document, language='TPE', raw_children=document.children, children=children,
                   diagnostics=(*document.diagnostics, Diagnostic('warning', 'zw_source_structure',
                       'Applied PDF-verified ZW sheet structure, retaining raw fragments and source paths.',
                       {'changes': changes, 'source_document_language': document.language,
                        'source_element_languages': source_languages, 'sha256': document.source_sha256})))
