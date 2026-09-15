"""Source-owned Latin model token must keep its wildcard in RTL display."""
from xml.etree import ElementTree as E
import pytest
from tagged_pdf_extractor.infrastructure.markdown_writer import MarkdownDocumentWriter as W
from tagged_pdf_extractor.domain.tk_arabic_source import VERIFIED_SOURCE_SHA256


def marked_token():
    span=E.Element('span',{'language':'ARA','page-index':'1','source-structure-path':'0/0/1/72/0/1'})
    attrs=E.SubElement(span,'attributes')
    for name,value in [('review-inline','ltr-model-token'),('review-source-token','TK_ARA'),
                       ('review-source-sha256',VERIFIED_SOURCE_SHA256)]:
        E.SubElement(attrs,'attribute',{'name':name,'value':value})
    E.SubElement(span,'text',{'page-index':'1','mcid':'770'}).text='LS03H'
    E.SubElement(span,'text',{'page-index':'1','mcid':'771','join-previous':'source-token'}).text='*'
    return span


def test_model_token_is_one_safe_inline_event_with_plain_source_text():
    span=marked_token()
    parent=E.Element('list_body');parent.append(span)
    assert list(W._list_events(parent,{}))==[('text',span)]
    assert list(W._mixed_content_events(parent,{}))==[('text',span)]
    assert W._element_text(span)=='LS03H*'
    assert W._event_text_part(span)=='<bdi dir="ltr">LS03H&#42;</bdi>'


def test_inline_model_retains_list_and_paragraph_context():
    for tag in ['list_item','paragraph']:
        root=E.Element('list') if tag=='list_item' else E.Element('paragraph')
        parent=E.SubElement(E.SubElement(root,'list_item'),'list_body') if tag=='list_item' else root
        E.SubElement(parent,'text').text='نص '
        parent.append(marked_token())
        E.SubElement(parent,'text').text=' .'
        text='\n'.join(W._render_element(root,{}))
        assert '<bdi dir="ltr">LS03H&#42;</bdi>' in text
        if tag=='list_item':assert text.startswith('- ')


@pytest.mark.parametrize('tag', ['paragraph', 'list_item'])
@pytest.mark.parametrize('suffix', ['', ' text'])
def test_leading_model_token_remains_generated_inline_html(tag, suffix):
    root = E.Element('list' if tag == 'list_item' else 'paragraph')
    parent = E.SubElement(E.SubElement(root, 'list_item'), 'list_body') if tag == 'list_item' else root
    parent.append(marked_token())
    if suffix:
        E.SubElement(parent, 'text').text = suffix
    rendered = '\n'.join(W._render_element(root, {}))
    prefix = '- ' if tag == 'list_item' else ''
    assert rendered == prefix + '<bdi dir="ltr">LS03H&#42;</bdi>' + suffix


@pytest.mark.parametrize('with_marker', [False, True])
def test_source_html_prefix_remains_escaped_beside_trusted_token(with_marker):
    root = E.Element('paragraph')
    E.SubElement(root, 'text').text = '<bdi dir="ltr">source</bdi>'
    if with_marker:
        root.append(marked_token())
    rendered = '\n'.join(W._render_element(root, {}))
    assert rendered.startswith('\\<bdi dir="ltr">source</bdi>')
    if with_marker:
        assert rendered.endswith('<bdi dir="ltr">LS03H&#42;</bdi>')


def marked_source_space():
    span = E.Element('span', {'language': 'ARA', 'page-index': '1', 'source-structure-path': '0/0/1/85/0/1/0/3'})
    attrs = E.SubElement(span, 'attributes')
    for name, value in [('review-whitespace', 'source-boundary'), ('review-whitespace-source-token', 'TK_ARA'),
                        ('review-whitespace-source-sha256', VERIFIED_SOURCE_SHA256)]:
        E.SubElement(attrs, 'attribute', {'name': name, 'value': value})
    E.SubElement(span, 'text', {'page-index': '1', 'mcid': '1026'}).text = '،'
    E.SubElement(span, 'text', {'page-index': '1', 'mcid': '1025'}).text = ' '
    E.SubElement(span, 'text', {'page-index': '1', 'mcid': '1024'}).text = 'R85H'
    return span


@pytest.mark.parametrize('marked', [False, True])
def test_source_spaces_preserved_only_by_reviewed_boundary(marked):
    paragraph = E.Element('paragraph', {'language': 'ARA', 'source-structure-path': '0/1',
        'display-direction': 'rtl', 'direction-reason': 'source-glyph-numeric-condition'})
    E.SubElement(paragraph, 'text').text = 'R85H ("55): 30 واط'
    span = marked_source_space()
    if marked:
        paragraph.append(span)
    else:
        paragraph.extend(span.findall('text'))
    E.SubElement(paragraph, 'text').text = ' ("100): 40 واط'
    rendered = '\n'.join(W._render_element(paragraph, {}))
    assert ('واط، R85H' in rendered) is marked
    assert ('واط، R85H' in W._element_text(paragraph)) is marked


@pytest.mark.parametrize('mutation', ['hash', 'scope', 'path', 'mcid', 'nonspace', 'page', 'nested'])
def test_unverified_source_boundary_marker_is_rejected(mutation):
    span = marked_source_space()
    if mutation == 'hash': span.find('attributes')[2].set('value', '0' * 64)
    if mutation == 'scope': span.find('attributes')[1].set('value', 'AFRICA_L05')
    if mutation == 'path': span.set('source-structure-path', '0/1')
    if mutation == 'mcid': span.findall('text')[1].set('mcid', '999')
    if mutation == 'nonspace': span.findall('text')[1].text = 'X'
    if mutation == 'page': span.findall('text')[1].set('page-index', '0')
    if mutation == 'nested': span.findall('text')[0].tag = 'paragraph'
    with pytest.raises(ValueError): W._element_text(span)


def test_unrelated_whitespace_does_not_gain_numeric_condition_display():
    paragraph = E.Element('paragraph', {'language': 'ENG', 'source-structure-path': '0/1'})
    for part in ['One', ' ', 'Connect']:
        E.SubElement(paragraph, 'text').text = part
    assert W._render_element(paragraph, {}) == [W._element_text(paragraph)]
    paragraph.set('display-direction', 'rtl')
    paragraph.set('direction-reason', 'source-glyph-numeric-condition')
    with pytest.raises(ValueError):
        W._render_element(paragraph, {})


@pytest.mark.parametrize('mutation',['marker','missing_marker','scope','hash','language','page','path','duplicate','html','whitespace','mcid','nested','suffix'])
def test_invalid_inline_model_marker_is_rejected(mutation):
    span=marked_token();attrs=span.find('attributes');text=span.findall('text')
    if mutation=='marker':attrs[0].set('value','untrusted')
    if mutation=='missing_marker':attrs.remove(attrs[0])
    if mutation=='scope':attrs[1].set('value','AFRICA_L05')
    if mutation=='hash':attrs[2].set('value','0'*64)
    if mutation=='language':span.set('language','ENG')
    if mutation=='page':text[1].set('page-index','0')
    if mutation=='path':span.set('source-structure-path','0/1')
    if mutation=='duplicate':E.SubElement(attrs,'attribute',dict(attrs[0].attrib))
    if mutation=='html':text[0].text='<img>'
    if mutation=='whitespace':text[0].text='LS 03H'
    if mutation=='mcid':text[0].set('mcid','999')
    if mutation=='nested':text[0].tag='paragraph'
    if mutation=='suffix':text[1].text='!'
    with pytest.raises(ValueError):W._event_text_part(span)
