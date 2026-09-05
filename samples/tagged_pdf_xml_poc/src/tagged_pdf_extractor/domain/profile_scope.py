from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


_STANDARD_PDF_NAME = re.compile(
    r"^BN68-\d{5}[A-Z]-\d{2}_SUG_.+ ALL_"
    r"(?P<source_token>[^\r\n]+?)_\d{6}\.\d+\.pdf$",
    re.IGNORECASE,
)
_ENABLED_SOURCE_TOKEN = "ZG XN ZT_L05"


@dataclass(frozen=True)
class ProfileScope:
    source_token: str | None
    doc_type: str | None
    enabled: bool


def parse_source_token(filename: str) -> str | None:
    match = _STANDARD_PDF_NAME.fullmatch(filename)
    if match is None:
        return None
    source_token = match.group("source_token")
    if not source_token or source_token != source_token.strip():
        return None
    return source_token


def review_formatting_scope(source_path: Path) -> ProfileScope:
    source_token = parse_source_token(source_path.name)
    if (
        source_token is not None
        and source_token.casefold() == _ENABLED_SOURCE_TOKEN.casefold()
    ):
        return ProfileScope(source_token, "BOOK", True)
    return ProfileScope(source_token, None, False)
