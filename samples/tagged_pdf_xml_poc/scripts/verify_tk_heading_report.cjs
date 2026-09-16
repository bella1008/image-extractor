// Verify the actual RTL browser display and all table headings against full MD previews.
const fs=require('fs'),path=require('path'),assert=require('assert/strict');
const {pathToFileURL}=require('url');
const modules=process.env.REVIEW_NODE_MODULES||'C:/Users/bella/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules';
const {chromium}=require(path.join(modules,'playwright'));
const out=path.resolve(process.argv[2]);
(async()=>{
 const browser=await chromium.launch({headless:true,channel:'msedge'});
 try{
  const page=await browser.newPage({viewport:{width:1400,height:1000}});
  await page.goto(pathToFileURL(path.join(out,'tk_review.html')).href);
  const table=page.locator('table').nth(1);
  const rows=await table.locator('tr').allTextContents();
  const columns=await table.locator('tr').evaluateAll(rs=>rs.slice(1).map(r=>[...r.querySelectorAll('td')].map(c=>c.textContent)));
  const numbers=await table.locator('bdi').evaluateAll(ns=>ns.map(n=>{
   const rect=i=>{const r=document.createRange();r.setStart(n.firstChild,i);r.setEnd(n.firstChild,i+1);const b=r.getBoundingClientRect();return {left:b.left,right:b.right};};
   const a=rect(0),b=rect(1);
   return {text:n.textContent,dir:n.dir,bidi:getComputedStyle(n).unicodeBidi,zero_left_of_digit:a.left<b.left,gap:b.left-a.right};
  }));
  assert.deepEqual(numbers.map(n=>n.text),['01','02','03','04','05']);
  assert.ok(numbers.every(n=>n.dir==='ltr'&&n.bidi==='isolate'&&n.zero_left_of_digit&&Math.abs(n.gap)<1));
  for(let i=0;i<5;i++)await table.locator('tr').filter({has:page.locator('bdi').filter({hasText:'0'+(i+1)})}).screenshot({path:path.join(out,'heading_0'+(i+1)+'.png')});
  const expected=[];
  for(const buyer of ['TK_L02','TK_ARA']){
   await page.goto(pathToFileURL(path.join(out,buyer,'semantic_document.preview.html')).href);
   const values=await page.locator('h1,h2,h3,h4,h5,h6').allTextContents();
   expected.push(...values.slice(1));
  }
  const actual=[0,1,2].flatMap(i=>columns.map(r=>r[i]));
  const normalize=s=>s.replace(/\s/g,'');
  assert.equal(actual.length,72);
  assert.deepEqual(actual.map(normalize),expected.map(normalize));
  const proof={all_72_table_headings_match_full_preview:true,numbers,table_rows:rows.length-1,
               digit_direction_and_spacing_pass:true};
  fs.writeFileSync(path.join(out,'heading_display_validation.json'),JSON.stringify(proof,null,2));
  console.log(JSON.stringify(proof));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
