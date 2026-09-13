"""Transactional combined JSON/workbook export and self-contained archive reader."""
import json
import os
from pathlib import Path
import subprocess

from src.combined_review_model import (ARCHIVE_NAMES, build_combined_report, validate_combined_report,
    validate_source_run, parse_json, require, digest)
from src.combined_review_view import build_combined_review_view
from src.item_review_excel import validate_item_workbook as validate_workbook
from src.item_review_service import read_completed_item_review, _snapshot_completed_item_files, _write_new, _unchanged
from src.review_service import read_completed_observation
from src.review_source_archive import load_archived_source

FILES = ('review_report.json', 'review_report_view.json', 'review_report.xlsx')
COMPLETE = 'review_report_complete.json'
FAILED = 'review_report_failed.json'
LOCK = 'review_report.lock'


def _json(value):
    return json.dumps(value, ensure_ascii=True, indent=2, allow_nan=False) + '\n'


def _capture_source(folder, kind):
    folder = Path(folder)
    if kind == 'items':
        snapshots = _snapshot_completed_item_files(folder)
        report = read_completed_item_review(folder)
        failure = folder / 'item_review_failed.json'
    else:
        failure = folder / 'review_failed.json'
        require(not failure.exists(), 'failed checklist source')
        receipt_path = folder / 'review_complete.json'
        receipt_bytes = receipt_path.read_bytes()
        receipt = parse_json(receipt_bytes)
        require(isinstance(receipt, dict), 'invalid checklist completion')
        versions = {'review-observation-run/1': ('observation.json', 'review.html'),
                    'review-observation-run/2': ('observation.json',)}
        require(receipt.get('schema_version') in versions, 'invalid checklist completion version')
        snapshots = {receipt_path: receipt_bytes,
                     **{folder / name: (folder / name).read_bytes()
                        for name in versions[receipt['schema_version']]}}
        report = read_completed_observation(folder)
    files = {path.name: content.decode('utf-8') for path, content in snapshots.items()}
    validate_source_run(files, report, kind)
    _, _, source_snapshot = load_archived_source(report)
    snapshots.update(source_snapshot)
    archive = {name: source_snapshot[Path(report['inputs']['receipt']).parent / name].decode('utf-8')
               for name in ARCHIVE_NAMES}
    _unchanged(snapshots)
    require(not failure.exists(), 'source failed during capture')
    return report, files, archive, snapshots, failure


def _run_builder(view_path, output, node_executable, node_modules):
    node, modules = Path(node_executable).resolve(), Path(node_modules).resolve()
    require(node.is_file() and modules.is_dir(), 'Excel authoring runtime is not configured')
    script = Path(__file__).resolve().parents[1] / 'scripts/build_combined_review_excel.mjs'
    result = subprocess.run([str(node),str(script),str(view_path.resolve()),str(output.resolve()),
                             digest(view_path.read_bytes()),str(modules)], capture_output=True,
                            text=True,encoding='utf-8',errors='replace',timeout=240)
    _write_new(output/'authoring.log',result.stdout+'\n'+result.stderr)
    require(result.returncode == 0, 'Excel authoring failed; see authoring.log')


def export_combined_review(checklist_dir, item_dir, output_dir, node_executable, node_modules):
    """Create one fresh result folder; never overwrite inputs or an earlier run."""
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=False)
    return _export_into_reserved_directory(checklist_dir, item_dir, output, node_executable, node_modules)


def _export_into_reserved_directory(checklist_dir, item_dir, output, node_executable, node_modules):
    """Internal: caller owns the new directory; artifact writes still never overwrite."""
    output = Path(output)
    published = False
    try:
        _write_new(output/LOCK,str(os.getpid()))
        left = _capture_source(checklist_dir, 'checklist')
        right = _capture_source(item_dir, 'items')
        require(left[2] == right[2], 'different extraction archives')
        source = dict(left[3])
        for path, content in right[3].items():
            require(path not in source or source[path] == content, 'source changed between captures')
            source[path] = content
        report = build_combined_report(left[0],right[0],left[2],{'checklist':left[1],'items':right[1]})
        view = build_combined_review_view(report)
        expected = {}
        for name, data in ((FILES[0],report),(FILES[1],view)):
            text = _json(data)
            _write_new(output/name,text)
            expected[output/name] = text.encode('utf-8')
        _run_builder(output/FILES[1],output,node_executable,node_modules)
        content = (output/FILES[2]).read_bytes()
        validate_workbook(content,view)
        expected[output/FILES[2]] = content
        def verify():
            _unchanged(source)
            _unchanged(expected)
            require(not any(p.exists() for p in (left[4],right[4],output/FAILED)), 'source or output failed')
        verify()
        receipt = {'schema_version':'combined-review-run/1','status':'ready_for_human_review',
                   'decision_status':'not_evaluated','activation_status':'draft_only','summary':report['summary'],
                   'artifacts':{p.name:digest(data) for p,data in expected.items()}}
        pending = output/'review_report_complete.pending.json'
        text = _json(receipt)
        _write_new(pending,text)
        expected[pending] = text.encode('utf-8')
        verify()
        os.link(pending,output/COMPLETE)
        published = True
        expected[output/COMPLETE] = expected[pending]
        verify()
        pending.unlink()
        return receipt
    except Exception as exc:
        if published:
            try: (output/COMPLETE).unlink()
            except OSError: pass
        try: _write_new(output/FAILED,_json({'status':'failed','error_type':type(exc).__name__,'reason':str(exc)}))
        except OSError: pass
        raise
    finally:
        (output/LOCK).unlink(missing_ok=True)


def read_completed_combined_review(output_dir):
    """Validate display/download bytes without consulting historical files."""
    output = Path(output_dir)
    def ready():
        require(not any((output/name).exists() for name in (FAILED, LOCK, 'review_workflow.lock')),
                'combined run failed or is active')
    ready()
    snapshots = {output/name:(output/name).read_bytes() for name in (COMPLETE,*FILES)}
    receipt = parse_json(snapshots[output/COMPLETE])
    require(isinstance(receipt,dict) and receipt.get('schema_version')=='combined-review-run/1'
            and receipt.get('status')=='ready_for_human_review' and receipt.get('decision_status')=='not_evaluated'
            and receipt.get('activation_status')=='draft_only', 'invalid combined completion')
    require(isinstance(receipt.get('artifacts'),dict) and set(receipt['artifacts'])==set(FILES),
            'invalid combined artifact set')
    for name, expected in receipt['artifacts'].items():
        require(digest(snapshots[output/name]) == expected, f'combined artifact changed: {name}')
    report = parse_json(snapshots[output/FILES[0]])
    validate_combined_report(report)
    require(_json(receipt.get('summary')) == _json(report['summary']), 'combined receipt summary differs')
    view = build_combined_review_view(report)
    require(_json(parse_json(snapshots[output/FILES[1]])) == _json(view), 'combined view differs')
    validate_workbook(snapshots[output/FILES[2]],view)
    _unchanged(snapshots)
    ready()
    return {'report':report,'json_bytes':snapshots[output/FILES[0]],'excel_bytes':snapshots[output/FILES[2]]}
