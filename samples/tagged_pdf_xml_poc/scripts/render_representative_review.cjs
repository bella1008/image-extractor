// Local Markdown rendering and DOM comparison; no external semantic service.
const fs = require('fs'), path = require('path'), {pathToFileURL} = require('url');
const modules = process.env.REVIEW_NODE_MODULES || 'C:/Users/bella/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules';
const {chromium} = require(path.join(modules, 'playwright'));
const output = path.resolve(process.argv[2]);
const read = p => JSON.parse(fs.readFileSync(p, 'utf8'));
const dump = (p, v) => fs.writeFileSync(p, JSON.stringify(v, null, 2));
const digest = p => require('crypto').createHash('sha256').update(fs.readFileSync(p)).digest('hex');
const plain = s => s.replace(/\s/g, '');
const clean = s => plain(s.replace(/^\s*(?:행|열) \d+:[ \t]*/gm, '').replaceAll('[빈 셀]', '').replaceAll('[아이콘]', '').replaceAll('[그림: 텍스트 없음]', ''));
const css = 'body{font:18px Arial,sans-serif;line-height:1.8;margin:32px auto;max-width:1100px;padding:0 24px;color:#202428}h1{font-size:30px}h2{font-size:27px}h3{font-size:25px}h4{font-size:23px}h1,h2,h3,h4{font-weight:700;margin-top:1.5em}p,li,td{font-weight:400}table{border-collapse:collapse;width:100%;direction:ltr}td,th{border:1px solid #bbb;padding:8px;vertical-align:top}[dir=rtl]{font-family:Tahoma,Arial,sans-serif}h2[dir=rtl],h3[dir=rtl],h4[dir=rtl]{border-bottom:2px solid #bbb;padding-bottom:8px}a{overflow-wrap:anywhere}';
const direction = "document.querySelectorAll('p,li,h1,h2,h3,h4,td,th').forEach(e=>{if(/[\\u0590-\\u05ff\\u0600-\\u06ff]/.test(e.textContent))e.dir='rtl'});";
const wrap = body => '<!doctype html><html><head><meta charset="utf-8"><style>'+css+'</style></head><body>'+body+'<script>'+direction+'</script></body></html>';

(async () => {
  const {marked} = await import(pathToFileURL(path.join(modules, 'marked/lib/marked.esm.js')).href);
  const browser = await chromium.launch({headless:true, channel:'msedge'});
  const page = await browser.newPage({viewport:{width:1360,height:950}});
  const summaries = [], allRows = [];
  const signature = () => page.locator('body').evaluate(e => ({
    text:e.innerText.replace(/\s/g,''), elements:[...e.querySelectorAll('h1,h2,h3,h4,p,ul,ol,li,table,tr,td,th,a,strong,em,br,bdi')]
      .map(n=>[n.tagName,n.textContent.replace(/\s/g,''),n.getAttribute('href'),
        n.getAttribute('rowspan'),n.getAttribute('colspan'),n.tagName==='BDI'?n.dir:null])}));
  for (const run of read(path.join(output,'manifest.json')).runs) {
    const folder = path.join(output,run.buyer), input = read(path.join(folder,'render_input.json'));
    const html = marked.parse(fs.readFileSync(path.join(folder,'semantic_document.md'),'utf8'));
    await page.setContent(html);
    const sourceSignature = await signature();
    const rendered = await page.locator('body').innerText();
    const sourceView = rendered.slice(rendered.indexOf('\n', rendered.indexOf('주의:'))+1);
    const fullEqual = plain(input.source_text) === clean(sourceView);
    await page.setContent(input.units.map((u,i)=>'<section data-unit="'+i+'">'+marked.parse(u.markdown)+'</section>').join('\n'));
    const texts = await page.locator('section[data-unit]').evaluateAll(es=>es.map(e=>e.innerText));
    const unitFailures = input.units.map((u,i)=>({index:i,source_path:u.source_path,object_ref:u.object_ref,
      equal:plain(u.text)===clean(texts[i]),source:u.text,rendered:texts[i]})).filter(u=>!u.equal);
    const destination = path.join(folder,'semantic_document.preview.html');
    fs.writeFileSync(destination,wrap(html));
    await page.goto(pathToFileURL(destination).href);
    const previewSignature = await signature();
    const previewEqual = JSON.stringify(sourceSignature) === JSON.stringify(previewSignature);
    const isolatedModels = await page.locator('bdi').evaluateAll(es=>es.map(e=>{
      const value=e.textContent, text=e.firstChild, star=value.lastIndexOf('*');
      let starAfterPrevious=true;
      if(star>0 && text && text.nodeType===Node.TEXT_NODE){
        const a=document.createRange(),b=document.createRange();
        a.setStart(text,star-1);a.setEnd(text,star);b.setStart(text,star);b.setEnd(text,star+1);
        starAfterPrevious=b.getBoundingClientRect().left>=a.getBoundingClientRect().left;
      }
      return {text:value,direction:e.dir,unicodeBidi:getComputedStyle(e).unicodeBidi,star_after_previous_character:starAfterPrevious};
    }));
    const rows = [];
    for (const row of input.ownership) {
      const dom = await page.evaluate(row => {
        const clean = s=>s.replace(/\s/g,'');
        const nodes = [...document.querySelectorAll('p,li,span')];
        // Continuation can share its P with the preceding sentence after repair.
        const candidates = nodes.filter(n=>clean(n.textContent).includes(clean(row.target_text)));
        const target = candidates.sort((a,b)=>a.textContent.length-b.textContent.length)[0];
        if(!target) throw Error('Missing source target '+row.buyer+' '+row.language+' '+row.kind);
        const item = target.closest('li');
        let passed = !!item, snippet;
        if(row.kind==='power') snippet = item ? '<ul>'+item.outerHTML+'</ul>' : target.outerHTML;
        else {
          const intro = [...document.querySelectorAll('p')].find(n=>clean(n.textContent)===clean(row.intro_text));
          const listing = intro && intro.nextElementSibling;
          passed = !!(item && listing && listing.tagName==='UL' && listing.contains(item) && listing.children.length===2
            && row.condition_texts.every(t=>clean(listing.textContent).includes(clean(t))));
          snippet = intro ? intro.outerHTML+(listing?listing.outerHTML:'') : target.outerHTML;
        }
        return {passed,target_inside_list_item:!!item,html:snippet};
      },row);
      rows.push({...row,dom});
    }
    allRows.push(...rows);
    const proof = {buyer:run.buyer,xml_markdown_full_character_sequence:fullEqual,
      markdown_sha256:digest(path.join(folder,'semantic_document.md')),
      semantic_xml_sha256:digest(path.join(folder,'semantic_document.xml')),
      preview_html_sha256:digest(destination),
      source_nonspace_characters:plain(input.source_text).length,rendered_nonspace_characters:clean(sourceView).length,
      unit_count:input.units.length,unit_failures:unitFailures,md_preview_text_and_structure_equal:previewEqual,
      ownership_dom_pass:rows.every(r=>r.dom.passed),ownership:rows,isolated_models:isolatedModels,
      isolated_model_display_pass:isolatedModels.every(m=>m.direction==='ltr'&&m.unicodeBidi==='isolate'&&m.star_after_previous_character)
        && JSON.stringify(isolatedModels.map(m=>m.text))===JSON.stringify(input.expected_ltr_models||[])};
    dump(path.join(folder,'html_validation.json'),proof);
    const review=read(path.join(folder,'review_document.json'));
    Object.assign(review.hard_gates,{xml_markdown_full_character_sequence:fullEqual,
      xml_markdown_all_units:unitFailures.length===0,md_preview_text_and_structure_equal:previewEqual,
      ownership_dom_pass:proof.ownership_dom_pass,isolated_model_display_pass:proof.isolated_model_display_pass});
    review.status=Object.values(review.hard_gates).every(Boolean)?'targeted_extraction_review_pass':'hard_gate_failed';
    review.html_preview=destination;
    dump(path.join(folder,'review_document.json'),review);
    const summary={buyer:run.buyer,status:review.status,units:input.units.length,
      unit_failures:unitFailures.length,failed_gates:Object.entries(review.hard_gates).filter(([k,v])=>!v).map(([k])=>k)};
    summaries.push(summary); console.log(summary);
  }
  let body='<h1>대표 바이어 문장 연결 검토</h1><p>전원 연속문장과 비용 하위 조건의 PDF 원문 / 최종 Markdown 표시 비교입니다. 전체 HTML은 해당 바이어 링크에서 확인할 수 있습니다.</p><ul>';
  for(const s of summaries) body+='<li><a href="'+s.buyer+'/semantic_document.preview.html">'+s.buyer+' 전체 HTML</a> · '+s.status+'</li>';
  body+='</ul>';
  for(const [i,row] of allRows.entries()) body+='<section data-case="'+i+'"><h2>'+row.buyer+' '+row.language+' · '+(row.kind==='power'?'전원 연속문장':'비용 하위 조건')+' · PDF '+row.page+'p</h2><p>'+(row.before_status==='pass'?'기존 연결 유지':'분리 결함 수정')+' · XML/HTML '+(row.dom.passed?'PASS':'FAIL')+'</p><table><tr><th>PDF 원문</th><th>최종 Markdown 표시</th></tr><tr><td style="width:45%"><img style="max-width:100%" src="'+row.pdf_crop+'"></td><td>'+row.dom.html+'</td></tr></table></section>';
  const findings=path.join(output,'ownership_findings.html');
  fs.writeFileSync(findings,wrap(body));
  await page.goto(pathToFileURL(findings).href);
  for(const [i,row] of allRows.entries()) if(row.before_status!=='pass') {
    const section=page.locator('section[data-case="'+i+'"]');
    await section.screenshot({path:path.join(output,row.buyer+'_'+row.language+'_'+row.kind+'_comparison.png')});
  }
  dump(path.join(output,'html_summary.json'),summaries);
  await browser.close();
  if(summaries.some(s=>s.failed_gates.length)) process.exitCode=1;
})().catch(error=>{console.error(error);process.exitCode=1});
