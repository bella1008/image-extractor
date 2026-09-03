from pypdf.generic import DictionaryObject, NameObject, NumberObject
import pytest

from tagged_pdf_extractor.domain.models import Diagnostic
from tagged_pdf_extractor.infrastructure.mcid_text import McidTextCollector


class FakePage:
    def extract_text(self, *, visitor_operand_before, visitor_text):
        visitor_operand_before(b"BDC", ["/P", {"/MCID": 7}], None, None)
        visitor_text("Settings >", None, None, None, 10)
        visitor_operand_before(b"BDC", ["/Span", {}], None, None)
        visitor_text(" General", None, None, None, 10)
        visitor_operand_before(b"EMC", [], None, None)
        visitor_operand_before(b"EMC", [], None, None)
        return "Settings > General"


class MalformedMcid:
    def __int__(self) -> int:
        raise ValueError("not an integer")

    def __repr__(self) -> str:
        return "<malformed>"


def test_collects_text_under_inherited_mcid() -> None:
    result = McidTextCollector().collect(FakePage(), page_index=0)

    assert result.parts_by_mcid == {7: ("Settings >", " General")}
    assert result.diagnostics == ()


def test_collects_direct_mcid_from_bmc_properties() -> None:
    class BmcPage:
        def extract_text(self, *, visitor_operand_before, visitor_text):
            visitor_operand_before(b"BMC", ["/P", {"/MCID": 9}], None, None)
            visitor_text("Tagged", None, None, None, 10)
            visitor_operand_before(b"EMC", [], None, None)
            return "Tagged"

    result = McidTextCollector().collect(BmcPage(), page_index=0)

    assert result.parts_by_mcid == {9: ("Tagged",)}
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

        def extract_text(self, *, visitor_operand_before, visitor_text):
            visitor_operand_before(
                b"BDC", [NameObject("/P"), NameObject("/MC0")], None, None
            )
            visitor_text("Resolved", None, None, None, 10)
            visitor_operand_before(b"EMC", [], None, None)
            return "Resolved"

    result = McidTextCollector().collect(NamedPropertyPage(), page_index=0)

    assert result.parts_by_mcid == {12: ("Resolved",)}
    assert result.diagnostics == ()


def test_restores_parent_mcid_after_nested_direct_mcid() -> None:
    class NestedMcidPage:
        def extract_text(self, *, visitor_operand_before, visitor_text):
            visitor_operand_before(b"BDC", ["/P", {"/MCID": 7}], None, None)
            visitor_text("Parent before", None, None, None, 10)
            visitor_operand_before(b"BDC", ["/Span", {"/MCID": 8}], None, None)
            visitor_text("Child", None, None, None, 10)
            visitor_operand_before(b"EMC", [], None, None)
            visitor_text("Parent after", None, None, None, 10)
            visitor_operand_before(b"EMC", [], None, None)
            return "Parent beforeChildParent after"

    result = McidTextCollector().collect(NestedMcidPage(), page_index=0)

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
    class InvalidMcidPage:
        def extract_text(self, *, visitor_operand_before, visitor_text):
            if parent_mcid is not None:
                visitor_operand_before(
                    b"BDC", ["/P", {"/MCID": parent_mcid}], None, None
                )
            visitor_operand_before(
                b"BDC", ["/Span", {"/MCID": invalid_mcid}], None, None
            )
            visitor_text("Child", None, None, None, 10)
            visitor_operand_before(b"EMC", [], None, None)
            if parent_mcid is not None:
                visitor_text("Parent", None, None, None, 10)
                visitor_operand_before(b"EMC", [], None, None)
            return "ChildParent"

    result = McidTextCollector().collect(InvalidMcidPage(), page_index=4)

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
    class UnmatchedEmcPage:
        def extract_text(self, *, visitor_operand_before, visitor_text):
            visitor_operand_before(b"EMC", [], None, None)
            return ""

    result = McidTextCollector().collect(UnmatchedEmcPage(), page_index=3)

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
    class UnclosedPage:
        def extract_text(self, *, visitor_operand_before, visitor_text):
            visitor_operand_before(b"BDC", ["/P", {"/MCID": 3}], None, None)
            visitor_text("Open", None, None, None, 10)
            return "Open"

    result = McidTextCollector().collect(UnclosedPage(), page_index=5)

    assert result.parts_by_mcid == {3: ("Open",)}
    assert result.diagnostics == (
        Diagnostic(
            severity="warning",
            code="unclosed_marked_content",
            message="BMC/BDC without matching EMC",
            context={"page_index": 5, "depth": 1},
        ),
    )
