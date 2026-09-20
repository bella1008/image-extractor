"""Source-PDF regressions for the exact UA English A3 revision."""
from collections import Counter
from dataclasses import replace
from pathlib import Path
import pytest
from tagged_pdf_extractor.domain.models import ContentFragment, PdfProfile
from tagged_pdf_extractor.infrastructure.pypdf_reader import TaggedPdfReader

SOURCE = Path(__file__).resolve().parents[2] / 'SUG_RAW/TV_UA/BN68-26754A-00_SUG_Y26 TV ALL_UA_ENG_260520.0.pdf'
PROFILE = PdfProfile('UA_ENG','A3',('ENG',),1)
def walk(node):
    yield node
    if not isinstance(node,ContentFragment):
        for child in node.children: yield from walk(child)
def nodes(document):
    return [n for c in document.children for n in walk(c)]
def text(node):
    return ' '.join(''.join(f.text for f in walk(node) if isinstance(f,ContentFragment)).split())
@pytest.fixture(scope='module')
def raw(): return TaggedPdfReader().read(SOURCE)
def prepared(raw):
    from tagged_pdf_extractor.infrastructure.ua_source_evidence import add_ua_source_evidence
    from tagged_pdf_extractor.domain.ua_sheet import prepare_ua_sheet
    return prepare_ua_sheet(add_ua_source_evidence(raw,PROFILE),PROFILE)

def test_cover_precedes_body_with_source_paths(raw):
    doc=prepared(raw)
    article=next(n for n in nodes(doc) if getattr(n,'source_role',None)=='Article')
    assert [n.object_ref for n in article.children] == ['395 0 R','396 0 R','397 0 R','398 0 R','399 0 R','400 0 R','401 0 R','402 0 R','393 0 R']
    assert article.children[-1].source_structure_path == (0,0,1)

def test_power_continuation_is_owned_by_overload_bullet(raw):
    all_nodes=nodes(prepared(raw))
    continuation=next(n for n in all_nodes if getattr(n,'object_ref',None)=='522 0 R')
    parent=next(n for n in all_nodes if not isinstance(n,ContentFragment) and continuation in n.children)
    assert parent.semantic_role == 'list_body'
    assert 'Do not overload wall outlets' in text(parent)
    assert continuation.source_structure_path == (0,0,1,9)

def test_fee_conditions_have_source_preserving_parent_group(raw):
    all_nodes=nodes(prepared(raw))
    group=next((n for n in all_nodes if not isinstance(n,ContentFragment) and dict(n.attributes).get('review-group')=='administration-fee-conditions'),None)
    assert group is not None
    intro,listing=group.children
    assert intro.object_ref=='389 0 R'
    assert [item.children[0].object_ref for item in listing.children]==['390 0 R','391 0 R']
    assert [text(item)[:3] for item in listing.children]==['(a)','(b)']

def test_wifi_decimal_matches_pdf_not_spacing_artifact(raw):
    value=next(f for f in nodes(prepared(raw)) if isinstance(f,ContentFragment) and (f.page_index,f.mcid)==(1,1142))
    assert value.text.strip()=='[Precautions for using Wi-Fi 5.925 - 7.125 (or 6.425) GHz]'


def test_every_fragment_and_original_node_remains_traceable(raw):
    doc=prepared(raw)
    key=lambda f:(f.page_index,f.mcid,f.object_ref)
    assert Counter(key(f) for f in nodes(doc) if isinstance(f,ContentFragment))==Counter(key(f) for f in nodes(raw) if isinstance(f,ContentFragment))
    assert doc.raw_children==raw.children
    assert all(n.source_structure_path is not None for n in nodes(doc) if not isinstance(n,ContentFragment) and n.object_ref)
    assert Counter(n.object_ref for n in nodes(doc) if not isinstance(n,ContentFragment) and n.object_ref)==Counter(n.object_ref for n in nodes(raw) if not isinstance(n,ContentFragment) and n.object_ref)
    changed=[(a.page_index,a.mcid) for a in nodes(doc) if isinstance(a,ContentFragment) for b in nodes(raw) if isinstance(b,ContentFragment) and (a.page_index,a.mcid,a.object_ref)==(b.page_index,b.mcid,b.object_ref) and a.text!=b.text]
    assert changed==[(1,1142)]

def test_contact_source_header_and_all_eleven_country_rows_survive(raw):
    tables=[n for n in nodes(prepared(raw)) if getattr(n,'semantic_role',None)=='table']
    table=next(n for n in tables if 'Country/Region' in text(n))
    assert len(table.children)==12
    assert [text(c) for c in table.children[0].children]==['Country/Region','Samsung Service Centre','Website']
    assert [text(row.children[0]) for row in table.children[1:]]==['BELARUS','GEORGIA','ARMENIA','AZERBAIJAN','KAZAKHSTAN','UZBEKISTAN','KYRGYZSTAN','TAJIKISTAN','MONGOLIA','UKRAINE','MOLDOVA']
    assert all(len(row.children)==3 for row in table.children)
    assert '0-800-555-555 (B2C) 0-800-555-500 (B2B)'==text(table.children[2].children[1])
    assert text(table.children[9].children[2])=='https://www.samsung.com/mn/support'

@pytest.mark.parametrize('profile',[None,PdfProfile('XL_ENG','A3',('ENG',),1),PdfProfile('UA_ENG','A2',('ENG',),1),PdfProfile('UA_ENG','A3',('INS',),1)])
def test_scope_leaves_other_profiles_unchanged(raw,profile):
    from tagged_pdf_extractor.domain.ua_sheet import prepare_ua_sheet
    from tagged_pdf_extractor.infrastructure.ua_source_evidence import add_ua_source_evidence
    assert prepare_ua_sheet(raw,profile) is raw
    assert add_ua_source_evidence(raw,profile) is raw

def test_revision_missing_proof_and_repeat_fail_closed(raw):
    from tagged_pdf_extractor.domain.ua_sheet import SOURCE_SHA,prepare_ua_sheet
    with pytest.raises(ValueError,match='revision'): prepare_ua_sheet(replace(raw,source_sha256='0'*64),PROFILE)
    with pytest.raises(ValueError,match='operation evidence'): prepare_ua_sheet(replace(raw,source_sha256=SOURCE_SHA),PROFILE)
    with pytest.raises(ValueError,match='already prepared'): prepare_ua_sheet(prepared(raw),PROFILE)

def test_altered_operation_proof_fails_closed(raw):
    from tagged_pdf_extractor.domain.ua_sheet import prepare_ua_sheet
    from tagged_pdf_extractor.infrastructure.ua_source_evidence import add_ua_source_evidence
    doc=add_ua_source_evidence(raw,PROFILE)
    proof=next(d for d in doc.diagnostics if d.code=='ua_source_operations')
    altered=replace(proof,context={**proof.context,'runs':[{**r,'actual_text':True} for r in proof.context['runs']]})
    with pytest.raises(ValueError,match='decimal source operation evidence'):
        prepare_ua_sheet(replace(doc,diagnostics=tuple(altered if d is proof else d for d in doc.diagnostics)),PROFILE)

def test_semantic_markdown_exposes_source_order_intact_decimal_and_fee(raw,tmp_path):
    from tagged_pdf_extractor.cli import _build_use_case
    use=_build_use_case()
    doc=prepared(raw)
    class ReviewedReader:
        def read(self,path): return doc
    use.reader=ReviewedReader();use.profile_repository=None
    _,_,artifacts=use.run(SOURCE,tmp_path)
    md=artifacts.semantic_markdown.read_text(encoding='utf8')
    assert md.index('## Simple User Guide')<md.index('## Before Reading')
    assert '7.125' in md and '7 .' not in md
    assert '- (a) An engineer' in md and '- (b) You bring' in md
    assert 'Samsung Service Centre' in md and 'GSM: 7700 (e-store)' in md

@pytest.fixture(scope='module')
def bundle(tmp_path_factory):
    from tagged_pdf_extractor.cli import _build_use_case
    return _build_use_case().run(SOURCE,tmp_path_factory.mktemp('ua-source'))

def test_real_reader_dispatch_attaches_source_evidence():
    from tagged_pdf_extractor.domain.ua_sheet import SOURCE_SHA
    doc=TaggedPdfReader().read_for_profile(SOURCE,PROFILE)
    assert doc.source_sha256==SOURCE_SHA
    assert any(d.code=='ua_source_operations' for d in doc.diagnostics)
    assert doc.raw_children is None

def test_real_dispatch_rejects_changed_source_bytes(tmp_path):
    changed=tmp_path/SOURCE.name
    changed.write_bytes(SOURCE.read_bytes()+b'\n')
    with pytest.raises(ValueError,match='source revision'):
        TaggedPdfReader().read_for_profile(changed,PROFILE)

def test_cli_semantic_xml_ownership_and_raw_roundtrip(bundle):
    from xml.etree import ElementTree as E
    document,report,artifacts=bundle
    raw_xml=E.parse(artifacts.raw_xml).getroot();semantic=E.parse(artifacts.semantic_xml).getroot()
    parents={c:n for n in semantic.iter() for c in n}
    for ref,role in [('522 0 R','list_body'),('390 0 R','list_item'),('391 0 R','list_item')]:
        node=next(n for n in semantic.iter() if n.get('object-ref')==ref)
        assert parents[node].tag==role
        assert node.get('source-structure-path') is not None
    key=lambda n:(n.get('page-index'),n.get('mcid'),n.get('object-ref'))
    assert Counter(map(key,raw_xml.iter('fragment')))==Counter(map(key,semantic.iter('text')))
    text_by_key=lambda root,tag:{key(n):''.join(''.join(n.itertext()).split()) for n in root.iter(tag)}
    assert text_by_key(raw_xml,'fragment')==text_by_key(semantic,'text')
    assert len(list(semantic.iter('text')))==1155
    assert len(list(semantic.iter('table')))==19
    assert len(list(semantic.iter('figure')))==51
    assert all(report.hard_gates.values())
    assert len(document.heading_promotions)==5

def test_all_75_model_power_pairs_match_independent_pdf_text(bundle):
    import re,pymupdf
    from xml.etree import ElementTree as E
    root=E.parse(bundle[2].semantic_xml).getroot()
    content=' '.join(n.text or '' for n in root.iter('text') if n.get('page-index')=='1')
    pattern=r'\b((?:UE|QE|MRE)\d{2,3}[A-Z0-9]+):\s*(\d+)\s*W'
    with pymupdf.open(SOURCE) as pdf: observed=re.findall(pattern,pdf[1].get_text())
    extracted=re.findall(pattern,content)
    assert len(extracted)==75
    assert Counter(extracted)==Counter(observed)

def test_safety_table_ui_routes_and_source_phrasing_are_retained(bundle):
    from xml.etree import ElementTree as E
    root=E.parse(bundle[2].semantic_xml).getroot()
    table=next(n for n in root.iter('table') if n.get('object-ref')=='1088 0 R')
    assert len(list(table.iter('table_row')))==9
    assert len(list(table.iter('figure')))==6
    assert len([n for n in root.iter('figure') if n.get('icon-reason')=='navigation_route_inline_figure'])==12
    md=bundle[2].semantic_markdown.read_text(encoding='utf8')
    assert len([line for line in md.splitlines() if line.startswith('#')])==25  # document banner plus 24 source headings
    assert 'Always educate about the dangers of climbing' in md
    assert 'out of the reach.' in md
    assert '(M6\\*H: [아이콘] > left directional button' in md

@pytest.mark.parametrize('field,value',[('page_index',0),('page_index',True),('mcid',999),('mcid','1142')])
def test_operation_context_must_match_reviewed_page_and_mcid(raw,field,value):
    from tagged_pdf_extractor.domain.ua_sheet import prepare_ua_sheet
    from tagged_pdf_extractor.infrastructure.ua_source_evidence import add_ua_source_evidence
    doc=add_ua_source_evidence(raw,PROFILE)
    proof=next(d for d in doc.diagnostics if d.code=='ua_source_operations')
    changed=replace(proof,context={**proof.context,field:value})
    with pytest.raises(ValueError,match='operation evidence'):
        prepare_ua_sheet(replace(doc,diagnostics=tuple(changed if d is proof else d for d in doc.diagnostics)),PROFILE)

@pytest.mark.parametrize('field,value',[('actual_text',None),('actual_text',0),('glyphs','text'),('mcid','1142'),('operation_index','11023')])
def test_operation_runs_require_explicit_typed_evidence(raw,field,value):
    from tagged_pdf_extractor.domain.ua_sheet import prepare_ua_sheet
    from tagged_pdf_extractor.infrastructure.ua_source_evidence import add_ua_source_evidence
    doc=add_ua_source_evidence(raw,PROFILE)
    proof=next(d for d in doc.diagnostics if d.code=='ua_source_operations')
    run={**proof.context['runs'][0],field:value}
    if value is None:run.pop(field)
    changed=replace(proof,context={**proof.context,'runs':[run,*proof.context['runs'][1:]]})
    with pytest.raises(ValueError,match='operation evidence'):
        prepare_ua_sheet(replace(doc,diagnostics=tuple(changed if d is proof else d for d in doc.diagnostics)),PROFILE)
