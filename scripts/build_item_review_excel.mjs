// Explicit Artifact Tool backend. Python owns source validation and completion.
import fs from 'node:fs/promises';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';

const [viewArg, outputArg, expectedHash, modulesArg] = process.argv.slice(2);
if (!viewArg || !outputArg || !modulesArg || !/^[a-f0-9]{64}$/.test(expectedHash ?? '')) {
  throw new Error('Usage: build_item_review_excel.mjs VIEW OUTPUT_DIR SHA256 NODE_MODULES');
}
const require = createRequire(path.join(path.resolve(modulesArg), '..', '_item_excel_resolver.cjs'));
const { Workbook, SpreadsheetFile } = await import(pathToFileURL(require.resolve('@oai/artifact-tool')).href);
const digest = bytes => createHash('sha256').update(bytes).digest('hex');
const viewPath = path.resolve(viewArg), outputDir = path.resolve(outputArg);
const content = await fs.readFile(viewPath);
if (digest(content) !== expectedHash) throw new Error('Display contract hash differs');
const view = JSON.parse(content);
if (view.schema_version !== 'item-review-excel-view/1' || view.activation_status !== 'draft_only'
    || view.decision_status !== 'not_evaluated') throw new Error('Unsupported Excel view');
if (view.sheets.map(s => s.name).join('|') !== 'Summary|Item Results|Source Evidence') throw new Error('Unexpected sheets');
const column = n => {let result='';while(n){n--;result=String.fromCharCode(65+n%26)+result;n=Math.floor(n/26);}return result;};
const literal = value => typeof value === 'string' && value.startsWith('=') ? "'" + value : value;
const lines = (text, width) => String(text).split('\n').reduce((n, line) => n + Math.max(1,
  Math.ceil([...line].reduce((sum,ch) => sum + (ch.codePointAt(0)>255?1.9:1),0)/(width*0.82))),0);
const wb = Workbook.create();
for (const [index, spec] of view.sheets.entries()) {
  const sheet = wb.worksheets.add(spec.name);
  sheet.showGridLines = false;
  const matrix = [spec.headers, ...spec.rows];
  if (matrix.some(row => row.length !== spec.headers.length || row.some(v =>
      !(typeof v === 'string' || Number.isSafeInteger(v)) || (typeof v === 'string' && v.length > 32767)))) {
    throw new Error('Invalid Excel cell');
  }
  const range = sheet.getRangeByIndexes(0,0,matrix.length,spec.headers.length);
  range.values = matrix.map(row => row.map(literal));
  range.format.font = {name:'Arial',size:10,color:'#202B3A'};
  range.format.wrapText = true;
  range.format.verticalAlignment = 'top';
  spec.widths.forEach((width,c) => sheet.getRangeByIndexes(0,c,matrix.length,1).format.columnWidth=width);
  for (let r=1;r<matrix.length;r++) {
    const height = Math.max(30,Math.max(...matrix[r].map((v,c)=>lines(v,spec.widths[c])))*13+10);
    if(height>409) throw new Error(`Source needs more display space: ${spec.name} row ${r+1}`);
    range.getRow(r).format.rowHeight = height;
    matrix[r].forEach((v,c) => {
      if(typeof v==='number') sheet.getCell(r,c).setNumberFormat('#,##0');
    });
  }
  const header=range.getRow(0);
  header.format.fill='#D9EAF7';
  header.format.font={name:'Arial',size:10,bold:true,color:'#202B3A'};
  header.format.horizontalAlignment='center';
  header.format.rowHeight=32;
  const table = sheet.tables.add(`A1:${column(spec.headers.length)}${matrix.length}`,true,`ItemResultTable${index+1}`);
  table.showFilterButton = true;
  sheet.freezePanes.freezeRows(1);
  if(spec.name==='Item Results') {
    sheet.freezePanes.freezeColumns(1);
    sheet.getRangeByIndexes(1,2,spec.rows.length,1).format.fill='#FFF4CE';
    sheet.getRangeByIndexes(1,6,spec.rows.length,1).format.fill='#FFF4CE';
    sheet.tabColor='#243E60';
  }
  if(spec.name==='Source Evidence') sheet.freezePanes.freezeColumns(2);
}
wb.recalculate();
console.log((await wb.inspect({kind:'sheet',include:'id,name',maxChars:1500})).ndjson);
console.log((await wb.inspect({kind:'table',range:'Item Results!A1:D4',include:'values,formulas',tableMaxRows:4,tableMaxCols:4,maxChars:2500})).ndjson);
console.log((await wb.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!',
  options:{useRegex:true,maxResults:20},maxChars:1000})).ndjson);
const previews=[['Summary','A1:C12','summary.png'],['Summary','A12:C23','sources.png'],
  ['Item Results','A1:D7','items.png'],['Item Results','E1:J4','item_notes.png'],
  ['Source Evidence','A1:H4','evidence.png'],['Source Evidence','I1:I3','evidence_details.png']];
for (const [sheetName,range,name] of previews) {
  const blob = await wb.render({sheetName,range,scale:1,format:'png'});
  await fs.writeFile(path.join(outputDir,name),new Uint8Array(await blob.arrayBuffer()),{flag:'wx'});
}
if(digest(await fs.readFile(viewPath)) !== expectedHash) throw new Error('Display contract changed');
const pending=path.join(outputDir,`.item-review-${process.pid}.pending.xlsx`);
try {
  await (await SpreadsheetFile.exportXlsx(wb)).save(pending);
  if(digest(await fs.readFile(viewPath)) !== expectedHash) throw new Error('Display contract changed before publication');
  await fs.link(pending,path.join(outputDir,'item_review.xlsx'));
} finally {await fs.rm(pending,{force:true});}
console.log('Workbook saved; Python must validate all cells before completion.');
