import xml.etree.ElementTree as E
import pytest
from tagged_pdf_extractor.domain.sq_mi_sheet import SOURCE_SHA
from tagged_pdf_extractor.domain.sq_mi_inline import validate_sq_inline

def marker(value):
    n=E.Element('span',{'source-structure-path':'0/0/1/72/0/1','page-index':'0','language':'HEB'})
    attrs=E.SubElement(n,'attributes')
    for k,v in {'review-inline':'ltr-model-token','review-source-token':'SQ MI_HEAR','review-source-sha256':SOURCE_SHA,'review-source-owner':'1324 0 R'}.items():
        E.SubElement(attrs,'attribute',name=k,value=v)
    E.SubElement(n,'text',{'page-index':'0','mcid':'356'}).text=value
    return n

def test_source_marker_rejects_changed_model_at_valid_mcid():
    assert validate_sq_inline(marker('R9*H'))=='R9*H'
    with pytest.raises(ValueError,match='model'):validate_sq_inline(marker('WRONG999'))

@pytest.mark.parametrize('field,value',[('mcid','353'),('page-index','1')])
def test_source_marker_rejects_changed_identity(field,value):
    n=marker('R9*H');n.find('text').set(field,value)
    with pytest.raises(ValueError):validate_sq_inline(n)

@pytest.mark.parametrize('field,value',[('review-source-sha256','other'),('review-source-owner','other'),('review-source-token','OTHER')])
def test_source_marker_rejects_wrong_scope(field,value):
    n=marker('R9*H')
    next(a for a in n.findall('attributes/attribute') if a.get('name')==field).set('value',value)
    with pytest.raises(ValueError):validate_sq_inline(n)

def test_source_marker_rejects_duplicate_metadata_and_controls():
    n=marker('R9*H');n.find('attributes').append(E.Element('attribute',name='review-source-owner',value='1324 0 R'))
    with pytest.raises(ValueError):validate_sq_inline(n)
    with pytest.raises(ValueError):validate_sq_inline(marker('R9*H\u202e'))
