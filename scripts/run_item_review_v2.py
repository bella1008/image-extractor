"""Observe the bounded CHK-002 item draft against a new PDF or checked XML."""
import argparse
from pathlib import Path

from src.item_review_service import DEFAULT_ITEM_MASTER, DEFAULT_MAPPING, ItemReviewRequest, run_item_review


def main() -> int:
    parser = argparse.ArgumentParser(description='ZC ENG CHK-002 item observations; no automatic business decision')
    parser.add_argument('pdf', type=Path)
    parser.add_argument('--output', required=True, type=Path, help='fresh result directory')
    parser.add_argument('--bundle', type=Path, help='checked extraction directory; otherwise extract the PDF')
    parser.add_argument('--master-dir', type=Path, default=DEFAULT_ITEM_MASTER)
    parser.add_argument('--mapping', type=Path, default=DEFAULT_MAPPING)
    args = parser.parse_args()
    try:
        result = run_item_review(ItemReviewRequest(args.pdf, args.output, bundle=args.bundle,
                                                  master_dir=args.master_dir, mapping=args.mapping))
    except Exception as exc:
        parser.exit(1, f'Item review preparation failed; no business decision issued: {exc}\n')
    print(f"{result['status']}; checklist decision: {result['decision_status']}")
    print(args.output / 'item_observation.json')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
