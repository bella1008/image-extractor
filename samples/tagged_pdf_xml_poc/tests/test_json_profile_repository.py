from __future__ import annotations

import inspect
import json
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from tagged_pdf_extractor.domain.models import PdfProfile
from tagged_pdf_extractor.infrastructure.json_profile_repository import (
    JsonProfileRepository,
)
from tagged_pdf_extractor.ports.profile_repository import (
    DuplicateSourceTokenError,
    InvalidPdfFilenameError,
    InvalidProfileMappingError,
    InvalidProfileRowError,
    ProfileMappingFileError,
    ProfileRepositoryPort,
    UnknownSourceTokenError,
)


CANONICAL_MAPPING = (
    Path(__file__).resolve().parents[3]
    / "metadata"
    / "pdf_profile_mapping"
    / "pdf_profile_mapping.json"
)
ZC_FILENAME = "BN68-25100B-00_SUG_Y26 TV ALL_ZC_L02_260122.0.pdf"


def test_implements_repository_port_without_language_input() -> None:
    repository = JsonProfileRepository(CANONICAL_MAPPING)

    assert isinstance(repository, ProfileRepositoryPort)
    assert tuple(inspect.signature(repository.lookup).parameters) == ("pdf_path",)


def test_loads_zc_profile_in_exact_canonical_language_order() -> None:
    profile = JsonProfileRepository(CANONICAL_MAPPING).lookup(ZC_FILENAME)

    assert profile == PdfProfile(
        source_token="ZC_L02",
        region="ZC",
        buyer_codes=("ZC",),
        languages=("ENG", "C-FRA"),
        doc_type="A2",
        language_count=2,
    )
    with pytest.raises(FrozenInstanceError):
        profile.doc_type = "BOOK"  # type: ignore[misc]


def test_preserves_canonical_book_data_and_order() -> None:
    filename = "BN68-25448A-00_SUG_Y26 TV ALL_ZG XN ZT_L05_260204.0.pdf"

    profile = JsonProfileRepository(CANONICAL_MAPPING).lookup(filename)

    assert profile.source_token == "ZG XN ZT_L05"
    assert profile.doc_type == "BOOK"
    assert profile.buyer_codes == ("ZG", "XN", "ZT")
    assert profile.languages == ("ENG", "DEU", "FRA", "ITA", "DUT")
    assert profile.language_count == 5


def test_lookup_honors_existing_case_insensitive_filename_convention() -> None:
    filename = "bn68-25100b-00_sug_y26 tv all_zc_l02_260122.12.PDF"

    profile = JsonProfileRepository(CANONICAL_MAPPING).lookup(filename)

    assert profile.source_token == "ZC_L02"


def test_lookup_uses_only_filename_not_folder_or_pdf_language(tmp_path: Path) -> None:
    misleading_folder = tmp_path / "ZX_L02" / "document-lang-DEU"
    misleading_folder.mkdir(parents=True)
    pdf_path = misleading_folder / ZC_FILENAME
    pdf_path.write_bytes(b"%PDF-1.7\n1 0 obj << /Lang (de-DE) >> endobj\n")

    profile = JsonProfileRepository(CANONICAL_MAPPING).lookup(pdf_path)

    assert profile.source_token == "ZC_L02"
    assert profile.languages == ("ENG", "C-FRA")


def test_rejects_malformed_filename_with_typed_error() -> None:
    repository = JsonProfileRepository(CANONICAL_MAPPING)

    with pytest.raises(InvalidPdfFilenameError, match="manual.pdf"):
        repository.lookup("ZC_L02/manual.pdf")


def test_rejects_unknown_filename_token_with_typed_error() -> None:
    repository = JsonProfileRepository(CANONICAL_MAPPING)
    filename = "BN68-00000A-00_SUG_Y26 TV ALL_UNKNOWN_L02_260101.0.pdf"

    with pytest.raises(UnknownSourceTokenError, match="UNKNOWN_L02"):
        repository.lookup(filename)


def _valid_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "source_token": "ZC_L02",
        "region": "ZC",
        "buyer_codes": "ZC",
        "languages": "ENG;C-FRA",
        "doc_type": "A2",
        "language_count": 2,
    }
    row.update(overrides)
    return row


def _write_fixture(path: Path, payload: object) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_requires_existing_readable_mapping_file(tmp_path: Path) -> None:
    with pytest.raises(ProfileMappingFileError, match="profiles.json"):
        JsonProfileRepository(tmp_path / "profiles.json")


def test_rejects_malformed_json(tmp_path: Path) -> None:
    mapping_path = tmp_path / "profiles.json"
    mapping_path.write_text("[{", encoding="utf-8")

    with pytest.raises(InvalidProfileMappingError, match="valid JSON"):
        JsonProfileRepository(mapping_path)


def test_rejects_invalid_utf8(tmp_path: Path) -> None:
    mapping_path = tmp_path / "profiles.json"
    mapping_path.write_bytes(b"[\xff]")

    with pytest.raises(InvalidProfileMappingError, match="valid UTF-8 JSON"):
        JsonProfileRepository(mapping_path)


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"profiles": [_valid_row()]}, "JSON array"),
        ([], "at least one"),
        (["not-a-row"], "row 0.*object"),
        ([_valid_row(languages=None)], "row 0.*languages.*string"),
        (
            [
                {
                    key: value
                    for key, value in _valid_row().items()
                    if key != "region"
                }
            ],
            "row 0.*region",
        ),
        ([_valid_row(wording_rule="forbidden")], "unexpected field 'wording_rule'"),
    ],
)
def test_rejects_malformed_or_missing_rows(
    tmp_path: Path, payload: object, message: str
) -> None:
    mapping_path = _write_fixture(tmp_path / "profiles.json", payload)

    error_type = (
        InvalidProfileMappingError
        if not isinstance(payload, list) or not payload
        else InvalidProfileRowError
    )
    with pytest.raises(error_type, match=message):
        JsonProfileRepository(mapping_path)


def test_rejects_duplicate_source_tokens(tmp_path: Path) -> None:
    mapping_path = _write_fixture(
        tmp_path / "profiles.json", [_valid_row(), _valid_row(region="OTHER")]
    )

    with pytest.raises(DuplicateSourceTokenError, match="ZC_L02.*rows 0 and 1"):
        JsonProfileRepository(mapping_path)


def test_rejects_case_insensitive_duplicate_source_tokens(tmp_path: Path) -> None:
    mapping_path = _write_fixture(
        tmp_path / "profiles.json",
        [_valid_row(), _valid_row(source_token="zc_l02", buyer_codes="zc")],
    )

    with pytest.raises(DuplicateSourceTokenError, match="zc_l02.*rows 0 and 1"):
        JsonProfileRepository(mapping_path)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("source_token", 7),
        ("region", ["ZC"]),
        ("buyer_codes", ["ZC"]),
        ("languages", ["ENG", "C-FRA"]),
        ("doc_type", 2),
        ("language_count", "2"),
        ("language_count", True),
    ],
)
def test_rejects_invalid_field_types(
    tmp_path: Path, field: str, value: object
) -> None:
    mapping_path = _write_fixture(
        tmp_path / "profiles.json", [_valid_row(**{field: value})]
    )

    with pytest.raises(InvalidProfileRowError, match=f"row 0.*{field}"):
        JsonProfileRepository(mapping_path)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"language_count": 3}, "language_count 3 does not match 2 languages"),
        ({"language_count": 0}, "language_count must be positive"),
        ({"languages": "ENG;;C-FRA"}, "languages.*empty item"),
        ({"languages": "ENG;ENG"}, "languages.*duplicate item ENG"),
        (
            {"source_token": "ZC_L05", "language_count": 2},
            "ZC_L05.*declares 5",
        ),
        ({"buyer_codes": "ZX"}, "ZC_L02.*buyer_codes"),
        (
            {
                "source_token": "ZA_ENG",
                "region": "ZA",
                "buyer_codes": "ZA",
                "languages": "FRA",
                "doc_type": "A3",
                "language_count": 1,
            },
            "ZA_ENG.*languages",
        ),
        ({"doc_type": "BROCHURE"}, "doc_type.*A2, A3, or BOOK"),
    ],
)
def test_rejects_internally_inconsistent_rows(
    tmp_path: Path, overrides: dict[str, object], message: str
) -> None:
    mapping_path = _write_fixture(
        tmp_path / "profiles.json", [_valid_row(**overrides)]
    )

    with pytest.raises(InvalidProfileRowError, match=message):
        JsonProfileRepository(mapping_path)
