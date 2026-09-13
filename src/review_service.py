"""Checked local observation workflow; no UI dependency or business approval."""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from importlib.metadata import version as package_version
from pathlib import Path

from src.checklist_migration import read_excel_rows
from src.checklist_observation import observe_checklist
from src.review_observation_report import render_observation_html

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DRAFT = ROOT / 'metadata/checklist_v2/drafts/20260911'
DEFAULT_MAPPING = ROOT / 'metadata/pdf_profile_mapping/pdf_profile_mapping.json'
FROZEN_DRAFT_JSON_SHA256 = '9c0ff6c536517905f9a9d675da67ebbc8eeea23beebe8a9ee82dbce370e62762'


def validate_extraction_environment() -> None:
    actual = package_version('pypdf')
    if actual != '6.16.2':
        raise ValueError(f'XML extractor requires pypdf==6.16.2, found {actual}; use the v2 virtual environment')


def _digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _json_text(value):
    return json.dumps(value, ensure_ascii=True, indent=2) + '\n'


def _write_new(path, text):
    with Path(path).open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(text)


def run_observation(bundle: Path, pdf: Path, mapping: Path, draft: Path, output: Path) -> dict:
    """Existing CLI-compatible API; verify frozen Excel/JSON and XML before use."""
    from src.semantic_xml_reader import read_review_bundle
    from src.xml_review_gate import require, validate_bundle
    if output.exists():
        raise FileExistsError(f'use a fresh output file: {output}')
    receipt_path = bundle / 'review_run.json'
    json_path, excel_path = draft / 'checklist_v2_draft.json', draft / 'checklist_v2_draft.xlsx'
    paths = (receipt_path, json_path, excel_path)
    before = tuple(_digest(path) for path in paths)
    require(before[1] == FROZEN_DRAFT_JSON_SHA256, 'draft JSON is not the frozen audited version')
    payload = json.loads(json_path.read_text(encoding='utf-8'))
    require(payload.get('schema_version') == 'checklist-v2-draft/1', 'unsupported draft schema')
    require(payload.get('activation_status') == 'blocked_pending_contract_review', 'draft activation status changed')
    require(payload.get('master_sha256') == before[2], 'draft Excel hash differs from exported JSON')
    rows = read_excel_rows(excel_path, draft=True)
    require(rows == payload.get('rules'), 'draft Excel and JSON values differ')
    receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
    document = read_review_bundle(bundle, receipt, pdf_path=pdf, mapping_path=mapping)
    report = observe_checklist(document, rows)
    require(tuple(_digest(path) for path in paths) == before, 'input changed during observation')
    validate_bundle(bundle, receipt, pdf_path=pdf, mapping_path=mapping)
    report['inputs'] = {'receipt': str(receipt_path.resolve()), 'receipt_sha256': before[0],
                        'draft_json': str(json_path.resolve()), 'draft_json_sha256': before[1],
                        'draft_excel': str(excel_path.resolve()), 'draft_excel_sha256': before[2],
                        'source_bundle': receipt}
    output.parent.mkdir(parents=True, exist_ok=True)
    _write_new(output, _json_text(report))
    return report


@dataclass(frozen=True)
class ReviewRequest:
    pdf: Path
    output_dir: Path
    bundle: Path | None = None
    mapping: Path = DEFAULT_MAPPING
    draft: Path = DEFAULT_DRAFT
    include_html: bool = True


def run_review(request: ReviewRequest) -> dict:
    """PDF (or checked existing extraction) -> observation JSON + offline HTML.

    A completion receipt is published last. Failed directories are retained for
    diagnosis and never reused. This is an observation service, not an evaluator.
    """
    from src.xml_review_gate import require, validate_bundle
    output = Path(request.output_dir)
    output.mkdir(parents=True, exist_ok=False)
    try:
        bundle = Path(request.bundle) if request.bundle is not None else output / 'extraction'
        if request.bundle is None:
            validate_extraction_environment()
            from src.xml_review_run import extract_review_document
            extract_review_document(request.pdf, bundle, request.mapping)
        report = run_observation(bundle, request.pdf, request.mapping, request.draft, output / 'observation.json')
        expected = {'observation.json': _json_text(report).encode('utf-8')}
        if request.include_html:
            html = render_observation_html(report)
            expected['review.html'] = html.encode('utf-8')
            _write_new(output / 'review.html', html)
        inputs = report['inputs']
        for key in ('receipt', 'draft_json', 'draft_excel'):
            require(_digest(inputs[key]) == inputs[key + '_sha256'], 'input changed during report generation')
        validate_bundle(bundle, inputs['source_bundle'], pdf_path=request.pdf, mapping_path=request.mapping)
        for name, content in expected.items():
            require((output / name).read_bytes() == content, f'{name} changed during report generation')
        receipt = {'schema_version': 'review-observation-run/1' if request.include_html else 'review-observation-run/2',
                   'status': 'ready_for_human_review',
                   'decision_status': 'not_evaluated', 'summary': report['summary'],
                   'artifacts': {name: hashlib.sha256(content).hexdigest() for name, content in expected.items()}}
        pending = output / 'review_complete.pending.json'
        _write_new(pending, _json_text(receipt))
        require(pending.read_bytes() == _json_text(receipt).encode('utf-8'), 'completion staging changed')
        # Atomic, no-overwrite publication on the same filesystem. Unsupported
        # filesystems fail closed rather than leave a partial final receipt.
        os.link(pending, output / 'review_complete.json')
        try:
            pending.unlink()
        except OSError:
            pass  # A leftover staging name does not invalidate a complete receipt.
        return receipt
    except Exception as exc:
        try:
            _write_new(output / 'review_failed.json', _json_text({'status': 'failed', 'decision_status': 'not_evaluated',
                                                                'error_type': type(exc).__name__, 'reason': str(exc)}))
        except OSError:
            pass
        raise


def read_completed_observation(output: Path) -> dict:
    """Verify a completed snapshot before rendering another report format.

    This checks accidental mutation, not a cryptographic approval signature.
    Source files can be archived separately; their recorded hashes stay in JSON.
    """
    from src.xml_review_gate import require
    require(not (output / 'review_failed.json').exists(), 'failed run cannot be consumed')
    receipt = json.loads((output / 'review_complete.json').read_text(encoding='utf-8'))
    versions = {'review-observation-run/1': {'observation.json', 'review.html'},
                'review-observation-run/2': {'observation.json'}}
    require(isinstance(receipt, dict) and receipt.get('schema_version') in versions
            and receipt.get('status') == 'ready_for_human_review'
            and receipt.get('decision_status') == 'not_evaluated', 'invalid completion receipt')
    require(isinstance(receipt.get('artifacts'), dict)
            and set(receipt['artifacts']) == versions[receipt['schema_version']], 'unexpected completed artifacts')
    contents = {name: (output / name).read_bytes() for name in receipt['artifacts']}
    for name, data in contents.items():
        require(hashlib.sha256(data).hexdigest() == receipt['artifacts'][name], f'completed artifact changed: {name}')
    report = json.loads(contents['observation.json'])
    require(report.get('schema_version') == 'checklist-observation/2'
            and report.get('decision_status') == 'not_evaluated'
            and report.get('summary') == receipt.get('summary'), 'observation and completion differ')
    return report
