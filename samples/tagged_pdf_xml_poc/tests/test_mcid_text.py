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
