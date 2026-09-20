from dataclasses import replace
from pathlib import Path

import pytest

from tagged_pdf_extractor.domain.ce_book import ce_book_scope, decimal_source_parts, prepare_ce_book
from tagged_pdf_extractor.domain.models import BookmarkPageBounds, ContentFragment, PdfProfile, StructureElement, TaggedDocument
from tagged_pdf_extractor.infrastructure.ce_source_evidence import add_ce_source_evidence

PROFILE = PdfProfile('CE_L05', 'BOOK', ('RUS', 'ENG', 'KAZ', 'MON', 'KYR'), 5)


def source():
    titles = ('Простое руководство пользователя', 'Simple User Guide',
              'Стандартты пайдаланушы нұсқаулығы', 'Хэрэглэгчийн хялбар гарын авлага',
              'Жөнөкөй колдонуучу нускамасы')
    bookmarks = ('Русский', 'English', 'Қазақ', 'Монгол', 'Кыргызча')
    children = tuple(StructureElement('Cover_Title', 'paragraph', children=(ContentFragment(i*8, 0, (title,)),))
                     for i, title in enumerate(titles))
    contact = StructureElement('Cover_Description-7p', 'paragraph', children=(ContentFragment(43, 0, ('Связывайтесь с Samsung по всему миру',)),))
    return TaggedDocument(Path('sample.pdf'), True, 'ko', (), (*children, contact),
                          bookmark_page_bounds=tuple(BookmarkPageBounds(i+1, i*8+1, i*8+8 if i<4 else 43, title)
                                                     for i,title in enumerate(bookmarks)))


@pytest.mark.parametrize('profile', [
    replace(PROFILE, source_token='AFRICA_L05'), replace(PROFILE, source_token='ZG XN ZT_L05'),
    replace(PROFILE, source_token='ZC_L02'), replace(PROFILE, doc_type='A2'),
    replace(PROFILE, languages=('ENG','RUS','KAZ','MON','KYR')),
    replace(PROFILE, languages=('RUS','ENG','KAZ','MON','FRA')),
])
def test_scope_requires_source_type_and_complete_language_order(profile):
    d = source()
    assert not ce_book_scope(profile)
    assert prepare_ce_book(d, profile) is d
    assert add_ce_source_evidence(d, profile) is d


def test_annotated_semantic_view_does_not_mutate_source():
    d = source()
    result = prepare_ce_book(d, PROFILE)
    assert result.raw_children is d.children
    assert result.children[0].language == 'RUS'
    assert result.children[1].language == 'ENG'
    assert result.children[-1].language == 'RUS'
    assert [n.source_structure_path for n in result.children] == [(i,) for i in range(6)]
    assert d.bookmark_page_bounds[0].start_page_index == 1
    with pytest.raises(ValueError, match='already'):
        prepare_ce_book(result, PROFILE)


@pytest.mark.parametrize('change', ['bookmark', 'cover_title', 'cover_page', 'contact'])
def test_incomplete_or_changed_source_evidence_fails_closed(change):
    d = source()
    if change == 'bookmark':
        d = replace(d, bookmark_page_bounds=(replace(d.bookmark_page_bounds[0], source_title='English'), *d.bookmark_page_bounds[1:]))
    else:
        children = list(d.children)
        index = -1 if change == 'contact' else 0
        fragment = children[index].children[0]
        fragment = replace(fragment, page_index=2) if change == 'cover_page' else replace(fragment, text_parts=('Unknown source',))
        children[index] = replace(children[index], children=(fragment,))
        d = replace(d, children=tuple(children))
    with pytest.raises(ValueError, match='source review'):
        prepare_ce_book(d, PROFILE)


@pytest.mark.parametrize('separator', ['.', ','])
def test_decimal_repair_requires_exact_source_operation(separator):
    fragment = ContentFragment(7, 3, (f'7 {separator}125',))
    run = {'operation_index':12, 'glyphs':[f'7{separator}125'], 'actual_text':False}
    assert decimal_source_parts(fragment, [run]) == (f'7{separator}125',)
    assert decimal_source_parts(fragment, [{**run,'glyphs':[f'7 {separator}125']}]) is None
    assert decimal_source_parts(fragment, [{**run,'glyphs':['7.126']}]) is None
    assert decimal_source_parts(fragment, [{**run,'actual_text':True}]) is None
    assert decimal_source_parts(fragment, [{**run,'operation_index':None}]) is None
    assert decimal_source_parts(fragment, [run,{**run,'operation_index':13}]) is None
    assert decimal_source_parts(fragment, []) is None


def test_public_xml_imports_remain_available():
    from tagged_pdf_extractor.cli import main
    from tagged_pdf_extractor.infrastructure.pypdf_reader import TaggedPdfReader
    from tagged_pdf_extractor.application.extract_document import ExtractDocument
    assert all(callable(x) for x in (main, TaggedPdfReader.read, ExtractDocument.run))
