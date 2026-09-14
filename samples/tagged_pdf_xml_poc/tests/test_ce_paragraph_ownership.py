"""Negative source/context controls for the CE-only ownership repair."""
from dataclasses import replace
from pathlib import Path

import pytest

from tagged_pdf_extractor.domain.ce_paragraph_ownership import repair_ce_paragraph_ownership
from tagged_pdf_extractor.domain.ce_paragraph_source import CE_PARAGRAPH_SOURCE
from tagged_pdf_extractor.domain.models import ContentFragment as F, StructureElement as S, TaggedDocument, PdfProfile

PROFILE = PdfProfile('CE_L05', 'BOOK', ('RUS', 'ENG', 'KAZ', 'MON', 'KYR'), 5)


def example(kind):
    a = CE_PARAGRAPH_SOURCE['RUS']
    def node(role, semantic, text, path):
        return S(role, semantic, language='RUS', source_structure_path=path,
                 children=(F(1, path[-1], (text,)),))
    if kind == 'power':
        body = node('LBody', 'list_body', a['power_preceding'][2:], (0, 0, 0, 1))
        label = node('Lbl', 'label', '• ', (0, 0, 0, 0))
        item = S('LI', 'list_item', language='RUS', children=(label, body))
        lead = S('L', 'list', language='RUS', children=(item,))
        target = node('UnorderList_1-Bullet', 'paragraph', a['power_continuation'], (0, 1))
        following = S('L', 'list', language='RUS', children=(node('LBody', 'list_body', 'next', (0, 2, 0)),))
        children = (lead, target, following)
    else:
        children = (node('Description-L', 'paragraph', a['fee_intro'], (0, 0)),
                    *(node('UnorderList_1-Bullet', 'paragraph', text, (0, i+1)) for i, text in enumerate(a['fee_items'])))
    root = S('Sect', 'section', language='RUS', children=children)
    return TaggedDocument(Path('sample.pdf'), True, 'RUS', (), (root,), raw_children=(root,))


@pytest.mark.parametrize('kind', ['power', 'fee'])
@pytest.mark.parametrize('profile', [replace(PROFILE, source_token='ZG XN ZT_L05'),
                                    replace(PROFILE, source_token='ZC_L02'),
                                    replace(PROFILE, source_token='AFRICA_L05'),
                                    replace(PROFILE, doc_type='A2'),
                                    replace(PROFILE, languages=('ENG', 'RUS', 'KAZ', 'MON', 'KYR'))])
def test_other_profiles_never_receive_ce_ownership_repairs(kind, profile):
    d = example(kind)
    assert repair_ce_paragraph_ownership(d, profile) is d


@pytest.mark.parametrize('kind', ['power', 'fee'])
@pytest.mark.parametrize('change', ['text', 'role', 'language', 'page', 'missing_predecessor'])
def test_changed_source_or_context_is_not_reparented(kind, change):
    d = example(kind)
    siblings = list(d.children[0].children)
    n = siblings[1]
    if change == 'text':
        n = replace(n, children=(replace(n.children[0], text_parts=('different source',)),))
    elif change == 'role':
        n = replace(n, source_role='Description-L')
    elif change == 'language':
        n = replace(n, language='ENG')
    elif change == 'page':
        n = replace(n, children=(replace(n.children[0], page_index=2),))
    siblings[1] = n
    if change == 'missing_predecessor':
        siblings.pop(0)
    d = replace(d, children=(replace(d.children[0], children=tuple(siblings)),))
    result = repair_ce_paragraph_ownership(d, PROFILE)
    assert result.children == d.children
    assert result.diagnostics[-1].context['changes'] == []


@pytest.mark.parametrize('kind', ['power', 'fee'])
def test_repair_preserves_source_paths_and_is_structurally_idempotent(kind):
    d = example(kind)
    result = repair_ce_paragraph_ownership(d, PROFILE)
    assert len(result.diagnostics[-1].context['changes']) == 1
    assert result.raw_children is d.raw_children
    again = repair_ce_paragraph_ownership(result, PROFILE)
    assert again.children == result.children
    assert again.diagnostics[-1].context['changes'] == []
