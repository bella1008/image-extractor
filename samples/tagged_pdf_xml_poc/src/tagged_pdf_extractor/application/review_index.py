from __future__ import annotations

from dataclasses import dataclass
from html import escape
import json
import os
from pathlib import Path


@dataclass(frozen=True)
class ReviewIndexEntry:
    review_document: Path
    review_page: Path


def render_pending_review_index(
    entries: tuple[ReviewIndexEntry, ...],
    output: Path,
) -> None:
    if not entries:
        raise ValueError("at least one review entry is required")
    output = Path(output)
    rows: list[str] = []
    seen: set[tuple[str, str]] = set()
    for entry in entries:
        payload = json.loads(Path(entry.review_document).read_text(encoding="utf-8"))
        source = payload.get("source")
        stats_by_language = payload.get("language_stats")
        if not isinstance(source, dict) or not isinstance(stats_by_language, dict):
            raise ValueError(f"invalid review bundle: {entry.review_document}")
        buyer = source.get("buyer") or source.get("source_token")
        doc_type = source.get("doc_type")
        if not isinstance(buyer, str) or not buyer or not isinstance(doc_type, str):
            raise ValueError(f"missing review source identity: {entry.review_document}")
        review_href = _relative_href(output.parent, Path(entry.review_page))
        preview_href = _relative_href(
            output.parent,
            Path(entry.review_document).parent / "semantic_document.preview.html",
        )
        for language, stats in stats_by_language.items():
            key = (buyer, language)
            if key in seen:
                raise ValueError(f"duplicate buyer/language review row: {buyer} {language}")
            seen.add(key)
            blocks = stats.get("blocks")
            if not isinstance(blocks, dict):
                raise ValueError(f"missing block statistics: {buyer} {language}")
            values = (
                buyer,
                doc_type,
                language,
                _exact_count(stats, "headings", buyer, language),
                _exact_count(stats, "review_units", buyer, language),
                _exact_count(blocks, "table", buyer, language),
                _exact_count(blocks, "figure", buyer, language),
            )
            cells = "".join(f"<td>{escape(str(value))}</td>" for value in values)
            links = (
                f'<a href="{escape(review_href, quote=True)}">바이어 검토</a> · '
                f'<a href="{escape(preview_href, quote=True)}">전체 HTML</a>'
            )
            rows.append(f"<tr>{cells}<td>{links}</td></tr>")

    body = (
        "<!doctype html><html lang=\"ko\"><meta charset=\"utf-8\">"
        "<style>body{font:17px Arial,sans-serif;max-width:1320px;margin:32px auto;"
        "line-height:1.65;padding:0 20px}table{border-collapse:collapse;width:100%}"
        "th,td{border:1px solid #aaa;padding:8px;text-align:left}th{background:#eef2f6}"
        "td:nth-child(n+4):nth-child(-n+7){text-align:right}</style><body>"
        "<h1>승인 대기 XML 추출 결과</h1>"
        "<p>각 언어의 구조 수와 검토 화면을 한곳에서 확인합니다.</p>"
        "<table><tr><th>바이어/source_token</th><th>문서 유형</th><th>언어</th>"
        "<th>표시 제목</th><th>검토 단위</th><th>표</th><th>그림</th><th>검토 파일</th></tr>"
        + "".join(rows)
        + "</table><p>표시 제목은 표지 제목을 포함한 검토 화면 제목 수입니다. "
        "표와 그림은 semantic XML 노드 수이며, 그림 수는 고유 이미지 파일 수나 아이콘 종류 수가 아닙니다.</p>"
        "</body></html>"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(body, encoding="utf-8")


def _exact_count(stats: dict, key: str, buyer: str, language: str) -> int:
    value = stats.get(key, 0)
    if type(value) is not int or value < 0:
        raise ValueError(f"invalid {key} count: {buyer} {language}")
    return value


def _relative_href(base: Path, target: Path) -> str:
    return Path(os.path.relpath(target.resolve(), base.resolve())).as_posix()
