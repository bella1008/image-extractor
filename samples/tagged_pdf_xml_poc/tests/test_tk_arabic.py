"""TK A3 physical page order differs from the AFRICA RTL BOOK."""
from pathlib import Path
import pytest
from tagged_pdf_extractor.cli import _build_use_case

import os
from .acceptance_support import require_sample
ROOT=Path(__file__).resolve().parents[3]
RELATIVE='samples/SUG_RAW/TV_TK/BN68-26344A-00_SUG_Y26 TV ALL_TK_ARA_260327.0.pdf'
SOURCE=Path(os.environ.get('TAGGED_PDF_TK_ARA_SAMPLE',ROOT/RELATIVE))
if not SOURCE.is_file() and 'TAGGED_PDF_TK_ARA_SAMPLE' not in os.environ:
    SOURCE=ROOT.parent/'xml-extractor-release'/RELATIVE
@pytest.fixture(scope='module')
def bundle(tmp_path_factory):
    require_sample(SOURCE,'TK_ARA')
    return _build_use_case().run(SOURCE,tmp_path_factory.mktemp('tk_ara'))

def test_numbered_chapters_are_all_recovered(bundle):
    doc,report,_=bundle
    assert report.status=='pass'
    assert len(doc.heading_promotions)==5
    assert [p.label for p in doc.heading_promotions]==['01','02','03','04','05']

def test_arabic_cover_precedes_body(bundle):
    md=bundle[2].semantic_markdown.read_text(encoding='utf8')
    assert md.index('## الدليل البسيط للمستخدم\n') < md.index('## قبل قراءة')

def test_source_safety_label_stays_on_one_line(bundle):
    md=bundle[2].semantic_markdown.read_text(encoding='utf8')
    assert 'خطر التعرض لصدمة كهربائية. لا تفتحه.' in md


from collections import Counter
from xml.etree import ElementTree as ET
import re

def _node(bundle, ref):
    root=ET.parse(bundle[2].semantic_xml).getroot()
    return next(e for e in root.iter() if e.get('object-ref')==ref)

def _text(node):
    return ''.join(node.itertext())

def test_power_continuation_belongs_to_first_bullet(bundle):
    root=ET.parse(bundle[2].semantic_xml).getroot()
    parents={c:p for p in root.iter() for c in p}
    continuation=next(e for e in root.iter() if e.get('object-ref')=='436 0 R')
    assert parents[continuation].tag=='list_body'

def test_fee_conditions_are_owned_by_intro_group(bundle):
    root=ET.parse(bundle[2].semantic_xml).getroot()
    parents={c:p for p in root.iter() for c in p}
    for ref in ['339 0 R','340 0 R']:
        condition=next(e for e in root.iter() if e.get('object-ref')==ref)
        assert parents[condition].tag=='list_item'
        assert parents[parents[condition]].tag=='list'

def test_glyph_resets_preserve_complete_arabic_words(bundle):
    assert '*: الطُرُز المدعومة فقط من صندوق' in _text(_node(bundle,'447 0 R'))
    assert '**: قد لا يتم توفير بعض المكونات، اعتمادًا على طريقة اتصال' in _text(_node(bundle,'162 0 R'))

def test_ascii_tokens_have_no_synthetic_internal_spaces(bundle):
    for ref,good,bad in [('957 0 R','VESA','VES A'),('163 0 R','One Connect','One C onnect'),
                         ('353 0 R','QN990H','QN99 0 H'),('364 0 R','QN1EH','QN 1 EH')]:
        value=_text(_node(bundle,ref))
        assert good in value
        assert bad not in value

def test_microphone_model_delimiters_follow_source_model_order(bundle):
    value=_text(_node(bundle,'196 0 R'))
    value=re.sub(r'[\s\u200e\u200f]','',value)
    assert 'R9*H/R8*H/QN1EH/QN7*H/QN8*H/QN9**H/S8*H/S9*H/M8*H/M9*H/U9***H/LS03H*' in value

def test_output_model_delimiters_follow_source_model_order(bundle):
    value=re.sub(r'[\s\u200e\u200f]','',_text(_node(bundle,'295 0 R')))
    assert 'U8***H/U9***H/M7*H/M8*H/M9*H/S8*H/QN7*H/QN1EH/M1EH:20واط' in value


def test_split_wildcard_retains_disjoint_source_slices(bundle):
    proof=next(d for d in bundle[0].diagnostics if d.code=='tk_arabic_split_fragment')
    assert len(proof.context['splits'])==1
    split=proof.context['splits'][0]
    assert (split['page_index'],split['mcid'])==(1,771)
    assert Counter(''.join(p['text'] for p in split['source_parts']))==Counter(split['original_text'])
    assert sorted(i for p in split['source_parts'] for i in range(*p['slice']))==list(range(len(split['original_text'])))

def test_arabic_comma_output_condition_ownership(bundle):
    from tagged_pdf_extractor.domain.africa_rtl_conditions import condition_key
    assert condition_key(_text(_node(bundle,'298 0 R')))=='R85H("55-"85):30واط،R85H("100):40واط'
    assert condition_key(_text(_node(bundle,'302 0 R')))=='LS03HE("43):20واط،LS03HE("98):40واط'


@pytest.mark.parametrize('ref,mcid,model', [('298 0 R','1025','R85H'), ('302 0 R','1061','LS03HE')])
def test_actual_numeric_condition_retains_source_group_separator(bundle, ref, mcid, model):
    node = _node(bundle, ref)
    assert node.find(f".//text[@mcid='{mcid}']").text == ' '
    md = bundle[2].semantic_markdown.read_text(encoding='utf8')
    assert 'واط، ' + model in md


@pytest.mark.parametrize('ref,mcid,value', [('297 0 R','1014','30'), ('299 0 R','1037','40'),
    ('300 0 R','1042','70'), ('301 0 R','1049','90'), ('303 0 R','1072','40')])
def test_actual_simple_output_preserves_colon_space(bundle, ref, mcid, value):
    from tagged_pdf_extractor.infrastructure.markdown_writer import MarkdownDocumentWriter as W
    node = _node(bundle, ref)
    assert node.find(f".//text[@mcid='{mcid}']").text == ' '
    assert ': ' + value in '\n'.join(W._render_element(node, {}))


def test_actual_navigation_preserves_source_separator_space(bundle):
    from tagged_pdf_extractor.infrastructure.markdown_writer import MarkdownDocumentWriter as W
    node = _node(bundle, '282 0 R')
    assert node.find(".//text[@mcid='959']").text == ' '
    assert 'توفير الطاقة والكهرباء >' in '\n'.join(W._render_element(node, {}))


def test_rf_labels_keep_brackets_and_model_separators(bundle):
    for ref,expected in [('353 0 R','[QN990H]'),('359 0 R','[R9*H/R8*H/S9*H/S8*H/QN8*H]'),
                         ('364 0 R','[QN7*H/QN1EH/M9*H/M8*H/M7*H/M1EH/U9***H/U8***H]'),
                         ('368 0 R','[TheFrame(LS03HA,LS03HE)]'),('374 0 R','[TheFrame(LS03HW)]')]:
        assert re.sub(r'[\s\u200e\u200f]','',_text(_node(bundle,ref)))==expected

def test_cover_copyright_arabic_word_order(bundle):
    assert 'حقوق النشر © عام' in _text(_node(bundle,'395 0 R'))


def test_all_mcid_character_ownership_survives_repairs(bundle):
    from tagged_pdf_extractor.domain.tk_sheet import fragments
    def inventory(children):
        result={}
        for node in children:
            for f in fragments(node):
                result.setdefault((f.page_index,f.mcid),Counter()).update(c for c in f.text if not c.isspace())
        return result
    assert inventory(bundle[0].raw_children)==inventory(bundle[0].children)

@pytest.mark.parametrize('mutation',['missing','baseline','actual_text'])
def test_uncertain_source_glyphs_cannot_join_model_token(bundle,mutation):
    from copy import deepcopy
    from tagged_pdf_extractor.domain.tk_arabic_source import source_inventory,repair_fragment
    from tagged_pdf_extractor.domain.tk_sheet import fragments
    f=next(f for n in bundle[0].raw_children for f in fragments(n) if (f.page_index,f.mcid)==(1,1222))
    runs,actual=source_inventory(bundle[0].diagnostics)
    rr=deepcopy(runs[1,1222]);aa=list(actual[1,1222])
    if mutation=='missing':rr=[]
    if mutation=='baseline':rr[-1]['glyph_boxes'][0][1]+=1
    if mutation=='actual_text':aa=['7']
    assert repair_fragment(f,rr,aa)==f

def test_tk_arabic_scope_does_not_apply_to_other_buyers(bundle):
    from dataclasses import replace
    from tagged_pdf_extractor.domain.models import PdfProfile
    from tagged_pdf_extractor.domain.tk_arabic import prepare_tk_arabic
    raw=replace(bundle[0],children=bundle[0].raw_children,raw_children=None)
    assert prepare_tk_arabic(raw,PdfProfile('AFRICA_L05','BOOK',('ARA',),1)) is raw


def test_keyed_repairs_require_verified_source_revision(bundle):
    from dataclasses import replace
    from tagged_pdf_extractor.domain.models import PdfProfile
    from tagged_pdf_extractor.domain.tk_arabic import prepare_tk_arabic
    raw=replace(bundle[0],children=bundle[0].raw_children,raw_children=None,source_sha256='0'*64)
    result=prepare_tk_arabic(raw,PdfProfile('TK_ARA','A3',('ARA',),1))
    assert any(d.code=='tk_arabic_source_revision_unverified' for d in result.diagnostics)
    fresh=result.diagnostics[len(raw.diagnostics):]
    assert not any(d.code=='tk_arabic_source_fragments' for d in fresh)


def test_actual_microphone_model_isolated_without_source_text_change(bundle):
    node=_node(bundle,'196 0 R')
    spans=[s for s in node.iter('span') if s.find("attributes/attribute[@name='review-inline']") is not None]
    assert len(spans)==1
    assert _text(spans[0])=='LS03H*'
    assert [(e.get('page-index'),e.get('mcid')) for e in spans[0].findall('text')]==[('1','770'),('1','771')]
    md=bundle[2].semantic_markdown.read_text(encoding='utf8')
    assert '<bdi dir="ltr">LS03H&#42;</bdi>' in md
