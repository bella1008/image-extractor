"""A pilot ZIP is portable source plus frozen data, not a developer checkout."""
import hashlib
from io import BytesIO
import importlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from zipfile import ZipFile

import pytest

ROOT = Path(__file__).resolve().parents[1]


def api():
    assert importlib.util.find_spec('scripts.build_review_pilot'), 'Pilot release builder missing'
    return importlib.import_module('scripts.build_review_pilot')


def test_release_has_verified_contents_and_runs_after_relocation(tmp_path):
    archive = tmp_path / 'pilot.zip'
    api().build_release(ROOT, archive)
    with ZipFile(archive) as bundle:
        names = set(bundle.namelist())
        assert {'setup_review.py', 'start_review.py', '사용안내.md', 'release_manifest.json'} <= names
        assert {'src/combined_review_workbook.py', 'src/semantic_xml_reader.py',
                'metadata/checklist_v2/item_master_drafts/20260911/master_seed.json'} <= names
        assert not any(n.endswith(('.pdf', '.mjs', '.pyc')) or n.startswith(('outputs/', '.git/', '.venv/')) for n in names)
        assert 'src/content_poc.py' not in names and 'src/pdf_analyzer.py' not in names
        for name in names:
            data = bundle.read(name)
            blobs = [data]
            if name.endswith('.xlsx'):
                with ZipFile(BytesIO(data)) as workbook:
                    blobs = [workbook.read(part) for part in workbook.namelist()
                             if part.endswith(('.xml', '.rels'))]
            if name.endswith(('.py', '.json', '.md', '.txt', '.cmd', '.xlsx')):
                assert not any(b'C:\\Users\\' in blob or b'C:\\\\Users\\\\' in blob
                               for blob in blobs), name
        manifest = json.loads(bundle.read('release_manifest.json'))
        assert set(manifest['files']) == names - {'release_manifest.json'}
        for name, expected in manifest['files'].items():
            assert hashlib.sha256(bundle.read(name)).hexdigest() == expected
        draft_json = json.loads(bundle.read('metadata/checklist_v2/drafts/20260911/checklist_v2_draft.json'))
        draft_xlsx = bundle.read('metadata/checklist_v2/drafts/20260911/checklist_v2_draft.xlsx')
        assert draft_json['master_sha256'] == hashlib.sha256(draft_xlsx).hexdigest()
        review_service = bundle.read('src/review_service.py').decode('utf-8')
        assert f"FROZEN_DRAFT_JSON_SHA256 = '{hashlib.sha256(bundle.read('metadata/checklist_v2/drafts/20260911/checklist_v2_draft.json')).hexdigest()}'" in review_service
        destination = tmp_path / '다른 PC 검토 프로그램'
        bundle.extractall(destination)
    result = subprocess.run([sys.executable, 'start_review.py', '--check'], cwd=destination,
                            capture_output=True, text=True, encoding='utf-8')
    assert result.returncode == 0, result.stderr
    assert 'ZC_L02 ENG' in result.stdout
    # Direct CLI import resolves the copied src and bundled XML package, with
    # PYTHONPATH cleared; no source checkout or Node is needed.
    import os
    env = {k: v for k, v in os.environ.items() if k not in ('PYTHONPATH', 'ITEM_REVIEW_NODE', 'ITEM_REVIEW_NODE_MODULES')}
    result = subprocess.run([sys.executable, 'review_cli.py', '--help'],
                            cwd=destination, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    before = archive.read_bytes()
    with pytest.raises(FileExistsError):
        api().build_release(ROOT, archive)
    assert archive.read_bytes() == before
    (destination / 'src/combined_review_workbook.py').write_text('changed', encoding='utf-8')
    changed = subprocess.run([sys.executable, 'start_review.py', '--check'], cwd=destination,
                             capture_output=True, text=True, encoding='utf-8')
    assert changed.returncode != 0 and 'combined_review_workbook.py' in changed.stdout + changed.stderr


def test_missing_release_input_creates_no_zip(tmp_path):
    with pytest.raises((ValueError, FileNotFoundError)):
        api().build_release(tmp_path / 'missing-root', tmp_path / 'missing.zip')
    assert not (tmp_path / 'missing.zip').exists()


def test_release_built_from_relocated_checkout_removes_historic_paths(tmp_path):
    """The old author's paths can differ from this machine's checkout root."""
    import shutil
    builder = api()
    clone = tmp_path / 'new-machine-checkout'
    names = {*builder.DATA_FILES, *builder._python_dependencies(ROOT)}
    names.update(p.relative_to(ROOT).as_posix() for p in
                 (ROOT / 'samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor').rglob('*.py'))
    names.update('deployment/review-pilot/' + n for n in builder.LAUNCH_FILES)
    for name in names:
        target = clone / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    before = {n: (clone / n).read_bytes() for n in builder.DATA_FILES}
    subprocess.run(['git', 'init', '-q', str(clone)], check=True)
    subprocess.run(['git', '-c', 'user.name=Release Test', '-c', 'user.email=test@example.invalid',
                    'commit', '--allow-empty', '-qm', 'test checkout'], cwd=clone, check=True)
    archive = tmp_path / 'relocated.zip'
    builder.build_release(clone, archive)
    with ZipFile(archive) as bundle:
        for name in bundle.namelist():
            if name.endswith(('.json', '.py', '.md')):
                data = bundle.read(name)
                assert b'C:\\\\Users\\\\' not in data and b'C:\\Users\\' not in data, name
        destination = tmp_path / 'released'
        bundle.extractall(destination)
    result = subprocess.run([sys.executable, 'start_review.py', '--check'], cwd=destination,
                            capture_output=True, text=True, encoding='utf-8')
    assert result.returncode == 0, result.stdout + result.stderr
    assert all((clone / n).read_bytes() == data for n, data in before.items())


def test_pilot_supports_python_312_and_313_only():
    spec = importlib.util.spec_from_file_location(
        'pilot_support_policy', ROOT / 'deployment/review-pilot/pilot_support.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.is_supported_python((3, 12))
    assert module.is_supported_python((3, 13))
    assert not module.is_supported_python((3, 11))
    assert not module.is_supported_python((3, 14))


def test_setup_cmd_tries_python_313_before_falling_back_to_312_and_python():
    setup = (ROOT / 'deployment/review-pilot/setup.cmd').read_text(encoding='utf-8')
    first_313 = setup.index('py -3.13')
    fallback_312 = setup.index('py -3.12')
    fallback_python = setup.index('python setup_review.py')
    assert first_313 < fallback_312 < fallback_python
