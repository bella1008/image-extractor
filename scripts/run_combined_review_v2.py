"""Prepare one ZC ENG PDF's checklist and item report in one folder."""
import argparse
import os
from pathlib import Path

from src.combined_review_run import CombinedReviewRequest, run_combined_review
from src.review_service import DEFAULT_DRAFT, DEFAULT_MAPPING
from src.item_review_service import DEFAULT_ITEM_MASTER


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pdf', type=Path)
    parser.add_argument('--output', type=Path, required=True, help='New result folder')
    parser.add_argument('--bundle', type=Path, help='Reuse a checked extraction instead of extracting PDF')
    parser.add_argument('--mapping', type=Path, default=DEFAULT_MAPPING)
    parser.add_argument('--draft', type=Path, default=DEFAULT_DRAFT)
    parser.add_argument('--master-dir', type=Path, default=DEFAULT_ITEM_MASTER)
    parser.add_argument('--node', type=Path, default=os.environ.get('ITEM_REVIEW_NODE'))
    parser.add_argument('--node-modules', type=Path, default=os.environ.get('ITEM_REVIEW_NODE_MODULES'))
    args = parser.parse_args(argv)
    if args.node is None or args.node_modules is None:
        parser.error('Set ITEM_REVIEW_NODE and ITEM_REVIEW_NODE_MODULES, or pass --node and --node-modules')
    try:
        run_combined_review(CombinedReviewRequest(args.pdf, args.output, args.node, args.node_modules,
                                                  bundle=args.bundle, mapping=args.mapping,
                                                  draft=args.draft, master_dir=args.master_dir))
    except Exception as exc:
        parser.exit(1, f'Combined review failed; no business decision issued: {exc}\n')
    print(args.output / 'review_report.xlsx')
    print('Prepared for human review; automatic business decision not evaluated.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
