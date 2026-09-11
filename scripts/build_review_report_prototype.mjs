// Development-only visual prototype. Not a runtime dependency for colleagues.
import fs from 'node:fs/promises';
import path from 'node:path';
import { Workbook, SpreadsheetFile } from '@oai/artifact-tool';

const source = path.resolve(process.argv[2]);
const output = path.resolve(process.argv[3]);
const view = JSON.parse(await fs.readFile(source, 'utf8'));
const proposal = process.argv[4] ? JSON.parse(await fs.readFile(path.resolve(process.argv[4]), 'utf8')) : null;
if (view.schema_version !== 'review-report-view/2' || view.decision_status !== 'not_evaluated' || view.source.availability !== 'verified_archive') throw new Error('Unsupported or unverified view');
if (proposal && (proposal.schema_version !== 'checklist-item-proposal/1' || proposal.activation_status !== 'proposal_only' || proposal.decision_status !== 'not_evaluated' || proposal.source.source_completion_sha256 !== view.source_completion_sha256)) throw new Error('Unsupported proposal or different source run');
await fs.mkdir(output, { recursive: true });
const target = path.join(output, 'review_report_prototype.xlsx');
try { await fs.access(target); throw new Error('Refusing to overwrite workbook'); }
catch (error) { if (error.code !== 'ENOENT') throw error; }

const workbook = Workbook.create();
const summary = workbook.worksheets.add('Summary');
const checklist = workbook.worksheets.add('Checklist Results');
const items = proposal ? workbook.worksheets.add('Item Proposals') : null;
const evidence = workbook.worksheets.add('Source Evidence');
const excluded = workbook.worksheets.add('Excluded Rules');
const inventory = proposal ? workbook.worksheets.add('Migration Inventory') : null;
const labels = {result:'검토 판정',description:'설명',source_node_ids:'원문 노드 ID',structure_types:'태그 정보',pdf_pages:'PDF 페이지',evidence_ids:'상세 근거 ID',reviewer_note:'검토자 메모',source_marker:'원문 기호',condition_text:'조건 안내 원문',condition_node_ids:'조건 안내 노드 ID'};
function literal(value) { return typeof value === 'string' && value.startsWith('=') ? "'" + value : value; }
function column(n) { let s=''; while(n){n--;s=String.fromCharCode(65+n%26)+s;n=Math.floor(n/26);}return s; }
function table(sheet, headers, rows, widths, name) {
  const matrix = [headers.map(k=>labels[k]??k), ...rows.map(r => headers.map(k => literal(k==='result'&&r[k]==='needs_review'?'검토 필요':r[k] ?? '')))];
  const area = sheet.getRangeByIndexes(0,0,matrix.length,headers.length);
  area.values = matrix;
  area.format.font = { name:'Arial',size:10,color:'#202B3A' };
  area.format.wrapText = true;
  area.format.verticalAlignment = 'top';
  sheet.showGridLines = false;
  for(let c=0;c<headers.length;c++) sheet.getRangeByIndexes(0,c,matrix.length,1).format.columnWidth=widths[c];
  for(let r=1;r<matrix.length;r++) {
    const lines=Math.max(...matrix[r].map((v,c)=>String(v).split('\n').reduce((n,line)=>n+Math.max(1,Math.ceil([...line].reduce((sum,ch)=>sum+(ch.codePointAt(0)>255?1.8:1),0)/(widths[c]*0.85))),0)));
    area.getRow(r).format.rowHeight=Math.min(409,Math.max(26,lines*13+8));
  }
  const head=area.getRow(0);
  head.format.fill='#D9EAF7';head.format.font={name:'Arial',size:10,bold:true,color:'#202B3A'};
  head.format.rowHeight=32;head.format.horizontalAlignment='center';
  sheet.tables.add('A1:'+column(headers.length)+matrix.length,true,name);
  sheet.freezePanes.freezeRows(1);
}
const checklistWidths={scope:12,exclude_scope:14,common_id:15,check_id:25,section_heading:40,language:12,required_text:90,evidence_excerpt:90,result:18,description:62,source_node_ids:45,structure_types:60,pdf_pages:12,evidence_ids:35,reviewer_note:45};
table(checklist,view.columns.checklist,view.checklist,view.columns.checklist.map(k=>checklistWidths[k]??30),'ChecklistObservation');
const evidenceWidths={evidence_id:30,check_id:25,evidence_kind:16,composition_method:27,language:12,pdf_pages:12,required_fragment:65,text:100,source_node_ids:60,structure_types:70,mcids:60,object_refs:60,visual_node_ids:55,xml_paths:100,caveats:60};
table(evidence,view.columns.evidence,view.evidence,view.columns.evidence.map(k=>evidenceWidths[k]??30),'SourceEvidence');
table(excluded,view.columns.excluded,view.excluded,[30,18,12,22,22,18,18,25],'ExcludedRules');
checklist.getRange('I2:I'+(view.checklist.length+1)).conditionalFormats.add('containsText',{text:'검토 필요',format:{fill:'#FFF4CE'}});
if(proposal){
 const rows=proposal.items.map(i=>({source_check_id:i.source_check_id,item_key:i.item_key,required_text:i.required_text,actual_text:i.candidates.map(c=>c.text).join('\n\n'),source_marker:i.source_marker,condition_text:i.condition_candidates.map(c=>c.text).join('\n\n'),result:i.result,description:i.description,source_node_ids:i.candidates.flatMap(c=>c.owner_ids).join('\n'),structure_types:i.candidates.flatMap(c=>c.structure_types).join('\n'),pdf_pages:[...new Set(i.candidates.flatMap(c=>c.parts.flatMap(p=>p.evidence.filter(e=>Number.isInteger(e.page_index)).map(e=>e.page_index+1))))].join(', '),scope:i.scope,exclude_scope:i.exclude_scope,condition_node_ids:i.condition_candidates.flatMap(c=>c.owner_ids).join('\n'),proposal_state:i.proposal_state,reviewer_note:''}));
 table(items,Object.keys(rows[0]),rows,[25,30,90,90,12,90,18,65,50,20,12,12,25,50,18,45],'ItemProposal');
 items.getRange('G2:G'+(rows.length+1)).conditionalFormats.add('containsText',{text:'검토 필요',format:{fill:'#FFF4CE'}});
 const headers=['check_id','common_id','language','legacy_block_type','match_method','category','approval_status','definition_state','condition_state','required_text'];
 table(inventory,headers,proposal.inventory,[30,18,12,25,25,30,20,20,20,100],'MigrationInventory');
}

summary.showGridLines=false;
summary.getRange('A1:D29').format.font={name:'Arial',size:11,color:'#202B3A'};
summary.getRange('A1:A29').format.columnWidth=39;
summary.getRange('B1:B29').format.columnWidth=25;
summary.getRange('C1:C29').format.columnWidth=4;
summary.getRange('D1:D29').format.columnWidth=110;
summary.getRange('A1:D29').format.rowHeight=27;
summary.getRange('A2').values=[['XML 체크리스트 결과 양식 초안']];
summary.getRange('A2').format.font={name:'Arial',size:15,bold:true};
summary.getRange('A4:B13').values=[['문서',view.context.manual_code],['프로필',view.context.source_token],['전체 규칙',view.summary.rule_count],['적용 대상',view.summary.applicable_count],['단일 검토 단위 문구 근거',null],['추가 구조 연결 후보',null],['분산된 문구 근거',null],['연결 미완료',null],['대상 아님 / 기존 비승인',view.summary.excluded_count],['보존한 근거 행',view.summary.evidence_count]];
const end=view.checklist.length+1;
for(const [row,status] of [[8,'strict_evidence'],[9,'structure_candidate'],[10,'distributed_fragments'],[11,'unresolved']]) summary.getRange('B'+row).values=[[view.summary.by_observation[status]??0]];
summary.getRange('A15:B16').values=[['검토 필요 행',null],['CHK-002 분리 후보',proposal?proposal.items.length:0]];
summary.getRange('B15').formulas=[['=COUNTIFS(\'Checklist Results\'!$I$2:$I$'+end+',"검토 필요")']];
summary.getRange('D4:D10').values=[['자동 합격·불합격 판정 아님'],['검토 판정과 설명으로 표시합니다. 세부 진단은 JSON에 보존합니다.'],['기존 규칙 집계는 항목 분리 이전 기준입니다. 하위 후보를 중복 합산하지 않습니다.'],['Item Proposals에서 CHK-002의 구성품별 원문과 조건 근거를 확인합니다.'],['미구현: 표 전용 판정, 표지 범위, 모델·버전 비교, 다국어 평가'],['검토자 메모는 의견란이며 DB 승인 입력이 아닙니다.'],['항목별 모델 적용 조건은 미확정이며 원본 DB를 변경하지 않았습니다.']];
summary.getRange('D4:D10').format.wrapText=true;
summary.getRange('D4:D10').format.rowHeight=38;
summary.getRange('D4').format.fill='#FFF4CE';
const sourceRows=[['원본 PDF',view.source.pdf_filename],['추출 결과 폴더',view.source.bundle_path],['XML 위치',view.source.semantic_xml_path],['PDF SHA256',view.source.pdf_sha256],['XML SHA256',view.source.semantic_xml_sha256],['추출 완료 기록',view.source.receipt_ref]];
for(let i=0;i<sourceRows.length;i++){
 summary.getRange('A'+(19+i)).values=[[sourceRows[i][0]]];
 summary.getRange('D'+(19+i)).values=[[literal(sourceRows[i][1])]];
}
summary.getRange('D19:D24').format.wrapText=true;
summary.getRange('D19:D24').format.font={name:'Arial',size:10,color:'#202B3A'};
summary.getRange('D19:D24').format.rowHeight=54;
summary.getRange('D26').values=[['노드 ID는 위 추출본 안의 위치입니다. PDF나 추출 구조가 바뀌면 달라질 수 있습니다.']];
summary.getRange('D26').format.wrapText=true;
summary.getRange('D26').format.rowHeight=40;
workbook.recalculate();
console.log((await workbook.inspect({kind:'table',range:'Summary!A4:B13',include:'values,formulas',tableMaxRows:10,tableMaxCols:2,maxChars:1800})).ndjson);
console.log((await workbook.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#NUM!|#SPILL!|#CALC!',options:{useRegex:true,maxResults:20},maxChars:1500})).ndjson);
const previews=[['Summary','A1:D26','summary.png'],['Checklist Results','D1:J4','checklist.png'],['Source Evidence','A1:H4','evidence.png'],['Excluded Rules','A1:H8','excluded.png']];
if(proposal) previews.push(['Item Proposals','B1:H5','items.png'],['Migration Inventory','A1:I8','inventory.png']);
for(const [sheetName,range,file] of previews){
 const blob=await workbook.render({sheetName,range,scale:1,format:'png'});
 await fs.writeFile(path.join(output,file),new Uint8Array(await blob.arrayBuffer()));
}
await (await SpreadsheetFile.exportXlsx(workbook)).save(target);
console.log('Saved '+target);
