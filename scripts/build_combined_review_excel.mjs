// Trusted combined-report contract. No business evaluation occurs here.
import { isMain, runWorkbookCli } from './review_workbook_backend.mjs';

export const contract = {
  cliName: 'build_combined_review_excel.mjs', schemaVersion: 'combined-review-excel-view/1',
  outputFilename: 'review_report.xlsx', tablePrefix: 'CombinedReviewTable',
  sheets: [
    { name: 'Summary', headers: ['구분', '항목', '값'], dataRows: 11 },
    { name: 'Checklist Results', headers: ['체크 ID', '기준 제목', '언어', '기준 문구', '현재 원문',
      '검토 판정', '설명', 'PDF 페이지', '검토 메모'] },
    { name: 'Item Results', headers: ['고정 항목 키', '기준 문구', '검토 판정', '설명',
      '검토 메모', '원장 모델 조건 제안', '원장 제안 근거', '원장 검토 메모'] },
    { name: 'Source Evidence', headers: ['체크 ID', '고정 항목 키', '근거 종류', '현재 원문', '현재 노드 ID',
      '태그 종류', 'PDF 페이지', 'XML 경로', '상세 근거 JSON'] },
  ],
  inspectRange: 'Checklist Results!A1:D4',
  previews: [['Summary', 'A1:C12', 'summary.png'],
    ['Checklist Results', 'A1:D5', 'checklist.png'], ['Checklist Results', 'E1:I5', 'checklist_notes.png'],
    ['Item Results', 'A1:D7', 'items.png'], ['Item Results', 'E1:H4', 'item_notes.png'],
    ['Source Evidence', 'A1:D4', 'evidence.png'], ['Source Evidence', 'E1:H4', 'evidence_nodes.png'],
    ['Source Evidence', 'I1:I3', 'evidence_details.png']],
};

if (isMain(import.meta.url)) await runWorkbookCli(contract);
