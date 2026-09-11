"""Prepare an item authoring seed from a fresh, checked CHK-002 observation."""
import argparse
import json
from pathlib import Path
import tempfile

from scripts.prepare_item_proposal import prepare_proposal
from src.checklist_item_master import build_master_seed, publish_json
from src.review_service import DEFAULT_MAPPING, read_completed_observation
from src.xml_review_gate import require


def prepare_master(run_dir: Path, pdf: Path, output: Path, mapping: Path = DEFAULT_MAPPING) -> dict:
    if output.exists():
        raise FileExistsError(f'use a fresh seed file: {output}')
    report = read_completed_observation(run_dir)
    receipt_path = Path(report['inputs']['receipt'])
    receipt_bytes = receipt_path.read_bytes()
    receipt = json.loads(receipt_bytes)
    paths = {pdf, mapping, receipt_path, run_dir / 'review_complete.json',
             run_dir / 'observation.json', run_dir / 'review.html',
             *(Path(report['inputs'][key]) for key in ('draft_excel', 'draft_json')),
             *(receipt_path.parent / name for name in receipt['artifacts'])}
    before = {path: path.read_bytes() for path in paths}
    require(before[receipt_path] == receipt_bytes, 'receipt changed before preparation')
    output.parent.mkdir(parents=True, exist_ok=True)
    # The checked proposal is private to this invocation, never an arbitrary JSON input.
    with tempfile.TemporaryDirectory(prefix='item-master-', dir=output.parent) as temporary:
        proposal = prepare_proposal(run_dir, pdf, Path(temporary) / 'proposal.json', mapping)
        result = build_master_seed(proposal)
        def unchanged():
            require(all(path.read_bytes() == data for path, data in before.items()),
                    'source changed during master preparation')
            require(read_completed_observation(run_dir) == report, 'completed observation changed')
        publish_json(output, result, unchanged)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_dir', type=Path)
    parser.add_argument('pdf', type=Path)
    parser.add_argument('--mapping', type=Path, default=DEFAULT_MAPPING)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    prepare_master(args.run_dir, args.pdf, args.output, args.mapping)


if __name__ == '__main__':
    main()
