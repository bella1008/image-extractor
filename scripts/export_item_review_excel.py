"""Create a separate checked workbook from a completed item observation."""
import argparse
import os
from pathlib import Path

from src.item_review_excel import export_item_review_excel


def main():
    parser = argparse.ArgumentParser(description='Export item results; no DB edit or automatic approval')
    parser.add_argument('run_dir', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--node', default=os.environ.get('ITEM_REVIEW_NODE'), help='explicit local Node executable')
    parser.add_argument('--node-modules', default=os.environ.get('ITEM_REVIEW_NODE_MODULES'), help='bundled Node modules directory')
    args = parser.parse_args()
    if not args.node or not args.node_modules:
        parser.error('Set --node and --node-modules (or ITEM_REVIEW_NODE / ITEM_REVIEW_NODE_MODULES)')
    try:
        export_item_review_excel(args.run_dir, args.output, Path(args.node), Path(args.node_modules))
    except Exception as exc:
        parser.exit(1, f'Excel export failed: {exc}\n')
    print(args.output / 'item_review.xlsx')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
