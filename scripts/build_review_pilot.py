"""Build an internal Python-only ZC reviewer pilot ZIP from explicit runtime roots."""
import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
from zipfile import ZipFile, ZIP_DEFLATED

ENTRY_POINTS = ('scripts/combined_review_app.py', 'scripts/start_item_review_ui.py',
                'scripts/run_combined_review_v2.py', 'scripts/export_combined_review.py')
DATA_FILES = ('requirements-review-v2.txt', 'requirements-review-ui.txt',
              'metadata/pdf_profile_mapping/pdf_profile_mapping.json',
              'metadata/checklist_v2/drafts/20260911/checklist_v2_draft.json',
              'metadata/checklist_v2/drafts/20260911/checklist_v2_draft.xlsx',
              'metadata/checklist_v2/item_master_drafts/20260911/checklist_item_master.json',
              'metadata/checklist_v2/item_master_drafts/20260911/checklist_item_master.xlsx',
              'metadata/checklist_v2/item_master_drafts/20260911/master_seed.json')
LAUNCH_FILES = ('setup_review.py', 'start_review.py', 'review_cli.py', 'pilot_support.py',
                'setup.cmd', 'start.cmd', '사용안내.md')


def _python_dependencies(root):
    """Follow static src/scripts imports, including imports inside functions."""
    pending = list(ENTRY_POINTS) + ['src/__init__.py']
    found = set()
    while pending:
        name = pending.pop()
        if name in found:
            continue
        path = root / name
        tree = ast.parse(path.read_text(encoding='utf-8-sig'))
        found.add(name)
        modules = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules.append(node.module)
                modules.extend(f'{node.module}.{alias.name}' for alias in node.names)
        for module in modules:
            if module.split('.')[0] not in ('src', 'scripts'):
                continue
            candidate = module.replace('.', '/') + '.py'
            if (root / candidate).is_file():
                pending.append(candidate)
    return found


def build_release(root, output):
    root, output = Path(root).resolve(), Path(output).resolve()
    if output.exists():
        raise FileExistsError(output)
    paths = {name: root / name for name in (*DATA_FILES, *_python_dependencies(root))}
    for path in (root / 'samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor').rglob('*.py'):
        paths[path.relative_to(root).as_posix()] = path
    paths.update({name: root / 'deployment/review-pilot' / name for name in LAUNCH_FILES})
    if not any(name.endswith('/tagged_pdf_extractor/__init__.py') for name in paths):
        raise ValueError('XML package missing')
    if any(name in paths for name in ('src/content_poc.py', 'src/pdf_analyzer.py', 'src/text_extractor.py')):
        raise ValueError('Legacy extraction entered the pilot dependency set')
    for path in paths.values():
        if not path.resolve().is_relative_to(root):
            raise ValueError('Release input resolves outside the worktree')
    snapshots = {name: path.read_bytes() for name, path in sorted(paths.items())}
    def git(*args):
        result = subprocess.run(['git', *args], cwd=root, capture_output=True, text=True)
        if result.returncode:
            raise ValueError('Cannot record release Git revision')
        return result.stdout.strip()
    manifest = {'schema_version': 'review-pilot-release/1', 'support': 'ZC_L02 ENG',
                'decision_status': 'not_evaluated', 'python': '3.12',
                'created_utc': datetime.now(timezone.utc).isoformat(),
                'source_revision': git('rev-parse', 'HEAD'),
                'working_tree_changed': bool(git('status', '--porcelain')),
                'files': {name: hashlib.sha256(data).hexdigest() for name, data in snapshots.items()}}
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix='.review-release-', suffix='.pending.zip', dir=output.parent)
    pending = Path(name)
    try:
        with os.fdopen(descriptor, 'w+b') as stream:
            with ZipFile(stream, 'w', compression=ZIP_DEFLATED) as archive:
                for name, data in snapshots.items():
                    archive.writestr(name, data)
                archive.writestr('release_manifest.json', json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
        if any(path.read_bytes() != snapshots[name] for name, path in paths.items()):
            raise ValueError('Release source changed during build')
        with ZipFile(pending) as archive:
            if archive.testzip() is not None:
                raise ValueError('ZIP integrity check failed')
            for name, expected in manifest['files'].items():
                if hashlib.sha256(archive.read(name)).hexdigest() != expected:
                    raise ValueError(f'ZIP entry changed: {name}')
        os.link(pending, output)
    finally:
        pending.unlink(missing_ok=True)
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    manifest = build_release(Path(__file__).resolve().parents[1], args.output)
    print(f'{args.output}: {len(manifest["files"])} files; {manifest["support"]} pilot')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
