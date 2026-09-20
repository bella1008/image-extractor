"""Keep the PDF-observed AFRICA Arabic safety-table hazard label together."""
from tagged_pdf_extractor.domain.africa_book import africa_book_scope
from tagged_pdf_extractor.domain.tk_arabic import tk_ara_scope
from tagged_pdf_extractor.domain.models import ContentFragment, StructureElement, TaggedDocument


_SOURCE_LABEL = 'خطر التعرض لصدمة كهربائية. لا تفتحه.'


def safety_label_paths(document: TaggedDocument) -> frozenset[tuple[int, ...]]:
    profile = document.readability_profile
    if profile is None or not (africa_book_scope(profile) or tk_ara_scope(profile)):
        return frozenset()
    found = set()

    def walk(children, path=()):
        for index, node in enumerate(children):
            if not isinstance(node, StructureElement):
                continue
            node_path = (*path, index)
            if node.semantic_role == 'table' and node.language == 'ARA':
                rows = node.children
                if (len(rows) == 9 and all(isinstance(r, StructureElement)
                        and r.semantic_role == 'table_row' for r in rows)):
                    row = rows[1]
                    if len(row.children) == 1:
                        cell = row.children[0]
                        if (isinstance(cell, StructureElement) and cell.semantic_role == 'table_cell'
                                and dict(cell.attributes).get('/ColSpan') == '2'
                                and len(cell.children) == 1):
                            paragraph = cell.children[0]
                            if (isinstance(paragraph, StructureElement)
                                    and paragraph.semantic_role == 'paragraph'
                                    and paragraph.language == 'ARA'
                                    and all(isinstance(c, ContentFragment) for c in paragraph.children)
                                    and ' '.join(''.join(c.text for c in paragraph.children).split()) == _SOURCE_LABEL):
                                found.add((*node_path, 1, 0, 0))
            walk(node.children, node_path)

    walk(document.children)
    return frozenset(found)
