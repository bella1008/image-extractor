"""Seal independently source-reviewed UA/XD bundles without granting human approval."""
import argparse
from hashlib import sha256
from html import escape
import json
from pathlib import Path

from finalize_sheet_rollout import seal
from review_tk_xml import dump


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    out = parser.parse_args().output.resolve()
    manifest = json.loads((out / 'manifest.json').read_text(encoding='utf8'))
    if [r['buyer'] for r in manifest['runs']] != ['UA_ENG', 'XD_INS']:
        raise ValueError('Both distinct source reviews are required')
    comparison = json.loads((out / 'source_comparison_validation.json').read_text(encoding='utf8'))
    if (comparison.get('source_table_column_order') is not True
            or comparison.get('latin_table_cells_ltr') is not True
            or comparison.get('source_checks_sha256') != sha256((out / 'source_checks.html').read_bytes()).hexdigest()):
        raise ValueError('Source comparison render proof missing or stale')
    reviews = [seal(out / r['buyer'], json.loads((out / r['buyer'] / 'source_audit.json').read_text(encoding='utf8')))
               for r in manifest['runs']]
    body = '<h1>UA · XD 추출 검토</h1><p>추출 구조 검증 완료 · 사용자 승인 대기. 전체 HTML은 Markdown을 렌더링하고 XML 문자 순서 및 검토 단위 구조와 대조했습니다.</p>'
    body += '<p><a href="source_checks.html">PDF 원문 / Markdown 표지·표·수정 영역 비교</a></p>'
    body += '<table><tr><th>바이어</th><th>유형 / 언어</th><th>표시 제목</th><th>검토 단위</th><th>표</th><th>그림 노드</th><th>파일</th></tr>'
    for review in reviews:
        buyer = review['source']['buyer']
        for language, stats in review['language_stats'].items():
            body += f'<tr><td>{buyer}</td><td>A3 / {language}</td><td>{stats["headings"]}</td><td>{stats["review_units"]}</td><td>{stats["blocks"].get("table", 0)}</td><td>{stats["blocks"].get("figure", 0)}</td><td><a href="{buyer}/semantic_document.preview.html">전체 HTML</a> · <a href="{buyer}/semantic_document.md">MD</a> · <a href="{buyer}/semantic_document.xml">XML</a></td></tr>'
    body += '</table><p>표시 제목은 표지를 포함합니다. 그림은 XML figure 노드 수이며 고유 이미지 수와 다릅니다. XD는 보증서·보증 조건·서비스센터 주소표가 있어 UA와 전체 구조 수가 다릅니다.</p>'
    body += '<h2>검토 범위</h2><p>UA 영어는 ZC ENG를 먼저 기준으로 삼고 XL/XU A3 구조와 대조했습니다. XD는 영어가 없는 인도네시아어 문서이므로 원문과 A3 기준 구조를 대조했습니다. 국가별 고유 내용이나 원문 표현을 영어에 맞춰 바꾸지 않았습니다.</p>'
    body += '<p>표지 순서, 전원 문장·하위 조건의 소속, 소수·주소·URL 공백, 병합 셀과 특수 구조를 확인했습니다. 원문 그림으로 된 문서코드·바코드·안전 심볼·UI 아이콘은 텍스트 OCR 결과로 주장하지 않으며 PDF crop을 함께 확인합니다.</p>'
    body += '<h2>원문 표현 확인 사항</h2><ul><li>UA: “Always educate about the dangers of climbing”, “All voice”, “Guide came with this product” 등은 실제 PDF 표현이라 유지했습니다.</li><li>XD: “Situ Web”, 주소의 “15,,” 등과 인도네시아어 본문 안의 영어 LS03HW 문장은 원문 그대로입니다. Wi-Fi의 5,925 · 7,125 · 6.425처럼 쉼표와 점을 섞어 쓴 표기도 유지했습니다.</li><li>이 항목들은 후속 번역·편집 검토 후보입니다. 추출 과정에서 임의로 교정하지 않았습니다.</li></ul>'
    for review in reviews:
        buyer = review['source']['buyer']
        body += f'<h2>{buyer} 원문 제목</h2>'
        for language, stats in review['language_stats'].items():
            body += f'<h3>{language}</h3><ol>' + ''.join(f'<li>{escape(h)}</li>' for h in stats['heading_texts']) + '</ol>'
        body += f'<p><a href="{buyer}/source_audit.json">원문 비교 근거·차이·남은 Warning</a> · <a href="{buyer}/review_document.json">검증 bundle</a></p>'
    body += '<h2>함께 승인 대기 중인 결과</h2><p><a href="../xml_review_mena_xl_xt_20260917_ready/review.html">MENA · XL · XT</a> · <a href="../xml_review_tk_20260917_direction_review/tk_review.html">TK 2종</a> · <a href="../xml_review_zw_20260916_source_verified/zw_review.html">ZW</a> · <a href="../xml_review_py_sq_mi_20260919_verified/review.html">PY · SQ_MI</a></p><p>기존 7개 바이어의 승인 대기는 유지했습니다. UA · XD를 포함하면 총 9개 바이어가 사용자 승인 대기입니다. 추출 검증은 번역 품질 승인이나 사용자 컨펌을 뜻하지 않습니다.</p>'
    (out / 'review.html').write_text('<!doctype html><meta charset="utf-8"><style>body{font:18px Arial;max-width:1250px;margin:40px auto;line-height:1.8}table{border-collapse:collapse;width:100%}td,th{padding:9px;border:1px solid #aaa}li{margin:6px 0}</style>' + body, encoding='utf8')
    dump(out / 'final_summary.json', dict(human_approval=False,
         pending_buyers=['MENA', 'XL', 'XT', 'TK', 'ZW', 'PY', 'SQ_MI', 'UA', 'XD'],
         runs=[dict(buyer=r['source']['buyer'], status=r['status'], stats=r['language_stats'], hard_gate_failures=[]) for r in reviews]))
    print('UA/XD sealed; all nine buyers remain pending human approval.')


if __name__ == '__main__':
    main()
