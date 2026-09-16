"""Arabic prose must not reverse physical table columns or English phone strings."""
import json
from pathlib import Path
import subprocess

def test_arabic_source_comparison_preserves_physical_table_order(tmp_path):
    node=Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe'
    modules=node.parents[1]/'node_modules'
    if not node.is_file():
        import pytest
        pytest.skip('Local browser runtime unavailable')
    (tmp_path/'TEST').mkdir()
    (tmp_path/'manifest.json').write_text(json.dumps({'runs':[{'buyer':'TEST'}]}))
    data={'visual_checks':[{'label':'Arabic source table','source_ref':'source','language':'ARA','crop':None,
        'markdown':'نص عربي\n\n<table><tr><td>Website</td><td>800-SAMSUNG (800 - 726 7864)</td><td>البلد</td></tr></table>'}]}
    (tmp_path/'TEST/review_document.json').write_text(json.dumps(data),encoding='utf8')
    script=Path(__file__).resolve().parents[1]/'scripts/render_tk_source_checks.cjs'
    subprocess.run([str(node),str(script),str(tmp_path)],check=True,capture_output=True)
    probe=r"""
const {chromium}=require(process.argv[2]+'/playwright');const {pathToFileURL}=require('url');
(async()=>{const b=await chromium.launch({headless:true,channel:'msedge'});const p=await b.newPage();
await p.goto(pathToFileURL(process.argv[1]).href);const a=await p.locator('.extracted td').evaluateAll(es=>es.map(e=>({x:e.getBoundingClientRect().x,dir:getComputedStyle(e).direction})));
const prose=await p.locator('.extracted p').evaluate(e=>getComputedStyle(e).direction);await b.close();
if(!(a[0].x<a[1].x&&a[1].x<a[2].x&&a[1].dir==='ltr'&&a[2].dir==='rtl'&&prose==='rtl'))throw Error(JSON.stringify({a,prose}));
})().catch(e=>{console.error(e);process.exitCode=1});"""
    subprocess.run([str(node),'-e',probe,str(tmp_path/'source_checks.html'),str(modules)],check=True,capture_output=True)
