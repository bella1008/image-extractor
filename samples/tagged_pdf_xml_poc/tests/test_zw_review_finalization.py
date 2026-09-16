from hashlib import sha256
import importlib
import json
from pathlib import Path
import pytest

@pytest.fixture
def bundle(tmp_path,monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1]/'scripts'))
    module=importlib.import_module('finalize_zw_review')
    names=('raw_structure.xml','semantic_document.xml','semantic_document.md','extraction_report.json','semantic_document.preview.html')
    for name in names:(tmp_path/name).write_text(name,encoding='utf8')
    digest=lambda name:sha256((tmp_path/name).read_bytes()).hexdigest()
    validation={'xml_markdown_full_character_sequence':True,'unit_failures':[],
        'md_preview_text_and_structure_equal':True,'ownership_dom_pass':True,'isolated_model_display_pass':True,
        'markdown_sha256':digest('semantic_document.md'),'semantic_xml_sha256':digest('semantic_document.xml'),
        'preview_html_sha256':digest('semantic_document.preview.html')}
    (tmp_path/'html_validation.json').write_text(json.dumps(validation))
    gates=dict.fromkeys(('xml_markdown_full_character_sequence','xml_markdown_all_units','md_preview_text_and_structure_equal','ownership_dom_pass','isolated_model_display_pass'),True)
    return module,tmp_path,{'hard_gates':gates},{'artifact_sha256':{n:digest(n) for n in names[:4]}}

def test_current_artifacts_accepted(bundle):
    module,path,review,log=bundle
    module.validate_current_artifacts(path,review,log)

@pytest.mark.parametrize('case',['missing_gate','missing_validation','edited_md','edited_preview','failed_validation'])
def test_stale_or_absent_validation_rejected_before_status_change(bundle,case):
    module,path,review,log=bundle
    if case=='missing_gate':review['hard_gates'].pop('xml_markdown_all_units')
    if case=='missing_validation':(path/'html_validation.json').unlink()
    if case=='edited_md':(path/'semantic_document.md').write_text('modified')
    if case=='edited_preview':(path/'semantic_document.preview.html').write_text('modified')
    if case=='failed_validation':
        data=json.loads((path/'html_validation.json').read_text());data['unit_failures']=[{'failed':True}]
        (path/'html_validation.json').write_text(json.dumps(data))
    with pytest.raises((ValueError,FileNotFoundError)):
        module.validate_current_artifacts(path,review,log)
    assert 'status' not in review
