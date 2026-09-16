"""Regressions against the visually reviewed XL English A3 source."""
from collections import Counter
from dataclasses import replace
from pathlib import Path
import os

import pytest

from tagged_pdf_extractor.domain.models import ContentFragment, PdfProfile
from tagged_pdf_extractor.infrastructure.pypdf_reader import TaggedPdfReader
from .acceptance_support import require_sample

SOURCE = Path(os.environ.get('TAGGED_PDF_XL_SAMPLE',
    'C:/Users/bella/image-extractor/samples/SUG_RAW/2_TV_XL/BN68-25031J-00_SUG_Y26 TV ALL_XL_ENG_260306.0.pdf'))
PROFILE = PdfProfile('XL_ENG', 'A3', ('ENG',), 1)

def walk(node):
    yield node
    if not isinstance(node, ContentFragment):
        for child in node.children:
            yield from walk(child)

def elements(document):
    return [n for c in document.children for n in walk(c) if not isinstance(n, ContentFragment)]

@pytest.fixture(scope='module')
def raw():
    require_sample(SOURCE, 'XL_ENG')
    return TaggedPdfReader().read(SOURCE)

def prepared(raw):
    from tagged_pdf_extractor.infrastructure.xl_source_evidence import add_xl_source_evidence
    from tagged_pdf_extractor.domain.xl_sheet import prepare_xl_sheet
    return prepare_xl_sheet(add_xl_source_evidence(raw, PROFILE), PROFILE)

def test_cover_precedes_main_body_and_retains_original_paths(raw):
    doc = prepared(raw)
    article = next(n for n in elements(doc) if n.source_role == 'Article')
    assert [n.object_ref for n in article.children] == [
        '397 0 R', '398 0 R', '399 0 R', '400 0 R', '401 0 R', '402 0 R', '403 0 R', '395 0 R']
    assert article.children[-1].source_structure_path == (0, 0, 1)
    assert doc.raw_children == raw.children

def test_power_continuation_belongs_to_original_overload_bullet(raw):
    doc = prepared(raw)
    nodes = elements(doc)
    continuation = next(n for n in nodes if n.object_ref == '549 0 R')
    parent = next(n for n in nodes if continuation in n.children)
    assert parent.semantic_role == 'list_body'
    assert continuation.source_structure_path == (0, 0, 1, 9)
    assert 'Do not overload wall outlets' in ''.join(f.text for f in walk(parent) if isinstance(f, ContentFragment))

def test_contact_rows_preserve_source_header_and_shared_website_span(raw):
    table = next(n for n in elements(prepared(raw)) if n.object_ref == '417 0 R')
    assert dict(table.attributes)['review-table'] == 'source-spans'
    assert len(table.children) == 15
    assert len(table.children[7].children) == 2
    assert dict(table.children[6].children[2].attributes)['/RowSpan'] == '2'
    assert 'Samsung Service Centre' in ''.join(f.text for f in walk(table.children[0]) if isinstance(f, ContentFragment))

def test_wifi_decimal_is_proven_by_pdf_operations_and_raw_is_unchanged(raw):
    doc = prepared(raw)
    find = lambda cs: next(f for c in cs for f in walk(c) if isinstance(f, ContentFragment) and (f.page_index, f.mcid) == (1, 1054))
    assert '7.125' in find(doc.children).text
    assert '7 .125' in find(doc.raw_children).text
    assert any(d.code == 'xl_source_operations' for d in doc.diagnostics)

def test_all_fragments_tables_and_model_rows_survive(raw):
    doc = prepared(raw)
    key = lambda f: (f.page_index, f.mcid, f.object_ref)
    count = lambda cs: Counter(key(f) for c in cs for f in walk(c) if isinstance(f, ContentFragment))
    assert count(doc.children) == count(raw.children)
    assert len([n for n in elements(doc) if n.semantic_role == 'table']) == 21
    spec = next(n for n in elements(doc) if n.object_ref == '645 0 R')
    assert len(spec.children) == 18
    assert all(len(row.children) == 4 for row in spec.children)

def test_ua43m_weight_decimal_matches_visible_pdf(raw):
    doc = prepared(raw)
    value = next(f for c in doc.children for f in walk(c)
                 if isinstance(f, ContentFragment) and (f.page_index, f.mcid) == (1, 881))
    assert value.text.strip() == '7.3'

def test_nine_model_columns_match_visually_reviewed_specification(raw):
    table = next(n for n in elements(prepared(raw)) if n.object_ref == '645 0 R')
    text = lambda n: ' '.join(''.join(f.text for f in walk(n) if isinstance(f, ContentFragment)).split())
    observed = [tuple(text(table.children[start + row].children[column]) for row in range(6))
                for start in (0, 6, 12) for column in (1, 2, 3)]
    values = [
        ('UA43U8***H, UA43UE8**H','108 cm','96.75 x 56.15 x 8.32 cm None','7.4 kg None'),
        ('UA43M**H','108 cm','96.75 x 56.15 x 8.32 cm None','7.3 kg None'),
        ('UA50U8***H, UA50UE8**H','125 cm','111.08 x 64.38 x 8.64 cm None','8.9 kg None'),
        ('UA50M**H','125 cm','111.08 x 64.38 x 8.64 cm None','8.8 kg None'),
        ('UA55U8***H, UA55UE8**H, UA55M**H','138 cm','122.46 x 70.78 x 8.66 cm None','10.5 kg None'),
        ('UA55M8*H','138 cm','122.46 x 70.78 x 8.66 cm 122.46 x 76.0 x 19.9 cm','10.7 kg 11.0 kg'),
        ('UA65U8***H, UA65UE8**H','163 cm','144.41 x 83.12 x 8.68 cm 144.41 x 88.22 x 22.2 cm','14.3 kg 14.6 kg'),
        ('UA65M**H','163 cm','144.41 x 83.12 x 8.68 cm 144.41 x 88.22 x 22.2 cm','14.5 kg 14.8 kg'),
        ('UA65M8*H','163 cm','144.41 x 83.12 x 8.68 cm 144.41 x 88.22 x 22.2 cm','14.6 kg 14.9 kg'),
    ]
    assert observed == [(model, '3840 x 2160', size, '30 W', dimensions, weight)
                        for model, size, dimensions, weight in values]

def test_final_markdown_exposes_shared_contact_cell_and_intact_decimals(raw, tmp_path):
    from tagged_pdf_extractor.cli import _build_use_case
    use = _build_use_case()
    doc = prepared(raw)
    class ReviewedReader:
        def read(self, path):
            return doc
    use.reader = ReviewedReader()
    use.profile_repository = None
    _, _, artifacts = use.run(SOURCE, tmp_path)
    md = artifacts.semantic_markdown.read_text(encoding='utf8')
    assert md.index('## Simple User Guide') < md.index('## Before Reading')
    assert '<td rowspan="2">www.samsung.com/th/support</td>' in md
    assert '7.3 kg' in md and '7. 3' not in md
    assert '7.125' in md and '7 .' not in md

def test_missing_operation_proof_fails_closed(raw):
    from tagged_pdf_extractor.domain.xl_sheet import SOURCE_SHA, prepare_xl_sheet
    with pytest.raises(ValueError, match='operation evidence'):
        prepare_xl_sheet(replace(raw, source_sha256=SOURCE_SHA), PROFILE)

@pytest.mark.parametrize('profile', [None, PdfProfile('XU_ENG','A3',('ENG',),1),
    PdfProfile('XL_ENG','A2',('ENG',),1), PdfProfile('XL_ENG','A3',('FRA',),1)])
def test_scope_does_not_change_other_profiles(raw, profile):
    from tagged_pdf_extractor.domain.xl_sheet import prepare_xl_sheet
    from tagged_pdf_extractor.infrastructure.xl_source_evidence import add_xl_source_evidence
    assert prepare_xl_sheet(raw, profile) is raw
    assert add_xl_source_evidence(raw, profile) is raw

def test_unreviewed_source_and_repeated_preparation_fail_closed(raw):
    from tagged_pdf_extractor.domain.xl_sheet import prepare_xl_sheet
    with pytest.raises(ValueError, match='revision'):
        prepare_xl_sheet(replace(raw, source_sha256='0' * 64), PROFILE)
    with pytest.raises(ValueError, match='already prepared'):
        prepare_xl_sheet(prepared(raw), PROFILE)
