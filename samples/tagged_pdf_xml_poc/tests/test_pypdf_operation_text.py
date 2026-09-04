from io import BytesIO
import traceback
from types import SimpleNamespace

import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    ArrayObject,
    ContentStream,
    DecodedStreamObject,
    DictionaryObject,
    IndirectObject,
    NameObject,
    NullObject,
    NumberObject,
)

import tagged_pdf_extractor.infrastructure.pypdf_operation_text as operation_module
from tagged_pdf_extractor.infrastructure.pypdf_operation_text import (
    PypdfOperationTextError,
    PypdfOperationTextRunner,
)


class CallbackError(RuntimeError):
    pass


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


def _blank_in_memory_page(*, null_contents: bool = False):
    writer = PdfWriter()
    page = writer.add_blank_page(width=100, height=100)
    page[NameObject("/Resources")] = _font_resources()
    if null_contents:
        page[NameObject("/Contents")] = NullObject()
    output = BytesIO()
    writer.write(output)
    output.seek(0)
    return PdfReader(output).pages[0]


def test_runner_constructs_forced_bytes_content_stream_from_direct_raw_stream(
    monkeypatch,
) -> None:
    page = _in_memory_page(b"BT /F1 12 Tf [(Premiere) -120 (phrase)] TJ ET")
    source = page["/Contents"].get_object()
    source_bytes = source.get_data()
    source_items = dict(source.items())
    constructions: list[tuple[object, object, object]] = []

    real_import_module = operation_module.import_module
    generic_module = real_import_module("pypdf.generic")
    real_content_stream = generic_module.ContentStream

    class RecordingContentStream(real_content_stream):
        def __init__(self, stream, pdf, forced_encoding=None):
            constructions.append((stream, pdf, forced_encoding))
            super().__init__(stream, pdf, forced_encoding)

    def import_with_recording(module_name: str):
        if module_name == "pypdf.generic":
            return SimpleNamespace(
                ContentStream=RecordingContentStream,
                NullObject=generic_module.NullObject,
            )
        return real_import_module(module_name)

    monkeypatch.setattr(operation_module, "import_module", import_with_recording)

    PypdfOperationTextRunner().run(
        page,
        on_boundary=lambda _operator, _operands: None,
        on_text=lambda _value: None,
    )

    assert constructions == [(source, page.pdf, "bytes")]
    assert source.get_data() == source_bytes
    assert dict(source.items()) == source_items


def test_runner_constructs_forced_bytes_content_stream_from_stream_array(
    monkeypatch,
) -> None:
    writer = PdfWriter()
    page = writer.add_blank_page(width=100, height=100)
    page[NameObject("/Resources")] = _font_resources()
    first = DecodedStreamObject()
    first.set_data(b"BT /F1 12 Tf (First) Tj")
    second = DecodedStreamObject()
    second.set_data(b"(Second) Tj ET")
    page[NameObject("/Contents")] = ArrayObject(
        [writer._add_object(first), writer._add_object(second)]
    )
    output = BytesIO()
    writer.write(output)
    output.seek(0)
    page = PdfReader(output).pages[0]
    source = page["/Contents"].get_object()
    source_bytes = tuple(item.get_object().get_data() for item in source)
    constructions: list[tuple[object, object, object]] = []

    real_import_module = operation_module.import_module
    generic_module = real_import_module("pypdf.generic")
    real_content_stream = generic_module.ContentStream

    class RecordingContentStream(real_content_stream):
        def __init__(self, stream, pdf, forced_encoding=None):
            constructions.append((stream, pdf, forced_encoding))
            super().__init__(stream, pdf, forced_encoding)

    def import_with_recording(module_name: str):
        if module_name == "pypdf.generic":
            return SimpleNamespace(
                ContentStream=RecordingContentStream,
                NullObject=generic_module.NullObject,
            )
        return real_import_module(module_name)

    monkeypatch.setattr(operation_module, "import_module", import_with_recording)
    captured: list[str] = []

    PypdfOperationTextRunner().run(
        page,
        on_boundary=lambda _operator, _operands: None,
        on_text=captured.append,
    )

    assert constructions == [(source, page.pdf, "bytes")]
    assert tuple(item.get_object().get_data() for item in source) == source_bytes
    assert "FirstSecond" in "".join(captured)


def test_runner_reuses_existing_content_stream_without_mutating_cached_state() -> None:
    page = _in_memory_page(b"BT /F1 12 Tf (Existing) Tj ET")
    raw_source = page["/Contents"].get_object()

    class ObservedContentStream(ContentStream):
        def __init__(self, stream, pdf, forced_encoding=None):
            self.operation_reads = 0
            super().__init__(stream, pdf, forced_encoding)

        @property
        def operations(self):
            self.operation_reads += 1
            return ContentStream.operations.fget(self)

    existing = ObservedContentStream(raw_source, page.pdf, "bytes")
    expected_operations = repr(existing.operations)
    existing.operation_reads = 0
    expected_data = existing._data
    page[NameObject("/Contents")] = existing
    captured: list[str] = []

    PypdfOperationTextRunner().run(
        page,
        on_boundary=lambda _operator, _operands: None,
        on_text=captured.append,
    )

    assert existing.operation_reads == 1
    assert repr(existing.operations) == expected_operations
    assert existing._data == expected_data
    assert "".join(captured) == "Existing"


def test_runner_treats_an_empty_content_stream_as_no_text() -> None:
    page = _in_memory_page(b"")
    boundaries: list[tuple[bytes, list[object]]] = []
    text: list[str] = []

    PypdfOperationTextRunner().run(
        page,
        on_boundary=lambda operator, operands: boundaries.append(
            (operator, operands)
        ),
        on_text=text.append,
    )

    assert boundaries == []
    assert text == []


def test_runner_treats_page_without_contents_or_resources_as_no_text() -> None:
    writer = PdfWriter()
    page = writer.add_blank_page(width=100, height=100)
    del page[NameObject("/Resources")]
    output = BytesIO()
    writer.write(output)
    output.seek(0)
    page = PdfReader(output).pages[0]
    boundaries: list[tuple[bytes, list[object]]] = []
    text: list[str] = []

    assert "/Contents" not in page
    assert "/Resources" not in page

    PypdfOperationTextRunner().run(
        page,
        on_boundary=lambda operator, operands: boundaries.append(
            (operator, operands)
        ),
        on_text=text.append,
    )

    assert boundaries == []
    assert text == []


def test_runner_rejects_non_empty_page_without_resources() -> None:
    writer = PdfWriter()
    page = writer.add_blank_page(width=100, height=100)
    del page[NameObject("/Resources")]
    content = DecodedStreamObject()
    content.set_data(b"BT (Text) Tj ET")
    page[NameObject("/Contents")] = writer._add_object(content)
    output = BytesIO()
    writer.write(output)
    output.seek(0)
    page = PdfReader(output).pages[0]

    with pytest.raises(PypdfOperationTextError) as raised:
        PypdfOperationTextRunner().run(
            page,
            on_boundary=lambda _operator, _operands: None,
            on_text=lambda _value: None,
        )

    assert isinstance(raised.value.__cause__, KeyError)


@pytest.mark.parametrize("null_contents", [False, True])
def test_runner_treats_absent_or_null_content_as_no_text(
    null_contents: bool,
) -> None:
    page = _blank_in_memory_page(null_contents=null_contents)
    boundaries: list[tuple[bytes, list[object]]] = []
    text: list[str] = []

    PypdfOperationTextRunner().run(
        page,
        on_boundary=lambda operator, operands: boundaries.append(
            (operator, operands)
        ),
        on_text=text.append,
    )

    assert boundaries == []
    assert text == []


def test_runner_treats_indirect_null_content_as_no_text() -> None:
    writer = PdfWriter()
    page = writer.add_blank_page(width=100, height=100)
    page[NameObject("/Resources")] = _font_resources()
    page[NameObject("/Contents")] = writer._add_object(NullObject())
    output = BytesIO()
    writer.write(output)
    output.seek(0)
    page = PdfReader(output).pages[0]
    boundaries: list[tuple[bytes, list[object]]] = []
    text: list[str] = []

    assert isinstance(page.raw_get("/Contents"), IndirectObject)

    PypdfOperationTextRunner().run(
        page,
        on_boundary=lambda operator, operands: boundaries.append(
            (operator, operands)
        ),
        on_text=text.append,
    )

    assert boundaries == []
    assert text == []


def test_runner_wraps_malformed_content_with_the_original_cause() -> None:
    page = _in_memory_page(b"")
    page[NameObject("/Contents")] = NumberObject(7)

    with pytest.raises(PypdfOperationTextError) as raised:
        PypdfOperationTextRunner().run(
            page,
            on_boundary=lambda _operator, _operands: None,
            on_text=lambda _value: None,
        )

    assert raised.value.__cause__ is not None


def test_runner_flushes_before_mcid_boundaries_without_synthetic_cm(
    monkeypatch,
) -> None:
    source_page = _in_memory_page(
        b"BT /F1 12 Tf "
        b"/P << /MCID 2 >> BDC (First) Tj EMC "
        b"/P << /MCID 3 >> BDC (Deuxieme) Tj EMC ET"
    )
    content = ContentStream(
        source_page["/Contents"].get_object(), source_page.pdf, "bytes"
    )
    original = tuple(content.operations)
    original_operations = repr(content.operations)
    original_data = content._data
    source_page[NameObject("/Contents")] = content
    processed: list[bytes] = []
    active: list[int | None] = []
    captured: dict[int, list[str]] = {}

    from pypdf._text_extraction._text_extractor import TextExtraction

    original_process_operation = TextExtraction.process_operation

    def process_operation(self, operator: bytes, operands: list[object]) -> None:
        processed.append(operator)
        original_process_operation(self, operator, operands)

    monkeypatch.setattr(TextExtraction, "process_operation", process_operation)

    def boundary(operator: bytes, operands: list[object]) -> None:
        if operator == b"BDC":
            active.append(int(operands[1]["/MCID"]))
        elif operator == b"EMC":
            active.pop()

    def text(value: str) -> None:
        if value and active and active[-1] is not None:
            captured.setdefault(active[-1], []).append(value)

    PypdfOperationTextRunner().run(
        source_page, on_boundary=boundary, on_text=text
    )

    assert {key: "".join(parts) for key, parts in captured.items()} == {
        2: "First",
        3: "Deuxieme",
    }
    assert tuple(content.operations) == original
    assert repr(content.operations) == original_operations
    assert content._data == original_data
    assert all(operator != b"cm" for _, operator in original)
    assert b"cm" not in processed


def test_runner_preserves_explicit_word_spacing_from_tj_array() -> None:
    page = _in_memory_page(b"BT /F1 12 Tf [(First) -600 (Second)] TJ ET")
    captured: list[str] = []

    PypdfOperationTextRunner().run(
        page, on_boundary=lambda _operator, _operands: None, on_text=captured.append
    )

    assert "".join(captured) == "First Second"


def test_runner_uses_pypdf_space_width_fallback_for_font_without_widths() -> None:
    page = _in_memory_page(b"BT /F1 12 Tf [(First) -110 (Second)] TJ ET")
    font = page["/Resources"]["/Font"]["/F1"].get_object()
    font[NameObject("/BaseFont")] = NameObject("/UnlistedFont")
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
        b"/P << /MCID 6 >> BDC BT /F1 12 Tf (Before form) Tj /Fm0 Do ET EMC",
        form_data=b"BT /F1 12 Tf (Form text) Tj ET",
    )
    active: list[int] = []
    captured: list[str] = []
    xobjects: list[tuple[int, str]] = []
    events: list[tuple[str, str]] = []

    def boundary(operator: bytes, operands: list[object]) -> None:
        if operator == b"BDC":
            active.append(int(operands[1]["/MCID"]))
        elif operator == b"EMC":
            active.pop()

    def xobject(operand: object) -> None:
        xobjects.append((active[-1], str(operand)))
        events.append(("xobject", str(operand)))

    def text(value: str) -> None:
        captured.append(value)
        events.append(("text", value))

    PypdfOperationTextRunner().run(
        page,
        on_boundary=boundary,
        on_text=text,
        on_xobject=xobject,
    )

    assert xobjects == [(6, "/Fm0")]
    assert events[:2] == [("text", "Before form"), ("xobject", "/Fm0")]
    assert "Form text" not in "".join(captured)


def test_runner_resolves_inherited_resources_with_indirect_font() -> None:
    writer = PdfWriter()
    page = writer.add_blank_page(width=100, height=100)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    fonts = DictionaryObject({NameObject("/F1"): writer._add_object(font)})
    resources = DictionaryObject(
        {NameObject("/Font"): writer._add_object(fonts)}
    )
    parent = page["/Parent"].get_object()
    parent[NameObject("/Resources")] = writer._add_object(resources)
    del page["/Resources"]
    content = DecodedStreamObject()
    content.set_data(b"BT /F1 12 Tf (Inherited) Tj ET")
    page[NameObject("/Contents")] = writer._add_object(content)
    output = BytesIO()
    writer.write(output)
    output.seek(0)
    inherited_page = PdfReader(output).pages[0]
    captured: list[str] = []

    PypdfOperationTextRunner().run(
        inherited_page,
        on_boundary=lambda _operator, _operands: None,
        on_text=captured.append,
    )

    assert "".join(captured) == "Inherited"


@pytest.mark.parametrize(
    "content_data",
    [
        b"BT /F1 12 Tf 14 TL (First) Tj (Second) ' ET",
        b'BT /F1 12 Tf 14 TL (First) Tj 0 0 (Second) " ET',
        b"BT /F1 12 Tf (First) Tj 0 -14 TD (Second) Tj ET",
    ],
    ids=["quote", "double_quote", "TD"],
)
def test_runner_shorthand_expansion_matches_pypdf(content_data: bytes) -> None:
    page = _in_memory_page(content_data)
    expected = page.extract_text()
    captured: list[str] = []

    PypdfOperationTextRunner().run(
        page, on_boundary=lambda _operator, _operands: None, on_text=captured.append
    )

    assert "".join(captured) == expected


@pytest.mark.parametrize("callback_name", ["on_text", "on_boundary", "on_xobject"])
def test_runner_propagates_callback_exception_without_internal_context(
    callback_name: str,
) -> None:
    content = {
        "on_text": b"BT /F1 12 Tf (Text) Tj ET",
        "on_boundary": b"/P << /MCID 2 >> BDC EMC",
        "on_xobject": b"/Fm0 Do",
    }[callback_name]
    page = _in_memory_page(
        content, form_data=b"" if callback_name == "on_xobject" else None
    )
    expected = CallbackError(f"{callback_name} failed")

    def fail(*_args: object) -> None:
        raise expected

    callbacks = {
        "on_boundary": fail if callback_name == "on_boundary" else lambda *_: None,
        "on_text": fail if callback_name == "on_text" else lambda *_: None,
        "on_xobject": fail if callback_name == "on_xobject" else None,
    }

    with pytest.raises(CallbackError) as raised:
        PypdfOperationTextRunner().run(page, **callbacks)

    assert raised.value is expected
    assert raised.value.__context__ is None
    assert "_CallbackRaised" not in "".join(
        traceback.format_exception(raised.value)
    )


def test_runner_preserves_explicit_callback_exception_chain() -> None:
    page = _in_memory_page(b"BT /F1 12 Tf (Text) Tj ET")
    original_cause = ValueError("original explicit cause")
    expected = CallbackError("explicit callback failure")

    def on_text(_value: str) -> None:
        try:
            raise original_cause
        except ValueError as cause:
            raise expected from cause

    with pytest.raises(CallbackError) as raised:
        PypdfOperationTextRunner().run(
            page, on_boundary=lambda *_: None, on_text=on_text
        )

    assert raised.value is expected
    assert raised.value.__cause__ is original_cause
    assert raised.value.__context__ is original_cause
    assert raised.value.__suppress_context__ is True
    traceback_names = [
        frame.name for frame in traceback.extract_tb(raised.value.__traceback__)
    ]
    assert traceback_names[-1] == "on_text"
    formatted = "".join(traceback.format_exception(raised.value))
    assert "original explicit cause" in formatted
    assert "explicit callback failure" in formatted
    assert "_CallbackRaised" not in formatted


def test_runner_preserves_implicit_callback_exception_context() -> None:
    page = _in_memory_page(b"/P << /MCID 2 >> BDC EMC")
    original_context = ValueError("original implicit context")
    expected = CallbackError("implicit callback failure")

    def on_boundary(_operator: bytes, _operands: list[object]) -> None:
        try:
            raise original_context
        except ValueError:
            raise expected

    with pytest.raises(CallbackError) as raised:
        PypdfOperationTextRunner().run(
            page, on_boundary=on_boundary, on_text=lambda _value: None
        )

    assert raised.value is expected
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is original_context
    assert raised.value.__suppress_context__ is False
    traceback_names = [
        frame.name for frame in traceback.extract_tb(raised.value.__traceback__)
    ]
    assert traceback_names[-1] == "on_boundary"
    formatted = "".join(traceback.format_exception(raised.value))
    assert "original implicit context" in formatted
    assert "implicit callback failure" in formatted
    assert "_CallbackRaised" not in formatted


@pytest.mark.parametrize("expected", [KeyboardInterrupt(), SystemExit(7)])
def test_runner_propagates_callback_base_exception_unchanged(
    expected: BaseException,
) -> None:
    page = _in_memory_page(b"/P << /MCID 2 >> BDC EMC")

    def interrupt(_operator: bytes, _operands: list[object]) -> None:
        raise expected

    with pytest.raises(type(expected)) as raised:
        PypdfOperationTextRunner().run(
            page, on_boundary=interrupt, on_text=lambda _value: None
        )

    assert raised.value is expected
    assert raised.value.__context__ is None


def test_runner_wraps_missing_private_pypdf_helper_at_run_time(monkeypatch) -> None:
    page = _in_memory_page(b"BT /F1 12 Tf (Text) Tj ET")
    missing = ImportError("pypdf private helper missing")

    def unavailable(_module_name: str):
        raise missing

    monkeypatch.setattr(operation_module, "import_module", unavailable, raising=False)

    with pytest.raises(PypdfOperationTextError) as raised:
        PypdfOperationTextRunner().run(
            page,
            on_boundary=lambda _operator, _operands: None,
            on_text=lambda _value: None,
        )

    assert raised.value.__cause__ is missing
