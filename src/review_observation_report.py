"""Offline, escaped human view of provisional checklist observations."""
from html import escape

_METHODS = {'atomic_text': '단일 원문 단위', 'adjacent_paragraphs': '연속 문단 연결',
            'list_item_label_body': '같은 목록의 기호 + 본문', 'text_beside_visual': '아이콘 옆의 연속 텍스트'}
_REASONS = {'unsupported_selector': '현재 구조 선택 방식 미지원', 'heading_not_found': '기존 제목에 대응하는 검증된 범위 없음',
            'ambiguous_heading': '제목이 중복되어 범위 확정 불가', 'unsafe_heading': '제목 근거 추가 확인 필요',
            'provisional_scope_and_role_require_review': '새 구조 대응 승인 필요',
            'unsupported_match_method': '표 등 전용 검사 방식 미연결', 'no_bounded_candidate': '현재 안전 범위에서 전체 문구 후보 없음'}


def _text(value):
    return escape(str(value), quote=True)


def _evidence(view):
    refs = []
    for part in view.get('parts', []):
        for evidence in part.get('evidence', []):
            page = evidence.get('page_index')
            label = f'{page + 1}쪽' if type(page) is int else '페이지 미확정'
            refs.append(f"{label} · {evidence['xml_path']} · MCID {evidence.get('mcid')}")
    refs = list(dict.fromkeys(refs))
    visual = view.get('visual_node_ids', [])
    return ('<pre>' + _text(view['text']) + '</pre><small>' + '<br>'.join(_text(ref) for ref in refs) + '</small>'
            + ('<p>아이콘 문맥 확인 필요: ' + _text(', '.join(visual)) + '</p>' if visual else ''))


def render_observation_html(report: dict) -> str:
    if report.get('schema_version') != 'checklist-observation/2' or report.get('decision_status') != 'not_evaluated':
        raise ValueError('only unevaluated observation schema 2 may be rendered')
    rows = report['rows']
    active = [r for r in rows if r['status'] == 'needs_review']
    strict = sum(bool(r['matches']) for r in active)
    candidates = sum(bool(r['candidate_matches']) for r in active)
    body = ['<!doctype html><html lang="ko"><meta charset="utf-8"><title>XML 체크리스트 연결 검토</title>',
            '<style>body{font:16px/1.6 system-ui,sans-serif;max-width:1200px;margin:36px auto;padding:0 24px;color:#202c3c;background:#f4f6f9}'
            'article{background:white;border:1px solid #ccd4df;border-radius:8px;padding:20px;margin:18px 0}'
            'pre{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit;background:#f5f7fa;padding:12px}'
            'small{overflow-wrap:anywhere;color:#455468}.notice{padding:16px;background:#fff2cd}'
            '.columns{display:grid;grid-template-columns:1fr 1fr;gap:20px}h1,h2,h3{line-height:1.3}'
            '@media(max-width:800px){.columns{grid-template-columns:1fr}}@media print{article{break-inside:avoid}}</style>',
            '<h1>XML 체크리스트 연결 검토</h1><p class="notice">자동 합격·불합격 판정 아님. 원본 DB·승인 상태는 변경하지 않았습니다. '
            '문구를 찾았더라도 구조·검사 범위의 업무 적합성은 별도 검토가 필요합니다. 이 화면은 최종 Excel 양식이 아닌 연결 확인용입니다.</p>',
            '<p>' + _text(report['context']['manual_code']) + ' · ' + _text(report['context']['source_token']) + ' · ' + _text(report['language']) + '</p>',
            f'<p>전체 {len(rows)}개 / 적용 {len(active)}개 / 엄격한 검색 근거 {strict}개 / 추가 구조 연결 후보 {candidates}개 / 나머지 {len(active)-strict-candidates}개</p>',
            '<p>근거에 표시되는 페이지는 1부터 시작합니다. 후보의 줄바꿈은 보기용 연결이며, 원문 조각과 XML 위치는 결과 JSON에 각각 보존됩니다. '
            '아이콘 옆 텍스트 후보는 아이콘 자체가 올바르다는 뜻이 아닙니다.</p>']
    for row in active:
        rule = row['source_rule']
        label = '엄격한 검색 근거 발견' if row['matches'] else ('구조 연결 후보 — 새 구조 대응 승인 필요' if row['candidate_matches'] else '연결 미완료 — 원문 누락 판정 아님')
        body.extend(['<article><h2>' + _text(row['check_id']) + '</h2><p>' + label + '</p>',
                     '<p>' + _text(rule['legacy_section_heading']) + ' · 기존 유형 ' + _text(rule['legacy_block_type']) + ' · ' + _text(rule['match_method']) + '</p>',
                     '<p>' + _text(_REASONS.get(row['reason'], row['reason'])) + '</p>',
                     '<div class="columns"><section><h3>기준 문구</h3><pre>' + _text(rule['required_text']) + '</pre></section><section><h3>실제 근거</h3>'])
        for view in row['matches']:
            body.append(_evidence(view))
        for view in row['candidate_matches']:
            body.append('<h3>' + _text(_METHODS.get(view['method'], view['method'])) + '</h3>' + _evidence(view))
            if 'table_structure_requires_review' in view['caveats']:
                body.append('<p>표 안의 문구 후보입니다. 행·열·아이콘 관계는 별도 확인해야 합니다.</p>')
        if not row['matches'] and not row['candidate_matches']:
            body.append('<p>' + _text(_REASONS.get(row['candidate_reason'], row['candidate_reason'])) + '</p>')
            fragments = row.get('fragment_observations')
            if fragments:
                body.append('<h3>분산된 문구 근거 — 전체 일치 아님</h3><p>DB에 기록된 줄별 위치만 확인합니다. 순서·묶음·표 관계의 승인은 아닙니다.</p>')
                for fragment in fragments['fragments']:
                    body.append('<h4>기준 조각</h4><pre>' + _text(fragment['required_text']) + '</pre>')
                    for candidate in fragment['candidates']:
                        body.append(_evidence(candidate))
                    if not fragment['candidates']:
                        body.append('<p>현재 범위에서 이 조각의 근거 후보 없음</p>')
        body.append('</section></div></article>')
    body.append('<details><summary>이번 대상에서 제외된 규칙도 모두 보존</summary><ul>')
    for row in rows:
        if row['status'] != 'needs_review':
            body.append('<li>' + _text(row['check_id']) + ' · ' + _text(row['status']) + ' · ' + _text(row['reason']) + '</li>')
    body.append('</ul></details><p>원문·근거·해시와 모든 규칙: observation.json. 완료 파일: review_complete.json. 완료 파일이 없는 실행은 사용할 수 없습니다.</p></html>')
    return '\n'.join(body)
