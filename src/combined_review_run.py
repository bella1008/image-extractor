"""One checked extraction shared by checklist and item observations."""
from dataclasses import dataclass
import os
from pathlib import Path

from src.combined_review_service import COMPLETE, FAILED, _export_into_reserved_directory, _json
from src.item_review_service import DEFAULT_ITEM_MASTER, MASTER_NAMES, _write_new, _unchanged
from src.review_service import DEFAULT_DRAFT, DEFAULT_MAPPING, validate_extraction_environment
from src.xml_review_gate import ARTIFACT_NAMES

WORKFLOW_LOCK = 'review_workflow.lock'


@dataclass(frozen=True)
class CombinedReviewRequest:
    pdf: Path
    output_dir: Path
    node_executable: Path
    node_modules: Path
    bundle: Path | None = None
    mapping: Path = DEFAULT_MAPPING
    draft: Path = DEFAULT_DRAFT
    master_dir: Path = DEFAULT_ITEM_MASTER


def run_combined_review(request: CombinedReviewRequest) -> dict:
    """Keep internal evidence and the user-facing workbook in one new run folder.

    Observers independently validate the same extraction bundle. Neither gets
    permission to re-extract, approve rules or change the source document.
    """
    from src.review_service import ReviewRequest, run_review
    from src.item_review_service import ItemReviewRequest, run_item_review
    from src.xml_review_run import extract_review_document

    output = Path(request.output_dir).resolve()
    output.mkdir(parents=True, exist_ok=False)
    try:
        _write_new(output / WORKFLOW_LOCK, str(os.getpid()))
        pdf, mapping = Path(request.pdf), Path(request.mapping)
        inputs = (pdf, mapping,
                  *(Path(request.draft) / name for name in ('checklist_v2_draft.json', 'checklist_v2_draft.xlsx')),
                  *(Path(request.master_dir) / name for name in MASTER_NAMES))
        snapshots = {path: path.read_bytes() for path in inputs}
        internal = output / '_internal'
        bundle = Path(request.bundle) if request.bundle is not None else internal / 'extraction'
        if request.bundle is None:
            validate_extraction_environment()
            extract_review_document(pdf, bundle, mapping)
        for name in ('review_run.json', *ARTIFACT_NAMES):
            path = bundle / name
            snapshots[path] = path.read_bytes()
        document_path = bundle / 'review_document.json'
        if document_path.exists():
            snapshots[document_path] = document_path.read_bytes()
        _unchanged(snapshots)
        checklist, items = internal / 'checklist', internal / 'items'
        run_review(ReviewRequest(pdf, checklist, bundle=bundle, mapping=mapping,
                                 draft=Path(request.draft), include_html=False))
        run_item_review(ItemReviewRequest(pdf, items, bundle=bundle, mapping=mapping,
                                          master_dir=Path(request.master_dir)))
        _unchanged(snapshots)
        receipt = _export_into_reserved_directory(checklist, items, output,
                                                  request.node_executable, request.node_modules)
        _unchanged(snapshots)
        # The exporter validates the artifact snapshot around receipt publication;
        # this outer lock keeps it private until original inputs are rechecked.
        (output / WORKFLOW_LOCK).unlink()
        return receipt
    except Exception as exc:
        try:
            _write_new(output / FAILED, _json({'status': 'failed', 'decision_status': 'not_evaluated',
                                              'error_type': type(exc).__name__, 'reason': str(exc)}))
        except OSError:
            pass
        try:
            (output / COMPLETE).unlink(missing_ok=True)
        except OSError:
            pass
        # Retain the lock on failure as an additional signal that this workflow
        # did not finish, including interruption before a failure file was saved.
        raise
