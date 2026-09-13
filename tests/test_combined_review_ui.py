"""Thin viewer integration with real archived report validation."""
from pathlib import Path
import pytest

from tests.test_combined_review_model import combined_inputs
from tests.test_item_review_service import checked_bundle
from tests.test_combined_review_service import export

APP = Path(__file__).resolve().parents[1] / 'scripts/combined_review_app.py'


@pytest.fixture
def completed(combined_inputs, tmp_path, monkeypatch):
    return export(tmp_path, monkeypatch)


def app_test():
    assert APP.is_file(), 'combined review viewer missing'
    from streamlit.testing.v1 import AppTest
    return AppTest.from_file(str(APP), default_timeout=30).run()


def test_one_folder_shows_separate_counts_tables_and_downloads(completed):
    app = app_test()
    assert not app.exception and not app.dataframe and not app.get('download_button')
    assert len(app.text_input) == 1
    app.text_input[0].set_value(str(completed)).run()
    assert not app.dataframe
    app.button[0].click().run()
    assert not app.error and not app.exception
    assert [len(t.value) for t in app.dataframe] == [59, 14]
    assert [m.value for m in app.metric] == ['59', '14']
    assert len(app.get('download_button')) == 2
    assert all('검토 메모' not in t.value.columns for t in app.dataframe)
    assert not any(element.proto.allow_html for element in app.markdown)


@pytest.mark.parametrize('fault', ['file', 'failure', 'active', 'path'])
def test_invalidated_result_clears_display_and_downloads(completed, fault):
    app = app_test()
    app.text_input[0].set_value(str(completed))
    app.button[0].click().run()
    assert len(app.dataframe) == 2
    if fault == 'path':
        app.text_input[0].set_value(str(completed / 'other'))
    else:
        name = {'file':'review_report.xlsx', 'failure':'review_report_failed.json', 'active':'review_workflow.lock'}[fault]
        (completed / name).write_bytes(b'changed')
    app.run()
    assert not app.exception and not app.dataframe and not app.get('download_button')
    if fault != 'path':
        assert app.error


def test_download_revalidates_on_click(completed, monkeypatch):
    import streamlit as st
    captured = []
    original = st.download_button
    def capture(label, data, **kwargs):
        captured.append(data)
        return original(label, data, **kwargs)
    monkeypatch.setattr(st, 'download_button', capture)
    app = app_test()
    app.text_input[0].set_value(str(completed))
    app.button[0].click().run()
    assert len(captured) == 2 and all(callable(data) for data in captured)
    assert captured[0]() == (completed / 'review_report.xlsx').read_bytes()
    (completed / 'review_report_failed.json').write_text('{}')
    for data in captured:
        with pytest.raises(ValueError):
            data()


def test_launcher_selects_combined_viewer_on_localhost(monkeypatch):
    from scripts import start_item_review_ui as launcher
    seen = []
    def run(command, **kwargs):
        seen.append(command)
        return type('Result', (), {'returncode': 0})()
    monkeypatch.setattr(launcher.subprocess, 'run', run)
    assert launcher.main(['--combined', '--port', '8765']) == 0
    assert seen[0][4] == str(APP)
    assert seen[0][seen[0].index('--server.address') + 1] == '127.0.0.1'
