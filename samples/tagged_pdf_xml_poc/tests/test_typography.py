from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from tagged_pdf_extractor.domain.models import (
    ContentFragment,
    StructureElement,
    TextStyle,
)
from tagged_pdf_extractor.domain.typography import (
    TypographyEvidence,
    normalize_font_weight,
    typography_evidence,
)


def _paragraph(
    *fragments: ContentFragment,
) -> StructureElement:
    return StructureElement("P", "paragraph", children=fragments)


def test_typography_evidence_uses_visible_character_weighted_medians() -> None:
    paragraph = _paragraph(
        ContentFragment(
            2,
            10,
            ("X", "dominant visible text"),
            text_styles=(
                TextStyle("Family-900", 9.0),
                TextStyle("Family-600", 7.0),
            ),
        ),
        ContentFragment(
            2,
            11,
            ("second line",),
            text_styles=(TextStyle("Family-600", 7.0),),
        ),
    )

    assert typography_evidence(paragraph) == TypographyEvidence(
        font_weight=600,
        font_size=7.0,
        observed_lines=frozenset({(2, 10), (2, 11)}),
    )


def test_typography_evidence_is_immutable() -> None:
    evidence = TypographyEvidence(600, 7.0, frozenset({(0, 1)}))

    with pytest.raises(FrozenInstanceError):
        evidence.font_weight = 400  # type: ignore[misc]


def test_whitespace_only_parts_do_not_affect_evidence_or_require_style() -> None:
    paragraph = _paragraph(
        ContentFragment(0, 1, (" \t\n",)),
        ContentFragment(
            0,
            2,
            ("visible",),
            text_styles=(TextStyle("Family-Regular", 6.5),),
        ),
    )

    assert typography_evidence(paragraph) == TypographyEvidence(
        400, 6.5, frozenset({(0, 2)})
    )


@pytest.mark.parametrize(
    "fragment",
    [
        ContentFragment(0, 1, ("visible",)),
        ContentFragment(
            0,
            1,
            ("visible",),
            text_styles=(TextStyle("UnknownTypeface", 6.5),),
        ),
        ContentFragment(
            0,
            1,
            ("visible",),
            text_styles=(TextStyle("Family-600", None),),
        ),
        ContentFragment(
            -1,
            1,
            ("visible",),
            text_styles=(TextStyle("Family-600", 6.5),),
        ),
        ContentFragment(
            0,
            None,
            ("visible",),
            text_styles=(TextStyle("Family-600", 6.5),),
        ),
    ],
)
def test_visible_text_with_incomplete_or_unknown_style_evidence_is_rejected(
    fragment: ContentFragment,
) -> None:
    assert typography_evidence(_paragraph(fragment)) is None


def test_any_unresolved_visible_part_rejects_mixed_evidence() -> None:
    paragraph = _paragraph(
        ContentFragment(
            0,
            1,
            ("known", "unknown"),
            text_styles=(
                TextStyle("Family-600", 7.0),
                TextStyle("Mystery", 7.0),
            ),
        )
    )

    assert typography_evidence(paragraph) is None


def test_no_visible_text_has_no_typography_evidence() -> None:
    assert typography_evidence(_paragraph(ContentFragment(0, 1, ("  ",)))) is None


@pytest.mark.parametrize(
    ("font_name", "expected"),
    [
        ("ABCDEF+SamsungOne-600", 600),
        ("Family-Black", 900),
        ("Family-ExtraBold", 800),
        ("Family-Semibold", 600),
        ("Family_DemiBold", 600),
        ("Family-Bold", 700),
        ("Family-Medium", 500),
        ("Family-Regular", 400),
        ("Family-Normal", 400),
        ("Family-Light", 300),
        ("MysteryBlackbird", None),
        ("NotSemiboldish", None),
        ("Highlight", None),
        ("Family-950", None),
        (None, None),
    ],
)
def test_normalize_font_weight_requires_a_verified_terminal_token(
    font_name: str | None, expected: int | None
) -> None:
    assert normalize_font_weight(font_name) == expected
