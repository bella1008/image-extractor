"""TK source regressions: physical cover order and paragraph ownership."""
from collections import Counter
from pathlib import Path
import os
from xml.etree import ElementTree as E
import pytest
from tagged_pdf_extractor.cli import _build_use_case
from .acceptance_support import require_sample

ROOT = Path(__file__).resolve().parents[3]
RELATIVE = 'samples/SUG_RAW/TV_TK/BN68-26343A-00_SUG_Y26 TV ALL_TK_L02_260327.0.pdf'
SOURCE = Path(os.environ.get('TAGGED_PDF_TK_L02_SAMPLE', ROOT / RELATIVE))
if not SOURCE.is_file() and 'TAGGED_PDF_TK_L02_SAMPLE' not in os.environ:
    SOURCE = ROOT.parent / 'xml-extractor-release' / RELATIVE

@pytest.fixture(scope='module')
def bundle(tmp_path_factory):
    require_sample(SOURCE, 'TK_L02')
    return _build_use_case().run(SOURCE, tmp_path_factory.mktemp('tk'))

@pytest.mark.parametrize('language,title,before', [
    ('ENG','Simple User Guide','Before Reading This Simple User Guide'),
    ('TUR','Kolay Kullanım Kılavuzu','Bu Kolay Kullanım Kılavuzu Okumadan Önce')])
def test_cover_precedes_body(bundle,language,title,before):
    md=bundle[2].semantic_markdown.read_text(encoding='utf-8')
    assert md.index('## '+title+'\n') < md.index('## '+before+'\n')

@pytest.mark.parametrize('ref', ['301 0 R','302 0 R'])
def test_fee_conditions_owned_by_list(bundle,ref):
    root=E.parse(bundle[2].semantic_xml).getroot()
    parents={c:n for n in root.iter() for c in n}
    node=next(n for n in root.iter() if n.get('object-ref')==ref)
    assert parents[node].tag=='list_item'

def test_turkish_power_stays_in_warning(bundle):
    root=E.parse(bundle[2].semantic_xml).getroot()
    parents={c:n for n in root.iter() for c in n}
    node=next(n for n in root.iter() if n.get('object-ref')=='389 0 R')
    assert parents[node].tag=='list_body'

@pytest.mark.parametrize('bad,good', [('7 .','7.125'),('7 ,125','7,125'),('https:/ /www. samsung.com','https://www.samsung.com'),('http:/ /www.samsung.com','http://www.samsung.com'),('ecodesign_ energy','ecodesign_energy'),('network- based','network-based'),('62087 .','62087.')])
def test_source_tokens_have_no_synthetic_spaces(bundle,bad,good):
    md=bundle[2].semantic_markdown.read_text(encoding='utf-8')
    assert bad not in md
    assert good in md

def test_every_source_fragment_survives(bundle):
    raw=E.parse(bundle[2].raw_xml).getroot()
    xml=E.parse(bundle[2].semantic_xml).getroot()
    key=lambda n:(n.get('page-index'),n.get('mcid'),n.get('object-ref'))
    assert Counter(map(key,raw.iter('fragment')))==Counter(map(key,xml.iter('text')))

@pytest.mark.parametrize('ref,span', [('932 0 R','2'),('905 0 R','4')])
def test_manufacturer_and_lab_merged_cells_remain_visible(bundle,ref,span):
    from tagged_pdf_extractor.infrastructure.markdown_writer import MarkdownDocumentWriter as W
    root=E.parse(bundle[2].semantic_xml).getroot()
    table=next(n for n in root.iter('table') if n.get('object-ref')==ref)
    rendered='\n'.join(W._render_element(table,{}))
    assert f'rowspan="{span}"' in rendered

@pytest.mark.parametrize('token,kind,langs',[('TK_L02','A3',('ENG','TUR')),('TK_L02','A2',('TUR','ENG')),('ZX_L02','A2',('ENG','TUR'))])
def test_other_dispatch_combinations_are_untouched(bundle,token,kind,langs):
    from tagged_pdf_extractor.domain.models import PdfProfile
    from tagged_pdf_extractor.domain.tk_sheet import prepare_tk_sheet
    doc=bundle[0]
    assert prepare_tk_sheet(doc,PdfProfile(token,kind,langs,2)) is doc

def test_source_join_hint_does_not_change_unannotated_writer_text():
    from tagged_pdf_extractor.infrastructure.markdown_writer import MarkdownDocumentWriter as W
    plain=E.fromstring('<paragraph><text>ecodesign_</text><text> energy</text></paragraph>')
    assert W._element_text(plain)=='ecodesign_ energy'
    plain[1].set('join-previous','source-token')
    assert W._element_text(plain)=='ecodesign_energy'
