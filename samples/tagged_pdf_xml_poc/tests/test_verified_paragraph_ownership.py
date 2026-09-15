"""Scope, source-context, and repeat-run controls for verified ownership repair."""
from dataclasses import replace
from pathlib import Path

import pytest

from tagged_pdf_extractor.domain.models import (
    BookmarkPageBounds, ContentFragment as F, PdfProfile, StructureElement as S, TaggedDocument,
)
from tagged_pdf_extractor.domain.verified_paragraph_ownership import repair_verified_paragraph_ownership as repair
from tagged_pdf_extractor.domain.verified_paragraph_source import FEE_SOURCE, POWER_SOURCE

PROFILES = {
    'ZC_L02': PdfProfile('ZC_L02', 'A2', ('ENG', 'C-FRA'), 2),
    'AFRICA_L05': PdfProfile('AFRICA_L05', 'BOOK', ('ENG', 'FRA', 'SPA', 'POR', 'ARA'), 5),
    'ZG XN ZT_L05': PdfProfile('ZG XN ZT_L05', 'BOOK', ('ENG', 'DEU', 'FRA', 'ITA', 'DUT'), 5),
    'XU_ENG': PdfProfile('XU_ENG', 'A3', ('ENG',), 1),
}
KEYS = [*POWER_SOURCE, *FEE_SOURCE]


def example(key):
    profile = PROFILES[key[0]]
    lang = key[2]
    page = profile.languages.index(lang)
    def node(role, semantic, text, ref):
        return S(role, semantic, object_ref=ref, language=lang,
                 children=(F(page, len(ref), (text,), ref),))
    if key in POWER_SOURCE:
        preceding, continuation = POWER_SOURCE[key]
        body = node('LBody', 'list_body', preceding[2:], 'body')
        item = S('LI', 'list_item', language=lang,
                 children=(node('Lbl', 'label', '• ', 'label'), body))
        siblings = (S('L', 'list', language=lang, children=(item,)),
                    node('UnorderList_1-Bullet', 'paragraph', continuation, 'target'),
                    S('L', 'list', language=lang, children=(node('LBody', 'list_body', 'Next warning.', 'next'),)))
    else:
        intro, first, second = FEE_SOURCE[key]
        siblings = (node('Description-L', 'paragraph', intro, 'intro'),
                    node('UnorderList_1-Bullet', 'paragraph', first, 'target'),
                    node('UnorderList_1-Bullet', 'paragraph', second, 'second'))
    sections = tuple(S('Sect', 'section', language=language, children=(
        S('H1', 'heading', heading_level=1, language=language, children=(F(i, 0, ('Source heading',)),)),
        *(siblings if language == lang else ()))) for i, language in enumerate(profile.languages))
    bounds = tuple(BookmarkPageBounds(i + 1, i, i, language) for i, language in enumerate(profile.languages))
    return TaggedDocument(Path('source.pdf'), True, None, (), sections,
                          bookmark_page_bounds=bounds if profile.doc_type == 'BOOK' else ()), profile, page


@pytest.mark.parametrize('key', KEYS)
def test_explicit_profile_language_dispatch_and_idempotence(key):
    document, profile, _ = example(key)
    result = repair(document, profile)
    assert result is not document
    assert result.raw_children is document.children
    assert result.diagnostics[-1].context['changes'][0]['language'] == key[2]
    assert len(result.diagnostics[-1].context['changes']) == 1
    assert repair(result, profile) is result


@pytest.mark.parametrize('key', KEYS)
@pytest.mark.parametrize('change', ['source_token', 'doc_type', 'language_order'])
def test_other_profiles_are_untouched(key, change):
    document, profile, _ = example(key)
    if change == 'source_token':
        profile = replace(profile, source_token='TK_L02')
    elif change == 'doc_type':
        profile = replace(profile, doc_type='A2' if profile.doc_type != 'A2' else 'A3')
    else:
        languages = tuple(reversed(profile.languages)) if profile.language_count > 1 else ('TUR',)
        profile = replace(profile, languages=languages)
    assert repair(document, profile) is document


@pytest.mark.parametrize('key', POWER_SOURCE)
def test_power_does_not_move_continuation_before_trailing_item_text(key):
    document, profile, page = example(key)
    sections = list(document.children)
    siblings = list(sections[page].children)
    listing = siblings[1]
    item = listing.children[0]
    body = item.children[1]
    original = body.children[0]
    prefix, tail = original.text.rsplit(' ', 1)
    body = replace(body, children=(replace(original, text_parts=(prefix + ' ',)),))
    trailing = S('Span', 'span', language=key[2],
                 children=(replace(original, text_parts=(tail,), mcid=99),))
    item = replace(item, children=(item.children[0], body, trailing))
    siblings[1] = replace(listing, children=(item,))
    sections[page] = replace(sections[page], children=tuple(siblings))
    document = replace(document, children=tuple(sections))
    assert repair(document, profile) is document


@pytest.mark.parametrize('key', KEYS)
@pytest.mark.parametrize('change', ['text', 'role', 'language', 'page', 'missing_predecessor', 'non_inline', 'following_page'])
def test_unverified_source_context_is_untouched(key, change):
    document, profile, page = example(key)
    section = document.children[page]
    siblings = list(section.children)
    target = siblings[2]
    if change == 'text':
        target = replace(target, children=(replace(target.children[0], text_parts=('Changed source',)),))
    elif change == 'role':
        target = replace(target, source_role='Description-L')
    elif change == 'language':
        target = replace(target, language='TUR')
    elif change == 'page':
        target = replace(target, children=(replace(target.children[0], page_index=99),))
    elif change == 'non_inline':
        target = replace(target, children=(S('Table', 'table', children=target.children),))
    siblings[2] = target
    if change == 'missing_predecessor':
        siblings.pop(1)
    elif change == 'following_page':
        def move(node):
            return replace(node, page_index=99) if isinstance(node, F) else replace(node, children=tuple(move(c) for c in node.children))
        siblings[3] = move(siblings[3])
    sections = list(document.children)
    sections[page] = replace(section, children=tuple(siblings))
    document = replace(document, children=tuple(sections))
    assert repair(document, profile) is document
