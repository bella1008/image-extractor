"""Record the completed visual ZW review after automated source checks pass.

Run only after inspecting both pages and the generated source comparisons.
This records extraction fidelity, not human approval of Taiwan wording.
"""
import argparse
from hashlib import sha256
from html import escape
import json
from pathlib import Path
import re
from xml.etree import ElementTree as E

import pymupdf as fitz
from review_tk_xml import code_hashes, dump, norm, text

SOURCE_SHA='37e8ef8c16b250463c4a57f5efc199a0f65bd8f9a1e10eacc5562b727f82e99f'

def validate_current_artifacts(folder,review,log):
    required=('xml_markdown_full_character_sequence','xml_markdown_all_units',
              'md_preview_text_and_structure_equal','ownership_dom_pass','isolated_model_display_pass')
    if any(review.get('hard_gates',{}).get(key) is not True for key in required):
        raise ValueError('Required renderer gates absent or failed')
    validation=json.loads((folder/'html_validation.json').read_text(encoding='utf8'))
    if any(validation.get(k) is not True for k in required if k!='xml_markdown_all_units') or validation.get('unit_failures')!=[]:
        raise ValueError('Renderer validation absent or failed')
    required_artifacts=('raw_structure.xml','semantic_document.xml','semantic_document.md','extraction_report.json')
    for name in required_artifacts:
        if log.get('artifact_sha256',{}).get(name)!=sha256((folder/name).read_bytes()).hexdigest():
            raise ValueError('Extraction artifact changed: '+name)
    for name,key in [('semantic_document.md','markdown_sha256'),('semantic_document.xml','semantic_xml_sha256'),('semantic_document.preview.html','preview_html_sha256')]:
        if validation.get(key)!=sha256((folder/name).read_bytes()).hexdigest():
            raise ValueError('Rendered artifact changed: '+name)
    return validation

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path)
    parser.add_argument('--source-reviewed',action='store_true',required=True)
    out=parser.parse_args().output.resolve();folder=out/'ZW_TPE'
    read=lambda name:json.loads((folder/name).read_text(encoding='utf8'))
    review=read('review_document.json');run=review['source'];log=read('review_run.json')
    validate_current_artifacts(folder,review,log)
    if sha256(Path(run['pdf']).read_bytes()).hexdigest()!=SOURCE_SHA:raise ValueError('Unreviewed source')
    if run['code_sha256']!=code_hashes():raise ValueError('Runtime changed: extract into a fresh folder')
    if any(not v for k,v in review['hard_gates'].items() if k!='source_review_complete'):
        raise ValueError('Automated hard gates remain')
    root=E.parse(folder/'semantic_document.xml').getroot().find('document')
    with fitz.open(run['pdf']) as pdf:baseline=pdf[1].get_text()
    model_pattern=r'([A-Z][A-Z0-9]{7,})\s*:\s*(\d+)\s*W'
    source_values=re.findall(model_pattern,baseline)
    semantic_values=re.findall(model_pattern,text(root))
    if len(source_values)!=49 or source_values!=semantic_values:raise ValueError('Model/power mismatch')
    spec=next(n for n in root.iter('table') if n.get('object-ref')=='432 0 R')
    consumption=spec.findall('table_row')[3]
    if re.findall(model_pattern,text(consumption))!=source_values:raise ValueError('Consumption continuation ownership mismatch')
    rohs=next(n for n in root.iter('table') if n.get('object-ref')=='199 0 R')
    matrix=[[norm(text(c)) for c in row if c.tag in ('table_cell','table_header')] for row in rohs.findall('table_row')[3:9]]
    if len(matrix)!=6 or any(len(row)!=7 or row[1:]!=[('○' if i in (1,4) else '－'),*['○']*5] for i,row in enumerate(matrix)):
        raise ValueError('RoHS cell relationship mismatch')
    routes=[n for n in root.iter() if n.tag in ('paragraph','list_body') and '>' in text(n)]
    if len(routes)!=5:raise ValueError('Navigation count mismatch')
    if len(review['language_stats']['TPE']['heading_texts'])!=24:raise ValueError('Heading inventory changed')
    review['source_audit']={'method':'Both source pages and cover/table crops visually compared; no external semantic API.',
        'model_power_pairs':semantic_values,'model_power_sequence_matches_independent_pdf':True,
        'consumption_single_field':True,'rohs_matrix':matrix,'rohs_cells':36,
        'navigation_source_refs':[n.get('object-ref') for n in routes],
        'reference_layouts':['XU_ENG A3 ENG','KR_KOR A3 CJK','TK_L02 ENG'],
        'source_exceptions':['No fee conditions in this PDF','Four numbered chapters; Taiwan-specific wireless and RoHS sections','Taiwan cover contact block is not a country contact table']}
    warnings=[
        {'id':'ZW-source-01','kind':'source_editorial','text':'마이크 지원 모델은 PDF에도 9*H로 표기됨. R9*H로 추정 수정하지 않음.','source':'PDF 2p 마이크 설명'},
        {'id':'ZW-source-02','kind':'source_editorial','text':'전원 설명의 造成‵電擊 / 免受於受到 / 造成會電擊를 원문 그대로 보존. 향후 편집 검토 후보.','source':'PDF 1p 電源'},
        {'id':'ZW-visual-01','kind':'vector_text','text':'표지 BN68-24973D는 벡터 윤곽선이며 -00만 PDF 텍스트. 전체 BN68-24973D-00은 crop 직접 확인 전사이며 자동 텍스트 추출 결과가 아님.','crop':'ZW_TPE/document_code.png'},
        {'id':'ZW-visual-02','kind':'non_text','text':'안전 심볼·조작 그림·barcode·UI 아이콘은 원문 crop으로 검토. MD의 아이콘/그림 표시는 OCR 결과가 아님.','crop':'source_checks.html'}]
    review['warnings']=warnings
    review['hard_gates'].update(source_review_complete=True,model_power_source_sequence=True,consumption_single_field=True,rohs_matrix_preserved=True,navigation_inventory=True)
    review['status']='extraction_review_pass_pending_human_review'
    dump(folder/'review_document.json',review)
    log.update(review_status=review['status'],hard_gate_failures=[],human_approval=False,
               validation_sha256=sha256((folder/'html_validation.json').read_bytes()).hexdigest())
    dump(folder/'review_run.json',log)
    body='<h1>ZW 대만 추출 검토</h1><p>ZW_TPE · A3 · TPE · 2페이지 · 구조 Hard gate 0. 사용자 원문/표현 검토 대기.</p>'
    body+='<p><a href="ZW_TPE/semantic_document.preview.html">전체 HTML 검토</a> · <a href="ZW_TPE/semantic_document.md">Markdown</a> · <a href="ZW_TPE/semantic_document.xml">Semantic XML</a> · <a href="source_checks.html">원문과 표·표지 비교</a></p>'
    body+='<p>제목 24개(표지 포함), 검토 단위 122개, 표 17개, 안전 심볼 6개, UI 경로 5개. 모델·소비전력 49쌍과 RoHS 36셀 확인. HTML은 동일 MD에서 생성하고 전체 문자 순서와 구조를 검사했습니다. PDF와의 사진 같은 조판 일치를 뜻하지는 않습니다.</p>'
    body+='<h2>원문 확인 사항</h2><ul>'+''.join('<li><b>'+w['id']+'</b>: '+escape(w['text'])+'</li>' for w in warnings)+'</ul>'
    body+='<p>아래 코드는 PDF 벡터 원문 이미지입니다. 보이는 전체 코드는 BN68-24973D-00입니다.</p><img style="max-width:700px" src="ZW_TPE/document_code.png">'
    (out/'zw_review.html').write_text('<!doctype html><meta charset="utf-8"><style>body{font:18px Arial;max-width:1050px;margin:40px auto;line-height:1.8}li{margin:16px 0}</style>'+body,encoding='utf8')
    print(review['status'])

if __name__=='__main__':main()
