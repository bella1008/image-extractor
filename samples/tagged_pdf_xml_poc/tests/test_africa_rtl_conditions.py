from dataclasses import replace
from collections import Counter
from xml.etree import ElementTree as ET
import pytest
from tagged_pdf_extractor.domain.models import ContentFragment, StructureElement
from tagged_pdf_extractor.domain.africa_rtl_conditions import restore_condition_paragraph, condition_key
from tagged_pdf_extractor.infrastructure.markdown_writer import MarkdownDocumentWriter


def source_case():
    values=['LS03HE','"( \u200f','43','"-\u200f','85',' \u200f:)','20','واط']
    children=tuple(ContentFragment(29,i,(v,)) for i,v in enumerate(values))
    node=StructureElement('P','paragraph',language='ARA',children=children,source_structure_path=(0,12,0,7))
    runs={(29,i):[{'glyphs':list(v),'glyph_boxes':[[100-i*10+j,200,101-i*10+j,207] for j in range(len(v))]}] for i,v in enumerate(values)}
    return node,runs


def test_neutral_condition_preserves_every_source_character_and_identity():
    node,runs=source_case()
    result=restore_condition_paragraph(node,runs)
    assert result.display_direction=='rtl'
    assert [c.mcid for c in result.children]==[c.mcid for c in node.children]
    before=''.join(''.join(c.text_parts) for c in node.children)
    after=''.join(''.join(c.text_parts) for c in result.children)
    assert Counter(before)==Counter(after)
    assert condition_key(after)=='LS03HE("43-"85):20واط'


@pytest.mark.parametrize('mutation',['language','missing','baseline','glyph','rlm','pattern','infinite'])
def test_uncertain_neutral_conditions_keep_source(mutation):
    node,runs=source_case()
    if mutation=='language':node=replace(node,language='ENG')
    elif mutation=='missing':runs.pop((29,1))
    elif mutation=='baseline':runs[29,1][0]['glyph_boxes'][0][1]+=1
    elif mutation=='glyph':runs[29,1][0]['glyphs']=['(',':']
    elif mutation=='infinite':runs[29,1][0]['glyph_boxes'][0][0]=float('nan')
    else:
        cs=list(node.children)
        i=1 if mutation=='rlm' else 0
        cs[i]=replace(cs[i],text_parts=('"(',) if mutation=='rlm' else ('unrelated',))
        node=replace(node,children=tuple(cs))
    assert restore_condition_paragraph(node,runs)==node


def directed_xml():
    p=ET.Element('paragraph',{'language':'ARA','source-structure-path':'0/1','display-direction':'rtl','direction-reason':'source-glyph-numeric-condition'})
    ET.SubElement(p,'text').text='LS03HE ("43-"85): 20 واط'
    return p


def test_markdown_direction_hint_renders_literal_source_text():
    p=directed_xml()
    assert MarkdownDocumentWriter._render_element(p,{})==['<span dir="rtl">LS03HE ("43-"85): 20 واط</span>']


@pytest.mark.parametrize('key,value',[('language','ENG'),('display-direction','ltr'),('direction-reason','guess'),('source-structure-path','')])
def test_markdown_rejects_invalid_direction_hint(key,value):
    p=directed_xml();p.set(key,value)
    with pytest.raises(ValueError):MarkdownDocumentWriter._render_element(p,{})


def test_markdown_rejects_incomplete_condition_text():
    p=directed_xml();p.find('text').text='LS03HE ("43-"85: 20 واط'
    with pytest.raises(ValueError):MarkdownDocumentWriter._render_element(p,{})



def test_markdown_direction_hint_keeps_model_wildcards_literal():
    p=directed_xml();p.find('text').text='QN**H ("42): 20 واط, QN**H ("48): 40 واط'
    rendered=MarkdownDocumentWriter._render_element(p,{})[0]
    assert rendered.count('QN&#42;&#42;H')==2


@pytest.mark.parametrize('mutation',['reversed_x','ligature','missing_box','gap'])
def test_neutral_condition_requires_individual_ltr_punctuation_glyphs(mutation):
    node,runs=source_case();run=runs[29,1][0]
    if mutation=='reversed_x':run['glyph_boxes'][0],run['glyph_boxes'][1]=run['glyph_boxes'][1],run['glyph_boxes'][0]
    elif mutation=='ligature':run['glyphs']=['"(', ' ', '\u200f'];run['glyph_boxes']=run['glyph_boxes'][:3]
    elif mutation=='missing_box':run['glyph_boxes']=run['glyph_boxes'][:1]
    else:run['glyph_boxes'][1][0]+=50;run['glyph_boxes'][1][2]+=50
    assert restore_condition_paragraph(node,runs)==node



def wifi_case():
    values=['احتياطات استخدام شبكة [','Wi-Fi بتردد 5.925 - 7.125 (أو 6.425)','] جيجاهرتز']
    cs=tuple(ContentFragment(29,i,(v,)) for i,v in enumerate(values))
    node=StructureElement('P','paragraph',language='ARA',children=cs)
    runs={(29,i):[{'glyphs':list(v),'glyph_boxes':[[j,200-i*10,j+1,207-i*10] for j in range(len(v))]}] for i,v in enumerate(values)}
    return node,runs


def test_wifi_brackets_follow_source_glyph_edges_without_changing_words():
    from tagged_pdf_extractor.domain.africa_rtl_conditions import restore_wifi_brackets
    node,runs=wifi_case();result=restore_wifi_brackets(node,runs)
    assert result.display_direction=='rtl'
    text=''.join(''.join(c.text_parts) for c in result.children)
    assert condition_key(text)=='[احتياطاتاستخدامشبكةWi-Fiبتردد5.925-7.125(أو6.425)جيجاهرتز]'
    assert Counter(text)==Counter(''.join(''.join(c.text_parts) for c in node.children))


@pytest.mark.parametrize('mutation',['language','missing','edge','word','baseline'])
def test_wifi_brackets_reject_unproved_source(mutation):
    from tagged_pdf_extractor.domain.africa_rtl_conditions import restore_wifi_brackets
    node,runs=wifi_case()
    if mutation=='language':node=replace(node,language='ENG')
    elif mutation=='missing':runs.pop((29,0))
    elif mutation=='edge':runs[29,0][0]['glyph_boxes'][-1][0]=-10
    elif mutation=='word':runs[29,0][0]['glyphs'][0]='x'
    else:runs[29,0][0]['glyph_boxes'][-1][1]+=1
    assert restore_wifi_brackets(node,runs)==node
