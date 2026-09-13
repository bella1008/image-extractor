// Trusted standalone-item contract; preserve the existing CLI and output filename.
import { isMain, runWorkbookCli } from './review_workbook_backend.mjs';

export const contract = {
  cliName: 'build_item_review_excel.mjs', schemaVersion: 'item-review-excel-view/2',
  outputFilename: 'item_review.xlsx', tablePrefix: 'ItemResultTable',
  sheets: [
    { name: 'Summary', headers: ['구분', '항목', '값'], dataRows: 11 },
    { name: 'Item Results', headers: ['고정 항목 키', '기준 문구', '검토 판정', '설명',
      '검토 메모', '원장 모델 조건 제안', '원장 제안 근거', '원장 검토 메모'] },
    { name: 'Source Evidence', headers: ['고정 항목 키', '근거 종류', '현재 원문', '현재 노드 ID',
      '태그 종류', 'PDF 페이지', 'XML 경로', '상세 근거 JSON'] },
  ],
  inspectRange: 'Item Results!A1:D4',
  previews: [['Summary', 'A1:C12', 'summary.png'], ['Item Results', 'A1:D7', 'items.png'],
    ['Item Results', 'E1:H4', 'item_notes.png'], ['Source Evidence', 'A1:G4', 'evidence.png'],
    ['Source Evidence', 'H1:H3', 'evidence_details.png']],
};

if (isMain(import.meta.url)) await runWorkbookCli(contract);
