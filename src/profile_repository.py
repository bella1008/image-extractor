from __future__ import annotations

import json
from pathlib import Path

from src.models import PdfProfile


class PdfProfileNotFoundError(KeyError):
    """Raised when no profile exists for a source token."""


class PdfProfileRepository:
    def __init__(self, mapping_path: str | Path) -> None:
        self.mapping_path = Path(mapping_path)
        self._profiles = self._load_profiles()

    def get(self, source_token: str) -> PdfProfile:
        try:
            return self._profiles[source_token]
        except KeyError as exc:
            raise PdfProfileNotFoundError(source_token) from exc

    def all(self) -> tuple[PdfProfile, ...]:
        return tuple(self._profiles.values())

    def _load_profiles(self) -> dict[str, PdfProfile]:
        with self.mapping_path.open("r", encoding="utf-8") as file:
            rows = json.load(file)

        profiles: dict[str, PdfProfile] = {}
        for row in rows:
            profile = PdfProfile(
                source_token=row["source_token"],
                region=row["region"],
                buyer_codes=split_semicolon_values(row["buyer_codes"]),
                languages=split_semicolon_values(row["languages"]),
                doc_type=row["doc_type"],
                language_count=int(row["language_count"]),
            )
            profiles[profile.source_token] = profile
        return profiles


def split_semicolon_values(value: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in value.split(";") if part.strip())
