// Presentation only. Python validates sources and every saved cell before completion.
import fs from 'node:fs/promises';
import path from 'node:path';
import { createHash, randomUUID } from 'node:crypto';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';

const digest = bytes => createHash('sha256').update(bytes).digest('hex');
const column = n => {
  let result = '';
  while (n) { n--; result = String.fromCharCode(65 + n % 26) + result; n = Math.floor(n / 26); }
  return result;
};
const literal = value => typeof value === 'string' && value.startsWith('=') ? "'" + value : value;
const lines = (text, width) => String(text).split('\n').reduce((n, line) => n + Math.max(1,
  Math.ceil([...line].reduce((sum, ch) => sum + (ch.codePointAt(0) > 255 ? 1.9 : 1), 0) / (width * 0.82))), 0);
const rowHeight = (row, widths) => Math.max(30, Math.max(...row.map((v, c) => lines(v, widths[c]))) * 13 + 10);

export function validateView(view, contract) {
  if (!view || view.schema_version !== contract.schemaVersion || view.activation_status !== 'draft_only'
      || view.decision_status !== 'not_evaluated') throw new Error('Unsupported Excel view');
  if (!Array.isArray(view.sheets) || view.sheets.map(s => s?.name).join('|') !== contract.sheets.map(s => s.name).join('|')) {
    throw new Error('Unexpected sheets');
  }
  for (const [index, spec] of view.sheets.entries()) {
    const expected = contract.sheets[index];
    if (JSON.stringify(spec.headers) !== JSON.stringify(expected.headers)) throw new Error(`Unexpected headers: ${spec.name}`);
    if (!Array.isArray(spec.rows)) throw new Error('Invalid Excel rows');
    if (expected.dataRows !== undefined && spec.rows.length !== expected.dataRows) throw new Error(`Unexpected ${spec.name} rows`);
    if (!Array.isArray(spec.widths) || spec.widths.length !== spec.headers.length
        || spec.widths.some(w => typeof w !== 'number' || !Number.isFinite(w) || w <= 0 || w > 255)) {
      throw new Error('Invalid Excel widths');
    }
    if (!/^[ABC]2$/.test(spec.freeze)) throw new Error('Invalid freeze pane');
    const matrix = [spec.headers, ...spec.rows];
    if (matrix.some(row => !Array.isArray(row) || row.length !== spec.headers.length || row.some(v =>
      !(typeof v === 'string' || Number.isSafeInteger(v)) || (typeof v === 'string' && v.length > 32767)))) {
      throw new Error('Invalid Excel cell');
    }
    for (let r = 1; r < matrix.length; r++) {
      if (rowHeight(matrix[r], spec.widths) > 409) throw new Error(`Source needs more display space: ${spec.name} row ${r + 1}`);
    }
  }
}

export const isMain = url => Boolean(process.argv[1]) && pathToFileURL(path.resolve(process.argv[1])).href === url;

export async function runWorkbookCli(contract, args = process.argv.slice(2)) {
  const [viewArg, outputArg, expectedHash, modulesArg] = args;
  if (args.length !== 4 || !viewArg || !outputArg || !modulesArg || !/^[a-f0-9]{64}$/.test(expectedHash ?? '')) {
    throw new Error(`Usage: ${contract.cliName} VIEW OUTPUT_DIR SHA256 NODE_MODULES`);
  }
  const viewPath = path.resolve(viewArg), outputDir = path.resolve(outputArg);
  const content = await fs.readFile(viewPath);
  if (digest(content) !== expectedHash) throw new Error('Display contract hash differs');
  const view = JSON.parse(content);
  validateView(view, contract);
  const outputPath = path.join(outputDir, contract.outputFilename);
  try {
    await fs.lstat(outputPath);
    throw new Error(`Workbook already exists: ${contract.outputFilename}`);
  } catch (error) { if (error.code !== 'ENOENT') throw error; }

  // Resolve only from the explicitly supplied bundled dependencies; never install or fetch.
  const modulesPath = await fs.realpath(path.resolve(modulesArg));
  const require = createRequire(path.join(modulesPath, '..', '_review_excel_resolver.cjs'));
  const entry = await fs.realpath(require.resolve('@oai/artifact-tool'));
  const relativeEntry = path.relative(modulesPath, entry);
  if (relativeEntry.startsWith('..') || path.isAbsolute(relativeEntry)) throw new Error('Artifact Tool is outside explicit NODE_MODULES');
  const { Workbook, SpreadsheetFile } = await import(pathToFileURL(entry).href);
  const wb = Workbook.create();
  for (const [index, spec] of view.sheets.entries()) {
    const sheet = wb.worksheets.add(spec.name);
    sheet.showGridLines = false;
    const matrix = [spec.headers, ...spec.rows];
    const range = sheet.getRangeByIndexes(0, 0, matrix.length, spec.headers.length);
    range.values = matrix.map(row => row.map(literal));
    range.format.font = { name: 'Arial', size: 10, color: '#202B3A' };
    range.format.wrapText = true;
    range.format.verticalAlignment = 'top';
    spec.widths.forEach((width, c) => sheet.getRangeByIndexes(0, c, matrix.length, 1).format.columnWidth = width);
    for (let r = 1; r < matrix.length; r++) {
      range.getRow(r).format.rowHeight = rowHeight(matrix[r], spec.widths);
      matrix[r].forEach((v, c) => { if (typeof v === 'number') sheet.getCell(r, c).setNumberFormat('#,##0'); });
    }
    const header = range.getRow(0);
    header.format.fill = '#D9EAF7';
    header.format.font = { name: 'Arial', size: 10, bold: true, color: '#202B3A' };
    header.format.horizontalAlignment = 'center';
    header.format.rowHeight = 32;
    const table = sheet.tables.add(`A1:${column(spec.headers.length)}${matrix.length}`, true, `${contract.tablePrefix}${index + 1}`);
    table.showFilterButton = true;
    sheet.freezePanes.freezeRows(1);
    const frozenColumns = spec.freeze.charCodeAt(0) - 65;
    if (frozenColumns) sheet.freezePanes.freezeColumns(frozenColumns);
    if (spec.rows.length) {
      for (const label of ['검토 판정', '검토 메모']) {
        const c = spec.headers.indexOf(label);
        if (c >= 0) sheet.getRangeByIndexes(1, c, spec.rows.length, 1).format.fill = '#FFF4CE';
      }
    }
    if (spec.headers.includes('검토 판정')) sheet.tabColor = '#243E60';
  }
  wb.recalculate();
  console.log((await wb.inspect({ kind: 'sheet', include: 'id,name', maxChars: 1500 })).ndjson);
  console.log((await wb.inspect({ kind: 'table', range: contract.inspectRange, include: 'values,formulas',
    tableMaxRows: 4, tableMaxCols: 4, maxChars: 2500 })).ndjson);
  console.log((await wb.inspect({ kind: 'match', searchTerm: '#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!',
    options: { useRegex: true, maxResults: 20 }, maxChars: 1000 })).ndjson);
  for (const [sheetName, range, name] of contract.previews) {
    const blob = await wb.render({ sheetName, range, scale: 1, format: 'png' });
    await fs.writeFile(path.join(outputDir, name), new Uint8Array(await blob.arrayBuffer()), { flag: 'wx' });
  }
  if (digest(await fs.readFile(viewPath)) !== expectedHash) throw new Error('Display contract changed');
  const pending = path.join(outputDir, `.${contract.tablePrefix}-${randomUUID()}.pending.xlsx`);
  const reservation = await fs.open(pending, 'wx');
  await reservation.close();
  try {
    await (await SpreadsheetFile.exportXlsx(wb)).save(pending);
    if (digest(await fs.readFile(viewPath)) !== expectedHash) throw new Error('Display contract changed before publication');
    await fs.link(pending, outputPath);
  } finally { await fs.rm(pending, { force: true }); }
  console.log('Workbook saved; Python must validate all cells before completion.');
}
