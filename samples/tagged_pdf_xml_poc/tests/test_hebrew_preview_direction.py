"""Browser-level Hebrew direction while retaining physical columns and LTR data."""
import json
from pathlib import Path
import subprocess
import pytest

MARKDOWN = '''## הוראות בטיחות

טקסט בעברית

- הוראות בעברית

### Arabic heading عنوان

نص عربي

### English heading

English prose.

<table><tr><th>Website</th><th>Telephone</th><th>מדינה</th><th>البلد</th></tr><tr><td>www.samsung.com</td><td>800-SAMSUNG (800 - 726 7864)</td><td>ישראל</td><td>مصر</td></tr></table>

<ul><li>פרטי קשר<table><tr><td>https://www.samsung.com</td><td>1-800-726-7864</td><td>ישראל</td></tr></table></li></ul>
'''

@pytest.mark.parametrize('renderer,filename,selector',[
    ('render_tk_source_checks.cjs','source_checks.html','.extracted'),
    ('render_representative_review.cjs','TEST/semantic_document.preview.html','body'),
])
def test_hebrew_preview_direction_and_contact_column_order(tmp_path,renderer,filename,selector):
    node=Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe'
    modules=node.parents[1]/'node_modules'
    if not node.is_file():
        pytest.skip('Local browser runtime unavailable')
    folder=tmp_path/'TEST';folder.mkdir()
    (tmp_path/'manifest.json').write_text(json.dumps({'runs':[{'buyer':'TEST'}]}),encoding='utf-8')
    data={'hard_gates':{},'visual_checks':[{'label':'Hebrew source table','source_ref':'source','language':'HEB','crop':None,'markdown':MARKDOWN}]}
    (folder/'review_document.json').write_text(json.dumps(data),encoding='utf-8')
    (folder/'semantic_document.md').write_text('# Preview\n\n주의: Test source\n\n'+MARKDOWN,encoding='utf-8')
    (folder/'semantic_document.xml').write_text('<document/>',encoding='utf-8')
    source='הוראות בטיחות טקסט בעברית הוראות בעברית Arabic heading عنوان نص عربي English heading English prose. Website Telephone מדינה البلد www.samsung.com 800-SAMSUNG (800 - 726 7864) ישראל مصر פרטי קשר https://www.samsung.com 1-800-726-7864 ישראל'
    (folder/'render_input.json').write_text(json.dumps({'source_text':source,'units':[],'ownership':[]}),encoding='utf-8')
    script=Path(__file__).resolve().parents[1]/'scripts'/renderer
    completed=subprocess.run([str(node),str(script),str(tmp_path)],capture_output=True,text=True,encoding='utf-8')
    assert completed.returncode==0,completed.stdout+completed.stderr
    probe=r"""
const {chromium}=require(process.argv[2]+'/playwright');const {pathToFileURL}=require('url');
(async()=>{const browser=await chromium.launch({headless:true,channel:'msedge'});const p=await browser.newPage();
await p.goto(pathToFileURL(process.argv[1]).href);
const result=await p.locator(process.argv[3]).evaluate(root=>{
 const dir=e=>getComputedStyle(e).direction;
 const hebrew=[...root.querySelectorAll('p,li,h1,h2,h3,h4,td,th')].filter(e=>/[\u0590-\u05ff]/.test(e.textContent));
 const arabic=[...root.querySelectorAll('p,h3,td,th')].filter(e=>/[\u0600-\u06ff]/.test(e.textContent));
 const latin=[...root.querySelectorAll('td,th')].filter(e=>/^[\x00-\x7f]+$/.test(e.textContent));
 const english=[...root.querySelectorAll('p,h3')].filter(e=>e.textContent.startsWith('English'));
 return {hebrew:hebrew.map(e=>[e.tagName,dir(e)]),arabic:arabic.map(dir),latin:latin.map(dir),english:english.map(dir),
 tables:[...root.querySelectorAll('table')].map(dir),
 order:[...root.querySelectorAll('tr')].every(r=>[...r.cells].every((e,i,a)=>i===0||e.getBoundingClientRect().left>a[i-1].getBoundingClientRect().left))};
});await browser.close();console.log(JSON.stringify(result));
})().catch(e=>{console.error(e);process.exitCode=1});"""
    result=subprocess.run([str(node),'-e',probe,str(tmp_path/filename),str(modules),selector],check=True,capture_output=True,text=True,encoding='utf-8')
    actual=json.loads(result.stdout)
    assert actual['hebrew'] and {direction for tag,direction in actual['hebrew']}=={'rtl'},actual
    assert actual['arabic'] and set(actual['arabic'])=={'rtl'},actual
    assert actual['latin'] and set(actual['latin'])=={'ltr'},actual
    assert actual['english'] and set(actual['english'])=={'ltr'},actual
    assert actual['tables']==['ltr','ltr'],actual
    assert actual['order'],actual
