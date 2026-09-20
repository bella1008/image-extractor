from tagged_pdf_extractor.domain.africa_rtl_conditions import is_rtl_numeric_condition

def test_observed_arabic_comma_is_valid_model_condition_punctuation():
    assert is_rtl_numeric_condition('R85H("55-"85):30واط,R85H("100):40واط')
    assert is_rtl_numeric_condition('R85H("55-"85):30واط،R85H("100):40واط')

def test_tk_spacing_requires_source_operation_evidence():
    from tagged_pdf_extractor.domain.models import ContentFragment as F,StructureElement as S
    from tagged_pdf_extractor.domain.tk_source_text import restore_tk_text
    parent=S('P','paragraph',children=(F(0,1,('network-',)),F(0,2,('\n','based smart services.')),F(0,3,('7 .125',))))
    children,proof=restore_tk_text((parent,),())
    assert children==(parent,)
    assert not proof.context['changes']

def test_source_span_renderer_rejects_unreviewed_nested_content():
    import pytest
    from xml.etree import ElementTree as E
    from tagged_pdf_extractor.infrastructure.markdown_writer import MarkdownDocumentWriter as W
    table=E.fromstring('<table><attributes><attribute name="review-table" value="source-spans"/></attributes><table_row><table_cell><list><list_item><text>Preserve me</text></list_item></list></table_cell></table_row></table>')
    with pytest.raises(ValueError,match='nested structure'):W._render_table(table,{})
