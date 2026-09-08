from __future__ import annotations

import inspect
import json
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

from domain.models import PdfProfile
from infrastructure.json_profile_repository import JsonProfileRepository
from ports.profile_repository import (
    DuplicateSourceTokenError,
    InvalidProfileMappingError,
    InvalidProfileRowError,
    ProfileMappingFileError,
    ProfileRepositoryPort,
    UnknownSourceTokenError,
)
from src.filename_parser import FilenameParseError


CANONICAL_MAPPING = (
    Path(__file__).resolve().parents[1]
    / "metadata"
    / "pdf_profile_mapping"
    / "pdf_profile_mapping.json"
)
ZC_FILENAME = "BN68-25100B-00_SUG_Y26 TV ALL_ZC_L02_260122.0.pdf"


class JsonProfileRepositoryContractTests(unittest.TestCase):
    def test_implements_repository_port(self) -> None:
        repository = JsonProfileRepository(CANONICAL_MAPPING)

        self.assertIsInstance(repository, ProfileRepositoryPort)
        self.assertEqual(tuple(inspect.signature(repository.lookup).parameters), ("pdf_path",))

    def test_loads_zc_profile_in_exact_canonical_language_order(self) -> None:
        profile = JsonProfileRepository(CANONICAL_MAPPING).lookup(ZC_FILENAME)

        self.assertEqual(
            profile,
            PdfProfile(
                source_token="ZC_L02",
                region="ZC",
                buyer_codes=("ZC",),
                languages=("ENG", "C-FRA"),
                doc_type="A2",
                language_count=2,
            ),
        )
        with self.assertRaises(FrozenInstanceError):
            profile.doc_type = "BOOK"  # type: ignore[misc]

    def test_preserves_canonical_book_data_and_order(self) -> None:
        filename = "BN68-25448A-00_SUG_Y26 TV ALL_ZG XN ZT_L05_260708.0.pdf"

        profile = JsonProfileRepository(CANONICAL_MAPPING).lookup(filename)

        self.assertEqual(profile.source_token, "ZG XN ZT_L05")
        self.assertEqual(profile.doc_type, "BOOK")
        self.assertEqual(profile.buyer_codes, ("ZG", "XN", "ZT"))
        self.assertEqual(profile.languages, ("ENG", "DEU", "FRA", "ITA", "DUT"))
        self.assertEqual(profile.language_count, 5)

    def test_lookup_uses_only_filename_not_folder_or_pdf_language(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            misleading_folder = Path(temp_dir) / "ZX_L02" / "document-lang-DEU"
            misleading_folder.mkdir(parents=True)
            pdf_path = misleading_folder / ZC_FILENAME
            pdf_path.write_bytes(b"%PDF-1.7\n1 0 obj << /Lang (de-DE) >> endobj\n")

            profile = JsonProfileRepository(CANONICAL_MAPPING).lookup(pdf_path)

        self.assertEqual(profile.source_token, "ZC_L02")
        self.assertEqual(profile.languages, ("ENG", "C-FRA"))

    def test_rejects_malformed_filename_with_existing_typed_error(self) -> None:
        repository = JsonProfileRepository(CANONICAL_MAPPING)

        with self.assertRaisesRegex(FilenameParseError, "Expected at least 6"):
            repository.lookup("ZC_L02/manual.pdf")

    def test_rejects_unknown_filename_token_with_typed_error(self) -> None:
        repository = JsonProfileRepository(CANONICAL_MAPPING)
        filename = "BN68-00000A-00_SUG_Y26 TV ALL_UNKNOWN_L02_260101.0.pdf"

        with self.assertRaisesRegex(UnknownSourceTokenError, "UNKNOWN_L02"):
            repository.lookup(filename)


class JsonProfileRepositoryValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp_dir.cleanup)
        self.mapping_path = Path(self._temp_dir.name) / "profiles.json"

    def write_fixture(self, payload: object) -> Path:
        self.mapping_path.write_text(json.dumps(payload), encoding="utf-8")
        return self.mapping_path

    @staticmethod
    def valid_row(**overrides: object) -> dict[str, object]:
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

    def test_requires_existing_readable_mapping_file(self) -> None:
        with self.assertRaisesRegex(ProfileMappingFileError, "profiles.json"):
            JsonProfileRepository(self.mapping_path)

    def test_rejects_malformed_json(self) -> None:
        self.mapping_path.write_text("[{", encoding="utf-8")

        with self.assertRaisesRegex(InvalidProfileMappingError, "valid JSON"):
            JsonProfileRepository(self.mapping_path)

    def test_rejects_invalid_utf8(self) -> None:
        self.mapping_path.write_bytes(b"[\xff]")

        with self.assertRaisesRegex(InvalidProfileMappingError, "valid UTF-8 JSON"):
            JsonProfileRepository(self.mapping_path)

    def test_rejects_non_array_root(self) -> None:
        self.write_fixture({"profiles": [self.valid_row()]})

        with self.assertRaisesRegex(InvalidProfileMappingError, "JSON array"):
            JsonProfileRepository(self.mapping_path)

    def test_rejects_empty_mapping(self) -> None:
        self.write_fixture([])

        with self.assertRaisesRegex(InvalidProfileMappingError, "at least one"):
            JsonProfileRepository(self.mapping_path)

    def test_rejects_non_object_and_missing_field_rows(self) -> None:
        for payload, message in (
            (["not-a-row"], "row 0.*object"),
            ([self.valid_row(languages=None)], "row 0.*languages.*string"),
            (
                [
                    {
                        key: value
                        for key, value in self.valid_row().items()
                        if key != "region"
                    }
                ],
                "row 0.*region",
            ),
        ):
            with self.subTest(payload=payload):
                self.write_fixture(payload)
                with self.assertRaisesRegex(InvalidProfileRowError, message):
                    JsonProfileRepository(self.mapping_path)

    def test_rejects_unexpected_row_fields(self) -> None:
        self.write_fixture([self.valid_row(wording_rule="forbidden")])

        with self.assertRaisesRegex(
            InvalidProfileRowError, "unexpected field 'wording_rule'"
        ):
            JsonProfileRepository(self.mapping_path)

    def test_rejects_duplicate_source_tokens(self) -> None:
        self.write_fixture([self.valid_row(), self.valid_row(region="OTHER")])

        with self.assertRaisesRegex(DuplicateSourceTokenError, "ZC_L02.*rows 0 and 1"):
            JsonProfileRepository(self.mapping_path)

    def test_rejects_invalid_scalar_and_collection_types(self) -> None:
        invalid_values = (
            ("source_token", 7),
            ("region", ["ZC"]),
            ("buyer_codes", ["ZC"]),
            ("languages", ["ENG", "C-FRA"]),
            ("doc_type", 2),
            ("language_count", "2"),
            ("language_count", True),
        )
        for field, value in invalid_values:
            with self.subTest(field=field, value=value):
                self.write_fixture([self.valid_row(**{field: value})])
                with self.assertRaisesRegex(InvalidProfileRowError, f"row 0.*{field}"):
                    JsonProfileRepository(self.mapping_path)

    def test_rejects_invalid_language_count_and_order_encoding(self) -> None:
        invalid_values = (
            ({"language_count": 3}, "language_count 3 does not match 2 languages"),
            ({"language_count": 0}, "language_count must be positive"),
            ({"languages": "ENG;;C-FRA"}, "languages.*empty item"),
            ({"languages": "ENG;ENG"}, "languages.*duplicate item ENG"),
        )
        for overrides, message in invalid_values:
            with self.subTest(overrides=overrides):
                self.write_fixture([self.valid_row(**overrides)])
                with self.assertRaisesRegex(InvalidProfileRowError, message):
                    JsonProfileRepository(self.mapping_path)

    def test_rejects_internally_inconsistent_l_count_token(self) -> None:
        self.write_fixture(
            [self.valid_row(source_token="ZC_L05", language_count=2)]
        )

        with self.assertRaisesRegex(InvalidProfileRowError, "ZC_L05.*declares 5"):
            JsonProfileRepository(self.mapping_path)

    def test_rejects_source_token_that_disagrees_with_buyer_codes(self) -> None:
        self.write_fixture([self.valid_row(buyer_codes="ZX")])

        with self.assertRaisesRegex(InvalidProfileRowError, "ZC_L02.*buyer_codes"):
            JsonProfileRepository(self.mapping_path)

    def test_rejects_single_language_token_that_disagrees_with_languages(self) -> None:
        self.write_fixture(
            [
                self.valid_row(
                    source_token="ZA_ENG",
                    region="ZA",
                    buyer_codes="ZA",
                    languages="FRA",
                    doc_type="A3",
                    language_count=1,
                )
            ]
        )

        with self.assertRaisesRegex(InvalidProfileRowError, "ZA_ENG.*languages"):
            JsonProfileRepository(self.mapping_path)

    def test_rejects_invalid_document_type(self) -> None:
        self.write_fixture([self.valid_row(doc_type="BROCHURE")])

        with self.assertRaisesRegex(InvalidProfileRowError, "doc_type.*A2, A3, or BOOK"):
            JsonProfileRepository(self.mapping_path)


if __name__ == "__main__":
    unittest.main()
