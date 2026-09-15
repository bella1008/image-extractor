// Development-only visual verification of an already saved workbook.
import fs from 'node:fs/promises';
import path from 'node:path';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';
import { contract } from './build_combined_review_excel.mjs';

const [workbookPath, outputDir, modulesPath] = process.argv.slice(2);
if (!workbookPath || !outputDir || !modulesPath) throw new Error('Usage: WORKBOOK OUTPUT_DIR NODE_MODULES');
const require = createRequire(path.join(path.resolve(modulesPath), '..', '_preview_resolver.cjs'));
const { FileBlob, SpreadsheetFile } = await import(pathToFileURL(require.resolve('@oai/artifact-tool')).href);
const wb = await SpreadsheetFile.importXlsx(await FileBlob.load(path.resolve(workbookPath)));
console.log((await wb.inspect({ kind: 'sheet', include: 'id,name', maxChars: 1500 })).ndjson);
await fs.mkdir(outputDir, { recursive: true });
for (const [sheetName, range, name] of contract.previews) {
  const preview = await wb.render({ sheetName, range, scale: 1, format: 'png' });
  await fs.writeFile(path.join(outputDir, name), new Uint8Array(await preview.arrayBuffer()), { flag: 'wx' });
}
console.log('Rendered saved workbook without re-exporting or changing it.');
