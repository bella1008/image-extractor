"""Actual source regressions for the eight cross-buyer ownership defects."""
from collections import Counter
import os
from pathlib import Path
from xml.etree import ElementTree as E

import pytest

from tagged_pdf_extractor.cli import _build_use_case
from tagged_pdf_extractor.infrastructure.markdown_writer import MarkdownDocumentWriter as W
from .acceptance_support import require_sample

ROOT = Path(__file__).resolve().parents[3]
SOURCES = {
    'ZC': 'TV_ZC/BN68-25100B-00_SUG_Y26 TV ALL_ZC_L02_260122.0.pdf',
    'AFRICA': 'TV_AFRICA/BN68-25031G-00_SUG_Y26 TV ALL_AFRICA_L05_251230.0.pdf',
    'ZG': 'TV_ZG/BN68-25448A-00_SUG_Y26 TV ALL_ZG XN ZT_L05_260204.0.pdf',
    'XU': 'TV_XU/BN68-24437C-01_SUG_Y26 TV ALL_XU_ENG_260129.0.pdf',
}
CASES = [('ZC', 'C-FRA', 'power', '117 0 R'),
         ('AFRICA', 'ARA', 'power', '403 0 R'),
         ('ZG', 'ENG', 'fee', '5755 0 R'), ('ZG', 'DEU', 'fee', '4562 0 R'),
         ('ZG', 'FRA', 'fee', '3369 0 R'), ('ZG', 'ITA', 'fee', '2177 0 R'),
         ('ZG', 'DUT', 'fee', '981 0 R'), ('XU', 'ENG', 'fee', '303 0 R')]


@pytest.fixture(scope='module')
def bundles(tmp_path_factory):
    result = {}
    for buyer, relative in SOURCES.items():
        source = Path(os.environ.get(f'TAGGED_PDF_{buyer}_SAMPLE', ROOT / 'samples/SUG_RAW' / relative))
        require_sample(source, buyer)
        result[buyer] = _build_use_case().run(source, tmp_path_factory.mktemp(buyer))
    return result


def text(node):
    return ' '.join(''.join(t.text or '' for t in node.iter('text')).split())


@pytest.mark.parametrize('buyer,language,kind,ref', CASES)
def test_source_paragraph_has_its_proven_owner(bundles, buyer, language, kind, ref):
    _, report, artifacts = bundles[buyer]
    assert report.status == 'pass'
    root = E.parse(artifacts.semantic_xml).getroot()
    raw = E.parse(artifacts.raw_xml).getroot()
    parents = {c:n for n in root.iter() for c in n}
    raw_parents = {c:n for n in raw.iter() for c in n}
    target = next(n for n in root.iter() if n.get('object-ref') == ref)
    source = next(n for n in raw.iter('element') if n.get('object-ref') == ref)
    if kind == 'power':
        assert parents[target].tag == 'list_body'
        owner = parents[parents[target]]
        assert owner.tag == 'list_item'
        rendered = '\n'.join(W._render_list_item(owner, {}, indent=''))
        assert '<br>\n  ' in rendered
    else:
        siblings = list(raw_parents[source])
        index = siblings.index(source)
        second_ref = siblings[index + 1].get('object-ref')
        intro_ref = siblings[index - 1].get('object-ref')
        second = next(n for n in root.iter() if n.get('object-ref') == second_ref)
        assert parents[target].tag == parents[second].tag == 'list_item'
        listing = parents[parents[target]]
        assert listing is parents[parents[second]] and listing.tag == 'list'
        assert len(listing.findall('list_item')) == 2
        group = parents[listing]
        assert group.tag == 'section'
        assert group.find('paragraph').get('object-ref') == intro_ref
        rendered = '\n\n'.join(W._render_element(group, {}))
        assert '- (a)' in rendered and '- (b)' in rendered
    assert target.get('source-structure-path')
    assert text(target) in ' '.join(rendered.split())


@pytest.mark.parametrize('buyer', SOURCES)
def test_repair_preserves_source_fragment_identity(bundles, buyer):
    _, _, artifacts = bundles[buyer]
    raw = E.parse(artifacts.raw_xml).getroot()
    semantic = E.parse(artifacts.semantic_xml).getroot()
    key = lambda n: (n.get('page-index'), n.get('mcid'), n.get('object-ref'))
    assert Counter(key(n) for n in raw.iter('fragment')) == Counter(key(n) for n in semantic.iter('text'))
