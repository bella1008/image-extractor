from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest

from tagged_pdf_extractor.domain.display_hint_validation import (
    validate_review_formatting_hints,
)
from tagged_pdf_extractor.domain.models import (
    ContentFragment,
    HeadingPromotion,
    LineBreakHint,
    StructureElement,
    SubtitleHint,
    TaggedDocument,
    TextDisplayHint,
)


def _element(
    semantic_role: str,
    *children: StructureElement | ContentFragment,
    source_role: str = "P",
    actual_text: str | None = None,
) -> StructureElement:
    return StructureElement(
        source_role=source_role,
        semantic_role=semantic_role,
        actual_text=actual_text,
        children=children,
    )


def _fragment(text: str) -> ContentFragment:
    return ContentFragment(page_index=0, mcid=1, text_parts=(text,))


def _document(*children: StructureElement | ContentFragment) -> TaggedDocument:
    return TaggedDocument(
        source_path=Path("sample.pdf"),
        marked=True,
        language="ENG",
        role_map=(),
        children=children,
    )


def _line_document() -> tuple[TaggedDocument, tuple[int, ...]]:
    newline = _element("span", source_role="Span", actual_text="\n")
    paragraph = _element(
        "paragraph",
        _fragment("first,"),
        newline,
        _fragment("second"),
    )
    document = _document(
        _element(
            "table",
            _element("table_row", _element("table_cell", paragraph)),
            source_role="Table",
        )
    )
    return replace(document, line_break_hints=(LineBreakHint((0, 0, 0, 0, 1)),)), (
        0,
        0,
        0,
        0,
        1,
    )


def _text_hint(
    path: tuple[int, ...] = (0,),
    *,
    display_role: Any = "section_heading",
    font_weight: Any = 800,
    font_size: Any = 8.0,
    comparison_body_font_weight: Any = 400,
    comparison_body_font_size: Any = 6.5,
) -> TextDisplayHint:
    return TextDisplayHint(
        child_path=path,
        display_role=cast(Any, display_role),
        font_weight=cast(Any, font_weight),
        font_size=cast(Any, font_size),
        comparison_body_font_weight=cast(Any, comparison_body_font_weight),
        comparison_body_font_size=cast(Any, comparison_body_font_size),
        reason="verified structural typography cluster",
    )


def _text_document(
    *,
    target: StructureElement | ContentFragment | None = None,
    hints: tuple[TextDisplayHint, ...] | None = None,
) -> TaggedDocument:
    if target is None:
        target = _element("paragraph", _fragment("Visible title"))
    if hints is None:
        hints = (_text_hint(),)
    return replace(_document(target), text_display_hints=hints)


def _promotion(path: tuple[int, ...]) -> HeadingPromotion:
    return HeadingPromotion(
        child_path=path,
        level=2,
        label="01",
        title="Title",
        series_index=0,
        heading_font_size=10.0,
        body_font_size=6.0,
        font_size_ratio=1.5,
        promotion_reason="test",
    )


def _subtitle(path: tuple[int, ...]) -> SubtitleHint:
    return SubtitleHint(
        child_path=path,
        font_weight=700,
        comparison_body_font_weight=400,
        observed_line_count=1,
    )


def test_returns_read_only_path_lookups_for_valid_hints() -> None:
    line_document, line_path = _line_document()
    title = _element("paragraph", _fragment("Visible title"))
    document = replace(
        line_document,
        children=(*line_document.children, title),
        text_display_hints=(_text_hint((1,)),),
    )

    validated = validate_review_formatting_hints(document)

    assert validated.line_break_by_path[line_path] == document.line_break_hints[0]
    assert validated.text_display_by_path[(1,)] == document.text_display_hints[0]
    with pytest.raises(TypeError):
        validated.line_break_by_path[line_path] = document.line_break_hints[0]  # type: ignore[index]
    with pytest.raises(TypeError):
        validated.text_display_by_path[(1,)] = document.text_display_hints[0]  # type: ignore[index]


@pytest.mark.parametrize(
    "path",
    [(), [0], (True,), (-1,), (0, 1.0), ("0",)],
)
def test_rejects_invalid_exact_tuple_paths(path: Any) -> None:
    document = _text_document(hints=(_text_hint(cast(Any, path)),))

    with pytest.raises(ValueError, match=r"text display hint.*path"):
        validate_review_formatting_hints(document)


@pytest.mark.parametrize("kind", ["line", "text"])
def test_rejects_duplicate_paths_per_hint_kind(kind: str) -> None:
    if kind == "line":
        document, _ = _line_document()
        document = replace(
            document, line_break_hints=document.line_break_hints * 2
        )
    else:
        document = _text_document(hints=(_text_hint(), _text_hint()))

    with pytest.raises(ValueError, match=rf"duplicate {kind}.*path.*\(0"):
        validate_review_formatting_hints(document)


@pytest.mark.parametrize("kind", ["line", "text"])
def test_rejects_unresolved_paths(kind: str) -> None:
    if kind == "line":
        document, _ = _line_document()
        document = replace(document, line_break_hints=(LineBreakHint((9,)),))
    else:
        document = _text_document(hints=(_text_hint((9,)),))

    with pytest.raises(ValueError, match=rf"unresolved {kind}.*path.*\(9,"):
        validate_review_formatting_hints(document)


@pytest.mark.parametrize("kind", ["line", "text"])
def test_rejects_content_fragment_targets(kind: str) -> None:
    if kind == "line":
        document = replace(
            _document(_fragment("text")),
            line_break_hints=(LineBreakHint((0,)),),
        )
    else:
        document = _text_document(
            target=_fragment("text"), hints=(_text_hint((0,)),)
        )

    with pytest.raises(ValueError, match=rf"{kind}.*StructureElement.*\(0,"):
        validate_review_formatting_hints(document)


@pytest.mark.parametrize(
    ("role", "actual_text"),
    [("paragraph", "\n"), ("span", "\r"), ("span", "\r\n"), ("link", None)],
)
def test_line_hint_requires_inline_target_with_exact_newline(
    role: str, actual_text: str | None
) -> None:
    target = _element(role, source_role="Span", actual_text=actual_text)
    paragraph = _element("paragraph", _fragment("first,"), target, _fragment("next"))
    document = replace(
        _document(
            _element("table", _element("table_cell", paragraph), source_role="Table")
        ),
        line_break_hints=(LineBreakHint((0, 0, 0, 1)),),
    )

    with pytest.raises(ValueError, match=r"line break hint.*span/link.*\(0, 0, 0, 1\)"):
        validate_review_formatting_hints(document)


def test_line_hint_requires_paragraph_inside_table_cell() -> None:
    newline = _element("span", source_role="Span", actual_text="\n")
    paragraph = _element("paragraph", _fragment("first,"), newline, _fragment("next"))
    document = replace(
        _document(paragraph), line_break_hints=(LineBreakHint((0, 1)),)
    )

    with pytest.raises(ValueError, match=r"table_cell paragraph.*\(0, 1\)"):
        validate_review_formatting_hints(document)


def test_line_hint_recomputes_detector_evidence_to_block_manual_adjacency_bypass() -> None:
    newline = _element("span", source_role="Span", actual_text="\n")
    paragraph = _element("paragraph", _fragment("missing comma"), newline, _fragment("next"))
    document = replace(
        _document(
            _element("table", _element("table_cell", paragraph), source_role="Table")
        ),
        line_break_hints=(LineBreakHint((0, 0, 0, 1)),),
    )

    with pytest.raises(ValueError, match=r"adjacency evidence.*\(0, 0, 0, 1\)"):
        validate_review_formatting_hints(document)


@pytest.mark.parametrize("role", ["section_heading", "strong_label"])
def test_accepts_each_runtime_text_display_role(role: str) -> None:
    document = _text_document(hints=(_text_hint(display_role=role),))

    validated = validate_review_formatting_hints(document)

    assert validated.text_display_by_path[(0,)].display_role == role


@pytest.mark.parametrize("role", ["heading", "SECTION_HEADING", "", 1, None])
def test_rejects_non_runtime_text_display_roles(role: Any) -> None:
    document = _text_document(hints=(_text_hint(display_role=role),))

    with pytest.raises(ValueError, match=r"text display role.*\(0,"):
        validate_review_formatting_hints(document)


def test_text_display_hint_requires_nonempty_paragraph() -> None:
    document = _text_document(target=_element("paragraph", _fragment("  \n  ")))

    with pytest.raises(ValueError, match=r"nonempty paragraph.*\(0,"):
        validate_review_formatting_hints(document)


def test_text_display_hint_rejects_non_paragraph_target() -> None:
    document = _text_document(target=_element("list_item", _fragment("Visible")))

    with pytest.raises(ValueError, match=r"must target a paragraph.*\(0,"):
        validate_review_formatting_hints(document)


@pytest.mark.parametrize(
    "descendant_role",
    [
        "figure",
        "caption",
        "article",
        "division",
        "paragraph",
        "table",
        "list",
        "section",
    ],
)
def test_text_display_leaf_paragraph_rejects_every_non_inline_descendant(
    descendant_role: str,
) -> None:
    target = _element(
        "paragraph",
        _element(descendant_role, _fragment("Nested visible text")),
    )
    document = _text_document(target=target)

    with pytest.raises(ValueError, match=r"nonempty leaf paragraph.*\(0,"):
        validate_review_formatting_hints(document)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("font_weight", True),
        ("font_weight", 0),
        ("font_size", -1.0),
        ("font_size", float("nan")),
        ("comparison_body_font_weight", float("inf")),
        ("comparison_body_font_size", "6.5"),
    ],
)
def test_rejects_invalid_typography_numbers(field: str, value: Any) -> None:
    hint = replace(_text_hint(), **{field: value})
    document = _text_document(hints=(hint,))

    with pytest.raises(ValueError, match=r"typography.*\(0,"):
        validate_review_formatting_hints(document)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("font_weight", 400),
        ("font_weight", 399),
        ("font_size", 6.5),
        ("font_size", 6.4),
    ],
)
def test_text_display_typography_must_be_strictly_stronger_than_body(
    field: str,
    value: int | float,
) -> None:
    hint = replace(_text_hint(), **{field: value})
    document = _text_document(hints=(hint,))

    with pytest.raises(ValueError, match=r"strictly stronger.*\(0,"):
        validate_review_formatting_hints(document)


def test_rejects_overlapping_text_display_paths() -> None:
    nested = _element("paragraph", _fragment("Nested"))
    outer = _element("paragraph", nested)
    document = _text_document(
        target=outer,
        hints=(_text_hint((0,), display_role="section_heading"), _text_hint((0, 0), display_role="strong_label")),
    )

    with pytest.raises(ValueError, match=r"overlapping text display hint paths.*\(0,\).+\(0, 0\)"):
        validate_review_formatting_hints(document)


@pytest.mark.parametrize("conflict_kind", ["promotion", "subtitle"])
@pytest.mark.parametrize("conflict_path", [(0,), (0, 0), ()])
def test_rejects_equal_ancestor_or_descendant_existing_hint_conflicts(
    conflict_kind: str, conflict_path: tuple[int, ...]
) -> None:
    target = _element("paragraph", _element("span", _fragment("Visible")))
    document = _text_document(target=target)
    if conflict_kind == "promotion":
        document = replace(document, heading_promotions=(_promotion(conflict_path),))
    else:
        document = replace(document, subtitle_hints=(_subtitle(conflict_path),))

    with pytest.raises(ValueError, match=rf"{conflict_kind}.*conflict.*\(0,"):
        validate_review_formatting_hints(document)


@pytest.mark.parametrize("candidate_path", [(0,), (0, 0), ()])
def test_rejects_equal_ancestor_or_descendant_source_heading_candidate_conflicts(
    candidate_path: tuple[int, ...]
) -> None:
    target = _element("paragraph", _element("span", _fragment("Visible")))
    if candidate_path == (0,):
        target = replace(target, source_role="Heading2")
        document = _text_document(target=target)
    elif candidate_path == (0, 0):
        child = replace(cast(StructureElement, target.children[0]), source_role="my-title")
        document = _text_document(target=replace(target, children=(child,)))
    else:
        wrapper = _element("section", target, source_role="Heading")
        document = replace(_document(wrapper), text_display_hints=(_text_hint((0, 0)),))

    with pytest.raises(ValueError, match=r"heading candidate.*conflict"):
        validate_review_formatting_hints(document)


def test_rejects_overlapping_line_and_text_targets() -> None:
    line_document, line_path = _line_document()
    document = replace(
        line_document,
        text_display_hints=(_text_hint(line_path[:-1]),),
    )

    with pytest.raises(ValueError, match=r"line break.*text display.*overlap"):
        validate_review_formatting_hints(document)
