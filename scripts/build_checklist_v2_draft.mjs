// Development-only workbook authoring. Run in a task output directory with the
// bundled @oai/artifact-tool package linked as node_modules. No application import.
import fs from "node:fs/promises";
import path from "node:path";
import { Workbook, SpreadsheetFile } from "@oai/artifact-tool";

const directory = path.resolve(process.argv[2]);
const audit = JSON.parse(await fs.readFile(path.join(directory, "migration_audit.json"), "utf8"));
const destination = path.join(directory, "checklist_v2_draft.xlsx");
try { await fs.access(destination); throw new Error("Output already exists; use a new build directory."); }
catch (error) { if (error.code !== "ENOENT") throw error; }
const workbook = Workbook.create();
const summary = workbook.worksheets.add("Summary");
const master = workbook.worksheets.add("Checklist_V2");
const migration = workbook.worksheets.add("Migration_Audit");
const scope = workbook.worksheets.add("Scope_Differences");

function cellText(value) {
  return typeof value === "string" && value.startsWith("=") ? "'" + value : value;
}
function fillTable(sheet, headers, rows, widths, name) {
  const matrix = [headers, ...rows.map(row => headers.map(key => cellText(row[key] ?? "")))];
  const range = sheet.getRangeByIndexes(0, 0, matrix.length, headers.length);
  range.values = matrix;
  range.format.font = { name: "Arial", size: 10, color: "#202B3A" };
  range.format.verticalAlignment = "top";
  range.format.wrapText = true;
  sheet.showGridLines = false;
  for (let c = 0; c < headers.length; c++) sheet.getRangeByIndexes(0, c, matrix.length, 1).format.columnWidth = widths[c] ?? 22;
  const header = sheet.getRangeByIndexes(0, 0, 1, headers.length);
  header.format.fill = "#233752";
  header.format.font = { name: "Arial", size: 10, color: "#FFFFFF", bold: true };
  header.format.rowHeight = 34;
  header.format.horizontalAlignment = "center";
  header.format.verticalAlignment = "center";
  for (let r = 1; r < matrix.length; r++) {
    const lines = Math.max(...matrix[r].map((value, c) => {
      const text = String(value ?? "");
      return text.split("\n").reduce((sum, line) => sum + Math.max(1, Math.ceil(
        [...line].reduce((n, char) => n + (char.codePointAt(0) > 255 ? 1.8 : 1), 0) / ((widths[c] ?? 22) * 0.87))), 0);
    }));
    sheet.getRangeByIndexes(r, 0, 1, headers.length).format.rowHeight = Math.min(409, Math.max(28, lines * 14 + 8));
  }
  sheet.tables.add(`A1:${columnName(headers.length)}${matrix.length}`, true, name);
  sheet.freezePanes.freezeRows(1);
}
function columnName(number) {
  let name = "";
  while (number) { number--; name = String.fromCharCode(65 + number % 26) + name; number = Math.floor(number / 26); }
  return name;
}

fillTable(master, audit.draft_headers, audit.draft_rows,
  [18, 38, 20, 22, 28, 28, 18, 14, 48, 26, 24, 100, 24, 16, 22, 75, 105], "ChecklistV2Draft");
master.getRange(`A2:Q${audit.draft_rows.length + 1}`).setNumberFormat("@");
master.getRange(`O2:O${audit.draft_rows.length + 1}`).dataValidation = {
  rule: { type: "list", values: ["approved", "review", "deprecated"] },
};
const auditHeaders = ["excel_row", "check_id", "approval_status", "migration_status", "evidence_state",
  "source_restriction_would_drop", "overlap_contexts", "reason", "evidence_file"];
fillTable(migration, auditHeaders, audit.rows, [12, 42, 20, 20, 29, 26, 21, 55, 100], "ChecklistMigrationAudit");
const scopeHeaders = ["check_id", "source_token", "region", "language", "doc_type", "rule_source_token",
  "legacy_applicable", "if_source_token_restricts"];
fillTable(scope, scopeHeaders, audit.scope_differences, [42, 29, 16, 16, 16, 28, 22, 29], "SourceRestrictionCounterfactual");
migration.getRange(`D2:D${audit.rows.length + 1}`).conditionalFormats.add("containsText", {
  text: "pending", format: { fill: "#FFF1CE", font: { color: "#714800" } },
});

summary.showGridLines = false;
summary.tabColor = "#233752";
summary.getRange("A1:F28").format.font = { name: "Arial", size: 10, color: "#202B3A" };
summary.getRange("A1:F28").format.rowHeight = 25;
summary.getRange("A1:A28").format.columnWidth = 43;
summary.getRange("B1:B28").format.columnWidth = 23;
summary.getRange("C1:C28").format.columnWidth = 4;
summary.getRange("D1:D28").format.columnWidth = 40;
summary.getRange("E1:F28").format.columnWidth = 32;
summary.getRange("A2").values = [["체크리스트 v2 이관 대조"]];
summary.getRange("A2").format.font = { name: "Arial", size: 14, bold: true };
summary.getRange("A4:B12").values = [
  ["항목", "수량 / 상태"], ["원본 규칙", audit.summary.source_rows],
  ["v2 초안 규칙", null], ["기존 승인 상태 유지", null],
  ["기존 검토 중 상태 유지", null], ["기존 폐기 상태 유지", null],
  ["원본 Excel / JSON 값 차이", audit.summary.sync_differences],
  ["업무 요구사항 common_id", audit.summary.common_ids], ["자동 판정 연결", "미연결"],
];
summary.getRange("A4:B4").format.fill = "#233752";
summary.getRange("A4:B4").format.font = { name: "Arial", bold: true, color: "#FFFFFF" };
const end = audit.draft_rows.length + 1;
summary.getRange("B6:B9").formulas = [
  [`=COUNTA(Checklist_V2!B2:B${end})`],
  [`=COUNTIFS(Checklist_V2!O2:O${end},"approved")`],
  [`=COUNTIFS(Checklist_V2!O2:O${end},"review")`],
  [`=COUNTIFS(Checklist_V2!O2:O${end},"deprecated")`],
];
summary.getRange("D4:E9").values = [
  ["근거 기록 현황", "규칙 수"],
  ["파일 존재 · 내용 재검증 전", audit.summary.evidence_states.exists_not_revalidated ?? 0],
  ["기록된 경로에 파일/폴더 없음", audit.summary.evidence_states.missing ?? 0],
  ["폴더만 지정", audit.summary.evidence_states.directory_reference ?? 0],
  ["설명문으로 기록", audit.summary.evidence_states.descriptive_reference ?? 0],
  ["source_token 오해 시 영향 규칙", audit.summary.source_restriction_affected_rules],
];
summary.getRange("D4:E4").format.fill = "#233752";
summary.getRange("D4:E4").format.font = { name: "Arial", bold: true, color: "#FFFFFF" };
summary.getRange("A15:B19").values = [
  ["기존 열", "v2 열"], ["status", "approval_status"],
  ["source_token", "source_reference_token"], ["section_heading", "legacy_section_heading"],
  ["block_type", "legacy_block_type"],
];
summary.getRange("B15:B19").format.columnWidth = 32;
summary.getRange("A15:B15").format.fill = "#E7EDF4";
summary.getRange("D12").values = [["source_reference_token은 출처 기록입니다."]];
summary.getRange("D13").values = [["빈 값도 보존하며 적용 제한으로 쓰지 않습니다."]];
summary.getRange("D15").values = [["Scope_Differences는 적용하면 안 되는 제한의 영향표입니다."]];
summary.getRange("D17").values = [["pending: 원문/승인은 보존, XML 검토 호환성은 확인 전"]];
summary.getRange("D18").values = [["excluded: 기존 review/deprecated 행. 삭제하지 않았습니다."]];
summary.getRange("D20").values = [["같은 common_id의 복수 행은 국가/모델별 기준일 수 있습니다."]];
summary.getRange("D21").values = [["중복으로 단정하여 합치거나 제거하지 않았습니다."]];
summary.getRange("A23").values = [["원본: mvp_checklist_master.xlsx / 복구 기준 4b001ff9"]];
summary.getRange("A24").values = [["원문·범위·승인·ID·근거 기록 17개 필드의 값을 그대로 보존했습니다."]];
summary.getRange("A25").values = [["이관 대조 기준: 2026-09-11. 변경 후에는 대조 도구를 다시 실행합니다."]];
workbook.recalculate();
console.log((await workbook.inspect({ kind: "table", range: "Summary!A4:B12", include: "values,formulas", tableMaxRows: 9, tableMaxCols: 2 })).ndjson);
console.log((await workbook.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#NUM!", options: { useRegex: true, maxResults: 10 }, maxChars: 1000 })).ndjson);
for (const [sheetName, range, label] of [
  ["Summary", "A1:F26", "summary"], ["Checklist_V2", "A1:H5", "master"],
  ["Checklist_V2", "I1:O4", "wording"], ["Migration_Audit", "A1:H5", "audit"],
  ["Scope_Differences", "A1:H7", "scope"],
]) {
  const preview = await workbook.render({ sheetName, range, scale: 1, format: "png" });
  await fs.writeFile(path.join(directory, `${label}.png`), new Uint8Array(await preview.arrayBuffer()));
}
await (await SpreadsheetFile.exportXlsx(workbook)).save(destination);
console.log(destination);
