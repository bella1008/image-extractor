"""The exact Thai source must be readable without guessed word replacements."""
from collections import Counter
from dataclasses import replace
from pathlib import Path
import os
import pytest
from tagged_pdf_extractor.domain.models import ContentFragment, PdfProfile
from tagged_pdf_extractor.infrastructure.pypdf_reader import TaggedPdfReader
from .acceptance_support import require_sample

ROOT = Path(__file__).resolve().parents[3]
RELATIVE = 'samples/SUG_RAW/2_TV_XT/BN68-25031M-00_SUG_Y26 TV ALL_XT_L02_260113.0.pdf'
SOURCE = Path(os.environ.get('TAGGED_PDF_XT_SAMPLE', ROOT / RELATIVE))
if not SOURCE.is_file() and 'TAGGED_PDF_XT_SAMPLE' not in os.environ:
    SOURCE = ROOT.parent.parent / RELATIVE
PROFILE = PdfProfile('XT_L02', 'A2', ('ENG', 'THA'), 2)

def walk(node):
    yield node
    if not isinstance(node, ContentFragment):
        for child in node.children:
            yield from walk(child)

def text(node):
    return ''.join(n.text for n in walk(node) if isinstance(n, ContentFragment))

@pytest.fixture(scope='module')
def raw():
    require_sample(SOURCE, 'XT_L02')
    return TaggedPdfReader().read(SOURCE)

@pytest.fixture(scope='module')
def evidence(raw):
    from tagged_pdf_extractor.infrastructure.xt_source_evidence import add_xt_source_evidence
    return add_xt_source_evidence(raw, PROFILE)

def prepare(document, profile=PROFILE):
    from tagged_pdf_extractor.domain.xt_sheet import prepare_xt_sheet
    return prepare_xt_sheet(document, profile)

def test_cover_precedes_body_but_appendix_stays_after_body(evidence):
    result = prepare(evidence)
    article = result.children[0].children[0]
    assert [n.object_ref for n in article.children] == [
        '612 0 R', '613 0 R', '615 0 R', '616 0 R', '617 0 R', '618 0 R', '619 0 R', '614 0 R', '620 0 R',
        '621 0 R', '97 0 R', '623 0 R', '624 0 R', '625 0 R', '626 0 R', '622 0 R', '610 0 R']
    assert article.children[7].source_structure_path == (0, 0, 2)
    assert article.children[8].source_structure_path == (0, 0, 8)
    assert result.raw_children is evidence.children

def test_thai_glyphs_recovered_without_translations(evidence):
    result = prepare(evidence)
    title = next(n for n in walk(result) if getattr(n, 'object_ref', None) == '623 0 R')
    assert text(title).strip() == 'คู่มือผู้ใช้อย่างง่าย'
    thai = ''.join(n.text for n in walk(result) if isinstance(n, ContentFragment) and n.page_index == 1)
    assert '\ufffd' not in thai
    assert 'ขอขอบคุณที่เลือกซื้อผลิตภัณฑ์ Samsung' in thai
    assert 'www.samsung.com/th/support' in thai
    assert '5.925 - 7.125 (หรือ 6.425) GHz' in thai
    assert 'UA43U8000H' in thai

def test_raw_fragments_and_source_paths_are_preserved(evidence):
    result = prepare(evidence)
    assert Counter((n.page_index, n.mcid, n.object_ref) for n in walk(result) if isinstance(n, ContentFragment)) == Counter(
        (n.page_index, n.mcid, n.object_ref) for n in walk(evidence) if isinstance(n, ContentFragment))
    assert all(n.source_structure_path is not None for n in walk(result) if hasattr(n, 'source_role'))
    assert all(n.language in {'ENG', 'THA'} for n in walk(result)
               if hasattr(n, 'source_role') and len({f.page_index for f in walk(n) if isinstance(f, ContentFragment)}) == 1)

@pytest.mark.parametrize('profile', [None, PdfProfile('XT_L02','A3',('ENG','THA'),2), PdfProfile('XT_L02','A2',('ENG','TUR'),2), PdfProfile('TK_L02','A2',('ENG','THA'),2)])
def test_other_profiles_unchanged(raw, profile):
    assert prepare(raw, profile) is raw

@pytest.mark.parametrize('sha', [None, '0' * 64])
def test_unverified_revision_rejected(evidence, sha):
    with pytest.raises(ValueError, match='source revision'):
        prepare(replace(evidence, source_sha256=sha))

def test_missing_glyph_evidence_fails_closed(evidence):
    with pytest.raises(ValueError, match='glyph evidence'):
        prepare(replace(evidence, diagnostics=()))

def test_repeated_preparation_rejected(evidence):
    with pytest.raises(ValueError, match='already prepared'):
        prepare(prepare(evidence))

def test_effective_font_size_survives_glyph_recovery(evidence):
    result = prepare(evidence)
    original = {(n.page_index, n.mcid): n for n in walk(evidence) if isinstance(n, ContentFragment)}
    for node in walk(result):
        if isinstance(node, ContentFragment) and node.page_index == 1 and node.text.strip():
            sizes = {s.font_size for s in original[node.page_index, node.mcid].text_styles if s.font_size}
            assert {s.font_size for s in node.text_styles} <= sizes

@pytest.mark.parametrize('reference', ['1123 0 R', '336 0 R'])
def test_power_continuation_belongs_to_first_bullet(evidence, reference):
    result = prepare(evidence)
    node = next(n for n in walk(result) if getattr(n, 'object_ref', None) == reference)
    parent = next(n for n in walk(result) if not isinstance(n, ContentFragment) and node in n.children)
    assert parent.semantic_role == 'list_body'
    assert node.source_structure_path[-1] == 9

@pytest.mark.parametrize('reference', ['1093 0 R', '628 0 R'])
def test_contact_table_preserves_source_header_and_data_rows(evidence, reference):
    result = prepare(evidence)
    table = next(n for n in walk(result) if getattr(n, 'object_ref', None) == reference)
    assert dict(table.attributes).get('review-table') == 'source-spans'
    assert [len(r.children) for r in table.children] == [2, 2]
    assert '1282' not in text(table.children[0])
    assert '1282' in text(table.children[1])
    assert 'Samsung' in text(table.children[0])
