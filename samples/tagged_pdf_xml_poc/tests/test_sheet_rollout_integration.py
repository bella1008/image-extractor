"""The public XML use case dispatches reviewed sheet profiles end to end."""
import json
from pathlib import Path
from xml.etree import ElementTree as E
import pytest
from tagged_pdf_extractor.cli import _build_use_case

POC=Path(__file__).resolve().parents[1]

@pytest.mark.parametrize('buyer,folder,filename,languages,headings',[
 ('MENA_L02','TV_MENA','BN68-25031L-00_SUG_Y26 TV ALL_MENA_L02_260114.0.pdf',['ENG','ARA'],8),
 ('XL_ENG','TV_XL','BN68-25031J-00_SUG_Y26 TV ALL_XL_ENG_260306.0.pdf',['ENG'],4),
 ('XT_L02','TV_XT','BN68-25031M-00_SUG_Y26 TV ALL_XT_L02_260113.0.pdf',['ENG','THA'],8)])
def test_actual_xml_dispatch_complete_buyer_source(tmp_path,buyer,folder,filename,languages,headings):
    source=POC.parents[1]/'samples/SUG_RAW'/folder/filename
    assert source.is_file(), f'Required reviewed source sample unavailable: {source}'
    canonical=POC.parents[1]/'metadata/pdf_profile_mapping/pdf_profile_mapping.json'
    rows=json.loads(canonical.read_text(encoding='utf8'))
    if buyer=='XL_ENG':rows.append(dict(source_token=buyer,doc_type='A3',languages='ENG',language_count=1))
    mapping=tmp_path/'profiles.json';mapping.write_text(json.dumps(rows),encoding='utf8')
    document,report,artifacts=_build_use_case(profile_mapping_path=mapping).run(source,tmp_path/buyer)
    assert report.status=='pass'
    assert document.readability_profile.languages==tuple(languages)
    assert document.raw_children is not None
    root=E.parse(tmp_path/buyer/'semantic_document.xml').getroot().find('document')
    assert len(list(root.iter('heading')))==headings
    assert (tmp_path/buyer/'semantic_document.md').stat().st_size>10000
    if buyer=='MENA_L02':
        assert [n.get('numbered-label') for n in root.iter('heading') if n.get('language')=='ARA']==['01','02','03','04']
        assert '<bdi dir="ltr">LS03H&#42;</bdi>' in (tmp_path/buyer/'semantic_document.md').read_text(encoding='utf8')
    if buyer=='XT_L02':assert '\ufffd' not in ''.join(n.text or '' for n in root.iter('text'))
