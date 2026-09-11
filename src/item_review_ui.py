"""Checked archival screen data, independent of Streamlit and extraction tools."""
import json
from pathlib import Path

from src.item_review_service import read_completed_item_review


def _read_report(run_dir: Path) -> dict:
    try:
        return read_completed_item_review(run_dir)
    except AttributeError as exc:
        # The archival reader expects JSON objects. Invalid JSON shapes must use
        # the same controlled failure path as invalid hashes and missing files.
        raise ValueError('invalid completed item receipt or report structure') from exc


def load_item_review_screen(run_dir: Path, excel_dir: Path | None = None) -> dict:
    """Load a completed observation and downloads as one validated snapshot.

    Historical PDF/master inputs are provenance, not live dependencies. No report
    or bytes are cached: callers must repeat this read on each display/download.
    An explicitly requested but invalid Excel export invalidates the full request.
    """
    run_dir = Path(run_dir)
    names = ('item_review_complete.json', 'item_observation.json', 'item_review.html')
    before = {name: (run_dir / name).read_bytes() for name in names}
    report = _read_report(run_dir)
    excel_bytes = None
    if excel_dir is not None:
        try:
            from src.item_review_excel import read_completed_item_excel
            excel_bytes = read_completed_item_excel(Path(excel_dir), run_dir)
        except (ImportError, OSError, ValueError, KeyError, TypeError) as exc:
            raise ValueError('Excel unavailable: completed export could not be verified') from exc
    if any((run_dir / name).read_bytes() != content for name, content in before.items()):
        raise ValueError('completed item snapshot changed during screen read')
    if json.loads(before['item_observation.json']) != report:
        raise ValueError('completed item report changed during screen read')
    if _read_report(run_dir) != report:
        raise ValueError('completed item snapshot changed during screen validation')
    if excel_dir is not None:
        try:
            if read_completed_item_excel(Path(excel_dir), run_dir) != excel_bytes:
                raise ValueError('completed export changed during screen validation')
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise ValueError('Excel unavailable: completed export changed or failed validation') from exc
    if any((run_dir / name).read_bytes() != content for name, content in before.items()):
        raise ValueError('completed item snapshot changed after screen validation')
    if (run_dir / 'item_review_failed.json').exists():
        raise ValueError('failed run cannot be displayed or downloaded')
    return {'report': report, 'json_bytes': before['item_observation.json'],
            'html_bytes': before['item_review.html'], 'excel_bytes': excel_bytes}
