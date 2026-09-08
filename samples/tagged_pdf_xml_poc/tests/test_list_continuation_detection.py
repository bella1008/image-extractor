from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
import math
from pathlib import Path

import pytest

from tagged_pdf_extractor.domain.list_continuation_detection import (
    detect_list_continuation_hints,
)
from tagged_pdf_extractor.domain.models import (
    ContentFragment,
    ContinuationHint,
    ContinuationTypographyEvidence,
    StructureElement,
    TaggedDocument,
    TextStyle,
)


def _fragment(
    text: str,
    *,
    page_index: int,
    mcid: int,
    bbox: tuple[float, float, float, float] | None,
    font_name: str = "Body-Regular",
    font_size: float = 8.0,
) -> ContentFragment:
    return ContentFragment(
        page_index,
        mcid,
        (text,),
        text_styles=(TextStyle(font_name, font_size),),
        text_bboxes=(bbox,),
    )


def _list(
    *,
    page_index: int,
    marker_mcid: int,
    body_mcid: int,
    marker_bbox: tuple[float, float, float, float] | None,
    body_bboxes: tuple[tuple[float, float, float, float] | None, ...],
) -> StructureElement:
    marker = StructureElement(
        "Lbl",
        "label",
        children=(
            _fragment(
                "•",
                page_index=page_index,
                mcid=marker_mcid,
                bbox=marker_bbox,
            ),
        ),
    )
    body = StructureElement(
        "LBody",
        "list_body",
        children=tuple(
            _fragment(
                f"List body line {index}",
                page_index=page_index,
                mcid=body_mcid + index,
                bbox=bbox,
            )
            for index, bbox in enumerate(body_bboxes)
        ),
    )
    item = StructureElement("LI", "list_item", children=(marker, body))
    return StructureElement("L", "list", children=(item,))


def _document(
    *,
    target_text: str = "Continuation text",
    target_bbox: tuple[float, float, float, float] | None = (
        100.0,
        176.0,
        180.0,
        184.0,
    ),
    target_page: int = 0,
    target_language: str | None = None,
    target_source_role: str = "LBody",
    target_font_name: str = "Body-Regular",
    target_font_size: float = 8.0,
    preceding_marker_bbox: tuple[float, float, float, float] | None = (
        88.0,
        200.0,
        96.0,
        208.0,
    ),
    preceding_body_bboxes: tuple[
        tuple[float, float, float, float] | None, ...
    ] = (
        (100.0, 200.0, 180.0, 208.0),
        (100.0, 188.0, 180.0, 196.0),
    ),
    following_page: int = 0,
    section: bool = True,
    role_map: tuple[tuple[str, str], ...] = (),
) -> TaggedDocument:
    preceding = _list(
        page_index=0,
        marker_mcid=10,
        body_mcid=11,
        marker_bbox=preceding_marker_bbox,
        body_bboxes=preceding_body_bboxes,
    )
    target = StructureElement(
        target_source_role,
        "paragraph",
        page_index=target_page,
        language=target_language,
        children=(
            _fragment(
                target_text,
                page_index=target_page,
                mcid=20,
                bbox=target_bbox,
                font_name=target_font_name,
                font_size=target_font_size,
            ),
        ),
    )
    following = _list(
        page_index=following_page,
        marker_mcid=30,
        body_mcid=31,
        marker_bbox=(88.0, 164.0, 96.0, 172.0),
        body_bboxes=((100.0, 164.0, 180.0, 172.0),),
    )
    siblings = (preceding, target, following)
    children = (
        StructureElement("Sect", "section", language="en", children=siblings),
    ) if section else siblings
    return TaggedDocument(Path("manual.pdf"), True, "en", role_map, children)


def test_detects_evidenced_list_continuation_and_preserves_source() -> None:
    source = _document()
    original_children = source.children

    hints = detect_list_continuation_hints(source)

    assert hints == (
        ContinuationHint(
            child_path=(0, 1),
            preceding_list_item_path=(0, 0, 0),
            preceding_list_body_path=(0, 0, 0, 1),
            page_index=0,
            paragraph_bbox=(100.0, 176.0, 180.0, 184.0),
            list_body_bbox=(100.0, 188.0, 180.0, 208.0),
            left_delta=0.0,
            vertical_gap=4.0,
            reference_font_size=8.0,
            source_role="LBody",
            typography_evidence=ContinuationTypographyEvidence(
                preceding_body_font_weight=400,
                preceding_body_font_size=8.0,
                preceding_body_observed_lines=((0, 11), (0, 12)),
                target_font_weight=400,
                target_font_size=8.0,
                target_observed_lines=((0, 20),),
            ),
        ),
    )
    assert source.children is original_children
    with pytest.raises(FrozenInstanceError):
        hints[0].vertical_gap = 0.0  # type: ignore[misc]


def test_sibling_topology_without_complete_geometry_returns_no_hint() -> None:
    source = _document(
        target_bbox=None,
        preceding_marker_bbox=None,
        preceding_body_bboxes=(None, None),
    )

    assert detect_list_continuation_hints(source) == ()


@pytest.mark.parametrize(
    "target_text",
    (
        "• Bullet text",
        "-",
        "- Hyphen bullet text",
        "*",
        "* Asterisk bullet text",
        "2. Numbered text",
        "2.Numbered text",
        "01 Heading text",
        "## Heading text",
    ),
    ids=(
        "bullet",
        "bare-hyphen",
        "hyphen",
        "bare-asterisk",
        "asterisk",
        "numeric",
        "compact-numeric",
        "numbered-heading",
        "markdown-heading",
    ),
)
def test_visible_marker_returns_no_hint(target_text: str) -> None:
    assert detect_list_continuation_hints(_document(target_text=target_text)) == ()


def test_wrong_sibling_topology_returns_no_hint() -> None:
    source = _document()
    section = source.children[0]
    assert isinstance(section, StructureElement)
    preceding = StructureElement(
        "P",
        "paragraph",
        children=(
            _fragment(
                "Not a list",
                page_index=0,
                mcid=9,
                bbox=(100.0, 200.0, 180.0, 208.0),
            ),
        ),
    )
    wrong_topology = replace(
        source,
        children=(
            replace(
                section,
                children=(preceding, section.children[1], section.children[2]),
            ),
        ),
    )

    assert detect_list_continuation_hints(wrong_topology) == ()


def test_non_list_associated_target_source_role_returns_no_hint() -> None:
    source = _document(target_source_role="P")

    assert detect_list_continuation_hints(source) == ()


def test_role_map_alias_resolving_to_list_body_returns_hint() -> None:
    source = _document(
        target_source_role="CustomListBody",
        role_map=(("CustomListBody", "LBody"),),
    )

    hints = detect_list_continuation_hints(source)

    assert len(hints) == 1
    assert hints[0].source_role == "CustomListBody"


def test_different_page_returns_no_hint() -> None:
    assert detect_list_continuation_hints(_document(target_page=1)) == ()


def test_different_language_context_returns_no_hint() -> None:
    assert detect_list_continuation_hints(_document(target_language="fr")) == ()


def test_missing_section_context_returns_no_hint() -> None:
    assert detect_list_continuation_hints(_document(section=False)) == ()


def test_typography_tier_mismatch_returns_no_hint() -> None:
    source = _document(target_font_name="Body-Bold", target_font_size=9.0)

    assert detect_list_continuation_hints(source) == ()


def test_alignment_with_list_marker_instead_of_body_returns_no_hint() -> None:
    source = _document(target_bbox=(88.0, 176.0, 168.0, 184.0))

    assert detect_list_continuation_hints(source) == ()


def test_alignment_with_neither_list_body_nor_marker_returns_no_hint() -> None:
    source = _document(target_bbox=(94.0, 176.0, 174.0, 184.0))

    assert detect_list_continuation_hints(source) == ()


@pytest.mark.parametrize(
    "target_bbox",
    (
        (100.0, 160.0, 180.0, 168.0),
        (100.0, 184.0, 180.0, 192.0),
    ),
    ids=("excessive", "negative"),
)
def test_inconsistent_vertical_gap_returns_no_hint(
    target_bbox: tuple[float, float, float, float],
) -> None:
    assert detect_list_continuation_hints(_document(target_bbox=target_bbox)) == ()


@pytest.mark.parametrize(
    "target_bbox",
    (
        (100.0, 176.0, math.nan, 184.0),
        (100.0, 176.0, 90.0, 184.0),
    ),
    ids=("nonfinite", "not_normalized"),
)
def test_invalid_geometry_returns_no_hint(
    target_bbox: tuple[float, float, float, float],
) -> None:
    assert detect_list_continuation_hints(_document(target_bbox=target_bbox)) == ()


def test_multi_page_geometry_returns_no_hint() -> None:
    source = _document()
    section = source.children[0]
    assert isinstance(section, StructureElement)
    target = section.children[1]
    assert isinstance(target, StructureElement)
    fragment = target.children[0]
    assert isinstance(fragment, ContentFragment)
    multi_page_target = replace(
        target,
        children=(
            fragment,
            _fragment(
                "Other page",
                page_index=1,
                mcid=21,
                bbox=(100.0, 176.0, 150.0, 184.0),
            ),
        ),
    )
    changed = replace(
        source,
        children=(
            replace(
                section,
                children=(section.children[0], multi_page_target, section.children[2]),
            ),
        ),
    )

    assert detect_list_continuation_hints(changed) == ()


@pytest.mark.parametrize(
    "conflict_name",
    (
        "heading_paths",
        "promotion_paths",
        "subtitle_paths",
        "strong_label_paths",
        "existing_continuation_paths",
    ),
)
def test_conflict_path_returns_no_hint(conflict_name: str) -> None:
    conflicts = {conflict_name: ((0, 1),)}

    assert detect_list_continuation_hints(_document(), **conflicts) == ()
