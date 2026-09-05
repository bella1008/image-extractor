from pathlib import Path

import pytest

from tagged_pdf_extractor.domain.profile_scope import (
    ProfileScope,
    parse_source_token,
    review_formatting_scope,
)


@pytest.mark.parametrize(
    ("filename", "source_token"),
    [
        (
            "BN68-25448A-00_SUG_Y26 TV ALL_ZG XN ZT_L05_260204.0.pdf",
            "ZG XN ZT_L05",
        ),
        ("BN68-25100B-00_SUG_Y26 TV ALL_ZC_L02_260122.0.pdf", "ZC_L02"),
        ("BN68-25099B-00_SUG_Y26 TV ALL_ZA_ENG_260126.0.pdf", "ZA_ENG"),
        ("BN68-25031B-00_SUG_Y26 TV ALL_XY_ENG_251229.0.pdf", "XY_ENG"),
        ("BN68-25108A-00_SUG_Y26 TV ALL_KR_KOR_251218.0.pdf", "KR_KOR"),
        (
            "bn68-25448a-00_sug_y26 tv all_ZG XN ZT_L05_260204.12.PDF",
            "ZG XN ZT_L05",
        ),
    ],
)
def test_parse_source_token_uses_the_standard_filename_boundary(
    filename: str, source_token: str
) -> None:
    assert parse_source_token(filename) == source_token


@pytest.mark.parametrize(
    "filename",
    [
        "BN68-25448A-00_SUG_Y26 TV ZG XN ZT_L05_260204.0.pdf",
        "BN68-25448A-00_SUG_Y26 TV ALL_ZG XN ZT_L05_20260204.0.pdf",
        "BN68-25448A-00_SUG_Y26 TV ALL_ZG XN ZT_L05_260204.pdf",
        "BN68-25448A-00_SUG_Y26 TV ALL__260204.0.pdf",
        "BN68-25448A-00_SUG_Y26 TV ALL_ZG XN ZT_L05_260204.0.pdf.backup",
        "prefix_BN68-25448A-00_SUG_Y26 TV ALL_ZG XN ZT_L05_260204.0.pdf_suffix",
    ],
)
def test_parse_source_token_rejects_malformed_or_unanchored_names(
    filename: str,
) -> None:
    assert parse_source_token(filename) is None


def test_only_verified_zg_book_source_token_enables_formatting() -> None:
    assert review_formatting_scope(
        Path("BN68-25448A-00_SUG_Y26 TV ALL_ZG XN ZT_L05_260204.0.pdf")
    ) == ProfileScope("ZG XN ZT_L05", "BOOK", True)

    for filename in (
        "BN68-25100B-00_SUG_Y26 TV ALL_ZC_L02_260122.0.pdf",
        "BN68-25099B-00_SUG_Y26 TV ALL_ZA_ENG_260126.0.pdf",
        "BN68-25031B-00_SUG_Y26 TV ALL_XY_ENG_251229.0.pdf",
        "BN68-25108A-00_SUG_Y26 TV ALL_KR_KOR_251218.0.pdf",
    ):
        scope = review_formatting_scope(Path(filename))
        assert scope.source_token is not None
        assert scope.doc_type is None
        assert not scope.enabled


def test_verified_source_token_dispatch_is_case_insensitive() -> None:
    assert review_formatting_scope(
        Path("bn68-25448a-00_sug_y26 tv all_zg xn zt_l05_260204.0.PDF")
    ) == ProfileScope("zg xn zt_l05", "BOOK", True)


def test_parent_folder_names_cannot_enable_or_disable_formatting() -> None:
    enabled = review_formatting_scope(
        Path("XY/TV_KR/BN68-25448A-00_SUG_Y26 TV ALL_ZG XN ZT_L05_260204.0.pdf")
    )
    disabled = review_formatting_scope(
        Path("ZG XN ZT_L05/BOOK/BN68-25031B-00_SUG_Y26 TV ALL_XY_ENG_251229.0.pdf")
    )

    assert enabled == ProfileScope("ZG XN ZT_L05", "BOOK", True)
    assert disabled == ProfileScope("XY_ENG", None, False)


def test_malformed_filename_returns_a_fully_disabled_scope() -> None:
    assert review_formatting_scope(Path("ZG XN ZT_L05/manual.pdf")) == ProfileScope(
        None, None, False
    )
