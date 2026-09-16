from tagged_pdf_extractor.domain.models import ContentFragment,StructureElement,Diagnostic
from tagged_pdf_extractor.domain import zw_line_join as zw

def evidence(*items):
 return (Diagnostic('warning','zw_source_operations','source',{'sha256':zw.SOURCE_SHA,'fragments':[{'page_index':0,'mcid':i,'runs':[{'glyphs':list(s),'actual_text':False,'operation_index':i,'axis_aligned':True}]} for i,s in items]}),)
def frag(i,text):return ContentFragment(0,i,(text,))
def root(*items):return (StructureElement('P','P',children=items),)

def test_proven_cjk_line_wrap_joins_across_empty_overprint():
 cs,audit=zw.restore_zw_line_join(root(frag(1,'產品'),frag(2,''),frag(3,'\n安全。')),evidence((1,'產品'),(2,'產品'),(3,'安全。')))
 assert cs[0].children[2].join_previous
 assert len(audit.context['changes'])==1

def test_source_spaces_are_preserved():
 cs,_=zw.restore_zw_line_join(root(frag(1,'Samsung '),frag(2,'\n產品')),evidence((1,'Samsung '),(2,'產品')))
 assert not cs[0].children[1].join_previous
 assert cs[0].children[0].text=='Samsung '

def test_model_line_separation_preserved():
 cs,_=zw.restore_zw_line_join(root(frag(1,'QA55 ABC'),frag(2,'\nQA65 DEF')),evidence((1,'QA55 ABC'),(2,'QA65 DEF')))
 assert not cs[0].children[1].join_previous

def test_source_proven_url_join():
 cs,_=zw.restore_zw_line_join(root(frag(918,'www.'),frag(919,'\nsamsung.com')),evidence((918,'www.'),(919,'samsung.com')))
 assert cs[0].children[1].join_previous

def test_changed_source_and_missing_evidence_refuse():
 children=root(frag(1,'產品'),frag(2,'\n安全'))
 for ev in [(),(Diagnostic('warning','zw_source_operations','source',{'sha256':'changed','fragments':[]}),)]:
  cs,audit=zw.restore_zw_line_join(children,ev)
  assert cs==children and not audit.context['changes']

def test_source_whitespace_inside_chinese_is_not_removed():
 children=root(frag(1,'產 品'))
 cs,_=zw.restore_zw_line_join(children,evidence((1,'產 品')))
 assert cs==children

def test_internal_synthetic_whitespace_removed_only_if_full_source_matches():
 cs,_=zw.restore_zw_line_join(root(frag(1,'產品\n安全')),evidence((1,'產品安全')))
 assert cs[0].children[0].text=='產品安全'

def test_different_source_characters_refuse():
 children=root(frag(1,'產品'),frag(2,'\n安全'))
 cs,_=zw.restore_zw_line_join(children,evidence((1,'產品'),(2,'其他')))
 assert cs==children

def test_internal_spacing_across_parts_preserves_style_alignment():
 from tagged_pdf_extractor.domain.models import TextStyle
 f=ContentFragment(0,1,('產品','\n','安全'),text_styles=(TextStyle('font',8),)*3)
 cs,_=zw.restore_zw_line_join(root(f),evidence((1,'產品安全')))
 assert cs[0].children[0].text_parts==('產品','','安全')
 assert cs[0].children[0].text_styles==f.text_styles

def test_inline_span_and_link_boundaries_join():
 span=StructureElement('Span','span',children=(frag(1,'使用者'),))
 link=StructureElement('Link','link',children=(frag(2,'\n指南'),))
 cs,_=zw.restore_zw_line_join(root(span,link),evidence((1,'使用者'),(2,'指南')))
 assert cs[0].children[1].children[0].join_previous

def test_block_boundaries_do_not_join():
 for role in ('paragraph','table_cell','list_item'):
  block=StructureElement('P',role,children=(frag(2,'\n指南'),))
  cs,_=zw.restore_zw_line_join(root(frag(1,'使用者'),block),evidence((1,'使用者'),(2,'指南')))
  assert not cs[0].children[1].children[0].join_previous

def test_synthetic_leading_space_does_not_hide_valid_boundary():
 cs,_=zw.restore_zw_line_join(root(frag(1,' 如固'),frag(2,'\n定件')),evidence((1,'如固'),(2,'定件')))
 assert cs[0].children[1].join_previous

def test_source_leading_space_still_blocks_join():
 cs,_=zw.restore_zw_line_join(root(frag(1,'產品'),frag(2,' 安全')),evidence((1,'產品'),(2,' 安全')))
 assert not cs[0].children[1].join_previous

def test_observed_source_boundary_regression():
 from pathlib import Path
 import pytest
 from tagged_pdf_extractor.infrastructure.pypdf_reader import TaggedPdfReader
 from tagged_pdf_extractor.infrastructure.zw_source_evidence import add_zw_source_evidence
 from tagged_pdf_extractor.domain.zw_source_text import restore_zw_text
 from tagged_pdf_extractor.domain.models import PdfProfile
 path=Path.home()/'image-extractor/samples/SUG_RAW/2_TV_ZW/BN68-24973D-00_SUG_Y26 TV ALL_ZW_TPE_260327.0.pdf'
 if not path.exists():pytest.skip('ZW source unavailable')
 doc=add_zw_source_evidence(TaggedPdfReader().read(path),PdfProfile('ZW_TPE','A3',('TPE',),1))
 children,_=restore_zw_text(doc.children,doc.diagnostics)
 children,_=zw.restore_zw_line_join(children,doc.diagnostics)
 def leaves(nodes):
  for n in nodes:
   if isinstance(n,ContentFragment):yield n
   else:yield from leaves(n.children)
 fragments={(n.page_index,n.mcid):n for n in leaves(children)}
 for mcid in (39,53,399):assert fragments[0,mcid].join_previous
