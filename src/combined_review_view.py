"""Four-sheet presentation only; parent and item decisions stay unevaluated."""
from copy import deepcopy
import json

from src.combined_review_model import validate_combined_report
from src.item_review_excel import build_item_excel_view, _cell


def _general_evidence_row(row):
    # Columns already contain the flattened text/location. Keep the complete
    # node evidence and remaining context here, without repeating those columns.
    # The untouched original observation is also archived in review_report.json.
    kinds = {'strict':'일반 문구','candidate':'구조 후보','fragment':'분산 문구'}
    detail = {key:row[key] for key in ('composition_method','language','required_fragment',
                                      'node_details','visual_node_ids','caveats')}
    return [row['check_id'],'',kinds[row['evidence_kind']],row['text'],row['source_node_ids'],
            row['structure_types'],row['pdf_pages'],row['xml_paths'].replace('\n','; '),
            json.dumps(detail,ensure_ascii=False,sort_keys=True,separators=(',', ':'))]


def build_combined_review_view(report, *, version='combined-review-excel-view/2'):
    if version not in ('combined-review-excel-view/1', 'combined-review-excel-view/2'):
        raise ValueError('unsupported combined view version')
    checklist_view = validate_combined_report(report)
    item_view = build_item_excel_view(report['items'])
    summary = report['summary']
    item_summary = report['items']['summary']
    summary_rows = [
        ['검토 대상','PDF 파일',checklist_view['source']['pdf_filename']],
        ['검토 대상','프로필',report['checklist']['context']['source_token']],
        ['검토 대상','검토 언어',report['checklist']['language']],
        ['검토 범위','상태','모든 항목 검토 필요. 모델 적용 미확정. 자동 합격·불합격 아님.'],
        ['집계','상위 체크리스트',summary['parent_check_count']],
        ['집계','그중 구성품 상세',summary['child_item_count']],
        ['구성품','단일 문구 근거',item_summary['found']],
        ['구성품','조건 안내 연결 후보',item_summary['condition_candidate_items']],
        ['근거','상세 근거 행',summary['checklist_evidence_count']+summary['item_evidence_count']],
        ['제외','대상 아님 / 기존 비승인',summary['excluded_count']],
        ['사용 방법','검토 메모','사본에 메모하세요. DB 승인 입력이 아닙니다. 상위 건수에 구성품 상세를 더하지 않습니다.'],
    ]
    rows = []
    for row in checklist_view['checklist']:
        description = row['description']
        if row['check_id'] == report['items']['parent_check_id']:
            description += ' 구성품별 근거는 Item Results 참조.'
        rows.append([row['check_id'],row['section_heading'],row['language'],row['required_text'],
                     row['evidence_excerpt'],'검토 필요',description,row['pdf_pages'],''])
    evidence = [_general_evidence_row(row) for row in checklist_view['evidence']]
    for row in item_view['sheets'][2]['rows']:
        evidence.append([report['items']['parent_check_id'],row[0],
                         '구성품 문구' if row[1]=='항목 문구' else row[1],*row[2:]])
    sheets = [
        dict(name='Summary',headers=['구분','항목','값'],rows=summary_rows,widths=[20,30,110],freeze='A2'),
        dict(name='Checklist Results',headers=['체크 ID','기준 제목','언어','기준 문구','현재 원문',
             '검토 판정','설명','PDF 페이지','검토 메모'],rows=rows,
             widths=[27,40,12,90,90,14,65,12,45],freeze='B2'),
        deepcopy(item_view['sheets'][1]),
        dict(name='Source Evidence',headers=['체크 ID','고정 항목 키','근거 종류','현재 원문','현재 노드 ID',
             '태그 종류','PDF 페이지','XML 경로','상세 근거 JSON'],rows=evidence,
             widths=[27,30,20,90,55,65,12,95,255],freeze='C2'),
    ]
    if version == 'combined-review-excel-view/2':
        # Display current-run evidence, never historical author proposals as facts.
        item_rows = []
        for item in report['items']['items']:
            pages = sorted({entry['page_index'] + 1
                            for window in item['candidates'] for part in window['parts']
                            for entry in part.get('evidence', [])
                            if type(entry.get('page_index')) is int})
            item_rows.append([item['item_key'], item['required_text'],
                              '\n\n'.join(w['text'] for w in item['candidates']),
                              '검토 필요', item['description'], ', '.join(map(str, pages)),
                              '\n\n'.join(w['text'] for w in item['condition_candidates']), ''])
        sheets[2] = dict(name='Item Results', headers=['고정 항목 키', '기준 문구', '현재 원문',
                         '검토 판정', '설명', 'PDF 페이지', '조건 안내 원문 (후보)', '검토 메모'],
                         rows=item_rows, widths=[30, 58, 58, 14, 65, 12, 65, 45], freeze='B2')
        sheets[3]['headers'] = sheets[3]['headers'][:-1]
        sheets[3]['rows'] = [row[:-1] for row in sheets[3]['rows']]
        sheets[3]['widths'] = sheets[3]['widths'][:-1]
        summary_rows[8] = ['사용 방법', '근거 확인',
                           'Source Evidence에서 체크 ID 또는 고정 항목 키로 필터하세요. PDF 페이지는 파일의 실제 페이지 순서입니다.']
        summary_rows[9] = ['검토 범위', '포함 기능',
                           '체크리스트 문구 조사. PDF 변경 비교·회사 사양 검토·다국어 의미/맞춤법 검토는 미실행.']
    for sheet in sheets:
        sheet['rows'] = [[_cell(value) for value in row] for row in sheet['rows']]
    return {'schema_version':version,'decision_status':'not_evaluated',
            'activation_status':'draft_only','sheets':sheets}
