from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PdfProfile:
    source_token: str
    region: str
    buyer_codes: tuple[str, ...]
    languages: tuple[str, ...]
    doc_type: str
    language_count: int
