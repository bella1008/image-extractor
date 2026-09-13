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


def build_combined_review_view(report):
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
    for sheet in sheets:
        sheet['rows'] = [[_cell(value) for value in row] for row in sheet['rows']]
    return {'schema_version':'combined-review-excel-view/1','decision_status':'not_evaluated',
            'activation_status':'draft_only','sheets':sheets}
