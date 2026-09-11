"""Local PDF/checked-bundle observation report entry point."""
import argparse
from pathlib import Path

from src.review_service import DEFAULT_MAPPING, ReviewRequest, run_review


def main() -> int:
    parser = argparse.ArgumentParser(description='ZC ENG XML review observation; never automatic approval')
    parser.add_argument('pdf', type=Path)
    parser.add_argument('--output', type=Path, required=True, help='fresh run directory')
    parser.add_argument('--bundle', type=Path, help='reuse a checked XML extraction; otherwise extract PDF')
    parser.add_argument('--mapping', type=Path, default=DEFAULT_MAPPING)
    args = parser.parse_args()
    try:
        result = run_review(ReviewRequest(args.pdf, args.output, bundle=args.bundle, mapping=args.mapping))
    except Exception as exc:
        parser.exit(1, f'Review preparation failed; no business decision issued: {exc}\n')
    print(f"{result['status']}; checklist decision: {result['decision_status']}")
    print(args.output / 'review.html')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
