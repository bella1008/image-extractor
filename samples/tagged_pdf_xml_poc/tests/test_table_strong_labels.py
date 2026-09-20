from pathlib import Path

from tagged_pdf_extractor.domain.models import (
    ContentFragment,
    StructureElement,
    TaggedDocument,
    TextStyle,
)
from tagged_pdf_extractor.domain.table_strong_labels import (
    detect_table_strong_label_hints,
)


def fragment(
    text: str,
    weight: int,
    size: float,
    mcid: int,
    *,
    font_name: str | None = None,
) -> ContentFragment:
    return ContentFragment(
        0,
        mcid,
        (text,),
        text_styles=(TextStyle(font_name or f"Synthetic-{weight}", size),),
    )


def paragraph(text: str, weight: int, size: float, mcid: int) -> StructureElement:
    role = "Description-L-B" if weight > 400 else "Description-L"
    return StructureElement(role, "paragraph", children=(fragment(text, weight, size, mcid),))


def paragraph_with_style(
    text: str,
    weight: int,
    size: float,
    mcid: int,
    *,
    source_role: str,
    font_name: str,
) -> StructureElement:
    return StructureElement(
        source_role,
        "paragraph",
        children=(fragment(text, weight, size, mcid, font_name=font_name),),
    )


def document(*cells: StructureElement) -> TaggedDocument:
    table = StructureElement(
        "Table",
        "table",
        children=(StructureElement("TR", "table_row", children=cells),),
    )
    return TaggedDocument(Path("manual.pdf"), True, None, (), (table,))


def cell(*children: StructureElement) -> StructureElement:
    return StructureElement("TD", "table_cell", children=children)


def test_repeated_bold_label_value_groups_become_common_strong_labels() -> None:
    source = document(
        cell(
            paragraph("Display Resolution", 600, 7.5, 1),
            paragraph("7680 x 4320", 400, 7.0, 2),
            paragraph("Model Name", 600, 7.5, 3),
            paragraph("QA100...", 400, 7.0, 4),
            paragraph("Operating Temperature", 600, 7.5, 5),
            paragraph("10 C to 40 C", 400, 7.0, 6),
        )
    )

    hints = detect_table_strong_label_hints(source)

    assert [hint.child_path for hint in hints] == [
        (0, 0, 0, 0),
        (0, 0, 0, 2),
        (0, 0, 0, 4),
    ]
    assert all(hint.display_role == "strong_label" for hint in hints)
    assert all(hint.reason == "repeated_table_label_value_typography" for hint in hints)


def test_equal_font_size_still_preserves_source_bold_labels() -> None:
    source = document(
        cell(
            paragraph("Label one", 600, 7.0, 1),
            paragraph("Value 100", 400, 7.0, 2),
            paragraph("Label two", 600, 7.0, 3),
            paragraph("Value 200", 400, 7.0, 4),
        )
    )

    assert len(detect_table_strong_label_hints(source)) == 2


def test_single_pair_or_unproven_typography_stays_plain() -> None:
    single_pair = document(
        cell(
            paragraph("Only label", 600, 7.0, 1),
            paragraph("Only value", 400, 7.0, 2),
        )
    )
    same_weight = document(
        cell(
            paragraph("Maybe label", 400, 7.0, 1),
            paragraph("Maybe value", 400, 7.0, 2),
            paragraph("Maybe label two", 400, 7.0, 3),
            paragraph("Maybe value two", 400, 7.0, 4),
        )
    )

    assert detect_table_strong_label_hints(single_pair) == ()
    assert detect_table_strong_label_hints(same_weight) == ()


def test_repeated_text_only_form_rows_are_not_mistaken_for_specifications() -> None:
    text_only = document(
        cell(
            paragraph("Question one", 600, 7.0, 1),
            paragraph("Answer one", 400, 7.0, 2),
            paragraph("Question two", 600, 7.0, 3),
            paragraph("Answer two", 400, 7.0, 4),
        )
    )

    assert detect_table_strong_label_hints(text_only) == ()


def test_repeated_first_column_spec_labels_become_strong_labels() -> None:
    table = StructureElement(
        "Table",
        "table",
        children=(
            StructureElement(
                "TR",
                "table_row",
                children=(
                    cell(paragraph("Display Resolution", 600, 7.5, 1)),
                    cell(paragraph("3840 x 2160", 400, 7.0, 2)),
                    cell(paragraph("7680 x 4320", 400, 7.0, 3)),
                ),
            ),
            StructureElement(
                "TR",
                "table_row",
                children=(
                    cell(
                        paragraph("Dimensions", 600, 7.5, 4),
                        paragraph("Without Stand", 600, 7.5, 5),
                    ),
                    cell(paragraph("100 x 50 x 5 cm", 400, 7.0, 6)),
                    cell(paragraph("120 x 60 x 6 cm", 400, 7.0, 7)),
                ),
            ),
        ),
    )
    source = TaggedDocument(Path("manual.pdf"), True, None, (), (table,))

    hints = detect_table_strong_label_hints(source)

    assert [hint.child_path for hint in hints] == [
        (0, 0, 0, 0),
        (0, 1, 0, 0),
        (0, 1, 0, 1),
    ]


def test_source_bold_role_supports_localized_value_with_incomplete_font_name() -> None:
    source = document(
        cell(
            paragraph_with_style(
                "Localized label one",
                700,
                7.5,
                1,
                source_role="Description-L-B",
                font_name="Tahoma-Bold",
            ),
            paragraph_with_style(
                "Localized value 100",
                400,
                7.0,
                2,
                source_role="Description-L",
                font_name="EmbeddedSubset",
            ),
            paragraph_with_style(
                "Localized label two",
                700,
                7.5,
                3,
                source_role="Description-L-B",
                font_name="Tahoma-Bold",
            ),
            paragraph_with_style(
                "Localized value 200",
                400,
                7.0,
                4,
                source_role="Description-L",
                font_name="EmbeddedSubset",
            ),
        )
    )

    assert len(detect_table_strong_label_hints(source)) == 2
