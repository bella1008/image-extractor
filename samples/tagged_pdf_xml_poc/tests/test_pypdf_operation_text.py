from io import BytesIO

from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    ArrayObject,
    DecodedStreamObject,
    DictionaryObject,
    NameObject,
    NumberObject,
)

from tagged_pdf_extractor.infrastructure.pypdf_operation_text import (
    PypdfOperationTextRunner,
)


def _font_resources() -> DictionaryObject:
    fonts = DictionaryObject()
    for name, base_font in (("/F1", "/Helvetica"), ("/F2", "/Courier")):
        fonts[NameObject(name)] = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject(base_font),
            }
        )
    return DictionaryObject({NameObject("/Font"): fonts})


def _in_memory_page(content_data: bytes, form_data: bytes | None = None):
    writer = PdfWriter()
    page = writer.add_blank_page(width=100, height=100)
    resources = _font_resources()
    if form_data is not None:
        form = DecodedStreamObject()
        form.set_data(form_data)
        form[NameObject("/Type")] = NameObject("/XObject")
        form[NameObject("/Subtype")] = NameObject("/Form")
        form[NameObject("/BBox")] = ArrayObject(
            [NumberObject(0), NumberObject(0), NumberObject(100), NumberObject(100)]
        )
        form[NameObject("/Resources")] = _font_resources()
        resources[NameObject("/XObject")] = DictionaryObject(
            {NameObject("/Fm0"): form}
        )
    page[NameObject("/Resources")] = resources
    content = DecodedStreamObject()
    content.set_data(content_data)
    page[NameObject("/Contents")] = content
    output = BytesIO()
    writer.write(output)
    output.seek(0)
    return PdfReader(output).pages[0]


def test_runner_flushes_before_mcid_boundaries_without_synthetic_cm() -> None:
    page = _in_memory_page(
        b"BT /F1 12 Tf "
        b"/P << /MCID 2 >> BDC (First) Tj EMC "
        b"/P << /MCID 3 >> BDC (Deuxieme) Tj EMC ET"
    )
    original = list(page.get_contents().operations)
    active: list[int | None] = []
    captured: dict[int, list[str]] = {}

    def boundary(operator: bytes, operands: list[object]) -> None:
        if operator == b"BDC":
            active.append(int(operands[1]["/MCID"]))
        elif operator == b"EMC":
            active.pop()

    def text(value: str) -> None:
        if value and active and active[-1] is not None:
            captured.setdefault(active[-1], []).append(value)

    PypdfOperationTextRunner().run(page, on_boundary=boundary, on_text=text)

    assert {key: "".join(parts) for key, parts in captured.items()} == {
        2: "First",
        3: "Deuxieme",
    }
    assert page.get_contents().operations == original
    assert all(operator != b"cm" for _, operator in original)


def test_runner_preserves_explicit_word_spacing_from_tj_array() -> None:
    page = _in_memory_page(b"BT /F1 12 Tf [(First) -600 (Second)] TJ ET")
    captured: list[str] = []

    PypdfOperationTextRunner().run(
        page, on_boundary=lambda _operator, _operands: None, on_text=captured.append
    )

    assert "".join(captured) == "First Second"


def test_runner_flushes_font_change_text_under_current_mcid() -> None:
    page = _in_memory_page(
        b"BT /F1 12 Tf /P << /MCID 4 >> BDC "
        b"(Helvetica) Tj /F2 12 Tf (Courier) Tj EMC ET"
    )
    active: list[int] = []
    captured: dict[int, list[str]] = {}

    def boundary(operator: bytes, operands: list[object]) -> None:
        if operator == b"BDC":
            active.append(int(operands[1]["/MCID"]))
        elif operator == b"EMC":
            active.pop()

    def text(value: str) -> None:
        if value and active:
            captured.setdefault(active[-1], []).append(value)

    PypdfOperationTextRunner().run(page, on_boundary=boundary, on_text=text)

    assert "".join(captured[4]) == "HelveticaCourier"
    assert len(captured[4]) == 2


def test_runner_preserves_text_across_bt_and_et() -> None:
    page = _in_memory_page(
        b"/P << /MCID 5 >> BDC "
        b"BT /F1 12 Tf (First) Tj ET BT /F1 12 Tf (Second) Tj ET "
        b"EMC"
    )
    active: list[int] = []
    captured: dict[int, list[str]] = {}

    def boundary(operator: bytes, operands: list[object]) -> None:
        if operator == b"BDC":
            active.append(int(operands[1]["/MCID"]))
        elif operator == b"EMC":
            active.pop()

    def text(value: str) -> None:
        if value and active:
            captured.setdefault(active[-1], []).append(value)

    PypdfOperationTextRunner().run(page, on_boundary=boundary, on_text=text)

    assert "".join(captured[5]) == "FirstSecond"


def test_runner_reports_do_without_recursing_into_form_xobject() -> None:
    page = _in_memory_page(
        b"/P << /MCID 6 >> BDC /Fm0 Do EMC",
        form_data=b"BT /F1 12 Tf (Form text) Tj ET",
    )
    active: list[int] = []
    captured: list[str] = []
    xobjects: list[tuple[int, str]] = []

    def boundary(operator: bytes, operands: list[object]) -> None:
        if operator == b"BDC":
            active.append(int(operands[1]["/MCID"]))
        elif operator == b"EMC":
            active.pop()

    def xobject(operand: object) -> None:
        xobjects.append((active[-1], str(operand)))

    PypdfOperationTextRunner().run(
        page,
        on_boundary=boundary,
        on_text=captured.append,
        on_xobject=xobject,
    )

    assert xobjects == [(6, "/Fm0")]
    assert "Form text" not in "".join(captured)
