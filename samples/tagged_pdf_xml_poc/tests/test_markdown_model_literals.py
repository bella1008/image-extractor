"""Model wildcards are source characters, never Markdown emphasis delimiters."""
from xml.etree import ElementTree as ET

import pytest

from tagged_pdf_extractor.infrastructure.markdown_writer import MarkdownDocumentWriter


@pytest.mark.parametrize('tag', ['paragraph', 'heading', 'caption', 'list_body', 'table_cell'])
def test_model_wildcards_survive_in_source_text_containers(tag):
    node = ET.Element(tag)
    ET.SubElement(node, 'text').text = 'U8***H/QN9**H/R8*H/LS03H*: 90 W'
    if tag == 'table_cell':
        table = ET.Element('table')
        row = ET.SubElement(table, 'table_row')
        row.append(node)
        node = table
    if tag == 'list_body':
        listing = ET.Element('list')
        ET.SubElement(listing, 'list_item').append(node)
        node = listing
    md = '\n'.join(MarkdownDocumentWriter._render_element(node, {}))
    assert r'U8\*\*\*H/QN9\*\*H/R8\*H/LS03H\*' in md


def test_strong_subtitle_keeps_its_writer_markup_and_source_wildcards():
    node = ET.Element('paragraph', {'display-role': 'subtitle'})
    ET.SubElement(node, 'text').text = 'QN9**H WARNING'
    assert MarkdownDocumentWriter._render_element(node, {}) == [r'**QN9\*\*H WARNING**']


def test_ordinary_model_and_source_backslash_are_not_changed():
    node = ET.Element('paragraph')
    ET.SubElement(node, 'text').text = r'QN900H: 90 W; already\*literal'
    assert MarkdownDocumentWriter._render_element(node, {}) == [r'QN900H: 90 W; already\*literal']
