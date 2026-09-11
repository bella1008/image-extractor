"""Escaped, offline presentation of draft item observations; no decisions."""
from collections import Counter
from html import escape


def _text(value):
    return escape(str(value))


def _source_panel(source, title):
    labels = {'pdf_filename': 'PDF 파일', 'pdf_sha256': 'PDF SHA256',
              'semantic_xml_sha256': 'XML SHA256', 'bundle_path': '추출 결과 위치',
              'receipt_ref': '추출 완료 기록', 'receipt_sha256': '완료 기록 SHA256'}
    rows = ''.join(f'<dt>{label}</dt><dd>{_text(source[key])}</dd>'
                   for key, label in labels.items() if key in source)
    return f'<section><h2>{title}</h2><dl>{rows}</dl></section>'


def _evidence(windows):
    if not windows:
        return '<p class="muted">연결된 원문 근거 없음</p>'
    pieces = []
    for window in windows:
        evidence = [entry for part in window.get('parts', []) for entry in part.get('evidence', [])]
        pages = sorted({entry['page_index'] + 1 for entry in evidence if type(entry.get('page_index')) is int})
        paths = list(dict.fromkeys(entry['xml_path'] for entry in evidence if entry.get('xml_path')))
        identifiers = [('소유 노드 ID', ', '.join(window.get('owner_ids', []))),
                       ('태그', ', '.join(window.get('structure_types', []))),
                       ('PDF 페이지', ', '.join(map(str, pages)) or '정보 없음')]
        metadata = ''.join(f'<p class="metadata">{label}: {_text(value)}</p>' for label, value in identifiers)
        xml = '<details><summary>XML 상세 위치</summary><pre>' + _text('\n'.join(paths)) + '</pre></details>'
        pieces.append(f'<div class="evidence"><pre>{_text(window["text"])}</pre>{metadata}{xml}</div>')
    return ''.join(pieces)


def render_item_review_html(report: dict) -> str:
    """Render only unresolved observations and keep current evidence distinct."""
    if (report.get('schema_version') != 'checklist-item-observation/1'
            or report.get('decision_status') != 'not_evaluated'
            or report.get('activation_status') != 'draft_only'):
        raise ValueError('unsupported or activated item report')
    items, summary = report['items'], report['summary']
    states = ('found', 'ambiguous', 'not_found', 'not_examined')
    for item in items:
        if (item.get('result') != 'needs_review' or item.get('model_applicability') != 'unknown'
                or item.get('condition_state') != 'unverified' or item.get('observation') not in states):
            raise ValueError('unsupported item decision')
    counts = Counter(item['observation'] for item in items)
    expected = {'item_count': len(items), 'needs_review': len(items),
                'condition_candidate_items': sum(bool(item['condition_candidates']) for item in items),
                **{state: counts[state] for state in states}}
    if any(summary.get(key) != value for key, value in expected.items()):
        raise ValueError('item summary differs from rows')
    labels = [('item_count', '하위 항목'), ('found', '단일 문구 근거'), ('ambiguous', '복수 근거'),
              ('not_found', '검색 범위 내 미발견'), ('not_examined', '범위 미확정'),
              ('condition_candidate_items', '조건 안내 연결 후보')]
    stats = ''.join(f'<div><span>{label}</span><strong>{summary[key]}</strong></div>' for key, label in labels)
    table = ''.join('<tr><td>' + _text(item['item_key']) + '</td><td class="wording">'
                    + _text(item['required_text']) + '</td><td><span class="pending">검토 필요</span></td><td>'
                    + _text(item['description']) + '</td></tr>' for item in items)
    details = []
    for item in items:
        proposal = item['author_proposal']
        proposal_rows = ''.join(f'<dt>{label}</dt><dd class="wording">{_text(proposal[key]) or "입력 없음"}</dd>'
                               for key, label in [('proposed_model_rule', '모델 조건 제안'),
                                                  ('proposal_evidence', '제안 근거 자료'),
                                                  ('reviewer_note', '검토 메모')])
        details.append('<details class="item"><summary>' + _text(item['item_key']) + ' — '
                       + _text(item['required_text']) + '</summary><h3>현재 문서의 항목 원문</h3>'
                       + _evidence(item['candidates']) + '<h3>현재 문서의 조건 안내 후보</h3>'
                       + _evidence(item['condition_candidates'])
                       + '<h3>담당자 제안</h3><p>제안문은 자동 실행하지 않습니다. 모델 적용 여부는 미확정입니다.</p><dl>'
                       + proposal_rows + '</dl></details>')
    return ('''<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>구성품 항목별 검토</title><style>
body{font-family:Arial,"Malgun Gothic",sans-serif;color:#233044;background:#f6f8fb;margin:0;padding:28px}
main{max-width:1400px;margin:auto}h1{font-size:26px;margin-bottom:10px}h2{font-size:19px}h3{font-size:16px}
section,.item{background:white;border:1px solid #dce3ec;border-radius:8px;padding:18px;margin:18px 0}
.notice{background:#fff4ce;padding:14px;border-radius:6px;line-height:1.7}
.stats{display:flex;gap:12px;flex-wrap:wrap;margin:20px 0}.stats div{background:white;padding:12px 18px;border:1px solid #dce3ec;border-radius:6px}
.stats span{display:block;font-size:13px}.stats strong{display:block;font-size:23px;margin-top:6px}
dl{display:grid;grid-template-columns:180px minmax(0,1fr);gap:10px;margin:0}dt{font-weight:600}dd{margin:0;overflow-wrap:anywhere}
.table-wrap{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:14px}th{text-align:left;background:#e6eef8}
td,th{padding:12px;border-bottom:1px solid #dce3ec;vertical-align:top}td{overflow-wrap:anywhere}
.pending{white-space:nowrap;background:#fff4ce;padding:3px 7px;border-radius:4px}.wording,pre{white-space:pre-wrap;overflow-wrap:anywhere}
pre{font-family:inherit;font-size:14px;line-height:1.65}.evidence{border-left:3px solid #9cb3d2;padding:6px 14px;margin:12px 0}
.metadata,.muted{font-size:13px;color:#506176}.metadata{overflow-wrap:anywhere}summary{cursor:pointer;line-height:1.6}
@media(max-width:700px){body{padding:12px}dl{grid-template-columns:1fr}dd{margin-bottom:10px}}
</style></head><body><main><h1>구성품 항목별 검토</h1>
<p class="notice">문구를 찾았다는 사실과 모델별 필수 여부는 다릅니다. 모든 항목은 검토 필요이며 자동 합격·불합격 판정이 아닙니다.
부모 항목은 출처 연결용으로만 보존하고 하위 항목 수에 중복 합산하지 않습니다.</p>'''
    + f'<p>부모 체크항목: {_text(report["parent_check_id"])}</p><div class="stats">{stats}</div>'
    + _source_panel(report['target_source'], '검토 대상 PDF')
    + '<section><h2>항목별 결과</h2><div class="table-wrap"><table><thead><tr><th>고정 항목 키</th><th>기준 문구</th><th>검토 판정</th><th>설명</th></tr></thead><tbody>'
    + table + '</tbody></table></div></section><h2>현재 문서의 상세 근거</h2>' + ''.join(details)
    + '<details class="item"><summary>원장 작성 당시 출처 — 현재 문서 근거와 별개</summary>'
    + _source_panel(report['master_source'], '원장 작성 당시 출처') + '</details></main></body></html>')
