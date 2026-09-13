from copy import deepcopy
import importlib
import pytest
from tests.test_combined_review_model import combined_inputs
from tests.test_item_review_service import checked_bundle
from src.combined_review_model import build_combined_report
from src.item_review_excel import build_item_excel_view


def api():
    assert importlib.util.find_spec('src.combined_review_view'), 'combined display view missing'
    return importlib.import_module('src.combined_review_view')


def test_four_sheets_keep_children_and_separate_counts(combined_inputs):
    report=build_combined_report(*combined_inputs)
    before=deepcopy(report)
    view=api().build_combined_review_view(report)
    assert view['schema_version']=='combined-review-excel-view/1'
    assert [s['name'] for s in view['sheets']]==['Summary','Checklist Results','Item Results','Source Evidence']
    summary,checklist,items,evidence=view['sheets']
    assert len(summary['rows'])==11 and len(checklist['rows'])==59
    assert items==build_item_excel_view(report['items'])['sheets'][1]
    assert not any(row[-1] in (72,73) for row in summary['rows'])
    assert report==before
    assert evidence['headers'][:3]==['체크 ID','고정 항목 키','근거 종류']


def test_parent_referral_is_display_only(combined_inputs):
    report=build_combined_report(*combined_inputs)
    view=api().build_combined_review_view(report)
    parent=next(row for row in view['sheets'][1]['rows'] if row[0]=='CHK-002-ZC-ENG')
    assert parent[5]=='검토 필요'
    assert 'Item Results' in parent[6]
    assert 'Item Results' not in str(report['checklist'])


def test_no_internal_sources_or_temporary_ids_in_summary(combined_inputs):
    view=api().build_combined_review_view(build_combined_report(*combined_inputs))
    text=str(view['sheets'][0])
    assert all(word not in text for word in ('sha256','bundle_path','receipt','E0001'))
    assert view['sheets'][0]['rows'][2][-1]=='ENG'


def test_changed_combined_summary_cannot_be_rendered(combined_inputs):
    report=build_combined_report(*combined_inputs)
    report['summary']['child_item_count']=99
    with pytest.raises(ValueError): api().build_combined_review_view(report)


def test_general_evidence_compacts_only_repeated_display_fields():
    import json
    row = dict(check_id='CHK-001-ZC-ENG', evidence_id='E0001', evidence_kind='strict',
               text='Original text', source_node_ids='xml:1\nxml:2', structure_types='P',
               pdf_pages='1', xml_paths='/document/P[1]\n/document/P[2]',
               mcids='10', object_refs='20', composition_method='single', language='ENG',
               required_fragment='', node_details=[{'mcid':10,'object_ref':20}],
               visual_node_ids=[], caveats=[])
    before=deepcopy(row)
    cells=api()._general_evidence_row(row)
    detail=json.loads(cells[-1])
    assert cells[:8]==['CHK-001-ZC-ENG','','일반 문구','Original text','xml:1\nxml:2',
                       'P','1','/document/P[1]; /document/P[2]']
    assert detail=={key:row[key] for key in ('composition_method','language','required_fragment',
                                          'node_details','visual_node_ids','caveats')}
    assert '\n' not in cells[-1] and ': ' not in cells[-1]
    assert row==before
