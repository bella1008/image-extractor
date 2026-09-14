"""The observed full-width hazard label is one review unit, not body prose."""
from dataclasses import replace
from pathlib import Path

import pytest

from tagged_pdf_extractor.domain.models import ContentFragment, PdfProfile, StructureElement, TaggedDocument
from tagged_pdf_extractor.domain.readability_formatting import apply_readability_formatting

SOURCE_LABEL = 'خطر التعرض لصدمة كهربائية. لا تفتحه.'


def source_document(*, language='ARA', colspan='2', rows=9, text=SOURCE_LABEL, source_token='AFRICA_L05', doc_type='BOOK'):
    def node(role,*children,attributes=()):
        return StructureElement(role,role,language=language,children=children,attributes=attributes)
    label=node('paragraph',ContentFragment(34,104,(text,)))
    label_row=node('table_row',node('table_cell',label,attributes=(('/ColSpan',colspan),)))
    body=node('paragraph',ContentFragment(34,105,('First sentence. Next sentence.',)))
    table=node('table',node('table_row'),label_row,node('table_row',node('table_cell',body)),
        *(node('table_row',node('table_cell',node('figure'))) for _ in range(rows-3)))
    profile=PdfProfile(source_token,doc_type,('ENG','FRA','SPA','POR','ARA'),5)
    return TaggedDocument(Path('manual.pdf'),True,None,(),(table,),readability_profile=profile)


def test_verified_arabic_hazard_label_has_no_sentence_break_but_body_still_does():
    result=apply_readability_formatting(source_document())
    assert [h.child_path for h in result.sentence_break_hints]==[(0,2,0,0,0)]


@pytest.mark.parametrize('kwargs',[
    {'source_token':'OTHER_L05'}, {'doc_type':'A2'}, {'language':'ENG'},
    {'colspan':'1'}, {'rows':8}, {'text':'Another label. More text.'},
])
def test_label_exception_does_not_extend_beyond_verified_profile_and_structure(kwargs):
    result=apply_readability_formatting(source_document(**kwargs))
    assert len(result.sentence_break_hints)==2


def test_same_arabic_text_outside_safety_table_keeps_normal_sentence_policy():
    document=source_document()
    paragraph=document.children[0].children[1].children[0].children[0]
    result=apply_readability_formatting(replace(document,children=(paragraph,)))
    assert len(result.sentence_break_hints)==1
