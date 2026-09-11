from html.parser import HTMLParser

import pytest

from src.checklist_observation import observe_checklist
from src.review_observation_report import render_observation_html
from tests.test_checklist_observation import document, heading, node, rule


def test_html_shows_expected_observed_page_and_pending_without_source_markup():
    text = '<script>alert(1)</script> & words'
    report = observe_checklist(document(heading(), node('p', 'paragraph', text)), [rule(required_text=text)])
    html = render_observation_html(report)
    assert '&lt;script&gt;alert(1)&lt;/script&gt; &amp; words' in html
    assert '<script>' not in html
    assert '1쪽' in html and '/p' in html
    assert '자동 합격·불합격 판정 아님' in html
    assert '기준 문구' in html and '실제 근거' in html
    assert report['rows'][0]['status'] == 'needs_review'
    class Tags(HTMLParser):
        def handle_starttag(self, tag, attrs):
            assert tag not in ('script', 'iframe', 'img', 'link')
    Tags().feed(html)


def test_html_distinguishes_candidate_from_strict_evidence():
    report = observe_checklist(document(heading(), node('a', 'paragraph', 'Required'), node('b', 'paragraph', 'words.')), [rule()])
    html = render_observation_html(report)
    assert '구조 연결 후보' in html
    assert '연속 문단' in html
    assert 'Required\nwords.' in html
    assert '새 구조 대응 승인 필요' in html


def test_unresolved_and_excluded_rows_are_not_hidden():
    report = observe_checklist(document(heading()), [rule(), rule(check_id='TEST-002-ZC-ENG', common_id='TEST-002', status='review')])
    html = render_observation_html(report)
    assert 'TEST-001-ZC-ENG' in html and 'TEST-002-ZC-ENG' in html
    assert '원문 누락 판정 아님' in html


def test_report_refuses_evaluated_or_unknown_schema():
    report = observe_checklist(document(heading()), [rule()])
    for field, value in [('decision_status', 'pass'), ('schema_version', 'unknown')]:
        with pytest.raises(ValueError):
            render_observation_html({**report, field: value})


def test_distributed_evidence_report_never_calls_it_a_whole_match():
    report = observe_checklist(document(heading(), node('p', 'paragraph', 'First.'),
        node('t', 'table', node('r', 'table_row', node('c', 'table_cell', 'Second.')))), [rule(required_text='First.\nSecond.')])
    html = render_observation_html(report)
    assert '분산된 문구 근거 — 전체 일치 아님' in html
    assert 'First.' in html and 'Second.' in html
