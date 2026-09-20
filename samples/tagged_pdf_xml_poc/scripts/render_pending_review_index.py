"""Render one count-and-link index for pending buyer review bundles."""

import argparse
from pathlib import Path

from tagged_pdf_extractor.application.review_index import (
    ReviewIndexEntry,
    render_pending_review_index,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--entry",
        action="append",
        nargs=2,
        required=True,
        metavar=("REVIEW_DOCUMENT", "REVIEW_PAGE"),
    )
    args = parser.parse_args()
    entries = tuple(
        ReviewIndexEntry(Path(review_document), Path(review_page))
        for review_document, review_page in args.entry
    )
    render_pending_review_index(entries, args.output)
    print(args.output.resolve())


if __name__ == "__main__":
    main()
