"""Read-only screen and real Streamlit entrypoint regression tests."""
import importlib
import hashlib
import json
import os
from pathlib import Path
import sys
from types import ModuleType

import pytest
from tests.test_item_review_service import checked_bundle, request_for

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'scripts/item_review_app.py'


def implementation():
    assert importlib.util.find_spec('src.item_review_ui'), 'item screen loader missing'
    return importlib.import_module('src.item_review_ui')


@pytest.fixture
def completed(tmp_path, checked_bundle):
    from src.item_review_service import run_item_review
    request = request_for(tmp_path, checked_bundle)
    run_item_review(request)
    return request.output_dir


def test_loader_returns_exact_validated_downloads_and_fourteen_pending_items(completed):
    screen = implementation().load_item_review_screen(completed)
    assert screen['json_bytes'] == (completed / 'item_observation.json').read_bytes()
    assert 'html_bytes' not in screen
    assert screen['excel_bytes'] is None
    assert screen['report'] == json.loads(screen['json_bytes'])
    assert len(screen['report']['items']) == 14
    assert {item['result'] for item in screen['report']['items']} == {'needs_review'}


@pytest.mark.parametrize('mutation', ['json', 'receipt', 'failure'])
def test_loader_refuses_changed_or_failed_runs(completed, mutation):
    names = {'json': 'item_observation.json',
             'receipt': 'item_review_complete.json', 'failure': 'item_review_failed.json'}
    with (completed / names[mutation]).open('ab') as stream:
        stream.write(b'changed')
    with pytest.raises((ValueError, OSError)):
        implementation().load_item_review_screen(completed)


def test_loader_detects_change_between_validation_and_download_read(completed, monkeypatch):
    module = implementation()
    original = module.read_completed_item_review
    def changed(folder):
        report = original(folder)
        path = folder / 'item_observation.json'
        path.write_bytes(path.read_bytes() + b'changed')
        return report
    monkeypatch.setattr(module, 'read_completed_item_review', changed)
    with pytest.raises(ValueError, match='changed'):
        module.load_item_review_screen(completed)


@pytest.mark.parametrize('mutation', ['json', 'failure'])
def test_loader_rechecks_snapshot_after_final_validation(completed, monkeypatch, mutation):
    module = implementation()
    original = module.read_completed_item_review
    calls = 0
    def changed(folder):
        nonlocal calls
        report = original(folder)
        calls += 1
        if calls == 2:
            name = 'item_observation.json' if mutation == 'json' else 'item_review_failed.json'
            with (folder / name).open('ab') as stream:
                stream.write(b'changed')
        return report
    monkeypatch.setattr(module, 'read_completed_item_review', changed)
    with pytest.raises(ValueError, match='changed|failed'):
        module.load_item_review_screen(completed)


def test_optional_excel_bytes_are_validated_and_failure_invalidates_request(completed, monkeypatch):
    fake = ModuleType('src.item_review_excel')
    from src.item_review_excel import EXCEL_STATE_FILES
    fake.EXCEL_STATE_FILES = EXCEL_STATE_FILES
    (completed / 'item_excel_complete.json').write_text('{}')
    def read_excel(folder):
        assert folder == completed
        return b'checked excel'
    fake.read_completed_item_excel = read_excel
    monkeypatch.setitem(sys.modules, 'src.item_review_excel', fake)
    module = implementation()
    assert module.load_item_review_screen(completed)['excel_bytes'] == b'checked excel'
    def fail(*args):
        raise ValueError('changed workbook')
    fake.read_completed_item_excel = fail
    with pytest.raises(ValueError, match='Excel unavailable'):
        module.load_item_review_screen(completed)


def test_excel_change_during_screen_validation_is_not_served(completed, monkeypatch):
    module = implementation()
    fake = ModuleType('src.item_review_excel')
    from src.item_review_excel import EXCEL_STATE_FILES
    fake.EXCEL_STATE_FILES = EXCEL_STATE_FILES
    (completed / 'item_excel_complete.json').write_text('{}')
    current = [b'original verified export']
    fake.read_completed_item_excel = lambda *args: current[0]
    monkeypatch.setitem(sys.modules, 'src.item_review_excel', fake)
    original = module.read_completed_item_review
    calls = 0
    def changed(folder):
        nonlocal calls
        report = original(folder)
        calls += 1
        if calls == 2:
            current[0] = b'a different verified export'
        return report
    monkeypatch.setattr(module, 'read_completed_item_review', changed)
    with pytest.raises(ValueError, match='Excel unavailable'):
        module.load_item_review_screen(completed)


def app_test():
    assert APP.is_file(), 'Streamlit entrypoint missing'
    from streamlit.testing.v1 import AppTest
    return AppTest.from_file(str(APP), default_timeout=15).run()


def test_app_starts_empty_and_requires_explicit_load(completed):
    app = app_test()
    assert not app.exception and not app.dataframe and not app.get('download_button')
    assert app.text_input[0].value == ''
    app.text_input[0].set_value(str(completed)).run()
    assert not app.dataframe
    app.button[0].click().run()
    assert not app.exception and not app.error
    table = app.dataframe[0].value
    assert len(table) == 14
    assert list(table.columns) == ['item_key', 'required_text', '검토 판정', '설명']
    assert set(table['검토 판정']) == {'검토 필요'}
    assert len(app.get('download_button')) == 1
    assert any(metric.value == '14' and metric.label == '검토 필요' for metric in app.metric)
    assert len(app.expander) == 14
    assert not any(element.proto.allow_html for element in app.markdown)


@pytest.mark.parametrize('mutation', ['file', 'failure', 'path'])
def test_app_drops_previous_display_and_downloads_on_changes(completed, mutation):
    app = app_test()
    app.text_input[0].set_value(str(completed))
    app.button[0].click().run()
    assert len(app.dataframe[0].value) == 14
    if mutation == 'file':
        path = completed / 'item_observation.json'
        path.write_bytes(path.read_bytes() + b'changed')
    elif mutation == 'failure':
        (completed / 'item_review_failed.json').write_text('{}')
    else:
        app.text_input[0].set_value(str(completed / 'different'))
    app.run()
    assert not app.exception and not app.dataframe and not app.get('download_button')
    if mutation != 'path':
        assert app.error
    app.run()
    assert not app.dataframe and not app.get('download_button')


def test_app_invalid_path_shows_error_without_results(tmp_path):
    app = app_test()
    app.text_input[0].set_value(str(tmp_path / 'missing'))
    app.button[0].click().run()
    assert app.error and not app.exception and not app.dataframe and not app.get('download_button')


@pytest.mark.parametrize('malformed', ['[]', 'null'])
@pytest.mark.parametrize('name', ['item_review_complete.json', 'item_observation.json'])
def test_malformed_top_level_json_clears_loaded_screen(completed, name, malformed):
    app = app_test()
    app.text_input[0].set_value(str(completed))
    app.button[0].click().run()
    assert len(app.dataframe[0].value) == 14
    assert 'loaded_item_paths' in app.session_state
    (completed / name).write_text(malformed, encoding='utf-8')
    if name == 'item_observation.json':
        receipt_path = completed / 'item_review_complete.json'
        receipt = json.loads(receipt_path.read_bytes())
        receipt['artifacts'][name] = hashlib.sha256((completed / name).read_bytes()).hexdigest()
        receipt_path.write_text(json.dumps(receipt), encoding='utf-8')
    app.run()
    assert not app.exception and app.error
    assert not app.dataframe and not app.get('download_button')
    assert 'loaded_item_paths' not in app.session_state


def test_optional_excel_failure_removes_whole_display(completed, monkeypatch):
    fake = ModuleType('src.item_review_excel')
    from src.item_review_excel import EXCEL_STATE_FILES
    fake.EXCEL_STATE_FILES = EXCEL_STATE_FILES
    (completed / 'item_excel_complete.json').write_text('{}')
    fake.read_completed_item_excel = lambda *args: b'checked excel'
    monkeypatch.setitem(sys.modules, 'src.item_review_excel', fake)
    app = app_test()
    app.text_input[0].set_value(str(completed))
    app.button[0].click().run()
    assert not app.exception and len(app.get('download_button')) == 2
    def failed(*args):
        raise ValueError('workbook changed')
    fake.read_completed_item_excel = failed
    app.run()
    assert not app.exception and app.error and not app.dataframe and not app.get('download_button')
    assert any('Excel unavailable' in element.value for element in app.text)


def test_download_data_is_revalidated_at_click(completed, monkeypatch):
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
    assert len(captured) == 1 and all(callable(data) for data in captured)
    assert captured[0]() == (completed / 'item_observation.json').read_bytes()
    (completed / 'item_review_failed.json').write_text('{}')
    for data in captured:
        with pytest.raises(ValueError):
            data()


def test_launcher_is_loopback_only_and_preserves_environment(monkeypatch):
    assert importlib.util.find_spec('scripts.start_item_review_ui'), 'local launcher missing'
    module = importlib.import_module('scripts.start_item_review_ui')
    seen = []
    def run(command, **kwargs):
        seen.append((command, kwargs))
        return type('Result', (), {'returncode': 0})()
    monkeypatch.setattr(module.subprocess, 'run', run)
    monkeypatch.setenv('PYTHONPATH', 'existing-path')
    monkeypatch.setenv('ITEM_UI_TEST_ENV', 'preserved')
    assert module.main(['--port', '8765']) == 0
    command, options = seen[0]
    assert command[:4] == [sys.executable, '-m', 'streamlit', 'run']
    assert command[4] == str(APP)
    assert command[command.index('--server.address') + 1] == '127.0.0.1'
    assert command[command.index('--server.port') + 1] == '8765'
    assert command[command.index('--browser.gatherUsageStats') + 1] == 'false'
    assert options['cwd'] == ROOT and not options.get('shell', False)
    assert options['env']['PYTHONPATH'] == str(ROOT) + os.pathsep + 'existing-path'
    assert options['env']['ITEM_UI_TEST_ENV'] == 'preserved'


@pytest.mark.parametrize('port', ['1', '65536', 'text'])
def test_launcher_refuses_invalid_ports(port):
    assert importlib.util.find_spec('scripts.start_item_review_ui'), 'local launcher missing'
    module = importlib.import_module('scripts.start_item_review_ui')
    with pytest.raises(SystemExit) as error:
        module.main(['--port', port])
    assert error.value.code == 2
