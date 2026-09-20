import importlib
from pathlib import Path
from xml.etree import ElementTree as E
import pytest
import json
import os
import shutil
import subprocess

@pytest.fixture
def report_module(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1]/'scripts'))
    return importlib.import_module('review_tk_xml')

@pytest.mark.parametrize('number',['01','02','03','04','05'])
def test_report_heading_uses_validated_compact_number(report_module,number):
    n=E.fromstring(f'<heading level="2" numbered-label="{number}" promotion-reason="numbered_chapter_structure_sequence_typography"><label><text>{number[0]}</text><text> {number[1]}</text></label><list_body><text>محتويات العبوة</text></list_body></heading>')
    assert report_module.heading_display_text(n,{})==number+' محتويات العبوة'

def test_heading_number_must_match_source(report_module):
    n=E.fromstring('<heading level="2" numbered-label="01" promotion-reason="numbered_chapter_structure_sequence_typography"><label><text>0 2</text></label><list_body><text>عنوان</text></list_body></heading>')
    with pytest.raises(ValueError):report_module.heading_display_text(n,{})

def test_other_heading_text_unchanged(report_module):
    n=E.fromstring('<heading><text>TV 2026</text></heading>')
    assert report_module.heading_display_text(n,{})=='TV 2026'

def test_arabic_report_digits_are_ltr_isolated(tmp_path):
    node=os.environ.get('REVIEW_NODE') or shutil.which('node')
    if not node:
        candidate=Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe'
        node=str(candidate) if candidate.is_file() else None
    if not node:pytest.skip('Node is needed for report renderer regression')
    (tmp_path/'TK_ARA').mkdir()
    stats={'headings':5,'heading_texts':[n+' عنوان' for n in ('01','02','03','04','05')],
           'blocks':dict.fromkeys(('paragraph','list','list_item','table','figure'),0)}
    (tmp_path/'manifest.json').write_text(json.dumps({'runs':[{'buyer':'TK_ARA'}]}))
    (tmp_path/'TK_ARA/review_document.json').write_text(json.dumps({'source':{'buyer':'TK_ARA','source_token':'TK_ARA'},'status':'pass','language_stats':{'ARA':stats}}))
    (tmp_path/'source_findings.json').write_text('{"cases":[]}')
    script=Path(__file__).resolve().parents[1]/'scripts/render_tk_review.cjs'
    subprocess.run([node,str(script),str(tmp_path)],check=True)
    output=(tmp_path/'tk_review.html').read_text(encoding='utf8')
    for number in ('01','02','03','04','05'):
        assert f'<bdi dir="ltr">{number}</bdi> عنوان' in output
