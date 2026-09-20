from dataclasses import replace
from pathlib import Path
import os
import pytest
from tagged_pdf_extractor.domain.models import PdfProfile
from tagged_pdf_extractor.infrastructure.pypdf_reader import TaggedPdfReader
from tagged_pdf_extractor.domain.tk_sheet import fragments

PROFILE=PdfProfile('MENA_L02','A2',('ENG','ARA'),2)
SOURCE=Path(os.environ.get('TAGGED_PDF_MENA_SAMPLE', Path(__file__).resolve().parents[3] / 'samples/SUG_RAW/TV_MENA/BN68-25031L-00_SUG_Y26 TV ALL_MENA_L02_260114.0.pdf'))

@pytest.fixture(scope='module')
def document():
    return TaggedPdfReader().read_for_profile(SOURCE,PROFILE)

def test_mena_cover_language_and_raw_owners(document):
    from tagged_pdf_extractor.domain.mena_sheet import prepare_mena_sheet
    result=prepare_mena_sheet(document,PROFILE)
    assert result.raw_children is document.children
    article=result.children[0].children[0]
    assert [n.object_ref for n in article.children]==['651 0 R','652 0 R','654 0 R','655 0 R','656 0 R','657 0 R','658 0 R','653 0 R','659 0 R','121 0 R','661 0 R','662 0 R','649 0 R','663 0 R','660 0 R']
    assert all(n.language==('ENG' if i<8 else 'ARA') for i,n in enumerate(article.children))
    before=[(f.page_index,f.mcid,f.object_ref) for n in document.children for f in fragments(n)]
    after=[(f.page_index,f.mcid,f.object_ref) for n in result.children for f in fragments(n)]
    assert sorted(before,key=repr)==sorted(after,key=repr)

def test_mena_requires_source_revision(document):
    from tagged_pdf_extractor.domain.mena_sheet import prepare_mena_sheet
    with pytest.raises(ValueError,match='revision'):
        prepare_mena_sheet(replace(document,source_sha256='unknown'),PROFILE)

def test_mena_does_not_change_other_profiles(document):
    from tagged_pdf_extractor.domain.mena_sheet import prepare_mena_sheet
    assert prepare_mena_sheet(document,PdfProfile('TK_L02','A2',('ENG','TUR'),2)) is document

def nodes(document):
    from tagged_pdf_extractor.domain.models import ContentFragment
    def walk(n):
        if isinstance(n,ContentFragment):return
        yield n
        for c in n.children:yield from walk(c)
    return [n for c in document.children for n in walk(c)]

def test_mena_power_continuations_keep_bullet_owner(document):
    from tagged_pdf_extractor.domain.mena_sheet import prepare_mena_sheet
    ns=nodes(prepare_mena_sheet(document,PROFILE))
    for ref in ('1175 0 R','390 0 R'):
        continuation=next(n for n in ns if n.object_ref==ref)
        owner=next(n for n in ns if continuation in n.children)
        assert owner.semantic_role=='list_body'
        assert continuation.semantic_role=='span'
        assert continuation.source_structure_path

def test_mena_contact_source_spans(document):
    from tagged_pdf_extractor.domain.mena_sheet import prepare_mena_sheet
    ns=nodes(prepare_mena_sheet(document,PROFILE))
    for ref in ('1056 0 R','647 0 R'):
        table=next(n for n in ns if n.object_ref==ref)
        assert dict(table.attributes)['review-table']=='source-spans'
        assert len(table.children)==14
        assert sum(dict(c.attributes).get('/RowSpan')=='5' for r in table.children for c in r.children)==1

def test_mena_english_wifi_uses_original_operation_decimal(document):
    from tagged_pdf_extractor.domain.mena_sheet import prepare_mena_sheet
    result=prepare_mena_sheet(document,PROFILE)
    f=next(f for c in result.children for f in fragments(c) if (f.page_index,f.mcid)==(0,805))
    assert '5.925 - 7.125 (or 6.425)' in f.text

def test_mena_arabic_original_chapter_digits_promote_like_english(document):
    from tagged_pdf_extractor.domain.mena_sheet import prepare_mena_sheet
    from tagged_pdf_extractor.domain.numbered_heading_promotion import promote_numbered_chapter_headings
    result=promote_numbered_chapter_headings(prepare_mena_sheet(document,PROFILE))
    assert len(result.numbered_heading_series)==2
    assert [s.labels for s in result.numbered_heading_series]==[('01','02','03','04')]*2
    assert len(result.heading_promotions)==8
