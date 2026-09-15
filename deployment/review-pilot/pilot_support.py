"""Standard-library bootstrap used before the pilot's dependencies are installed."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import sys

ROOT = Path(__file__).resolve().parent


def verify_release():
    if sys.version_info[:2] != (3, 12):
        raise ValueError('Python 3.12 is required. Run with: py -3.12')
    manifest = json.loads((ROOT / 'release_manifest.json').read_text(encoding='utf-8'))
    if manifest.get('schema_version') != 'review-pilot-release/1' or not isinstance(manifest.get('files'), dict):
        raise ValueError('Invalid release manifest')
    for name, expected in manifest['files'].items():
        relative = PurePosixPath(name)
        if relative.is_absolute() or '..' in relative.parts or '\\' in name or ':' in name:
            raise ValueError('Invalid release filename')
        path = ROOT / name
        if not path.resolve().is_relative_to(ROOT) or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError(f'Release file changed: {name}. Extract a fresh ZIP.')
    return manifest


def prepare_imports():
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / 'samples/tagged_pdf_xml_poc/src'))


def check_runtime():
    from importlib.metadata import version
    for name, expected in {'pypdf': '6.16.2', 'PyMuPDF': '1.27.2.3',
                           'openpyxl': '3.1.5', 'streamlit': '1.63.0'}.items():
        if version(name) != expected:
            raise ValueError(f'{name} must be {expected}; run setup.cmd again')
    prepare_imports()
    from src.xml_review_run import extractor_digest
    from src.xml_review_gate import EXTRACTOR_SHA256
    from src.item_review_service import load_checked_item_master
    if extractor_digest() != EXTRACTOR_SHA256:
        raise ValueError('XML extractor differs from the verified source')
    load_checked_item_master()
