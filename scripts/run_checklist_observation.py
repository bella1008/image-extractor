"""Run the frozen-draft ZC ENG observation pilot without activating the DB."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.review_service import DEFAULT_DRAFT, DEFAULT_MAPPING, run_observation


def main() -> int:
    parser = argparse.ArgumentParser(description="Provisional ZC ENG evidence observations; no checklist Pass/Fail")
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--mapping", type=Path, default=DEFAULT_MAPPING)
    parser.add_argument("--draft", type=Path, default=DEFAULT_DRAFT)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = run_observation(args.bundle, args.pdf, args.mapping, args.draft, args.output)
    except (OSError, ValueError, ImportError) as exc:
        parser.exit(1, f"Checklist observation failed: {exc}\n")
    print(json.dumps(report["summary"], ensure_ascii=True))
    print("No rule approved; no business Pass/Fail issued.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
