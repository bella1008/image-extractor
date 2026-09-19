"""XD source regressions: inspected Indonesian sheet, not translated aliases."""
from collections import Counter
from dataclasses import replace
from pathlib import Path
import pytest
from tagged_pdf_extractor.domain.models import ContentFragment, PdfProfile
from tagged_pdf_extractor.infrastructure.pypdf_reader import TaggedPdfReader

SOURCE = Path(__file__).resolve().parents[2] / 'SUG_RAW/TV_XD/BN68-25031D-00_SUG_Y26 TV ALL_XD_INS_260113.0.pdf'
PROFILE = PdfProfile('XD_INS', 'A3', ('INS',), 1)

def walk(n):
    yield n
    if not isinstance(n, ContentFragment):
        for c in n.children:
            yield from walk(c)

def nodes(doc):
    return [n for c in doc.children for n in walk(c) if not isinstance(n, ContentFragment)]

def text(n):
    return ' '.join(''.join(f.text for f in walk(n) if isinstance(f, ContentFragment)).split())

@pytest.fixture(scope='module')
def raw():
    return TaggedPdfReader().read(SOURCE)

def prepared(raw):
    from tagged_pdf_extractor.infrastructure.xd_source_evidence import add_xd_source_evidence
    from tagged_pdf_extractor.domain.xd_sheet import prepare_xd_sheet
    return prepare_xd_sheet(add_xd_source_evidence(raw, PROFILE), PROFILE)

def test_cover_precedes_body_and_warranty_stays_separate(raw):
    doc = prepared(raw)
    article = next(n for n in nodes(doc) if n.source_role == 'Article')
    assert [n.object_ref for n in article.children[:10]] == [
        '490 0 R','492 0 R','494 0 R','495 0 R','497 0 R','498 0 R',
        '499 0 R','500 0 R','491 0 R','493 0 R']
    assert next(n for n in nodes(doc) if n.object_ref == '491 0 R').source_structure_path == (0,0,1)
    assert doc.raw_children == raw.children

def test_model_matrix_has_all_eighty_models_in_pdf_rows(raw):
    table = next(n for n in nodes(prepared(raw)) if dict(n.attributes).get('review-table-kind') == 'xd-cover-models')
    assert len(table.children) == 16
    assert all(len(r.children) == 5 for r in table.children)
    assert [text(c) for c in table.children[0].children] == ['UA43U8000H','UA50U8000H','UA55U8000H','UA65U8000H','UA75U8000H']
    assert [text(c) for c in table.children[-1].children] == ['MRA75R95HA','MRA85R95HA','MRA65R95HX','MRA75R95HX','MRA85R95HX']

def test_source_merged_cells_and_exact_headers(raw):
    ns = nodes(prepared(raw))
    city = next(n for n in ns if n.object_ref == '512 0 R')
    warranty = next(n for n in ns if n.object_ref == '653 0 R')
    assert len(city.children) == 45 and len(warranty.children) == 15
    assert dict(city.attributes)['review-table'] == 'source-spans'
    assert dict(warranty.attributes)['review-table'] == 'source-spans'
    assert text(city.children[12].children[0]) == 'Jakarta'
    assert dict(city.children[12].children[0].attributes)['/RowSpan'] == '2'
    contact = next(n for n in ns if n.object_ref == '803 0 R')
    assert text(contact.children[0]) == 'Pusat Servis Samsung Situ Web'
    assert len(contact.children) == 2

def test_spacing_repairs_have_operation_proof_and_raw_stays_original(raw):
    doc = prepared(raw)
    fs = [f for c in doc.children for f in walk(c) if isinstance(f, ContentFragment)]
    assert next(f for f in fs if (f.page_index,f.mcid)==(0,447)).text.strip() == 'https://www.samsung.com/id/support/servicelocation'
    assert next(f for f in fs if (f.page_index,f.mcid)==(1,1076)).text.strip() == '[Peringatan penggunaan Wi-Fi 5,925 - 7,125 (atau 6.425) GHz]'
    assert any(d.code == 'xd_source_operations' for d in doc.diagnostics)
    assert 'https:/ /' in text(raw.children[0]) and '7 ,125' in text(raw.children[0])

def test_all_source_fragments_and_safety_rows_survive(raw):
    doc = prepared(raw)
    counts = lambda cs: Counter((f.page_index,f.mcid,f.object_ref) for c in cs for f in walk(c) if isinstance(f,ContentFragment))
    assert counts(doc.children) == counts(raw.children)
    table = next(n for n in nodes(doc) if n.object_ref == '1989 0 R')
    assert len(table.children) == 9
    assert sum(n.semantic_role == 'figure' for n in walk(table) if not isinstance(n,ContentFragment)) == 6
    assert all(n.source_structure_path is not None for n in nodes(doc) if n.object_ref)

def test_indonesian_spec_model_conditions_are_retained(raw):
    table = next(n for n in nodes(prepared(raw)) if n.object_ref == '1571 0 R')
    assert len(table.children) == 3
    assert 'QN9**H: 7680 x 4320' in text(table)
    assert 'S90H (42"): 20 W, S90H (48"-83"): 40 W' in text(table)
    assert 'LS03HE (98")/LS03HW: 40 W' in text(table)

def test_power_continuation_is_owned_by_source_overload_bullet(raw):
    ns = nodes(prepared(raw))
    continuation = next(n for n in ns if n.object_ref == '1506 0 R')
    parent = next(n for n in ns if continuation in n.children)
    assert parent.semantic_role == 'list_body'
    assert parent.object_ref == '1986 0 R'
    assert continuation.source_structure_path == (0,0,1,9)

def test_final_markdown_retains_address_abbreviations_and_source_punctuation(raw,tmp_path):
    from tagged_pdf_extractor.cli import _build_use_case
    use = _build_use_case()
    _,_,artifacts = use.run(SOURCE,tmp_path)
    md = artifacts.semantic_markdown.read_text(encoding='utf8')
    assert md.index('## Panduan Sederhana untuk Pengguna') < md.index('## Sebelum Membaca')
    assert 'PT.<br>' not in md and 'no.<br>' not in md and 'Jend.<br>' not in md
    assert '<td rowspan="2">Jakarta</td>' in md
    assert '15,,' in md and 'Situ Web' in md
    assert '7,125' in md and 'https://www.samsung.com/id/support/servicelocation' in md

@pytest.mark.parametrize('profile',[None,PdfProfile('XL_ENG','A3',('ENG',),1),PdfProfile('XD_INS','A2',('INS',),1),PdfProfile('XD_INS','A3',('ENG',),1)])
def test_scope_leaves_other_profiles_untouched(raw,profile):
    from tagged_pdf_extractor.domain.xd_sheet import prepare_xd_sheet
    from tagged_pdf_extractor.infrastructure.xd_source_evidence import add_xd_source_evidence
    assert prepare_xd_sheet(raw,profile) is raw
    assert add_xd_source_evidence(raw,profile) is raw

def test_unknown_revision_missing_proof_and_repeat_fail_closed(raw):
    from tagged_pdf_extractor.domain.xd_sheet import prepare_xd_sheet,SOURCE_SHA
    with pytest.raises(ValueError,match='revision'): prepare_xd_sheet(raw,PROFILE)
    with pytest.raises(ValueError,match='operation evidence'): prepare_xd_sheet(replace(raw,source_sha256=SOURCE_SHA),PROFILE)
    with pytest.raises(ValueError,match='already prepared'): prepare_xd_sheet(prepared(raw),PROFILE)

def test_missing_actual_text_proof_fails_closed(raw):
    from tagged_pdf_extractor.infrastructure.xd_source_evidence import add_xd_source_evidence
    from tagged_pdf_extractor.domain.xd_sheet import prepare_xd_sheet
    doc = add_xd_source_evidence(raw,PROFILE)
    diagnostics=[]
    for d in doc.diagnostics:
        if d.code == 'xd_source_operations':
            runs=[{k:v for k,v in r.items() if k != 'actual_text'} for r in d.context['runs']]
            d=replace(d,context={**d.context,'runs':runs})
        diagnostics.append(d)
    with pytest.raises(ValueError,match='operation evidence'):
        prepare_xd_sheet(replace(doc,diagnostics=tuple(diagnostics)),PROFILE)

@pytest.mark.parametrize('tamper',['operation_index','nan_model_geometry'])
def test_tampered_source_operations_fail_closed(raw,tamper):
    from tagged_pdf_extractor.infrastructure.xd_source_evidence import add_xd_source_evidence
    from tagged_pdf_extractor.domain.xd_sheet import prepare_xd_sheet
    doc=add_xd_source_evidence(raw,PROFILE)
    diagnostics=[]
    for d in doc.diagnostics:
        if d.code=='xd_source_operations':
            runs=[]
            for r in d.context['runs']:
                r=dict(r)
                if tamper=='operation_index' and r['mcid']==447: r['operation_index']=1
                if tamper=='nan_model_geometry' and r['page_index']==0 and r['mcid']==0:
                    r['glyph_boxes']=[[float('nan'),*b[1:]] for b in r['glyph_boxes']]
                runs.append(r)
            d=replace(d,context={**d.context,'runs':runs})
        diagnostics.append(d)
    with pytest.raises(ValueError,match='evidence|geometry'):
        prepare_xd_sheet(replace(doc,diagnostics=tuple(diagnostics)),PROFILE)
