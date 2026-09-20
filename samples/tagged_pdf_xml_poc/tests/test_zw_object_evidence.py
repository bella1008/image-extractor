from pathlib import Path
from dataclasses import replace
import pytest
from tagged_pdf_extractor.domain.models import PdfProfile, Diagnostic
from tagged_pdf_extractor.infrastructure.pypdf_reader import TaggedPdfReader
from tagged_pdf_extractor.infrastructure import zw_object_evidence as zw

SOURCE=Path(__file__).resolve().parents[3]/'samples/SUG_RAW/TV_ZW/BN68-24973D-00_SUG_Y26 TV ALL_ZW_TPE_260327.0.pdf'
PROFILE=PdfProfile('ZW_TPE','A3',('TPE',),1)
@pytest.fixture(scope='module')
def document():
    if not SOURCE.exists():pytest.skip('ZW source unavailable')
    return TaggedPdfReader().read(SOURCE)

def test_verified_vector_and_annotation_evidence_resolves_without_changing_raw(document):
    result=zw.add_zw_object_evidence(document,PROFILE)
    assert result.children==document.children
    assert [d.code for d in result.diagnostics]==['zw_vector_form_resolved','zw_link_objr_resolved','zw_link_objr_resolved']
    assert result.diagnostics[0].context['evidence']['text_operator_count']==0
    assert result.diagnostics[1].context['evidence']['annotation_ref']=='31 0 R'
    assert result.diagnostics[2].context['evidence']['annotation_ref']=='32 0 R'
    assert result.diagnostics[1].context['original_diagnostic']['code']=='unsupported_objr'

def test_other_profile_remains_blocked(document):
    assert zw.add_zw_object_evidence(document,replace(PROFILE,source_token='OTHER_TPE')) is document

def test_changed_source_remains_blocked(document,tmp_path):
    source=tmp_path/'changed.pdf';source.write_bytes(SOURCE.read_bytes()+b'\n')
    changed=replace(document,source_path=source)
    assert zw.add_zw_object_evidence(changed,PROFILE) is changed

def test_changed_diagnostic_context_remains_blocked(document):
    ds=list(document.diagnostics);ds[0]=replace(ds[0],context={'page_index':0,'operand_repr':"'/Fm0'"})
    changed=replace(document,diagnostics=tuple(ds))
    assert zw.add_zw_object_evidence(changed,PROFILE) is changed

def test_changed_object_remains_blocked(document,monkeypatch):
    from pypdf import PdfReader
    from pypdf.generic import NameObject,TextStringObject
    reader=PdfReader(SOURCE);reader.get_object(33)[NameObject('/URI')]=TextStringObject('http://different.test')
    monkeypatch.setattr(zw,'PdfReader',lambda path:reader)
    assert zw.add_zw_object_evidence(document,PROFILE) is document

def test_missing_link_text_remains_blocked(document):
    assert zw.add_zw_object_evidence(replace(document,children=()),PROFILE).diagnostics==document.diagnostics

def test_changed_form_stream_remains_blocked(document,monkeypatch):
    from pypdf import PdfReader
    reader=PdfReader(SOURCE)
    reader.get_object(29).set_data(b'BT (missing text) Tj ET')
    monkeypatch.setattr(zw,'PdfReader',lambda path:reader)
    assert zw.add_zw_object_evidence(document,PROFILE) is document

def test_additional_objr_remains_blocked(document):
    changed=replace(document,diagnostics=document.diagnostics+(document.diagnostics[-1],))
    assert zw.add_zw_object_evidence(changed,PROFILE) is changed

def test_unrelated_blocker_is_preserved(document):
    blocker=Diagnostic('warning','unresolved_mcid','Missing content',{'page_index':1,'mcid':9999})
    changed=replace(document,diagnostics=document.diagnostics+(blocker,))
    assert zw.add_zw_object_evidence(changed,PROFILE).diagnostics[-1] is blocker
