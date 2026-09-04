from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import pytest
from pypdf import PdfWriter
from pypdf.generic import (
    ArrayObject,
    BooleanObject,
    DecodedStreamObject,
    DictionaryObject,
    IndirectObject,
    NameObject,
    NullObject,
    NumberObject,
    TextStringObject,
)

from tagged_pdf_extractor.domain.models import (
    ContentFragment,
    Diagnostic,
    StructureElement,
    TextStyle,
)
from tagged_pdf_extractor.infrastructure.mcid_text import McidTextResult
from tagged_pdf_extractor.infrastructure.pypdf_operation_text import (
    PypdfOperationTextError,
)
from tagged_pdf_extractor.infrastructure.pypdf_reader import (
    TaggedPdfError,
    TaggedPdfReader,
)


StructureFactory = Callable[
    [PdfWriter, list[Any]],
    tuple[Any, DictionaryObject | None],
]


class RecordingCollector:
    def __init__(
        self,
        parts_by_page: dict[int, dict[int, tuple[str, ...]]] | None = None,
        diagnostics_by_page: dict[int, tuple[Diagnostic, ...]] | None = None,
        seen_mcids_by_page: dict[int, frozenset[int]] | None = None,
        styles_by_page: dict[int, dict[int, tuple[TextStyle, ...]]] | None = None,
    ) -> None:
        self.parts_by_page = parts_by_page or {}
        self.diagnostics_by_page = diagnostics_by_page or {}
        self.seen_mcids_by_page = seen_mcids_by_page or {}
        self.styles_by_page = styles_by_page or {}
        self.calls: list[int] = []

    def collect(self, _page: Any, page_index: int) -> McidTextResult:
        self.calls.append(page_index)
        parts_by_mcid = self.parts_by_page.get(page_index, {})
        return McidTextResult(
            parts_by_mcid=parts_by_mcid,
            styles_by_mcid=self.styles_by_page.get(page_index, {}),
            seen_mcids=self.seen_mcids_by_page.get(
                page_index, frozenset(parts_by_mcid)
            ),
            diagnostics=self.diagnostics_by_page.get(page_index, ()),
        )


def test_translates_decoder_failure_at_page_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    decoder_error = PypdfOperationTextError("decoder state failed")

    class FailingCollector:
        def collect(self, _page: Any, page_index: int) -> McidTextResult:
            assert page_index == 0
            raise decoder_error

    class FakeReader:
        trailer = {"/Root": {"/StructTreeRoot": {"/K": []}}}
        pages = [object()]

    monkeypatch.setattr(
        "tagged_pdf_extractor.infrastructure.pypdf_reader.PdfReader",
        lambda _: FakeReader(),
    )

    with pytest.raises(TaggedPdfError) as raised:
        TaggedPdfReader(FailingCollector()).read(tmp_path / "decoder-failure.pdf")

    assert str(raised.value) == (
        "Failed to decode tagged text on page index 0: decoder state failed"
    )
    assert raised.value.__cause__ is decoder_error
    assert not hasattr(raised.value, "diagnostics")


def test_content_fragment_preserves_four_argument_positional_construction() -> None:
    fragment = ContentFragment(2, 7, ("Title",), "12 0 R")

    assert fragment.object_ref == "12 0 R"
    assert fragment.text_styles == ()


def test_does_not_translate_non_decoder_collector_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    programmer_error = AssertionError("collector invariant failed")

    class FailingCollector:
        def collect(self, _page: Any, _page_index: int) -> McidTextResult:
            raise programmer_error

    class FakeReader:
        trailer = {"/Root": {"/StructTreeRoot": {"/K": []}}}
        pages = [object()]

    monkeypatch.setattr(
        "tagged_pdf_extractor.infrastructure.pypdf_reader.PdfReader",
        lambda _: FakeReader(),
    )

    with pytest.raises(AssertionError) as raised:
        TaggedPdfReader(FailingCollector()).read(tmp_path / "programmer-error.pdf")

    assert raised.value is programmer_error


def _write_tagged_pdf(
    path: Path,
    structure_factory: StructureFactory,
    *,
    page_count: int = 2,
    marked: bool = True,
    language: str | None = "en-US",
) -> None:
    writer = PdfWriter()
    pages = [writer.add_blank_page(width=100, height=100) for _ in range(page_count)]
    root_kids, role_map = structure_factory(writer, pages)
    struct_root = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/StructTreeRoot"),
            NameObject("/K"): root_kids,
        }
    )
    if role_map is not None:
        struct_root[NameObject("/RoleMap")] = role_map
    writer._root_object[NameObject("/StructTreeRoot")] = writer._add_object(
        struct_root
    )
    writer._root_object[NameObject("/MarkInfo")] = DictionaryObject(
        {NameObject("/Marked"): BooleanObject(marked)}
    )
    if language is not None:
        writer._root_object[NameObject("/Lang")] = TextStringObject(language)
    writer.write(path)


def test_rejects_pdf_without_structure_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FakeReader:
        trailer = {"/Root": {"/MarkInfo": {"/Marked": False}}}
        pages: list[Any] = []

    monkeypatch.setattr(
        "tagged_pdf_extractor.infrastructure.pypdf_reader.PdfReader",
        lambda _: FakeReader(),
    )

    with pytest.raises(TaggedPdfError, match="StructTreeRoot") as exc_info:
        TaggedPdfReader().read(tmp_path / "plain.pdf")

    assert str(exc_info.value) == "PDF has no /StructTreeRoot"


def test_rejects_structure_tree_reference_that_resolves_to_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class NullStructureTreeReference:
        def get_object(self):
            return None

    class FakeReader:
        trailer = {"/Root": {"/StructTreeRoot": NullStructureTreeReference()}}
        pages: list[Any] = []

    monkeypatch.setattr(
        "tagged_pdf_extractor.infrastructure.pypdf_reader.PdfReader",
        lambda _: FakeReader(),
    )

    with pytest.raises(TaggedPdfError) as exc_info:
        TaggedPdfReader().read(tmp_path / "null-structure-tree.pdf")

    assert str(exc_info.value) == "PDF has no /StructTreeRoot"


def test_rejects_real_null_structure_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FakeReader:
        trailer = {"/Root": {"/StructTreeRoot": NullObject()}}
        pages: list[Any] = []

    monkeypatch.setattr(
        "tagged_pdf_extractor.infrastructure.pypdf_reader.PdfReader",
        lambda _: FakeReader(),
    )

    with pytest.raises(TaggedPdfError) as exc_info:
        TaggedPdfReader().read(tmp_path / "null-object-structure-tree.pdf")

    assert str(exc_info.value) == "PDF has no /StructTreeRoot"


def test_real_null_objects_are_absent_catalog_and_structure_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    element = {
        "/S": NameObject("/P"),
        "/T": NullObject(),
        "/Lang": NullObject(),
        "/Alt": NullObject(),
        "/ActualText": NullObject(),
        "/A": NullObject(),
    }

    class FakeReader:
        trailer = {
            "/Root": {
                "/MarkInfo": NullObject(),
                "/Lang": NullObject(),
                "/StructTreeRoot": {"/K": [element]},
            }
        }
        pages: list[Any] = []

    monkeypatch.setattr(
        "tagged_pdf_extractor.infrastructure.pypdf_reader.PdfReader",
        lambda _: FakeReader(),
    )

    result = TaggedPdfReader(RecordingCollector()).read(tmp_path / "nulls.pdf")

    assert result.marked is False
    assert result.language is None
    structure = result.children[0]
    assert isinstance(structure, StructureElement)
    assert structure.title is None
    assert structure.language is None
    assert structure.alternate_text is None
    assert structure.actual_text is None
    assert structure.attributes == ()


def test_resolve_follows_chained_references_until_stable_object() -> None:
    terminal = {"resolved": True}

    class Reference:
        def __init__(self, target: Any) -> None:
            self.target = target

        def get_object(self):
            return self.target

    assert TaggedPdfReader.resolve(Reference(Reference(terminal))) is terminal


def test_resolve_rejects_dereference_cycle() -> None:
    class Reference:
        idnum: int
        generation = 0
        target: Any

        def get_object(self):
            return self.target

    first = Reference()
    first.idnum = 21
    second = Reference()
    second.idnum = 22
    first.target = second
    second.target = first

    with pytest.raises(TaggedPdfError, match=r"(?i)dereference cycle.*21 0 R"):
        TaggedPdfReader.resolve(first)


def test_reads_pypdf_false_marked_value_as_false(tmp_path: Path) -> None:
    def empty_structure(_writer: PdfWriter, _pages: list[Any]):
        return ArrayObject(), None

    pdf_path = tmp_path / "not-marked.pdf"
    _write_tagged_pdf(
        pdf_path,
        empty_structure,
        page_count=1,
        marked=False,
    )

    result = TaggedPdfReader(RecordingCollector()).read(pdf_path)

    assert result.marked is False


def test_object_reference_is_stable_for_ref_and_owning_object() -> None:
    ref = IndirectObject(81, 0, object())

    class OwningObject:
        indirect_reference = ref

    assert TaggedPdfReader.object_ref(ref) == "81 0 R"
    assert TaggedPdfReader.object_ref(OwningObject()) == "81 0 R"
    assert TaggedPdfReader.object_ref(object()) is None


def test_resolve_keeps_direct_objects_and_reports_broken_references() -> None:
    direct = {"value": 1}

    class BrokenReference:
        idnum = 12
        generation = 0

        def get_object(self):
            raise ValueError("damaged xref")

    assert TaggedPdfReader.resolve(direct) is direct
    with pytest.raises(
        TaggedPdfError, match=r"Failed to dereference 12 0 R.*damaged xref"
    ):
        TaggedPdfReader.resolve(BrokenReference())


def test_reads_nested_structure_in_logical_order_and_merges_diagnostics(
    tmp_path: Path,
) -> None:
    def structure(writer: PdfWriter, pages: list[Any]):
        unknown = writer._add_object(
            DictionaryObject(
                {
                    NameObject("/S"): NameObject("/Mystery"),
                    NameObject("/K"): NumberObject(6),
                }
            )
        )
        heading = writer._add_object(
            DictionaryObject(
                {
                    NameObject("/S"): NameObject("/CustomHeading"),
                    NameObject("/T"): TextStringObject("Visible title"),
                    NameObject("/Lang"): TextStringObject("ko-KR"),
                    NameObject("/Alt"): TextStringObject("Alternative"),
                    NameObject("/ActualText"): TextStringObject("Actual"),
                    NameObject("/A"): DictionaryObject(
                        {
                            NameObject("/Placement"): NameObject("/Block"),
                            NameObject("/O"): NameObject("/Layout"),
                        }
                    ),
                    NameObject("/K"): ArrayObject([NumberObject(3), unknown]),
                }
            )
        )
        mcr = writer._add_object(
            DictionaryObject(
                {
                    NameObject("/Pg"): pages[1].indirect_reference,
                    NameObject("/MCID"): NumberObject(9),
                }
            )
        )
        objr = writer._add_object(
            DictionaryObject(
                {
                    NameObject("/Type"): NameObject("/OBJR"),
                    NameObject("/Obj"): NumberObject(99),
                }
            )
        )
        document = writer._add_object(
            DictionaryObject(
                {
                    NameObject("/S"): NameObject("/Document"),
                    NameObject("/Pg"): pages[0].indirect_reference,
                    NameObject("/K"): ArrayObject(
                        [
                            heading,
                            NumberObject(4),
                            mcr,
                            objr,
                            TextStringObject("unsupported kid"),
                        ]
                    ),
                }
            )
        )
        role_map = DictionaryObject(
            {NameObject("/CustomHeading"): NameObject("/H3")}
        )
        return ArrayObject([document]), role_map

    pdf_path = tmp_path / "nested.pdf"
    _write_tagged_pdf(pdf_path, structure)
    collector_diagnostic = Diagnostic(
        severity="warning",
        code="collector_note",
        message="collector diagnostic",
        context={"page_index": 1},
    )
    collector = RecordingCollector(
        {
            0: {
                3: ("Heading",),
                4: ("After heading",),
                6: ("Unknown child",),
            },
            1: {9: ("Second page",)},
        },
        {1: (collector_diagnostic,)},
        styles_by_page={
            1: {9: (TextStyle("SamsungOne-600", 16.0),)},
        },
    )

    result = TaggedPdfReader(collector).read(pdf_path)

    assert result.source_path == pdf_path
    assert result.marked is True
    assert result.language == "en-US"
    assert result.role_map == (("CustomHeading", "H3"),)
    assert collector.calls == [0, 1]

    assert len(result.children) == 1
    document = result.children[0]
    assert isinstance(document, StructureElement)
    assert document.source_role == "Document"
    assert document.semantic_role == "document"
    assert document.page_index == 0
    assert document.object_ref is not None

    assert len(document.children) == 3
    heading, direct_fragment, mcr_fragment = document.children
    assert isinstance(heading, StructureElement)
    assert (
        heading.source_role,
        heading.semantic_role,
        heading.heading_level,
        heading.page_index,
    ) == ("CustomHeading", "heading", 3, 0)
    assert heading.title == "Visible title"
    assert heading.language == "ko-KR"
    assert heading.alternate_text == "Alternative"
    assert heading.actual_text == "Actual"
    assert heading.attributes == (
        ("/Placement", "/Block"),
        ("/O", "/Layout"),
    )
    assert heading.object_ref is not None

    inherited_fragment, unknown = heading.children
    assert inherited_fragment == ContentFragment(0, 3, ("Heading",))
    assert isinstance(unknown, StructureElement)
    assert unknown.source_role == "Mystery"
    assert unknown.semantic_role == "unknown"
    assert unknown.page_index == 0
    assert unknown.children == (ContentFragment(0, 6, ("Unknown child",)),)

    assert direct_fragment == ContentFragment(0, 4, ("After heading",))
    assert isinstance(mcr_fragment, ContentFragment)
    assert (mcr_fragment.page_index, mcr_fragment.mcid, mcr_fragment.text_parts) == (
        1,
        9,
        ("Second page",),
    )
    assert mcr_fragment.object_ref is not None
    assert mcr_fragment.text_styles == (TextStyle("SamsungOne-600", 16.0),)

    assert result.diagnostics[0] == collector_diagnostic
    assert [item.code for item in result.diagnostics[1:]] == [
        "unsupported_objr",
        "unsupported_structure_kid",
    ]
    assert result.diagnostics[1].context["object_ref"] is not None
    assert result.diagnostics[2].context == {
        "value_type": "TextStringObject",
        "value_repr": "'unsupported kid'",
        "object_ref": None,
    }


def test_attribute_array_preserves_mapping_grouping_and_iteration_order(
    tmp_path: Path,
) -> None:
    def structure(writer: PdfWriter, _pages: list[Any]):
        element = writer._add_object(
            DictionaryObject(
                {
                    NameObject("/S"): NameObject("/P"),
                    NameObject("/A"): ArrayObject(
                        [
                            DictionaryObject(
                                {
                                    NameObject("/O"): NameObject("/Layout"),
                                    NameObject("/Z"): TextStringObject("first"),
                                }
                            ),
                            DictionaryObject(
                                {
                                    NameObject("/R"): NumberObject(2),
                                    NameObject("/O"): NameObject("/Table"),
                                }
                            ),
                        ]
                    ),
                }
            )
        )
        return ArrayObject([element]), None

    pdf_path = tmp_path / "attribute-order.pdf"
    _write_tagged_pdf(pdf_path, structure, page_count=1)

    result = TaggedPdfReader(RecordingCollector()).read(pdf_path)

    element = result.children[0]
    assert isinstance(element, StructureElement)
    assert element.attributes == (
        ("[0]/O", "/Layout"),
        ("[0]/Z", "first"),
        ("[1]/R", "2"),
        ("[1]/O", "/Table"),
    )


def test_indirect_attribute_cycle_raises_tagged_pdf_error(tmp_path: Path) -> None:
    def structure(writer: PdfWriter, _pages: list[Any]):
        attributes = DictionaryObject()
        attributes_ref = writer._add_object(attributes)
        attributes[NameObject("/Loop")] = attributes_ref
        element = writer._add_object(
            DictionaryObject(
                {
                    NameObject("/S"): NameObject("/P"),
                    NameObject("/A"): attributes_ref,
                }
            )
        )
        return ArrayObject([element]), None

    pdf_path = tmp_path / "attribute-cycle.pdf"
    _write_tagged_pdf(pdf_path, structure, page_count=1)

    with pytest.raises(
        TaggedPdfError, match=r"(?i)attribute cycle.*\d+ 0 R"
    ):
        TaggedPdfReader(RecordingCollector()).read(pdf_path)


def test_preserves_unresolved_fragments_with_contextual_diagnostics(
    tmp_path: Path,
) -> None:
    def structure(writer: PdfWriter, pages: list[Any]):
        orphan_page = writer._add_object(
            DictionaryObject({NameObject("/Type"): NameObject("/Page")})
        )
        unresolved_page = writer._add_object(
            DictionaryObject(
                {
                    NameObject("/Type"): NameObject("/MCR"),
                    NameObject("/Pg"): orphan_page,
                    NameObject("/MCID"): NumberObject(7),
                }
            )
        )
        missing_mcid = writer._add_object(
            DictionaryObject(
                {
                    NameObject("/Type"): NameObject("/MCR"),
                    NameObject("/Pg"): pages[0].indirect_reference,
                }
            )
        )
        container = writer._add_object(
            DictionaryObject(
                {
                    NameObject("/S"): NameObject("/P"),
                    NameObject("/Pg"): pages[0].indirect_reference,
                    NameObject("/K"): ArrayObject(
                        [NumberObject(404), unresolved_page, missing_mcid]
                    ),
                }
            )
        )
        return ArrayObject([container]), None

    pdf_path = tmp_path / "unresolved.pdf"
    _write_tagged_pdf(pdf_path, structure, page_count=1)

    result = TaggedPdfReader(RecordingCollector()).read(pdf_path)

    container = result.children[0]
    assert isinstance(container, StructureElement)
    missing_text, unresolved_page, missing_mcid = container.children
    assert missing_text == ContentFragment(0, 404, ())
    assert missing_text.text_styles == ()
    assert isinstance(unresolved_page, ContentFragment)
    assert unresolved_page.page_index == -1
    assert unresolved_page.mcid == 7
    assert unresolved_page.text_parts == ()
    assert unresolved_page.text_styles == ()
    assert unresolved_page.object_ref is not None
    assert isinstance(missing_mcid, ContentFragment)
    assert missing_mcid.page_index == 0
    assert missing_mcid.mcid is None
    assert missing_mcid.text_parts == ()
    assert missing_mcid.text_styles == ()
    assert missing_mcid.object_ref is not None

    assert [item.code for item in result.diagnostics] == [
        "unresolved_mcid",
        "unresolved_page_reference",
        "unresolved_mcid",
        "unresolved_mcid",
    ]
    assert result.diagnostics[0].context == {
        "page_index": 0,
        "mcid": 404,
        "object_ref": None,
    }
    assert result.diagnostics[2].context == {
        "page_index": -1,
        "mcid": 7,
        "object_ref": unresolved_page.object_ref,
    }
    assert result.diagnostics[3].context == {
        "page_index": 0,
        "mcid": None,
        "object_ref": missing_mcid.object_ref,
    }


def test_unresolved_page_reference_reports_page_and_owner_refs(
    tmp_path: Path,
) -> None:
    expected_refs: dict[str, str | None] = {}

    def structure(writer: PdfWriter, _pages: list[Any]):
        orphan_page = writer._add_object(
            DictionaryObject({NameObject("/Type"): NameObject("/Page")})
        )
        mcr = writer._add_object(
            DictionaryObject(
                {
                    NameObject("/Type"): NameObject("/MCR"),
                    NameObject("/Pg"): orphan_page,
                    NameObject("/MCID"): NumberObject(7),
                }
            )
        )
        expected_refs["page"] = TaggedPdfReader.object_ref(orphan_page)
        expected_refs["owner"] = TaggedPdfReader.object_ref(mcr)
        return ArrayObject([mcr]), None

    pdf_path = tmp_path / "unresolved-page.pdf"
    _write_tagged_pdf(pdf_path, structure, page_count=1)

    result = TaggedPdfReader(RecordingCollector()).read(pdf_path)

    fragment = result.children[0]
    assert isinstance(fragment, ContentFragment)
    assert fragment.page_index == -1
    assert fragment.object_ref == expected_refs["owner"]
    assert [diagnostic.code for diagnostic in result.diagnostics] == [
        "unresolved_page_reference",
        "unresolved_mcid",
    ]
    assert result.diagnostics[0].context == {
        "page_object_ref": expected_refs["page"],
        "object_ref": expected_refs["owner"],
    }


def test_explicit_null_page_reference_does_not_inherit_parent_page_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class PageReference:
        idnum = 10
        generation = 0

    class Page:
        indirect_reference = PageReference()

    class NullPageReference:
        idnum = 91
        generation = 0

        def get_object(self):
            return None

    mcr = {
        "/Type": NameObject("/MCR"),
        "/Pg": NullPageReference(),
        "/MCID": NumberObject(7),
    }

    class McrReference:
        idnum = 81
        generation = 0

        def get_object(self):
            return mcr

    parent = {
        "/S": NameObject("/P"),
        "/Pg": PageReference(),
        "/K": [McrReference()],
    }

    class FakeReader:
        trailer = {"/Root": {"/StructTreeRoot": {"/K": [parent]}}}
        pages = [Page()]

    monkeypatch.setattr(
        "tagged_pdf_extractor.infrastructure.pypdf_reader.PdfReader",
        lambda _: FakeReader(),
    )
    collector = RecordingCollector({0: {7: ("Inherited page text",)}})

    result = TaggedPdfReader(collector).read(tmp_path / "null-page-ref.pdf")

    structure = result.children[0]
    assert isinstance(structure, StructureElement)
    fragment = structure.children[0]
    assert fragment == ContentFragment(-1, 7, (), "81 0 R")
    assert [diagnostic.code for diagnostic in result.diagnostics] == [
        "unresolved_page_reference",
        "unresolved_mcid",
    ]
    assert result.diagnostics[0].context == {
        "page_object_ref": "91 0 R",
        "object_ref": "81 0 R",
    }
    assert result.diagnostics[1].context == {
        "page_index": -1,
        "mcid": 7,
        "object_ref": "81 0 R",
    }


def test_direct_null_page_value_inherits_parent_page(tmp_path: Path) -> None:
    def structure(writer: PdfWriter, pages: list[Any]):
        mcr = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/MCR"),
                NameObject("/Pg"): NullObject(),
                NameObject("/MCID"): NumberObject(7),
            }
        )
        parent = writer._add_object(
            DictionaryObject(
                {
                    NameObject("/S"): NameObject("/P"),
                    NameObject("/Pg"): pages[0].indirect_reference,
                    NameObject("/K"): mcr,
                }
            )
        )
        return ArrayObject([parent]), None

    pdf_path = tmp_path / "direct-null-page.pdf"
    _write_tagged_pdf(pdf_path, structure, page_count=1)

    result = TaggedPdfReader(RecordingCollector({0: {7: ("Inherited",)}})).read(
        pdf_path
    )

    structure = result.children[0]
    assert isinstance(structure, StructureElement)
    assert structure.children == (ContentFragment(0, 7, ("Inherited",), None),)
    assert result.diagnostics == ()


def test_null_structure_kids_are_empty_without_warning(tmp_path: Path) -> None:
    def structure(writer: PdfWriter, _pages: list[Any]):
        element = writer._add_object(
            DictionaryObject(
                {
                    NameObject("/S"): NameObject("/P"),
                    NameObject("/K"): NullObject(),
                }
            )
        )
        return ArrayObject([element]), None

    pdf_path = tmp_path / "null-kids.pdf"
    _write_tagged_pdf(pdf_path, structure, page_count=1)

    result = TaggedPdfReader(RecordingCollector()).read(pdf_path)

    structure = result.children[0]
    assert isinstance(structure, StructureElement)
    assert structure.children == ()
    assert result.diagnostics == ()


def test_seen_empty_mcid_is_not_unresolved_but_missing_mcid_is(
    tmp_path: Path,
) -> None:
    def structure(writer: PdfWriter, pages: list[Any]):
        container = writer._add_object(
            DictionaryObject(
                {
                    NameObject("/S"): NameObject("/P"),
                    NameObject("/Pg"): pages[0].indirect_reference,
                    NameObject("/K"): ArrayObject(
                        [NumberObject(5), NumberObject(99)]
                    ),
                }
            )
        )
        return ArrayObject([container]), None

    pdf_path = tmp_path / "seen-empty-mcid.pdf"
    _write_tagged_pdf(pdf_path, structure, page_count=1)
    collector = RecordingCollector(seen_mcids_by_page={0: frozenset({5})})

    result = TaggedPdfReader(collector).read(pdf_path)

    container = result.children[0]
    assert isinstance(container, StructureElement)
    assert container.children == (
        ContentFragment(0, 5, ()),
        ContentFragment(0, 99, ()),
    )
    assert all(fragment.text_styles == () for fragment in container.children)
    assert [diagnostic.code for diagnostic in result.diagnostics] == [
        "unresolved_mcid"
    ]
    assert result.diagnostics[0].context["mcid"] == 99


def test_stream_owned_mcr_is_preserved_without_page_text_lookup(
    tmp_path: Path,
) -> None:
    expected_refs: dict[str, str | None] = {}

    def structure(writer: PdfWriter, pages: list[Any]):
        stream = DecodedStreamObject()
        stream.set_data(b"")
        stream_ref = writer._add_object(stream)
        mcr = writer._add_object(
            DictionaryObject(
                {
                    NameObject("/Type"): NameObject("/MCR"),
                    NameObject("/Pg"): pages[0].indirect_reference,
                    NameObject("/MCID"): NumberObject(7),
                    NameObject("/Stm"): stream_ref,
                }
            )
        )
        expected_refs["stream"] = TaggedPdfReader.object_ref(stream_ref)
        return ArrayObject([mcr]), None

    pdf_path = tmp_path / "stream-mcr.pdf"
    _write_tagged_pdf(pdf_path, structure, page_count=1)
    collector = RecordingCollector({0: {7: ("Wrong page text",)}})

    result = TaggedPdfReader(collector).read(pdf_path)

    fragment = result.children[0]
    assert isinstance(fragment, ContentFragment)
    assert fragment.page_index == 0
    assert fragment.mcid == 7
    assert fragment.text_parts == ()
    assert fragment.text_styles == ()
    assert fragment.object_ref is not None
    assert len(result.diagnostics) == 1
    diagnostic = result.diagnostics[0]
    assert diagnostic.code == "unsupported_stream_mcr"
    assert diagnostic.context == {
        "page_index": 0,
        "mcid": 7,
        "object_ref": fragment.object_ref,
        "stream_object_ref": expected_refs["stream"],
    }
    assert diagnostic.context["stream_object_ref"].endswith(" R")


def test_repeated_indirect_reference_is_allowed_outside_active_path(
    tmp_path: Path,
) -> None:
    def structure(writer: PdfWriter, pages: list[Any]):
        repeated = writer._add_object(
            DictionaryObject(
                {
                    NameObject("/S"): NameObject("/P"),
                    NameObject("/Pg"): pages[0].indirect_reference,
                    NameObject("/K"): NumberObject(2),
                }
            )
        )
        return ArrayObject([repeated, repeated]), None

    pdf_path = tmp_path / "repeated.pdf"
    _write_tagged_pdf(pdf_path, structure, page_count=1)
    collector = RecordingCollector({0: {2: ("Repeated",)}})

    result = TaggedPdfReader(collector).read(pdf_path)

    assert len(result.children) == 2
    assert result.children[0] == result.children[1]


def test_detects_cycle_on_active_indirect_recursion_path(tmp_path: Path) -> None:
    def structure(writer: PdfWriter, pages: list[Any]):
        cyclic = DictionaryObject(
            {
                NameObject("/S"): NameObject("/Sect"),
                NameObject("/Pg"): pages[0].indirect_reference,
            }
        )
        cyclic_ref = writer._add_object(cyclic)
        cyclic[NameObject("/K")] = cyclic_ref
        return ArrayObject([cyclic_ref]), None

    pdf_path = tmp_path / "cycle.pdf"
    _write_tagged_pdf(pdf_path, structure, page_count=1)

    with pytest.raises(
        TaggedPdfError, match=r"(?i)(\d+ 0 R.*cycle|cycle.*\d+ 0 R)"
    ):
        TaggedPdfReader(RecordingCollector()).read(pdf_path)
