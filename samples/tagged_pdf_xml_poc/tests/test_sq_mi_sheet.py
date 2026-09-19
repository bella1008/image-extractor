from pathlib import Path
from dataclasses import replace
import pytest
from tagged_pdf_extractor.domain.models import PdfProfile, ContentFragment
from tagged_pdf_extractor.infrastructure.pypdf_reader import TaggedPdfReader
from tagged_pdf_extractor.domain.tk_sheet import fragments

PROFILE=PdfProfile('SQ MI_HEAR','A2',('HEB','ARA'),2)
SOURCE=next((Path(__file__).resolve().parents[2]/'SUG_RAW'/'TV_SQ_MI').glob('*.pdf'))

@pytest.fixture(scope='module')
def document():
    return TaggedPdfReader().read_for_profile(SOURCE,PROFILE)

def nodes(document):
    def walk(n):
        if isinstance(n,ContentFragment):return
        yield n
        for c in n.children:yield from walk(c)
    return [n for c in document.children for n in walk(c)]

def test_sq_cover_language_headings_and_source_owners(document):
    from tagged_pdf_extractor.domain.sq_mi_sheet import prepare_sq_mi_sheet
    result=prepare_sq_mi_sheet(document,PROFILE)
    assert result.raw_children is document.children
    article=result.children[0].children[0]
    assert [n.object_ref for n in article.children]==['623 0 R','625 0 R','626 0 R','627 0 R','628 0 R','629 0 R','630 0 R','631 0 R','624 0 R','632 0 R','610 0 R','634 0 R','635 0 R','621 0 R','636 0 R','633 0 R']
    assert [n.language for n in article.children]==['HEB']*9+['ARA']*7
    for lang in PROFILE.languages:
        assert sum(n.semantic_role=='heading' and n.language==lang for n in nodes(result))==18
    identity=lambda d:sorted((f.page_index,f.mcid,str(f.object_ref)) for n in d.children for f in fragments(n))
    assert identity(document)==identity(result)

def test_sq_exact_dispatch_and_revision(document):
    from tagged_pdf_extractor.domain.sq_mi_sheet import prepare_sq_mi_sheet
    assert prepare_sq_mi_sheet(document,PdfProfile('OTHER','A2',('HEB','ARA'),2)) is document
    with pytest.raises(ValueError,match='revision'):
        prepare_sq_mi_sheet(replace(document,source_sha256='changed'),PROFILE)

def test_sq_reader_collects_both_rtl_pages(document):
    assert {d.context['page_index'] for d in document.diagnostics if d.code=='africa_rtl_glyph_source'}=={0,1}

def test_sq_visible_chapter_labels(document):
    from tagged_pdf_extractor.domain.sq_mi_sheet import prepare_sq_mi_sheet
    from tagged_pdf_extractor.domain.numbered_heading_promotion import promote_numbered_chapter_headings
    result=promote_numbered_chapter_headings(prepare_sq_mi_sheet(document,PROFILE))
    assert [s.labels for s in result.numbered_heading_series]==[('01','02','03','04','05')]*2
    assert len(result.heading_promotions)==10

def test_sq_hebrew_and_arabic_first_heading_source_order(document):
    from tagged_pdf_extractor.domain.sq_mi_sheet import prepare_sq_mi_sheet
    result=prepare_sq_mi_sheet(document,PROFILE)
    ns=nodes(result)
    for ref,expected in [('1113 0 R','לפני קריאת מדריך פשוט למשתמש זה'),('98 0 R','قبل قراءة الدليل البسيط للمستخدم هذا')]:
        n=next(n for n in ns if n.object_ref==ref)
        actual=''.join(f.text for f in fragments(n))
        assert ''.join(actual.split())==''.join(expected.split())

def test_sq_power_continuations_belong_to_source_bullet(document):
    from tagged_pdf_extractor.domain.sq_mi_sheet import prepare_sq_mi_sheet
    ns=nodes(prepare_sq_mi_sheet(document,PROFILE))
    for ref in ['1121 0 R','348 0 R']:
        n=next(n for n in ns if n.object_ref==ref)
        assert n.semantic_role=='span'
        assert next(p for p in ns if n in p.children).semantic_role=='list_body'

def test_sq_punctuation_and_latin_source_runs(document):
    from tagged_pdf_extractor.domain.sq_mi_sheet import prepare_sq_mi_sheet
    result=prepare_sq_mi_sheet(document,PROFILE)
    fs={(f.page_index,f.mcid):f.text for n in result.children for f in fragments(n)}
    for key,value in {(0,698):'מגן, הסר את הסרט.',(0,1096):'[אמצעי זהירות לשימוש ב-',(1,2218):'حقوق النشر © عام',(0,1090):'7.125',(1,1828):'Customizable Frame',(1,1922):'One Connect'}.items():
        assert fs[key].strip()==value

def test_sq_microphone_source_model_separators(document):
    import re
    from tagged_pdf_extractor.domain.sq_mi_sheet import prepare_sq_mi_sheet
    ns=nodes(prepare_sq_mi_sheet(document,PROFILE))
    for ref in ('1324 0 R','276 0 R'):
        s=''.join(f.text for f in fragments(next(n for n in ns if n.object_ref==ref)))
        s=''.join(c for c in s if not c.isspace() and c not in '\u200e\u200f')
        assert re.search(r'R9\*H/R8\*H/QN1EH/QN7\*H/QN8\*H/QN9\*\*H/S8\*H/S9\*H/M8\*H/M9\*H/U9\*\*\*H/LS03H\*\.',s)

def test_sq_source_heading_levels_and_marked_fragments(document):
    from tagged_pdf_extractor.domain.sq_mi_sheet import prepare_sq_mi_sheet
    result=prepare_sq_mi_sheet(document,PROFILE)
    for n in nodes(result):
        if n.semantic_role=='heading':
            assert n.heading_level==int(n.source_role[-1])
    fs={(f.page_index,f.mcid):f.text for n in result.children for f in fragments(n)}
    assert fs[0,285].rstrip().endswith('מ-')
    assert 'الطُرُز' in fs[1,1991]
    assert 'اعتمادًا' in fs[1,1918]

def test_sq_nested_model_parentheses_use_visible_source_closers(document):
    from tagged_pdf_extractor.domain.sq_mi_sheet import prepare_sq_mi_sheet
    ns=nodes(prepare_sq_mi_sheet(document,PROFILE))
    for ref in ('1425 0 R','146 0 R','381 0 R','1166 0 R'):
        s=''.join(f.text for f in fragments(next(n for n in ns if n.object_ref==ref)))
        assert s.count('(')==s.count(')')==2
        assert 'The Frame (LS03HA)' in s

def test_sq_parenthesis_count_exception_requires_source_evidence(document):
    from tagged_pdf_extractor.domain.sq_mi_sheet import prepare_sq_mi_sheet
    from tagged_pdf_extractor.domain.sq_mi_brackets import verified_sq_special_counts
    d=prepare_sq_mi_sheet(document,PROFILE)
    baseline=''.join(f.text for c in d.raw_children for f in fragments(c))
    assert verified_sq_special_counts(d,baseline,'()')=={'(':69,')':69}
    assert verified_sq_special_counts(replace(d,source_sha256='other'),baseline,'()') is None
    assert verified_sq_special_counts(replace(d,diagnostics=()),baseline,'()') is None
    assert verified_sq_special_counts(d,baseline+'(','()') is None

def test_sq_latin_model_islands_preserve_mcid_traceability(document):
    from tagged_pdf_extractor.domain.sq_mi_sheet import prepare_sq_mi_sheet
    ns=nodes(prepare_sq_mi_sheet(document,PROFILE))
    islands=[n for n in ns if dict(n.attributes).get('review-source-owner') in {'1425 0 R','1166 0 R','146 0 R','381 0 R','1324 0 R','276 0 R'}]
    assert len(islands)==28
    assert sum(''.join(f.text for f in fragments(n))=='The Frame (LS03HA)' for n in islands)==4

def test_sq_actual_xml_markdown_writer_preserves_compact_heading_labels(tmp_path):
    from tagged_pdf_extractor.cli import _build_use_case
    import xml.etree.ElementTree as E
    _,report,_=_build_use_case().run(SOURCE,tmp_path/'out')
    assert report.status=='pass'
    root=E.parse(tmp_path/'out/semantic_document.xml').getroot()
    for language in ('HEB','ARA'):
        assert [n.get('numbered-label') for n in root.iter('heading') if n.get('language')==language and n.get('promotion-reason')]==['01','02','03','04','05']
    md=(tmp_path/'out/semantic_document.md').read_text(encoding='utf8')
    assert '## 0 1' not in md
    assert md.count('<bdi dir="ltr">')==44
    assert 'Wi-Fi\u200f 5.925' in md

def test_sq_wifi_word_space_stays_between_latin_label_and_frequency(document):
    from tagged_pdf_extractor.domain.sq_mi_sheet import prepare_sq_mi_sheet
    ns=nodes(prepare_sq_mi_sheet(document,PROFILE))
    n=next(n for n in ns if n.object_ref=='1207 0 R')
    s=''.join(f.text for f in fragments(n))
    assert 'Wi-Fi\u200f 5.925' in s
