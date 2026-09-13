"""Checked archival screen data, independent of Streamlit and extraction tools."""
import json
from pathlib import Path

from src.item_review_service import read_completed_item_review, _snapshot_completed_item_files
from src.item_review_excel import EXCEL_STATE_FILES


def _read_report(run_dir: Path) -> dict:
    try:
        return read_completed_item_review(run_dir)
    except AttributeError as exc:
        # The archival reader expects JSON objects. Invalid JSON shapes must use
        # the same controlled failure path as invalid hashes and missing files.
        raise ValueError('invalid completed item receipt or report structure') from exc


def load_item_review_screen(run_dir: Path) -> dict:
    """Load a completed observation and downloads as one validated snapshot.

    Historical PDF/master inputs are provenance, not live dependencies. No report
    or bytes are cached: callers must repeat this read on each display/download.
    A partial or invalid same-directory Excel export invalidates the request.
    """
    run_dir = Path(run_dir)
    before = _snapshot_completed_item_files(run_dir)
    report = _read_report(run_dir)
    excel_state = tuple((run_dir / name).exists() for name in EXCEL_STATE_FILES)
    excel_bytes = None
    if any(excel_state):
        try:
            from src.item_review_excel import read_completed_item_excel
            if not excel_state[0] or any(excel_state[3:]):
                raise ValueError('Excel export is incomplete or failed')
            excel_bytes = read_completed_item_excel(run_dir)
        except (ImportError, OSError, ValueError, KeyError, TypeError) as exc:
            raise ValueError('Excel unavailable: completed export could not be verified') from exc
    if any(path.read_bytes() != content for path, content in before.items()):
        raise ValueError('completed item snapshot changed during screen read')
    if json.loads(before[run_dir / 'item_observation.json']) != report:
        raise ValueError('completed item report changed during screen read')
    if _read_report(run_dir) != report:
        raise ValueError('completed item snapshot changed during screen validation')
    if excel_bytes is not None:
        try:
            if read_completed_item_excel(run_dir) != excel_bytes:
                raise ValueError('completed export changed during screen validation')
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise ValueError('Excel unavailable: completed export changed or failed validation') from exc
    if tuple((run_dir / name).exists() for name in EXCEL_STATE_FILES) != excel_state:
        raise ValueError('Excel export changed during screen validation')
    if any(path.read_bytes() != content for path, content in before.items()):
        raise ValueError('completed item snapshot changed after screen validation')
    if (run_dir / 'item_review_failed.json').exists():
        raise ValueError('failed run cannot be displayed or downloaded')
    return {'report': report, 'json_bytes': before[run_dir / 'item_observation.json'],
            'excel_bytes': excel_bytes}
