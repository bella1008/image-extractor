"""CLI entry point with the packaged XML source on the import path."""
from pilot_support import verify_release, check_runtime


if __name__ == '__main__':
    verify_release()
    check_runtime()
    from scripts.run_combined_review_v2 import main
    raise SystemExit(main())
