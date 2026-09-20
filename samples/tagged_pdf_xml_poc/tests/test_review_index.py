import json
from pathlib import Path

import pytest

from tagged_pdf_extractor.application.review_index import (
    ReviewIndexEntry,
    render_pending_review_index,
)


def write_review(path: Path, buyer: str, languages: dict[str, dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "source": {"buyer": buyer, "doc_type": "A2"},
                "language_stats": languages,
            }
        ),
        encoding="utf-8",
    )
    (path.parent / "semantic_document.preview.html").write_text("preview", encoding="utf-8")


def test_renders_one_row_per_buyer_language_with_structure_counts(tmp_path: Path) -> None:
    first = tmp_path / "first" / "review_document.json"
    second = tmp_path / "second" / "review_document.json"
    write_review(
        first,
        "MENA_L02",
        {
            "ENG": {"headings": 22, "review_units": 93, "blocks": {"table": 16, "figure": 40}},
            "ARA": {"headings": 22, "review_units": 92, "blocks": {"table": 15, "figure": 38}},
        },
    )
    write_review(
        second,
        "ZW_TPE",
        {"TPE": {"headings": 24, "review_units": 122, "blocks": {"table": 17, "figure": 6}}},
    )
    first_page = first.parent.parent / "review.html"
    second_page = second.parent.parent / "zw_review.html"
    first_page.write_text("review", encoding="utf-8")
    second_page.write_text("review", encoding="utf-8")
    output = tmp_path / "index" / "review.html"

    render_pending_review_index(
        (
            ReviewIndexEntry(first, first_page),
            ReviewIndexEntry(second, second_page),
        ),
        output,
    )

    html = output.read_text(encoding="utf-8")
    assert html.count("<tr>") == 4
    assert "MENA_L02" in html and "ENG" in html and ">22<" in html and ">93<" in html
    assert "ZW_TPE" in html and "TPE" in html and ">17<" in html and ">6<" in html
    assert "표시 제목" in html and "고유 이미지 파일 수" in html
    assert "../first/semantic_document.preview.html" in html


def test_rejects_duplicate_buyer_language_rows(tmp_path: Path) -> None:
    review = tmp_path / "review_document.json"
    write_review(
        review,
        "MENA_L02",
        {"ENG": {"headings": 1, "review_units": 1, "blocks": {"table": 0, "figure": 0}}},
    )
    entry = ReviewIndexEntry(review, tmp_path / "review.html")

    with pytest.raises(ValueError, match="duplicate buyer/language"):
        render_pending_review_index((entry, entry), tmp_path / "index.html")
