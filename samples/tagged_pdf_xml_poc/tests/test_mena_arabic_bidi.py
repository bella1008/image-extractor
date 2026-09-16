from xml.etree import ElementTree as E
import pytest
from tagged_pdf_extractor.infrastructure.markdown_writer import MarkdownDocumentWriter as W
from tagged_pdf_extractor.domain.mena_sheet import SOURCE_SHA

def source_span():
    n=E.Element('span',{'language':'ARA','page-index':'1','source-structure-path':'0/0/10/62/0/1'})
    attrs=E.SubElement(n,'attributes')
    for k,v in [('review-inline','ltr-model-token'),('review-source-token','MENA_L02'),('review-source-sha256',SOURCE_SHA)]:
        E.SubElement(attrs,'attribute',{'name':k,'value':v})
    E.SubElement(n,'text',{'page-index':'1','mcid':'1083'}).text='LS03H*'
    return n

def test_mena_source_model_is_isolated_for_rtl_display():
    assert W._event_text_part(source_span())=='<bdi dir="ltr">LS03H&#42;</bdi>'

@pytest.mark.parametrize('field,value',[('source-structure-path','0/1'),('page-index','0'),('language','ENG')])
def test_mena_marker_rejects_wrong_source(field,value):
    n=source_span();n.set(field,value)
    with pytest.raises(ValueError):W._event_text_part(n)

@pytest.mark.parametrize('value',['LS04H*','LS03H','<b>LS03H*</b>'])
def test_mena_marker_rejects_unreviewed_text(value):
    n=source_span();n.find('text').text=value
    with pytest.raises(ValueError):W._event_text_part(n)
