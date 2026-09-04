from io import BytesIO

import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    ArrayObject,
    DecodedStreamObject,
    DictionaryObject,
    NameObject,
    NumberObject,
)

from tagged_pdf_extractor.domain.models import Diagnostic, TextStyle
from tagged_pdf_extractor.infrastructure import mcid_text
from tagged_pdf_extractor.infrastructure.mcid_text import McidTextCollector


class FakeRunner:
    def __init__(self, events: list[tuple[str, object]]) -> None:
        self.events = events

    def run(self, page, *, on_boundary, on_text, on_xobject=None) -> None:
        for kind, value in self.events:
            if kind == "boundary":
                operator, operands = value
                on_boundary(operator, operands)
            elif kind == "text":
                text, font_name, font_size = value
                on_text(text, font_name, font_size)
            elif kind == "xobject" and on_xobject is not None:
                on_xobject(value)


class MalformedMcid:
    def __int__(self) -> int:
        raise ValueError("not an integer")

    def __repr__(self) -> str:
        return "<malformed>"


class IndirectValue:
    def __init__(self, value: object) -> None:
        self.value = value

    def get_object(self) -> object:
        return self.value


class BrokenIndirectValue:
    def get_object(self) -> object:
        raise ValueError("broken indirect object")


def _page_with_xobject(name: object, subtype: object = ...) -> dict:
    xobject = {"/Type": "/XObject"}
    if subtype is not ...:
        xobject["/Subtype"] = subtype
    return {
        "/Resources": IndirectValue(
            {"/XObject": IndirectValue({name: IndirectValue(xobject)})}
        )
    }


def _page_with_inherited_xobject(name: str, subtype: str):
    writer = PdfWriter()
    page = writer.add_blank_page(width=100, height=100)
    del page["/Resources"]

    xobject = DecodedStreamObject()
    xobject.set_data(b"")
    xobject[NameObject("/Type")] = NameObject("/XObject")
    xobject[NameObject("/Subtype")] = NameObject(subtype)
    xobject_reference = writer._add_object(xobject)
    resources = DictionaryObject(
        {
            NameObject("/XObject"): DictionaryObject(
                {NameObject(name): xobject_reference}
            )
        }
    )
    page["/Parent"].get_object()[NameObject("/Resources")] = writer._add_object(
        resources
    )
    return page


def _font_resources() -> DictionaryObject:
    return DictionaryObject(
        {
            NameObject("/Font"): DictionaryObject(
                {
                    NameObject("/F1"): DictionaryObject(
                        {
                            NameObject("/Type"): NameObject("/Font"),
                            NameObject("/Subtype"): NameObject("/Type1"),
                            NameObject("/BaseFont"): NameObject("/Helvetica"),
                        }
                    )
                }
            )
        }
    )


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


def test_collects_text_under_inherited_mcid() -> None:
    runner = FakeRunner(
        [
            ("boundary", (b"BDC", ["/P", {"/MCID": 7}])),
            ("text", ("Settings >", None, None)),
            ("boundary", (b"BDC", ["/Span", {}])),
            ("text", (" General", None, None)),
            ("boundary", (b"EMC", [])),
            ("boundary", (b"EMC", [])),
        ]
    )

    result = McidTextCollector(runner=runner).collect(object(), page_index=0)

    assert result.parts_by_mcid == {7: ("Settings >", " General")}
    assert result.diagnostics == ()


def test_collects_direct_mcid_from_bmc_properties() -> None:
    runner = FakeRunner(
        [
            ("boundary", (b"BMC", ["/P", {"/MCID": 9}])),
            ("text", ("Tagged", None, None)),
            ("boundary", (b"EMC", [])),
        ]
    )

    result = McidTextCollector(runner=runner).collect(object(), page_index=0)

    assert result.parts_by_mcid == {9: ("Tagged",)}
    assert result.diagnostics == ()


def test_records_valid_mcid_even_when_it_has_no_text() -> None:
    runner = FakeRunner(
        [
            ("boundary", (b"BMC", ["/Figure", {"/MCID": 5}])),
            ("boundary", (b"EMC", [])),
            ("boundary", (b"BDC", ["/Span", {"/MCID": 6}])),
            ("boundary", (b"EMC", [])),
        ]
    )

    result = McidTextCollector(runner=runner).collect(object(), page_index=0)

    assert result.parts_by_mcid == {}
    assert result.seen_mcids == frozenset({5, 6})
    assert result.diagnostics == ()


def test_resolves_mcid_from_named_page_property_list() -> None:
    class NamedPropertyPage(dict):
        def __init__(self) -> None:
            super().__init__(
                {
                    NameObject("/Resources"): DictionaryObject(
                        {
                            NameObject("/Properties"): DictionaryObject(
                                {
                                    NameObject("/MC0"): DictionaryObject(
                                        {NameObject("/MCID"): NumberObject(12)}
                                    )
                                }
                            )
                        }
                    )
                }
            )

    page = NamedPropertyPage()
    runner = FakeRunner(
        [
            (
                "boundary",
                (b"BDC", [NameObject("/P"), NameObject("/MC0")]),
            ),
            ("text", ("Resolved", None, None)),
            ("boundary", (b"EMC", [])),
        ]
    )

    result = McidTextCollector(runner=runner).collect(page, page_index=0)

    assert result.parts_by_mcid == {12: ("Resolved",)}
    assert result.diagnostics == ()


def test_collects_real_pypdf_text_before_emc_closes_scope() -> None:
    page = _in_memory_page(
        b"BT /F1 12 Tf /P << /MCID 2 >> BDC (Inside) Tj EMC ET"
    )

    result = McidTextCollector().collect(page, page_index=0)

    assert result.parts_by_mcid == {2: ("Inside",)}
    assert result.diagnostics == ()


def test_collect_does_not_mutate_original_page_content_operations() -> None:
    page = _in_memory_page(
        b"BT /F1 12 Tf /P << /MCID 2 >> BDC (Inside) Tj EMC ET"
    )
    original_operations = list(page.get_contents().operations)

    McidTextCollector().collect(page, page_index=0)

    assert page.get_contents().operations == original_operations
    assert all(operator != b"cm" for _, operator in original_operations)


def _collect_xobject(page: object, operand: object, *, active_mcid: bool = True):
    events: list[tuple[str, object]] = []
    if active_mcid:
        events.append(("boundary", (b"BDC", ["/P", {"/MCID": 4}])))
    events.append(("xobject", operand))
    if active_mcid:
        events.append(("boundary", (b"EMC", [])))
    return McidTextCollector(runner=FakeRunner(events)).collect(page, page_index=6)


def test_ignores_image_xobject_under_active_mcid() -> None:
    result = _collect_xobject(_page_with_xobject("/Im0", "/Image"), "/Im0")

    assert result.diagnostics == ()


def test_reports_form_xobject_under_active_mcid() -> None:
    result = _collect_xobject(_page_with_xobject("/Fm0", "/Form"), "/Fm0")

    assert result.diagnostics == (
        Diagnostic(
            severity="warning",
            code="tagged_form_xobject_unsupported",
            message="Form XObject under tagged content is unsupported",
            context={"page_index": 6, "operand_repr": "'/Fm0'"},
        ),
    )


def test_reports_unresolved_xobject_under_active_mcid() -> None:
    result = _collect_xobject(_page_with_xobject("/Other", "/Image"), "/Missing")

    assert result.diagnostics == (
        Diagnostic(
            severity="warning",
            code="tagged_xobject_unresolved",
            message="Tagged XObject reference could not be resolved",
            context={"page_index": 6, "operand_repr": "'/Missing'"},
        ),
    )


@pytest.mark.parametrize(
    ("subtype", "expected_subtype"),
    [(..., None), ("/PS", "/PS")],
)
def test_reports_unsupported_xobject_subtype_under_active_mcid(
    subtype: object, expected_subtype: str | None
) -> None:
    result = _collect_xobject(_page_with_xobject("/X0", subtype), "/X0")

    assert result.diagnostics == (
        Diagnostic(
            severity="warning",
            code="tagged_xobject_unsupported",
            message="Tagged XObject subtype is unsupported",
            context={
                "page_index": 6,
                "operand_repr": "'/X0'",
                "subtype": expected_subtype,
            },
        ),
    )


def test_reports_broken_indirect_xobject_subtype_as_unresolved() -> None:
    page = _page_with_xobject("/X0", BrokenIndirectValue())

    result = _collect_xobject(page, "/X0")

    assert result.diagnostics == (
        Diagnostic(
            severity="warning",
            code="tagged_xobject_unresolved",
            message="Tagged XObject reference could not be resolved",
            context={"page_index": 6, "operand_repr": "'/X0'"},
        ),
    )


def test_ignores_xobject_without_active_mcid() -> None:
    result = _collect_xobject(
        _page_with_xobject("/Fm0", "/Form"), "/Fm0", active_mcid=False
    )

    assert result.diagnostics == ()


def test_resolves_named_indirect_xobject_resources() -> None:
    result = _collect_xobject(
        _page_with_xobject(NameObject("/Im0"), NameObject("/Image")),
        NameObject("/Im0"),
    )

    assert result.diagnostics == ()


def test_resolves_indirect_image_xobject_from_inherited_page_resources() -> None:
    page = _page_with_inherited_xobject("/Im0", "/Image")

    result = _collect_xobject(page, NameObject("/Im0"))

    assert result.diagnostics == ()


def test_reports_indirect_form_xobject_from_inherited_page_resources() -> None:
    page = _page_with_inherited_xobject("/Fm0", "/Form")

    result = _collect_xobject(page, NameObject("/Fm0"))

    assert result.diagnostics == (
        Diagnostic(
            severity="warning",
            code="tagged_form_xobject_unsupported",
            message="Form XObject under tagged content is unsupported",
            context={"page_index": 6, "operand_repr": "'/Fm0'"},
        ),
    )


def test_malformed_inherited_resources_lookup_is_reported_as_unresolved() -> None:
    class MalformedInheritedPage(dict):
        def get_inherited(self, *, key: str, default: object = None) -> object:
            raise ValueError("broken parent tree")

    result = _collect_xobject(MalformedInheritedPage(), "/Im0")

    assert result.diagnostics == (
        Diagnostic(
            severity="warning",
            code="tagged_xobject_unresolved",
            message="Tagged XObject reference could not be resolved",
            context={"page_index": 6, "operand_repr": "'/Im0'"},
        ),
    )


def test_restores_parent_mcid_after_nested_direct_mcid() -> None:
    runner = FakeRunner(
        [
            ("boundary", (b"BDC", ["/P", {"/MCID": 7}])),
            ("text", ("Parent before", None, None)),
            ("boundary", (b"BDC", ["/Span", {"/MCID": 8}])),
            ("text", ("Child", None, None)),
            ("boundary", (b"EMC", [])),
            ("text", ("Parent after", None, None)),
            ("boundary", (b"EMC", [])),
        ]
    )

    result = McidTextCollector(runner=runner).collect(object(), page_index=0)

    assert result.parts_by_mcid == {
        7: ("Parent before", "Parent after"),
        8: ("Child",),
    }
    assert result.diagnostics == ()


@pytest.mark.parametrize(
    ("invalid_mcid", "value_type", "value_repr"),
    [
        (True, "bool", "True"),
        (7.8, "float", "7.8"),
        ("12", "str", "'12'"),
        (MalformedMcid(), "MalformedMcid", "<malformed>"),
    ],
)
@pytest.mark.parametrize("parent_mcid", [7, None])
def test_invalid_mcid_warns_and_inherits_parent(
    invalid_mcid, value_type: str, value_repr: str, parent_mcid: int | None
) -> None:
    events: list[tuple[str, object]] = []
    if parent_mcid is not None:
        events.append(("boundary", (b"BDC", ["/P", {"/MCID": parent_mcid}])))
    events.extend(
        [
            ("boundary", (b"BDC", ["/Span", {"/MCID": invalid_mcid}])),
            ("text", ("Child", None, None)),
            ("boundary", (b"EMC", [])),
        ]
    )
    if parent_mcid is not None:
        events.extend(
            [
                ("text", ("Parent", None, None)),
                ("boundary", (b"EMC", [])),
            ]
        )

    result = McidTextCollector(runner=FakeRunner(events)).collect(
        object(), page_index=4
    )

    expected_parts = {7: ("Child", "Parent")} if parent_mcid is not None else {}
    assert result.parts_by_mcid == expected_parts
    assert result.diagnostics == (
        Diagnostic(
            severity="warning",
            code="invalid_mcid",
            message="MCID must be an integer",
            context={
                "page_index": 4,
                "value_type": value_type,
                "value_repr": value_repr,
            },
        ),
    )


def test_reports_unmatched_emc() -> None:
    runner = FakeRunner([("boundary", (b"EMC", []))])

    result = McidTextCollector(runner=runner).collect(object(), page_index=3)

    assert result.parts_by_mcid == {}
    assert result.diagnostics == (
        Diagnostic(
            severity="warning",
            code="unbalanced_emc",
            message="EMC without matching BMC/BDC",
            context={"page_index": 3},
        ),
    )


def test_reports_unclosed_marked_content_after_extraction() -> None:
    runner = FakeRunner(
        [
            ("boundary", (b"BDC", ["/P", {"/MCID": 3}])),
            ("text", ("Open", None, None)),
        ]
    )

    result = McidTextCollector(runner=runner).collect(object(), page_index=5)

    assert result.parts_by_mcid == {3: ("Open",)}
    assert result.diagnostics == (
        Diagnostic(
            severity="warning",
            code="unclosed_marked_content",
            message="BMC/BDC without matching EMC",
            context={"page_index": 5, "depth": 1},
        ),
    )


def test_synthetic_marked_content_flush_helper_is_not_exposed() -> None:
    assert not hasattr(mcid_text, "_page_with_marked_content_flushes")


def test_collects_font_styles_aligned_with_each_mcid_text_part() -> None:
    runner = FakeRunner(
        [
            ("text", ("Outside", "IgnoredFont", 10.0)),
            ("boundary", (b"BDC", ["/P", {"/MCID": 7}])),
            ("text", ("03", "SamsungOne-600", 16.0)),
            ("text", ("Title", "SamsungOne-600", 16.0)),
            ("boundary", (b"EMC", [])),
        ]
    )

    result = McidTextCollector(runner=runner).collect(object(), page_index=0)

    assert result.parts_by_mcid == {7: ("03", "Title")}
    assert result.styles_by_mcid == {
        7: (
            TextStyle("SamsungOne-600", 16.0),
            TextStyle("SamsungOne-600", 16.0),
        )
    }
