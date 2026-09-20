"""Only source-pinned TK separators may bypass ordinary fragment joining."""
from dataclasses import replace
from xml.etree import ElementTree as X
import pytest
from tagged_pdf_extractor.domain.models import ContentFragment as F, StructureElement as E
from tagged_pdf_extractor.domain.tk_arabic_source import (
    VERIFIED_SOURCE_SHA256, VERIFIED_SPACE_BOUNDARIES, repair_tk_source,
)
from tagged_pdf_extractor.infrastructure.markdown_writer import MarkdownDocumentWriter as W


def source_case(ref):
    path, previous, space, following = VERIFIED_SPACE_BOUNDARIES[ref]
    return E('Description-L', 'paragraph', object_ref=ref, page_index=1,
             language='ARA', source_structure_path=path, children=(
                 F(1, previous, (':',)),
                 F(1, space, ('\n ' if ref == '282 0 R' else ' ',)),
                 F(1, following, ('30',))))


@pytest.mark.parametrize('ref', VERIFIED_SPACE_BOUNDARIES)
def test_source_separator_wrapper_keeps_original_fragments(ref):
    node = source_case(ref)
    result, _ = repair_tk_source((node,), (), VERIFIED_SOURCE_SHA256)
    assert result[0].children[0].semantic_role == 'span'
    assert result[0].children[0].children == node.children


@pytest.mark.parametrize('mutation', ['digest', 'path', 'page', 'mcid', 'role', 'space', 'barrier'])
def test_uncertain_source_separator_is_unchanged(mutation):
    node = source_case('297 0 R')
    digest = VERIFIED_SOURCE_SHA256
    if mutation == 'digest': digest = 'unknown-revision'
    if mutation == 'path': node = replace(node, source_structure_path=(9,))
    if mutation == 'page': node = replace(node, children=tuple(replace(c, page_index=0) for c in node.children))
    if mutation == 'mcid': node = replace(node, children=(node.children[0], replace(node.children[1], mcid=0), node.children[2]))
    if mutation == 'role': node = replace(node, semantic_role='heading')
    if mutation == 'space': node = replace(node, children=(node.children[0], replace(node.children[1], text_parts=('\t',)), node.children[2]))
    if mutation == 'barrier': node = replace(node, children=(*node.children[:2], E('Figure', 'figure'), node.children[2]))
    result, _ = repair_tk_source((node,), (), digest)
    assert result == (node,)


def marker(ref='297 0 R'):
    path, previous, space, following = VERIFIED_SPACE_BOUNDARIES[ref]
    span = X.Element('span', {'language': 'ARA', 'page-index': '1',
                             'source-structure-path': '/'.join(map(str, path))})
    attrs = X.SubElement(span, 'attributes')
    for name, value in [('review-whitespace', 'source-boundary'),
                        ('review-whitespace-source-token', 'TK_ARA'),
                        ('review-whitespace-source-sha256', VERIFIED_SOURCE_SHA256)]:
        X.SubElement(attrs, 'attribute', {'name': name, 'value': value})
    for mcid, text in [(previous, ':'), (space, ' '), (following, '30')]:
        X.SubElement(span, 'text', {'page-index': '1', 'mcid': str(mcid)}).text = text
    return span


@pytest.mark.parametrize('ref', VERIFIED_SPACE_BOUNDARIES)
def test_validated_marker_preserves_separator_in_plain_and_rendered_text(ref):
    span = marker(ref)
    node = X.Element('paragraph'); node.append(span)
    assert W._element_text(node) == ': 30'
    assert '\n'.join(W._render_element(node, {})) == ': 30'


@pytest.mark.parametrize('mutation', ['digest', 'buyer', 'language', 'page', 'path', 'mcid', 'space', 'nested', 'duplicate'])
def test_malformed_space_marker_is_rejected(mutation):
    span = marker(); attrs = span.find('attributes')
    if mutation == 'digest': attrs[-1].set('value', 'unknown')
    if mutation == 'buyer': attrs[1].set('value', 'AFRICA_L05')
    if mutation == 'language': span.set('language', 'ENG')
    if mutation == 'page': span.set('page-index', '0')
    if mutation == 'path': span.set('source-structure-path', '0/9')
    if mutation == 'mcid': span.findall('text')[1].set('mcid', '0')
    if mutation == 'space': span.findall('text')[1].text = '\t'
    if mutation == 'nested': X.SubElement(span.findall('text')[0], 'figure')
    if mutation == 'duplicate': X.SubElement(attrs, 'attribute', dict(attrs[0].attrib))
    with pytest.raises(ValueError, match='source-space'):
        W._element_text(span)


def test_unmarked_whitespace_keeps_existing_writer_behavior():
    span = marker(); span.remove(span.find('attributes'))
    assert W._element_text(span) == ':30'
