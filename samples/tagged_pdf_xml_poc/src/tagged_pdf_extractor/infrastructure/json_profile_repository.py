from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from tagged_pdf_extractor.domain.models import PdfProfile
from tagged_pdf_extractor.domain.profile_scope import parse_source_token
from tagged_pdf_extractor.ports.profile_repository import (
    DuplicateSourceTokenError,
    InvalidPdfFilenameError,
    InvalidProfileMappingError,
    InvalidProfileRowError,
    ProfileMappingFileError,
    UnknownSourceTokenError,
)


_FIELDS = (
    "source_token",
    "region",
    "buyer_codes",
    "languages",
    "doc_type",
    "language_count",
)
_DOC_TYPES = frozenset(("A2", "A3", "BOOK"))
_LANGUAGE_COUNT_TOKEN = re.compile(r"_L(?P<count>\d+)$", re.IGNORECASE)


class JsonProfileRepository:
    def __init__(self, mapping_path: str | Path) -> None:
        self._mapping_path = Path(mapping_path)
        self._profiles = self._load_profiles()

    def lookup(self, pdf_path: str | Path) -> PdfProfile:
        file_name = Path(pdf_path).name
        source_token = parse_source_token(file_name)
        if source_token is None:
            raise InvalidPdfFilenameError(
                f"Cannot derive source_token from PDF filename {file_name!r}"
            )
        try:
            return self._profiles[source_token.casefold()]
        except KeyError as exc:
            raise UnknownSourceTokenError(
                f"No canonical PDF profile for source_token {source_token!r}"
            ) from exc

    def _load_profiles(self) -> dict[str, PdfProfile]:
        try:
            with self._mapping_path.open("r", encoding="utf-8") as file:
                payload = json.load(file)
        except json.JSONDecodeError as exc:
            raise InvalidProfileMappingError(
                f"Profile mapping must contain valid JSON: {self._mapping_path}"
            ) from exc
        except UnicodeDecodeError as exc:
            raise InvalidProfileMappingError(
                f"Profile mapping must contain valid UTF-8 JSON: {self._mapping_path}"
            ) from exc
        except OSError as exc:
            raise ProfileMappingFileError(
                f"Could not read profile mapping file: {self._mapping_path}"
            ) from exc

        if not isinstance(payload, list):
            raise InvalidProfileMappingError("Profile mapping root must be a JSON array")
        if not payload:
            raise InvalidProfileMappingError("Profile mapping must contain at least one row")

        profiles: dict[str, PdfProfile] = {}
        first_rows: dict[str, int] = {}
        for row_index, row in enumerate(payload):
            profile = _parse_profile_row(row, row_index)
            normalized_token = profile.source_token.casefold()
            if normalized_token in profiles:
                raise DuplicateSourceTokenError(
                    f"Duplicate source_token {profile.source_token!r} in rows "
                    f"{first_rows[normalized_token]} and {row_index}"
                )
            profiles[normalized_token] = profile
            first_rows[normalized_token] = row_index
        return profiles


def _parse_profile_row(row: Any, row_index: int) -> PdfProfile:
    if not isinstance(row, dict):
        raise InvalidProfileRowError(f"Profile row {row_index} must be a JSON object")

    missing_fields = [field for field in _FIELDS if field not in row]
    if missing_fields:
        raise InvalidProfileRowError(
            f"Profile row {row_index} is missing required field {missing_fields[0]!r}"
        )

    unexpected_fields = sorted(set(row) - set(_FIELDS))
    if unexpected_fields:
        raise InvalidProfileRowError(
            f"Profile row {row_index} has unexpected field {unexpected_fields[0]!r}"
        )

    source_token = _required_string(row, row_index, "source_token")
    region = _required_string(row, row_index, "region")
    buyer_codes_text = _required_string(row, row_index, "buyer_codes")
    languages_text = _required_string(row, row_index, "languages")
    doc_type = _required_string(row, row_index, "doc_type")
    language_count = row["language_count"]
    if isinstance(language_count, bool) or not isinstance(language_count, int):
        raise InvalidProfileRowError(
            f"Profile row {row_index} field 'language_count' must be an integer"
        )
    if language_count <= 0:
        raise InvalidProfileRowError(
            f"Profile row {row_index} language_count must be positive"
        )

    buyer_codes = _ordered_values(buyer_codes_text, row_index, "buyer_codes")
    languages = _ordered_values(languages_text, row_index, "languages")
    if language_count != len(languages):
        raise InvalidProfileRowError(
            f"Profile row {row_index} language_count {language_count} does not match "
            f"{len(languages)} languages"
        )
    if doc_type not in _DOC_TYPES:
        raise InvalidProfileRowError(
            f"Profile row {row_index} field 'doc_type' must be A2, A3, or BOOK"
        )

    _validate_source_token_consistency(
        source_token, buyer_codes, languages, language_count, row_index
    )
    return PdfProfile(
        source_token=source_token,
        region=region,
        buyer_codes=buyer_codes,
        languages=languages,
        doc_type=doc_type,
        language_count=language_count,
    )


def _required_string(row: dict[str, Any], row_index: int, field: str) -> str:
    value = row[field]
    if not isinstance(value, str):
        raise InvalidProfileRowError(
            f"Profile row {row_index} field {field!r} must be a string"
        )
    if not value or value != value.strip():
        raise InvalidProfileRowError(
            f"Profile row {row_index} field {field!r} must be a non-empty trimmed string"
        )
    return value


def _ordered_values(value: str, row_index: int, field: str) -> tuple[str, ...]:
    raw_items = value.split(";")
    if any(not item.strip() for item in raw_items):
        raise InvalidProfileRowError(
            f"Profile row {row_index} field {field!r} contains an empty item"
        )
    items = tuple(item.strip() for item in raw_items)
    seen: set[str] = set()
    for item in items:
        if item in seen:
            raise InvalidProfileRowError(
                f"Profile row {row_index} field {field!r} contains duplicate item {item}"
            )
        seen.add(item)
    return items


def _validate_source_token_consistency(
    source_token: str,
    buyer_codes: tuple[str, ...],
    languages: tuple[str, ...],
    language_count: int,
    row_index: int,
) -> None:
    if "_" not in source_token:
        raise InvalidProfileRowError(
            f"Profile row {row_index} source_token {source_token!r} has no language token"
        )
    buyer_token, language_token = source_token.rsplit("_", 1)
    if tuple(part.casefold() for part in buyer_token.split()) != tuple(
        code.casefold() for code in buyer_codes
    ):
        raise InvalidProfileRowError(
            f"Profile row {row_index} source_token {source_token!r} does not match buyer_codes"
        )

    count_match = _LANGUAGE_COUNT_TOKEN.search(source_token)
    if count_match:
        declared_count = int(count_match.group("count"))
        if declared_count != language_count:
            raise InvalidProfileRowError(
                f"Profile row {row_index} source_token {source_token!r} declares "
                f"{declared_count} languages but language_count is {language_count}"
            )
    elif language_count == 1 and languages != (language_token,):
        raise InvalidProfileRowError(
            f"Profile row {row_index} source_token {source_token!r} does not match languages"
        )
