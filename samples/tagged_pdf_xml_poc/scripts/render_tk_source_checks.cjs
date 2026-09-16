const fs=require('fs'),path=require('path'),{pathToFileURL}=require('url');
const modules='C:/Users/bella/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules';
const {chromium}=require(path.join(modules,'playwright'));
const out=path.resolve(process.argv[2]);
(async()=>{
 const {marked}=await import(pathToFileURL(path.join(modules,'marked/lib/marked.esm.js')).href);
 const manifest=JSON.parse(fs.readFileSync(path.join(out,'manifest.json'),'utf8'));
 const buyers=manifest.runs.map(r=>r.buyer).join(' / ');
 let body='<h1>'+buyers+' 원문 / Markdown 세부 비교</h1>';let count=0;
 for(const run of manifest.runs){
  const r=JSON.parse(fs.readFileSync(path.join(out,run.buyer,'review_document.json'),'utf8'));
  for(const c of r.visual_checks){
   body+='<section data-check="'+count+'"><h2>'+c.label+' · '+c.source_ref+'</h2><div class="pair"><div>'+(c.crop?'<img src="'+run.buyer+'/'+c.crop+'">':'원문 전체 페이지 참조')+'</div><div class="extracted">'+marked.parse(c.markdown)+'</div></div></section>';count++;
  }
 }
 // Set prose/cell direction without reversing PDF-observed table columns or
 // English telephone strings inside an Arabic comparison section.
 const direction="document.querySelectorAll('.extracted p,.extracted li,.extracted h1,.extracted h2,.extracted h3,.extracted h4,.extracted td,.extracted th').forEach(e=>{if(/[\\u0600-\\u06ff]/.test(e.textContent))e.dir='rtl'});";
 const html='<!doctype html><meta charset="utf-8"><style>body{font:18px Arial;max-width:1500px;margin:30px auto;line-height:1.8}.pair{display:grid;grid-template-columns:1fr 1fr;gap:25px}.pair>div{min-width:0;border:1px solid #bbb;padding:16px}img{max-width:100%}[dir=rtl]{font-family:Tahoma}td,th{border:1px solid #999;padding:7px}table{border-collapse:collapse;width:100%;direction:ltr}section{margin-bottom:40px}h2{font-weight:700}p,li{font-weight:400}</style><body>'+body+'<script>'+direction+'</script></body>';
 const destination=path.join(out,'source_checks.html');fs.writeFileSync(destination,html);
 const browser=await chromium.launch({headless:true,channel:'msedge'});
 const page=await browser.newPage({viewport:{width:1580,height:1000}});await page.goto(pathToFileURL(destination).href);
 const validation=await page.locator('.extracted').evaluateAll(es=>({
   source_table_column_order:es.every(e=>[...e.querySelectorAll('tr')].every(r=>[...r.cells].every((c,i,a)=>i===0||c.getBoundingClientRect().left>a[i-1].getBoundingClientRect().left))),
   latin_table_cells_ltr:es.every(e=>[...e.querySelectorAll('td,th')].every(c=>/[\u0600-\u06ff]/.test(c.textContent)||getComputedStyle(c).direction==='ltr'))
 }));
 validation.source_checks_sha256=require('crypto').createHash('sha256').update(fs.readFileSync(destination)).digest('hex');
 fs.writeFileSync(path.join(out,'source_comparison_validation.json'),JSON.stringify(validation,null,2));
 if(!validation.source_table_column_order||!validation.latin_table_cells_ltr)throw Error('Source comparison table direction failed');
 for(let i=0;i<count;i++)await page.locator('[data-check="'+i+'"]').screenshot({path:path.join(out,'source_check_'+i+'.png')});
 await browser.close();console.log(count+' source comparisons rendered');
})().catch(e=>{console.error(e);process.exitCode=1});
