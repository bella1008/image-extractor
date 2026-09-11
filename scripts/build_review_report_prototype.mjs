// Development-only visual prototype. Not a runtime dependency for colleagues.
import fs from 'node:fs/promises';
import path from 'node:path';
import { Workbook, SpreadsheetFile } from '@oai/artifact-tool';

const source = path.resolve(process.argv[2]);
const output = path.resolve(process.argv[3]);
const view = JSON.parse(await fs.readFile(source, 'utf8'));
if (view.schema_version !== 'review-report-view/1' || view.decision_status !== 'not_evaluated') throw new Error('Unsupported view');
await fs.mkdir(output, { recursive: true });
const target = path.join(output, 'review_report_prototype.xlsx');
try { await fs.access(target); throw new Error('Refusing to overwrite workbook'); }
catch (error) { if (error.code !== 'ENOENT') throw error; }

const workbook = Workbook.create();
const summary = workbook.worksheets.add('Summary');
const checklist = workbook.worksheets.add('Checklist Results');
const evidence = workbook.worksheets.add('Source Evidence');
const excluded = workbook.worksheets.add('Excluded Rules');
function literal(value) { return typeof value === 'string' && value.startsWith('=') ? "'" + value : value; }
function column(n) { let s=''; while(n){n--;s=String.fromCharCode(65+n%26)+s;n=Math.floor(n/26);}return s; }
function table(sheet, headers, rows, widths, name) {
  const matrix = [headers, ...rows.map(r => headers.map(k => literal(r[k] ?? '')))];
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
table(checklist,view.columns.checklist,view.checklist,[12,14,15,25,40,12,90,90,18,25,50,12,35,45],'ChecklistObservation');
table(evidence,view.columns.evidence,view.evidence,[30,25,16,27,12,12,65,100,50,100,60],'SourceEvidence');
table(excluded,view.columns.excluded,view.excluded,[30,18,12,22,22,18,18,25],'ExcludedRules');
checklist.getRange('I2:I'+(view.checklist.length+1)).conditionalFormats.add('containsText',{text:'needs_review',format:{fill:'#FFF4CE'}});

summary.showGridLines=false;
summary.getRange('A1:D21').format.font={name:'Arial',size:11,color:'#202B3A'};
summary.getRange('A1:A21').format.columnWidth=39;
summary.getRange('B1:B21').format.columnWidth=25;
summary.getRange('C1:C21').format.columnWidth=4;
summary.getRange('D1:D21').format.columnWidth=84;
summary.getRange('A1:D21').format.rowHeight=27;
summary.getRange('A2').values=[['XML 체크리스트 결과 양식 초안']];
summary.getRange('A2').format.font={name:'Arial',size:15,bold:true};
summary.getRange('A4:B13').values=[['문서',view.context.manual_code],['프로필',view.context.source_token],['전체 규칙',view.summary.rule_count],['적용 대상',view.summary.applicable_count],['단일 검토 단위 문구 근거',null],['추가 구조 연결 후보',null],['분산된 문구 근거',null],['연결 미완료',null],['대상 아님 / 기존 비승인',view.summary.excluded_count],['보존한 근거 행',view.summary.evidence_count]];
const end=view.checklist.length+1;
for(const [row,status] of [[8,'strict_evidence'],[9,'structure_candidate'],[10,'distributed_fragments'],[11,'unresolved']]) {
  summary.getRange('B'+row).formulas=[['=COUNTIFS(\'Checklist Results\'!$J$2:$J$'+end+',"'+status+'")']];
}
summary.getRange('D4:D10').values=[['자동 합격·불합격 판정 아님'],['결과는 전부 needs_review로 유지합니다.'],['구조 후보는 기존 DB의 업무 승인과 별개입니다.'],['분산 근거는 조각별 위치이며 전체 일치가 아닙니다.'],['미구현: 표 전용 검사, 표지 범위, 모델·버전 비교, 다국어 평가'],['reviewer_note는 의견란이며 DB 승인 입력이 아닙니다.'],['이번 문서는 연결 확인용 양식 초안입니다.']];
summary.getRange('D4:D10').format.wrapText=true;
summary.getRange('D4:D10').format.rowHeight=38;
summary.getRange('D4').format.fill='#FFF4CE';
workbook.recalculate();
console.log((await workbook.inspect({kind:'table',range:'Summary!A4:B13',include:'values,formulas',tableMaxRows:10,tableMaxCols:2,maxChars:1800})).ndjson);
console.log((await workbook.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#NUM!|#SPILL!|#CALC!',options:{useRegex:true,maxResults:20},maxChars:1500})).ndjson);
for(const [sheetName,range,file] of [['Summary','A1:D14','summary.png'],['Checklist Results','D1:J4','checklist.png'],['Source Evidence','A1:H4','evidence.png'],['Excluded Rules','A1:H8','excluded.png']]){
 const blob=await workbook.render({sheetName,range,scale:1,format:'png'});
 await fs.writeFile(path.join(output,file),new Uint8Array(await blob.arrayBuffer()));
}
await (await SpreadsheetFile.exportXlsx(workbook)).save(target);
console.log('Saved '+target);
