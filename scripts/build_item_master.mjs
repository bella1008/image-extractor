// Development-only authoring. Colleagues edit Excel and use the Python exporter.
import fs from 'node:fs/promises';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { Workbook, SpreadsheetFile } from '@oai/artifact-tool';

const [seedArg, outputArg, expectedHash] = process.argv.slice(2);
if (!seedArg || !outputArg || !/^[a-f0-9]{64}$/.test(expectedHash ?? '')) {
  throw new Error('Usage: build_item_master.mjs SEED OUTPUT_DIR EXPECTED_SEED_SHA256');
}
const seedPath = path.resolve(seedArg);
const seedBytes = await fs.readFile(seedPath);
const digest = bytes => createHash('sha256').update(bytes).digest('hex');
if (digest(seedBytes) !== expectedHash) throw new Error('Seed hash mismatch');
const seed = JSON.parse(seedBytes);
if (seed.schema_version !== 'checklist-item-master-seed/1' || seed.activation_status !== 'draft_only') {
  throw new Error('Only checked item-master draft seeds are supported');
}
const outputDir = path.resolve(outputArg);
await fs.mkdir(outputDir, { recursive: true });
const target = path.join(outputDir, 'checklist_item_master.xlsx');
try { await fs.access(target); throw new Error('Use a fresh workbook path'); }
catch (error) { if (error.code !== 'ENOENT') throw error; }

const editable = new Set(['proposed_model_rule', 'proposal_evidence', 'reviewer_note']);
const widths = {source_check_id:26,item_key:31,required_text:68,model_applicability:23,
  condition_state:22,proposed_model_rule:60,proposal_evidence:60,reviewer_note:60,
  start:10,end:10,common_id:17,language:12,scope:15,exclude_scope:18,source_marker:17,
  evidence_refs:32,condition_refs:32,evidence_id:33,kind:18,text:95,
  source_node_ids:48,structure_types:23,pdf_pages:14,details_json:230,field:36,value:140};
const wb = Workbook.create();
const column = n => {let result='';while(n){n--;result=String.fromCharCode(65+n%26)+result;n=Math.floor(n/26);}return result;};
const literal = value => value.startsWith('=') ? "'" + value : value;
function estimatedLines(text, width) {
  return text.split('\n').reduce((n,line)=>n+Math.max(1,Math.ceil(
    [...line].reduce((total,ch)=>total+(ch.codePointAt(0)>255?1.9:1),0)/(width*0.82))),0);
}
for (const [index, contract] of seed.sheets.entries()) {
  const sheet = wb.worksheets.add(contract.name);
  sheet.showGridLines=false;
  const matrix=[contract.headers,...contract.rows];
  if (matrix.some(row=>row.length!==contract.headers.length || row.some(v=>typeof v!=='string' || v.length>32767))) {
    throw new Error(`Invalid text table: ${contract.name}`);
  }
  const range=sheet.getRangeByIndexes(0,0,matrix.length,contract.headers.length);
  range.values=matrix.map(row=>row.map(literal));
  range.format.font={name:'Arial',size:10,color:'#202B3A'};
  range.format.wrapText=true;
  range.format.verticalAlignment='top';
  contract.headers.forEach((key,c)=>{
    sheet.getRangeByIndexes(0,c,matrix.length,1).format.columnWidth=widths[key]??35;
    if (contract.name==='Items' && editable.has(key)) {
      sheet.getRangeByIndexes(1,c,contract.rows.length,1).format.fill='#FFF4CE';
    }
  });
  for(let r=1;r<matrix.length;r++) {
    const lines=Math.max(...matrix[r].map((v,c)=>estimatedLines(v,widths[contract.headers[c]]??35)));
    const height=Math.max(30,lines*13+10);
    if(height>409) throw new Error(`Source content needs a wider cell: ${contract.name} row ${r+1}`);
    range.getRow(r).format.rowHeight=height;
  }
  const head=range.getRow(0);
  head.format.fill='#D9EAF7';
  head.format.font={name:'Arial',size:10,bold:true,color:'#202B3A'};
  head.format.rowHeight=34;
  head.format.horizontalAlignment='center';
  sheet.tables.add(`A1:${column(contract.headers.length)}${matrix.length}`,true,`ItemMasterTable${index+1}`);
  sheet.freezePanes.freezeRows(1);
  if(contract.name==='Items') {
    sheet.freezePanes.freezeColumns(2);
    sheet.tabColor='#243E60';
  }
}
wb.recalculate();
console.log((await wb.inspect({kind:'sheet',include:'id,name',maxChars:1500})).ndjson);
const previews=[['Items','A1:H5','items.png'],['Items','I1:Q5','item_sources.png'],
  ['Parent','A1:B18','parent.png'],['Source Evidence','A1:G4','evidence.png'],
  ['Source Evidence','H1:H3','evidence_details.png'],['Source','A1:B14','source.png'],
  ['Guide','A1:B12','guide.png']];
for(const [sheetName,range,name] of previews){
  const blob=await wb.render({sheetName,range,scale:1,format:'png'});
  await fs.writeFile(path.join(outputDir,name),new Uint8Array(await blob.arrayBuffer()));
}
if(digest(await fs.readFile(seedPath))!==expectedHash) throw new Error('Seed changed during authoring');
const pending=path.join(outputDir,`.item-master-${process.pid}.pending.xlsx`);
try {
  await (await SpreadsheetFile.exportXlsx(wb)).save(pending);
  if(digest(await fs.readFile(seedPath))!==expectedHash) throw new Error('Seed changed before publication');
  await fs.link(pending,target);
} finally {await fs.rm(pending,{force:true});}
console.log(`Saved ${target}`);
