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
   body+='<section data-check="'+count+'"><h2>'+c.label+' · '+c.source_ref+'</h2><div class="pair"><div>'+(c.crop?'<img src="'+run.buyer+'/'+c.crop+'">':'원문 전체 페이지 참조')+'</div><div class="extracted"'+(c.language==='ARA'?' dir="rtl"':'')+'>'+marked.parse(c.markdown)+'</div></div></section>';count++;
  }
 }
 const html='<!doctype html><meta charset="utf-8"><style>body{font:18px Arial;max-width:1500px;margin:30px auto;line-height:1.8}.pair{display:grid;grid-template-columns:1fr 1fr;gap:25px}.pair>div{min-width:0;border:1px solid #bbb;padding:16px}img{max-width:100%}[dir=rtl]{font-family:Tahoma}td,th{border:1px solid #999;padding:7px}table{border-collapse:collapse;width:100%}section{margin-bottom:40px}h2{font-weight:700}p,li{font-weight:400}</style><body>'+body+'</body>';
 const destination=path.join(out,'source_checks.html');fs.writeFileSync(destination,html);
 const browser=await chromium.launch({headless:true,channel:'msedge'});
 const page=await browser.newPage({viewport:{width:1580,height:1000}});await page.goto(pathToFileURL(destination).href);
 for(let i=0;i<count;i++)await page.locator('[data-check="'+i+'"]').screenshot({path:path.join(out,'source_check_'+i+'.png')});
 await browser.close();console.log(count+' source comparisons rendered');
})().catch(e=>{console.error(e);process.exitCode=1});
