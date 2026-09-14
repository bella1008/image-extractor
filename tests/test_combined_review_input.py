from pathlib import Path
import sys

import pytest


def test_prepare_validates_before_creating_output(tmp_path, monkeypatch):
    from src.combined_review_input import prepare_combined_request
    pdf = tmp_path / 'BN68-25100B-00_SUG_Y26 TV ALL_ZC_L02_260122.0.pdf'
    pdf.write_bytes(b'%PDF')
    monkeypatch.setenv('ITEM_REVIEW_NODE', sys.executable)
    monkeypatch.setenv('ITEM_REVIEW_NODE_MODULES', str(tmp_path))
    first = prepare_combined_request(f'"{pdf}"', str(tmp_path / 'results'))
    second = prepare_combined_request(str(pdf), str(tmp_path / 'results'))
    assert first.pdf == pdf
    assert first.output_dir != second.output_dir
    assert not first.output_dir.parent.exists()
    assert first.node_executable == Path(sys.executable)
    for value in ('', str(tmp_path), str(tmp_path / 'missing.pdf')):
        with pytest.raises(ValueError):
            prepare_combined_request(value, str(tmp_path / 'results'))
    with pytest.raises(ValueError):
        prepare_combined_request(str(pdf), '')
    monkeypatch.delenv('ITEM_REVIEW_NODE')
    with pytest.raises(ValueError, match='ITEM_REVIEW_NODE'):
        prepare_combined_request(str(pdf), str(tmp_path / 'results'))


def test_launcher_includes_xml_package(monkeypatch):
    from scripts import start_item_review_ui as launcher
    def run(command, **kwargs):
        assert str(launcher.ROOT / 'samples/tagged_pdf_xml_poc/src') in kwargs['env']['PYTHONPATH']
        return type('Result', (), {'returncode': 0})()
    monkeypatch.setattr(launcher.subprocess, 'run', run)
    assert launcher.main(['--combined']) == 0
