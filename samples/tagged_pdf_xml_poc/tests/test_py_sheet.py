"""PY exact-source regressions through the full writer pipeline."""
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as E
import pytest
from tagged_pdf_extractor.cli import _build_use_case
from .acceptance_support import require_sample

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / 'samples/SUG_RAW/TV_PY/BN68-26639A-00_SUG_Y26 TV ALL_PY_ENRU_260427.0.pdf'

@pytest.fixture(scope='module')
def bundle(tmp_path_factory):
    require_sample(SOURCE, 'PY_ENRU')
    return _build_use_case().run(SOURCE, tmp_path_factory.mktemp('py-source'))

@pytest.mark.parametrize('title,before', [('Simple User Guide','Before Reading This Simple User Guide'), ('Простое руководство пользователя','Перед прочтением этого Простое руководство пользователя')])
def test_py_cover_precedes_content(bundle,title,before):
    md=bundle[2].semantic_markdown.read_text(encoding='utf-8')
    assert md.index('## '+title+'\n') < md.index('## '+before+'\n')

@pytest.mark.parametrize('ref', ['1278 0 R','399 0 R'])
def test_py_power_continuation_owned_by_warning(bundle,ref):
    root=E.parse(bundle[2].semantic_xml).getroot()
    parents={c:n for n in root.iter() for c in n}
    node=next(n for n in root.iter() if n.get('object-ref')==ref)
    assert parents[node].tag=='list_body'

@pytest.mark.parametrize('ref', ['1363 0 R','1364 0 R','627 0 R','628 0 R'])
def test_py_fee_conditions_owned_by_list(bundle,ref):
    root=E.parse(bundle[2].semantic_xml).getroot()
    parents={c:n for n in root.iter() for c in n}
    node=next(n for n in root.iter() if n.get('object-ref')==ref)
    assert parents[node].tag=='list_item'

@pytest.mark.parametrize('bad,good',[('7 .','7.125'),('7 ,125','7,125'),('network- based','network-based'),('www. samsung.com','www.samsung.com')])
def test_py_source_tokens_without_synthetic_spaces(bundle,bad,good):
    md=bundle[2].semantic_markdown.read_text(encoding='utf-8')
    assert bad not in md
    assert good in md

def test_py_source_fragment_identity_and_nonwhitespace_characters_preserved(bundle):
    raw=E.parse(bundle[2].raw_xml).getroot(); semantic=E.parse(bundle[2].semantic_xml).getroot()
    key=lambda n:(n.get('page-index'),n.get('mcid'),n.get('object-ref'))
    a={key(n):''.join(''.join(n.itertext()).split()) for n in raw.iter('fragment')}
    b={key(n):''.join(''.join(n.itertext()).split()) for n in semantic.iter('text')}
    assert Counter(map(key,raw.iter('fragment')))==Counter(map(key,semantic.iter('text')))
    assert a==b

def test_py_russian_controller_heading_matches_source_compound(bundle):
    md=bundle[2].semantic_markdown.read_text(encoding='utf-8')
    assert '### Использование руководства ТВ-контроллер\n' in md

@pytest.mark.parametrize('token,kind,languages', [('ZC_L02','A2',('RUS','ENG')),('PY_ENRU','A3',('RUS','ENG')),('PY_ENRU','A2',('ENG','RUS'))])
def test_py_other_scopes_are_untouched(bundle,token,kind,languages):
    from tagged_pdf_extractor.domain.models import PdfProfile
    from tagged_pdf_extractor.domain.py_sheet import prepare_py_sheet
    from tagged_pdf_extractor.infrastructure.py_source_evidence import add_py_source_evidence
    profile=PdfProfile(token,kind,languages,2)
    assert prepare_py_sheet(bundle[0],profile) is bundle[0]
    assert add_py_source_evidence(bundle[0],profile) is bundle[0]

def test_py_different_revision_fails_closed(bundle):
    from dataclasses import replace
    from tagged_pdf_extractor.domain.models import PdfProfile
    from tagged_pdf_extractor.domain.py_sheet import prepare_py_sheet
    with pytest.raises(ValueError,match='source revision'):
        prepare_py_sheet(replace(bundle[0],source_sha256='0'*64),PdfProfile('PY_ENRU','A2',('RUS','ENG'),2))

def test_py_original_element_paths_and_figures_preserved(bundle):
    raw=E.parse(bundle[2].raw_xml).getroot(); semantic=E.parse(bundle[2].semantic_xml).getroot()
    raw_refs=Counter(n.get('object-ref') for n in raw.iter('element'))
    semantic_refs=Counter(n.get('object-ref') for n in semantic.iter() if n.get('object-ref') is not None)
    assert raw_refs==semantic_refs
    assert sum(n.get('source-role')=='Figure' for n in raw.iter('element'))==len(list(semantic.iter('figure')))==95
    for n in semantic.iter():
        if n.get('object-ref') is not None:
            assert n.get('source-structure-path') is not None

@pytest.mark.parametrize('page', [0,1])
def test_py_all_model_power_pairs_match_independent_pdf_text(bundle,page):
    import re
    import pymupdf
    root=E.parse(bundle[2].semantic_xml).getroot()
    text=' '.join(n.text or '' for n in root.iter('text') if n.get('page-index')==str(page))
    pattern=r'\b((?:UE|QE|MRE)\d{2,3}[A-Z0-9]+):\s*(\d+)\s*(?:W|Вт)'
    with pymupdf.open(SOURCE) as pdf:
        observed=re.findall(pattern,pdf[page].get_text())
    extracted=re.findall(pattern,text)
    assert len(extracted)==80
    assert Counter(extracted)==Counter(observed)

@pytest.mark.parametrize('ref,header',[('1167 0 R','Страна/регион Сервисный центр Samsung Веб-узел'),('686 0 R','Country/Region Samsung Service Centre Website')])
def test_py_contact_header_and_twelve_countries_preserved(bundle,ref,header):
    root=E.parse(bundle[2].semantic_xml).getroot()
    table=next(n for n in root.iter('table') if n.get('object-ref')==ref)
    rows=list(table.iter('table_row'))
    text=lambda n:' '.join(''.join(n.itertext()).split())
    assert text(rows[0])==header
    assert len(rows)==13
    assert [text(list(row)[0]) for row in rows[1:]]==['RUSSIA','BELARUS','GEORGIA','ARMENIA','AZERBAIJAN','KAZAKHSTAN','UZBEKISTAN','KYRGYZSTAN','TAJIKISTAN','MONGOLIA','UKRAINE','MOLDOVA']
