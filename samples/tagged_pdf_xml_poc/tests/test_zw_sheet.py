"""ZW source preparation retains evidence while repairing verified structure."""
from collections import Counter
from dataclasses import replace
from pathlib import Path
import os
import hashlib
import pytest
from tagged_pdf_extractor.domain.models import ContentFragment, PdfProfile
from tagged_pdf_extractor.infrastructure.pypdf_reader import TaggedPdfReader
from .acceptance_support import require_sample

ROOT = Path(__file__).resolve().parents[3]
RELATIVE = 'samples/SUG_RAW/TV_ZW/BN68-24973D-00_SUG_Y26 TV ALL_ZW_TPE_260327.0.pdf'
SOURCE = Path(os.environ.get('TAGGED_PDF_ZW_SAMPLE', ROOT / RELATIVE))
PROFILE = PdfProfile('ZW_TPE', 'A3', ('TPE',), 1)

def walk(node):
    yield node
    if not isinstance(node, ContentFragment):
        for child in node.children:
            yield from walk(child)

def prepare(document, profile=PROFILE):
    from tagged_pdf_extractor.domain.zw_sheet import prepare_zw_sheet
    return prepare_zw_sheet(document, profile)

@pytest.fixture(scope='module')
def raw():
    require_sample(SOURCE, 'ZW_TPE')
    return replace(TaggedPdfReader().read(SOURCE), source_sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest())

def test_cover_precedes_body_and_original_paths_survive(raw):
    result = prepare(raw)
    article = result.children[0].children[0]
    assert [n.object_ref for n in article.children] == ['61 0 R','62 0 R','63 0 R','64 0 R','65 0 R','66 0 R','59 0 R']
    assert article.children[-1].source_structure_path == (0, 0, 0)
    assert article.children[1].source_structure_path == (0, 0, 2)
    assert result.raw_children is raw.children
    assert result.language == 'TPE'
    assert all(n.language == 'TPE' for n in walk(result) if not isinstance(n, ContentFragment))
    assert Counter(n for n in walk(result) if isinstance(n, ContentFragment)) == Counter(n for n in walk(raw) if isinstance(n, ContentFragment))

def test_rohs_table_retains_verified_source_spans(raw):
    result = prepare(raw)
    table = next(n for n in walk(result) if getattr(n, 'object_ref', None) == '199 0 R')
    assert dict(table.attributes)['review-table'] == 'source-spans'
    assert dict(table.children[1].children[0].attributes)['/RowSpan'] == '2'
    assert len(table.children) == 10

def test_power_continuation_is_owned_by_first_bullet(raw):
    result = prepare(raw)
    parents = {id(c): n for n in walk(result) if not isinstance(n, ContentFragment) for c in n.children}
    continuation = next(n for n in walk(result) if getattr(n, 'object_ref', None) == '125 0 R')
    assert parents[id(continuation)].semantic_role == 'list_body'
    assert continuation.source_structure_path == (0, 0, 0, 8)

@pytest.mark.parametrize('profile', [None, PdfProfile('ZW_TPE','A2',('TPE',),1), PdfProfile('ZW_TPE','A3',('ENG',),1), PdfProfile('TK_ARA','A3',('TPE',),1)])
def test_other_profiles_unchanged(raw, profile):
    assert prepare(raw, profile) is raw

def test_repeated_preparation_rejected(raw):
    with pytest.raises(ValueError, match='already prepared'):
        prepare(prepare(raw))

def test_changed_cover_layout_requires_review(raw):
    article = raw.children[0].children[0]
    changed = replace(article, children=article.children[:2])
    document = replace(raw, children=(replace(raw.children[0], children=(changed,)),))
    with pytest.raises(ValueError, match='cover'):
        prepare(document)

def test_unverified_rohs_span_layout_is_not_enabled(raw):
    def change(node):
        if isinstance(node, ContentFragment):
            return node
        children = tuple(change(c) for c in node.children)
        if getattr(node, 'object_ref', None) == '199 0 R':
            children = children[:-1]
        return replace(node, children=children)
    altered = replace(raw, children=tuple(change(c) for c in raw.children))
    result = prepare(altered)
    table = next(n for n in walk(result) if getattr(n, 'object_ref', None) == '199 0 R')
    assert 'review-table' not in dict(table.attributes)

def test_changed_power_wording_is_not_reparented(raw):
    def change(node):
        if isinstance(node, ContentFragment):
            return replace(node, text_parts=tuple('different source wording' for _ in node.text_parts)) if node.page_index == 0 and node.mcid == 105 else node
        return replace(node, children=tuple(change(c) for c in node.children))
    altered = replace(raw, children=tuple(change(c) for c in raw.children))
    result = prepare(altered)
    parent = next(n for n in walk(result) if not isinstance(n, ContentFragment)
                  and any(getattr(c, 'object_ref', None) == '125 0 R' for c in n.children))
    assert parent.semantic_role == 'section'

@pytest.mark.parametrize('sha', [None, '0' * 64])
def test_unverified_source_revision_requires_review(raw, sha):
    with pytest.raises(ValueError, match='ZW source revision needs review'):
        prepare(replace(raw, source_sha256=sha))

def test_original_declared_languages_remain_in_diagnostic(raw):
    result = prepare(raw)
    diagnostic = next(d for d in result.diagnostics if d.code == 'zw_source_structure')
    assert diagnostic.context['source_document_language'] == 'ko'
    assert {'source_path': (0,), 'language': 'en-GB'} in diagnostic.context['source_element_languages']

def test_consumption_continuation_keeps_one_field(raw, tmp_path):
    result = prepare(raw)
    table = next(n for n in walk(result) if getattr(n, 'object_ref', None) == '432 0 R')
    assert len(table.children) == 5
    cell = table.children[3].children[0]
    continuation = cell.children[-1]
    assert continuation.object_ref == '448 0 R'
    assert continuation.semantic_role == 'section'
    assert continuation.source_structure_path[-2:] == (4, 0)
    text = ''.join(n.text for n in walk(cell) if isinstance(n, ContentFragment))
    assert 'MRA65R95HAX' in text and 'UA98U9000HX' in text
    diagnostic = next(d for d in result.diagnostics if d.code == 'zw_source_structure')
    repair = next(c for c in diagnostic.context['changes'] if c['kind'] == 'consumption_continuation')
    assert repair['source_row_refs'] == ['436 0 R', '437 0 R']
    assert repair['source_cell_refs'] == ['457 0 R', '448 0 R']
    from xml.etree import ElementTree as E
    from tagged_pdf_extractor.infrastructure.xml_writer import XmlDocumentWriter
    from tagged_pdf_extractor.infrastructure.markdown_writer import MarkdownDocumentWriter
    output = tmp_path / 'semantic.xml'
    XmlDocumentWriter().write_semantic(replace(result, children=(table,)), output)
    xml_table = next(n for n in E.parse(output).iter('table') if n.get('object-ref') == '432 0 R')
    rendered = '\n'.join(MarkdownDocumentWriter._render_element(xml_table, {}))
    consumption = rendered.split('- 행 4:', 1)[1].split('- 행 5:', 1)[0]
    assert 'MRA65R95HAX: 300 W' in consumption
    assert 'UA98U9000HX: 510 W' in consumption
    assert '工作溫度' not in consumption

def test_unknown_consumption_topology_requires_review(raw):
    def change(node):
        if isinstance(node, ContentFragment):
            return node
        children = tuple(change(c) for c in node.children)
        if getattr(node, 'object_ref', None) == '432 0 R':
            children = children[:4] + children[5:]
        return replace(node, children=children)
    altered = replace(raw, children=tuple(change(c) for c in raw.children))
    with pytest.raises(ValueError, match='ZW consumption source topology needs review'):
        prepare(altered)
