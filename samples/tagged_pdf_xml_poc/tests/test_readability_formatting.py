from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from tagged_pdf_extractor.domain.models import (
    InlineIconHint,
    SentenceBreakHint,
    TaggedDocument,
)


def test_readability_hints_are_frozen_and_document_defaults_are_empty() -> None:
    sentence = SentenceBreakHint(
        child_path=(0, 1, 2),
        offsets=(41, 97),
    )
    icon = InlineIconHint(
        child_path=(0, 1, 3),
        page_index=4,
        bbox=(10.0, 20.0, 19.0, 29.0),
        reference_font_size=6.5,
        width_ratio=9.0 / 6.5,
        height_ratio=9.0 / 6.5,
    )

    assert sentence.child_path == (0, 1, 2)
    assert sentence.offsets == (41, 97)
    assert (
        sentence.reason
        == "conservative_sentence_terminal_in_review_container"
    )
    assert icon.child_path == (0, 1, 3)
    assert icon.page_index == 4
    assert icon.bbox == (10.0, 20.0, 19.0, 29.0)
    assert icon.reference_font_size == 6.5
    assert icon.width_ratio == 9.0 / 6.5
    assert icon.height_ratio == 9.0 / 6.5
    assert icon.reason == "small_inline_figure_with_adjacent_text"

    with pytest.raises(FrozenInstanceError):
        sentence.offsets = ()  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        icon.page_index = 0  # type: ignore[misc]

    document = TaggedDocument(Path("manual.pdf"), True, None, (), ())
    assert document.sentence_break_hints == ()
    assert document.inline_icon_hints == ()
