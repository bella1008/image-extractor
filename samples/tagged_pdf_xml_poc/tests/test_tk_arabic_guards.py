"""Negative source evidence must never authorize TK Arabic repairs."""
from dataclasses import replace
import pytest
from tagged_pdf_extractor.domain.models import ContentFragment as F, StructureElement as E
from tagged_pdf_extractor.domain.tk_arabic_source import repair_fragment, repair_tk_ownership

WARN='لا تقم بتحميل مآخذ الحائط أو أسلاك التمديد أو المحول فوق جهدها وسعتها. فقد يؤدي هذا إلى نشوب حريق أو حدوث صدمة كهربائية.'
CONT='راجع قسم مواصفات الطاقة في دليل المستخدم أو ملصق مصدر الطاقة الموجود على المنتج للحصول على معلومات عن الجهد وشدة التيار.'
INTRO='قد يتم احتساب رسوم إدارية في الحالات التالية:'
FEE_A='(أ) استدعاء مهندس بناءً على طلبك، لكن لا توجد أي عيوب في المنتج (مثلاً، في حالة عدم قراءة دليل المستخدم).'
FEE_B='(ب) إحضار الوحدة إلى مركز خدمة Samsung، لكن لم يتم إيجاد أي عيوب في المنتج (مثلاً في حالة عدم قراءة دليل المستخدم).'

def paragraph(value,page=0,ref=None,role='UnorderList_1-Bullet'):
    return E(role,'paragraph',object_ref=ref,page_index=page,language='ARA',children=(F(page,1,(value,)),))

def listing(value=WARN,page=0):
    return E('L','list',children=(E('LI','list_item',children=(
        E('Lbl','label',children=(F(page,2,('• ',)),)),
        E('LBody','list_body',children=(F(page,3,(value,)),)),)),))

def power_case():
    return (E('Sect','section',children=(listing(),paragraph(CONT,ref='436 0 R'),listing('Next warning'))),)

def fee_case():
    return (E('Sect','section',children=(paragraph(INTRO,1,'338 0 R','Description-L'),
        paragraph(FEE_A,1,'339 0 R'),paragraph(FEE_B,1,'340 0 R'))),)

@pytest.mark.parametrize('identity',[(0,17),(0,343),(1,660)])
@pytest.mark.parametrize('mutation',['none','empty','unaligned','mismatch','nan','short_box','marks_only'])
def test_arabic_fragment_requires_complete_valid_geometry(identity,mutation):
    fragment=F(*identity,('اب',))
    run={'glyphs':['ب','ا'],'glyph_boxes':[[0,0,1,7],[1,0,2,7]],'axis_aligned':True,'actual_text':False}
    if mutation=='none':run['glyph_boxes']=None
    if mutation=='empty':run['glyph_boxes']=[]
    if mutation=='unaligned':run.update(glyph_boxes=None,axis_aligned=False)
    if mutation=='mismatch':run['glyph_boxes']=run['glyph_boxes'][:1]
    if mutation=='nan':run['glyph_boxes'][0][2]=float('nan')
    if mutation=='short_box':run['glyph_boxes'][0]=[0,0]
    if mutation=='marks_only':run['glyphs']=['ُ','ً']
    assert repair_fragment(fragment,[run],[])==fragment

@pytest.mark.parametrize('mutation',['extra_item','changed_warning','changed_continuation','different_page','continuation_barrier','body_barrier','trailing_item_content','inline_role'])
def test_power_owner_requires_exact_reviewed_single_item(mutation):
    nodes=power_case();section=nodes[0];lst,c,following=section.children
    if mutation=='extra_item':lst=replace(lst,children=(*lst.children,*listing('Other warning').children))
    if mutation=='changed_warning':lst=listing(WARN+' Other warning')
    if mutation=='changed_continuation':c=paragraph(CONT+' Changed',ref='436 0 R')
    if mutation=='different_page':c=paragraph(CONT,1,'436 0 R')
    if mutation=='continuation_barrier':c=replace(c,children=(E('Table','table',children=c.children),))
    if mutation=='body_barrier':
        item=lst.children[0];body=item.children[-1]
        lst=replace(lst,children=(replace(item,children=(*item.children[:-1],replace(body,children=(E('Table','table',children=body.children),)))),))
    if mutation=='trailing_item_content':
        item=lst.children[0];lst=replace(lst,children=(replace(item,children=(*item.children,F(0,4,('',)))),))
    if mutation=='inline_role':c=replace(c,semantic_role='heading')
    nodes=(replace(section,children=(lst,c,following)),)
    result,proof=repair_tk_ownership(nodes)
    assert result==nodes
    assert proof.context['changes']==[]

@pytest.mark.parametrize('mutation',['different_page','condition_barrier','intro_barrier','wrong_role','changed_condition'])
def test_fee_group_requires_same_page_inline_source_paragraphs(mutation):
    nodes=fee_case();intro,a,b=nodes[0].children
    if mutation=='different_page':b=paragraph(FEE_B,0,'340 0 R')
    if mutation=='condition_barrier':a=replace(a,children=(E('Table','table',children=a.children),))
    if mutation=='intro_barrier':intro=replace(intro,children=(E('Table','table',children=intro.children),))
    if mutation=='wrong_role':a=replace(a,semantic_role='heading')
    if mutation=='changed_condition':b=paragraph(FEE_B+' Changed',1,'340 0 R')
    nodes=(replace(nodes[0],children=(intro,a,b)),)
    result,proof=repair_tk_ownership(nodes)
    assert result==nodes
    assert proof.context['changes']==[]
