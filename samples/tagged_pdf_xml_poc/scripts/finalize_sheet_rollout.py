"""Seal a source-reviewed MENA/XL/XT extraction bundle, keeping human approval pending."""
import argparse
from hashlib import sha256
from html import escape
import json
from pathlib import Path
from xml.etree import ElementTree as E
from collections import Counter
from review_tk_xml import code_hashes,dump,text,norm
from finalize_zw_review import validate_current_artifacts

def seal(folder,audit):
    load=lambda name:json.loads((folder/name).read_text(encoding='utf8'))
    review=load('review_document.json');log=load('review_run.json');run=review['source']
    validate_current_artifacts(folder,review,log)
    if sha256(Path(run['pdf']).read_bytes()).hexdigest()!=run['sha256'] or run['code_sha256']!=code_hashes():
        raise ValueError('Source or runtime changed since extraction')
    if audit.get('source_sha256',audit.get('sha256'))!=run['sha256']:
        raise ValueError('Source audit belongs to a different PDF')
    if audit.get('final_semantic_sha256')!=sha256((folder/'semantic_document.xml').read_bytes()).hexdigest():
        raise ValueError('Final source audit does not identify this semantic artifact')
    if audit.get('final_source_review_complete') is not True:raise ValueError('Final source review incomplete')
    if any(v is not True for k,v in review['hard_gates'].items() if k!='source_review_complete'):
        raise ValueError('Unresolved hard gates')
    review['source_audit']=audit;review['hard_gates']['source_review_complete']=True
    review['status']='extraction_review_pass_pending_human_review'
    review['human_approval']=False
    dump(folder/'review_document.json',review)
    log.update(review_status=review['status'],hard_gate_failures=[],human_approval=False,
               validation_sha256=sha256((folder/'html_validation.json').read_bytes()).hexdigest())
    dump(folder/'review_run.json',log)
    return review

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path)
    p.add_argument('--source-reviewed',action='store_true',required=True);a=p.parse_args();out=a.output.resolve()
    manifest=json.loads((out/'manifest.json').read_text(encoding='utf8'))
    comparison=json.loads((out/'source_comparison_validation.json').read_text(encoding='utf8'))
    if (comparison.get('source_table_column_order') is not True or comparison.get('latin_table_cells_ltr') is not True
        or comparison.get('source_checks_sha256')!=sha256((out/'source_checks.html').read_bytes()).hexdigest()):
        raise ValueError('Source comparison direction or artifact validation failed')
    if sorted(r['buyer'] for r in manifest['runs'])!=['MENA_L02','XL_ENG','XT_L02']:
        raise ValueError('Final rollout requires all three distinct reviewed buyers')
    reviews=[seal(out/r['buyer'],json.loads((out/r['buyer']/'source_audit.json').read_text(encoding='utf8'))) for r in manifest['runs']]
    body='<h1>MENA · XL · XT 추출 검토</h1><p>추출 구조 검증 완료 · 사용자 컨펌 대기. 전체 HTML은 동일 Markdown을 렌더링한 결과이며 문자 순서와 문서 구조를 대조했습니다.</p>'
    body+='<p><a href="source_checks.html">PDF 원문 / Markdown 표지·표 비교</a></p><table><tr><th>바이어</th><th>언어</th><th>제목</th><th>검토 단위</th><th>표</th><th>그림</th><th>검토 파일</th></tr>'
    for review in reviews:
        buyer=review['source']['buyer']
        for lang,stats in review['language_stats'].items():
            body+=f'<tr><td>{buyer}</td><td>{lang}</td><td>{stats["headings"]}</td><td>{stats["review_units"]}</td><td>{stats["blocks"].get("table",0)}</td><td>{stats["blocks"].get("figure",0)}</td><td><a href="{buyer}/semantic_document.preview.html">전체 HTML</a> · <a href="{buyer}/semantic_document.md">MD</a> · <a href="{buyer}/semantic_document.xml">XML</a></td></tr>'
    body+='</table><p>제목은 표지 포함 표시 제목, 검토 단위는 문단·목록·표를 묶은 개수입니다. 그림 수는 XML figure 노드 수로, 파일 수나 고유 아이콘 수와 다릅니다.</p>'
    body+='<h2>확인 사항</h2><ul><li>MENA: ENG/ARA 본문 구조와 모델 136개, 연락처 13행 일치. 영어에만 있는 QR·바코드·문서코드 영역 때문에 전체 표·그림 수가 다릅니다.</li><li>XL: 공식 프로필 목록에 없어 PDF로 확인한 XL_ENG/A3/ENG를 검토용 설정으로 사용했습니다. 대표 지역·바이어 확장 정보는 추정하지 않았습니다.</li><li>XT: PDF 내장 글꼴의 문자 매핑 결함을 실제 글자 근거로 복원했습니다. 태국어 제목은 원문 추출값이며 번역으로 만든 제목이 아닙니다.</li><li>문서코드·바코드·안전 심볼·UI 아이콘 중 그래픽 부분은 원문 이미지로 확인합니다. 텍스트 OCR 결과로 표시하지 않았습니다.</li></ul>'
    for r in reviews:
        buyer=r['source']['buyer'];body+=f'<h2>{buyer} 제목 목록</h2>'
        wording={'MENA_L02':['ENG의 DC v-oltage 표기와 Arabic 중복 표현은 원문 그대로 보존했습니다.'],
          'XL_ENG':['All voice, Star Labeling 등의 표현은 원문 그대로입니다.'],
          'XT_L02':['ENG broadcated, THA 전원 문장의 ตู้เย็น 및 스위치 표현 ชัตเตอร์สวิตช์는 실제 PDF 표현입니다. 후속 번역·편집 검토 대상으로 남겼습니다.']}[buyer]
        body+='<p>원문 표현 확인: '+' '.join(escape(s) for s in wording)+'</p>'
        for lang,stats in r['language_stats'].items():
            body+=f'<h3>{lang}</h3><ol>'
            for h in stats['heading_texts']:
                display=escape(h)
                if lang=='ARA' and len(h)>2 and h[:2].isdigit():display=f'<bdi dir="ltr">{h[:2]}</bdi>'+escape(h[2:])
                body+=f'<li'+(' dir="rtl"' if lang=='ARA' else '')+'>'+display+'</li>'
            body+='</ol>'
        body+=f'<p><a href="{buyer}/source_audit.json">원문 대조 근거와 남은 Warning</a> · <a href="{buyer}/review_document.json">전체 검증 자료</a></p>'
    body+='<h2>함께 컨펌할 기존 결과</h2><p><a href="../xml_review_tk_20260917_direction_review/tk_review.html">TK 2종 · ENG/TUR/ARA</a> · <a href="../xml_review_zw_20260916_source_verified/zw_review.html">ZW · TPE</a></p><p>MENA / XL / XT / TK / ZW 모두 사용자 승인 대기 상태입니다.</p>'
    (out/'review.html').write_text('<!doctype html><meta charset="utf-8"><style>body{font:18px Arial;max-width:1150px;margin:40px auto;line-height:1.8}table{border-collapse:collapse}td,th{padding:10px;border:1px solid #aaa}li{margin:6px 0}[dir=rtl]{font-family:Tahoma}</style>'+body,encoding='utf8')
    dump(out/'final_summary.json',[dict(buyer=r['source']['buyer'],status=r['status'],stats=r['language_stats'],hard_gate_failures=[]) for r in reviews])
    print('All three extraction reviews sealed; five buyers remain pending human approval.')
if __name__=='__main__':main()
