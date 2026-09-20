"""Seal two source-reviewed runs while preserving every human approval as pending."""
import argparse,json
from pathlib import Path
from hashlib import sha256
from html import escape
from finalize_sheet_rollout import seal
from review_tk_xml import dump

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path)
    out=p.parse_args().output.resolve()
    manifest=json.loads((out/'manifest.json').read_text(encoding='utf8'))
    if [r['buyer'] for r in manifest['runs']]!=['PY_ENRU','SQ_MI_HEAR']:
        raise ValueError('Final review requires both distinct sources')
    comparison=json.loads((out/'source_comparison_validation.json').read_text(encoding='utf8'))
    if (comparison.get('source_table_column_order') is not True or comparison.get('latin_table_cells_ltr') is not True
            or comparison.get('source_checks_sha256')!=sha256((out/'source_checks.html').read_bytes()).hexdigest()):
        raise ValueError('Source comparison rendering proof does not match')
    reviews=[seal(out/r['buyer'],json.loads((out/r['buyer']/'source_audit.json').read_text(encoding='utf8'))) for r in manifest['runs']]
    body='<h1>PY · SQ_MI 추출 검토</h1><p>추출 구조 검증 완료 · 사용자 승인 대기. 아래 전체 HTML은 Markdown을 그대로 렌더링하고 XML 문자 순서와 대조한 결과입니다.</p>'
    body+='<p><a href="source_checks.html">PDF 원문 / Markdown 표지·표·특수 영역 비교</a></p>'
    body+='<table><tr><th>바이어 / 유형</th><th>언어</th><th>표시 제목</th><th>검토 단위</th><th>표</th><th>그림 노드</th><th>파일</th></tr>'
    for r in reviews:
        buyer=r['source']['buyer']
        for lang,s in r['language_stats'].items():
            body+=f'<tr><td>{buyer} / A2</td><td>{lang}</td><td>{s["headings"]}</td><td>{s["review_units"]}</td><td>{s["blocks"].get("table",0)}</td><td>{s["blocks"].get("figure",0)}</td><td><a href="{buyer}/semantic_document.preview.html">전체 HTML</a> · <a href="{buyer}/semantic_document.md">MD</a> · <a href="{buyer}/semantic_document.xml">XML</a></td></tr>'
    body+='</table><p>표시 제목은 표지 제목 포함입니다. 본문 제목은 각 언어 23개이며 번호 제목 01~05를 포함합니다. 검토 단위는 문단·목록·표 단위, 그림은 XML figure 노드 수입니다.</p>'
    body+='<h2>원문 구조 확인</h2><ul><li>PY: RUS → ENG. ZC ENG와 먼저 비교한 뒤 PY ENG/RUS 및 CE RUS를 대조했습니다. 각 언어의 모델·소비전력 80쌍과 연락처 12개 국가 행을 확인했습니다. 러시아어의 포장재·규제 그림과 표지 코드 영역은 원문 차이입니다.</li><li>SQ_MI: HEB → ARA, 영어 없음. MENA/TK 아랍어 기준과 먼저 비교하고 두 현지어를 원문 대조했습니다. 각 본문 표 17개, 목록 항목 113개와 번호 제목 5개, 음향 모델 18종·마이크 모델 12종이 대응합니다.</li><li>SQ_MI 괄호는 글꼴 매핑과 실제 글자 위치로 확인했습니다. 원본 추출의 72/66개가 아닌, 실제 문장에 맞는 69/69개로 복원하고 변경 근거를 보존했습니다.</li></ul>'
    body+='<h2>사람이 확인할 내용</h2><ul><li>바코드·QR·문서코드 일부·안전 심볼·UI 아이콘은 그림입니다. 텍스트 OCR 결과로 주장하지 않으며 원문 crop을 함께 확인합니다.</li><li>PY 러시아어 중복 표현, SQ 아랍어 방향 표현과 قك 등은 실제 PDF 표현이므로 유지했습니다. 후속 번역·편집 검토 대상입니다.</li><li>추출 통과는 사용자 승인이나 번역 품질 승인을 뜻하지 않습니다.</li></ul>'
    for r in reviews:
        buyer=r['source']['buyer'];langs=list(r['language_stats'])
        body+=f'<h2>{buyer} 제목 대응</h2><table><tr>'+''.join(f'<th>{lang}</th>' for lang in langs)+'</tr>'
        headings=[r['language_stats'][lang]['heading_texts'] for lang in langs]
        for row in zip(*headings):
            body+='<tr>'
            for lang,h in zip(langs,row):
                value=escape(h)
                if lang in {'ARA','HEB'} and len(h)>2 and h[:2].isdigit():value=f'<bdi dir="ltr">{h[:2]}</bdi>'+escape(h[2:])
                body+='<td'+(' dir="rtl"' if lang in {'ARA','HEB'} else '')+'>'+value+'</td>'
            body+='</tr>'
        body+=f'</table><p><a href="{buyer}/source_audit.json">원문 대조 근거와 Warning</a> · <a href="{buyer}/review_document.json">검증 bundle</a></p>'
    body+='<h2>기존 승인 대기 5개 바이어</h2><p><a href="../xml_review_mena_xl_xt_20260917_ready/review.html">MENA · XL · XT</a> · <a href="../xml_review_tk_20260917_direction_review/tk_review.html">TK 2종</a> · <a href="../xml_review_zw_20260916_source_verified/zw_review.html">ZW</a></p><p>기존 5개 상태를 유지했습니다. PY · SQ_MI까지 포함하면 현재 승인 대기 대상은 총 7개 바이어입니다.</p>'
    (out/'review.html').write_text('<!doctype html><meta charset="utf-8"><style>body{font:18px Arial;max-width:1250px;margin:40px auto;line-height:1.8}table{border-collapse:collapse;width:100%;direction:ltr}td,th{padding:9px;border:1px solid #aaa}li{margin:6px 0}[dir=rtl]{font-family:Tahoma}</style>'+body,encoding='utf8')
    dump(out/'final_summary.json',dict(human_approval=False,pending_buyers=['MENA','XL','XT','TK','ZW','PY','SQ_MI'],
        runs=[dict(buyer=r['source']['buyer'],status=r['status'],stats=r['language_stats'],hard_gate_failures=[]) for r in reviews]))
    print('PY/SQ MI sealed; all seven buyers remain pending human approval.')
if __name__=='__main__':main()
