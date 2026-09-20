"""CE BOOK source regressions, independent of the legacy extraction stack."""
from collections import Counter
import os
from pathlib import Path
from xml.etree import ElementTree as E

import pytest

from tagged_pdf_extractor.cli import _build_use_case
from tagged_pdf_extractor.infrastructure.markdown_writer import MarkdownDocumentWriter as W

NAME = "BN68-26318A-00_SUG_Y26 TV ALL_CE_L05_260422.0.pdf"
LANGUAGES = ("RUS", "ENG", "KAZ", "MON", "KYR")


@pytest.fixture(scope="module")
def ce(tmp_path_factory):
    source = Path(os.environ.get("TAGGED_PDF_CE_SAMPLE", str(
        Path(__file__).resolve().parents[3] / "samples/SUG_RAW/TV_CE" / NAME)))
    if not source.is_file():
        pytest.skip("CE real PDF unavailable")
    return _build_use_case().run(source, tmp_path_factory.mktemp("ce"))


@pytest.mark.parametrize("index,language", enumerate(LANGUAGES))
def test_cover_and_body_share_their_actual_language(ce, index, language):
    document, _, artifacts = ce
    interval = document.multilingual_heading_audit.signatures[index].interval
    assert interval.language == language
    assert interval.start_page_index == index * 8
    assert interval.end_page_index == ((index + 1) * 8 - 1 if index < 4 else 42)
    root = E.parse(artifacts.semantic_xml).getroot()
    for node in root.iter('paragraph'):
        pages = {int(t.get('page-index')) for t in node.iter('text')}
        if pages and pages <= set(range(index * 8, (index + 1) * 8)):
            assert node.get('language') == language
            assert node.get('source-structure-path')


def test_russian_contact_cover_is_not_kyrgyz(ce):
    _, _, artifacts = ce
    root = E.parse(artifacts.semantic_xml).getroot()
    nodes = [n for n in root.iter('paragraph') if {t.get('page-index') for t in n.iter('text')} == {'43'}]
    assert nodes and all(n.get('language') == 'RUS' for n in nodes)


@pytest.mark.parametrize("page", (7, 15, 23, 31, 39))
def test_wifi_frequency_has_no_synthetic_internal_space(ce, page):
    _, _, artifacts = ce
    root = E.parse(artifacts.semantic_xml).getroot()
    labels = [n for n in root.iter('paragraph') if {int(t.get('page-index')) for t in n.iter('text')} == {page}
              and 'Wi-Fi' in ''.join(t.text or '' for t in n.iter('text')) and not list(n.iter('table'))]
    assert len(labels) == 1
    text = ''.join(t.text or '' for t in labels[0].iter('text'))
    assert '7.125' in text if page == 15 else '7,125' in text
    assert '7 .125' not in text and '7 ,125' not in text


@pytest.mark.parametrize("page", (6, 14, 22, 30, 38))
def test_eco_paragraph_breaks_sentences_without_splitting_route(ce, page):
    _, _, artifacts = ce
    root = E.parse(artifacts.semantic_xml).getroot()
    nodes = [n for n in root.iter('paragraph') if {int(t.get('page-index')) for t in n.iter('text')} == {page}
             and not ''.join(t.text or '' for t in n.iter('text')).strip().startswith('(')
             and len(n.findall(".//figure[@display-role='inline-icon']")) == 2]
    assert len(nodes) == 1
    assert len(nodes[0].findall(".//text[@display-role='sentence-break-source']")) == 1
    assert '\n\n'.join(W._render_element(nodes[0], {})).count('<br>') == 1


def test_source_text_identity_and_multilingual_structure_survive(ce):
    document, report, artifacts = ce
    assert report.status == 'pass'
    assert [len(s.entries) for s in document.multilingual_heading_audit.signatures] == [23] * 5
    raw = E.parse(artifacts.raw_xml).getroot()
    semantic = E.parse(artifacts.semantic_xml).getroot()
    identity = lambda root, tag: Counter((n.get('page-index'), n.get('mcid'), n.get('object-ref')) for n in root.iter(tag))
    assert identity(raw, 'fragment') == identity(semantic, 'text')
    chars = lambda text: Counter(c for c in text if not c.isspace())
    assert chars(''.join(p.text or '' for f in raw.iter('fragment') for p in f.findall('part'))) == chars(''.join(t.text or '' for t in semantic.iter('text')))


@pytest.mark.parametrize('language,title', [('RUS','Режим ожидания'), ('KAZ','Күту режимі')])
def test_source_standby_subtitle_is_distinguished_from_body(ce, language, title):
    _, _, artifacts = ce
    root = E.parse(artifacts.semantic_xml).getroot()
    nodes = [n for n in root.iter('paragraph') if ''.join(t.text or '' for t in n.iter('text')).strip() == title]
    assert len(nodes) == 1 and nodes[0].get('language') == language
    assert nodes[0].get('display-role') == 'strong-label'
    assert W._render_element(nodes[0], {}) == [f'**{title}**']


@pytest.mark.parametrize("index,language", enumerate(LANGUAGES))
def test_power_continuation_is_inside_first_bullet_with_sentence_break(ce, index, language):
    _, _, artifacts = ce
    root = E.parse(artifacts.semantic_xml).getroot()
    raw = E.parse(artifacts.raw_xml).getroot()
    source = next(n for n in raw.iter('element')
                  if n.get('source-role') == 'UnorderList_1-Bullet'
                  and n.get('page-index') == str(index * 8 + 1))
    target = next(n for n in root.iter() if n.get('object-ref') == source.get('object-ref'))
    parents = {c:n for n in root.iter() for c in n}
    assert parents[target].tag == 'list_body'
    assert parents[parents[target]].tag == 'list_item'
    assert target.get('language') == language and target.get('source-structure-path')
    source_text = ' '.join(''.join(t.text or '' for t in source.iter('part')).split())
    rendered = '\n'.join(W._render_list_item(parents[parents[target]], {}, indent=''))
    assert '<br>\n  ' + source_text in rendered
    assert rendered.count('\n- ') == 0


@pytest.mark.parametrize("index,language", enumerate(LANGUAGES))
def test_fee_conditions_are_children_of_the_source_introduction(ce, index, language):
    _, _, artifacts = ce
    root = E.parse(artifacts.semantic_xml).getroot()
    raw = E.parse(artifacts.raw_xml).getroot()
    source = [n for n in raw.iter('element') if n.get('source-role') == 'UnorderList_1-Bullet'
              and n.get('page-index') == str(index * 8 + 7)
              and ''.join(t.text or '' for t in n.iter('part')).strip().startswith('(')]
    assert len(source) == 2
    parents = {c:n for n in root.iter() for c in n}
    items = [next(n for n in root.iter() if n.get('object-ref') == s.get('object-ref')) for s in source]
    assert all(parents[n].tag == 'list_item' for n in items)
    lists = [parents[parents[n]] for n in items]
    assert lists[0] is lists[1] and lists[0].tag == 'list'
    group = parents[lists[0]]
    assert group.tag == 'section'
    assert [n.tag for n in group if n.tag != 'attributes'] == ['paragraph', 'list']
    intro = group.find('paragraph')
    assert ''.join(t.text or '' for t in intro.iter('text')).strip().endswith(':')
    rendered = '\n\n'.join(W._render_element(group, {}))
    for item in items:
        label = ''.join(t.text or '' for t in item.iter('text')).strip()[:3]
        assert '- ' + label in rendered
        assert item.get('language') == language and item.get('source-structure-path')
