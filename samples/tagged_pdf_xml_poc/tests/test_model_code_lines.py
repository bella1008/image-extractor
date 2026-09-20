from pathlib import Path

from tagged_pdf_extractor.domain.model_code_lines import annotate_model_code_lines
from tagged_pdf_extractor.domain.models import (
    ContentFragment,
    StructureElement,
    TaggedDocument,
    TextStyle,
)


def fragment(text: str, *, y: float | None, mcid: int) -> ContentFragment:
    bbox = None if y is None else (10.0, y, 100.0, y + 7.0)
    return ContentFragment(
        page_index=0,
        mcid=mcid,
        text_parts=(text,),
        text_styles=(TextStyle("SamsungOne-400", 7.0),),
        text_bboxes=(bbox,),
    )


def element(role: str, *children) -> StructureElement:
    return StructureElement(role, role, children=children)


def model_document(*children: ContentFragment) -> TaggedDocument:
    paragraph = element("paragraph", *children)
    cell = element("table_cell", paragraph)
    return TaggedDocument(
        Path("manual.pdf"),
        True,
        None,
        (),
        (element("table", element("table_row", cell)),),
    )


def target_attributes(document: TaggedDocument) -> dict[str, str]:
    table = document.children[0]
    assert isinstance(table, StructureElement)
    row = table.children[0]
    assert isinstance(row, StructureElement)
    cell = row.children[0]
    assert isinstance(cell, StructureElement)
    paragraph = cell.children[0]
    assert isinstance(paragraph, StructureElement)
    return dict(paragraph.attributes)


def test_marks_multi_baseline_model_only_rows() -> None:
    result = annotate_model_code_lines(
        model_document(
            fragment("QA100QN80HU QA85QN990HU", y=30.0, mcid=1),
            fragment("QA55QN1EHAU QA65QN1EHAU", y=20.0, mcid=2),
            fragment("QA75QN1EHAU QA83S85HAE", y=10.0, mcid=3),
        )
    )

    assert target_attributes(result) == {
        "review-line-layout": "model-code-rows",
        "review-line-break-before-child-indexes": "1,2",
    }


def test_groups_rtl_whitespace_fragments_on_the_same_baseline() -> None:
    result = annotate_model_code_lines(
        model_document(
            fragment("\n ", y=30.0, mcid=1),
            fragment("QA100QN80HU QA85QN990HU", y=30.0, mcid=2),
            fragment("\n ", y=20.0, mcid=3),
            fragment("QA55QN1EHAU QA65QN1EHAU", y=20.0, mcid=4),
            fragment("\n)", y=10.0, mcid=5),
            fragment("MRA85R95HAU", y=10.0, mcid=6),
        )
    )

    assert target_attributes(result)["review-line-break-before-child-indexes"] == "2,4"


def test_rejects_prose_or_measurements() -> None:
    source = model_document(
        fragment("QA100QN80HU QA85QN990HU", y=20.0, mcid=1),
        fragment("Width 122.4 cm", y=10.0, mcid=2),
    )

    assert annotate_model_code_lines(source) is source


def test_rejects_incomplete_geometry() -> None:
    source = model_document(
        fragment("QA100QN80HU", y=20.0, mcid=1),
        fragment("QA85QN990HU", y=None, mcid=2),
    )

    assert annotate_model_code_lines(source) is source
