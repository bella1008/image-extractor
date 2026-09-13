import pytest
from tagged_pdf_extractor.infrastructure.mcid_text import McidTextCollector
from .test_mcid_text import _in_memory_page

def test_authoritative_actual_text_replaces_wrong_glyphs_once():
    page = _in_memory_page(b"/P <</MCID 7>> BDC BT /F1 12 Tf /Span <</ActualText <FEFF00340009>>> BDC (14) Tj EMC ET EMC")
    result = McidTextCollector().collect(page, 0)
    # Adapter is opt-in; baseline must remain unchanged.
    assert ''.join(result.parts_by_mcid[7]).strip() == "14"
    from tagged_pdf_extractor.infrastructure.africa_actual_text import ActualTextRunner
    result = McidTextCollector(runner=ActualTextRunner()).collect(page, 0)
    assert ''.join(result.parts_by_mcid[7]) == "4\t"
    assert len(result.styles_by_mcid[7]) == len(result.parts_by_mcid[7])

@pytest.mark.parametrize("replacement", [b"<FEFF00>", b"123"])
def test_invalid_replacement_fails_closed(replacement):
    from tagged_pdf_extractor.infrastructure.africa_actual_text import ActualTextRunner
    page = _in_memory_page(b"/P <</MCID 7>> BDC BT /F1 12 Tf /Span <</ActualText " + replacement + b">> BDC (14) Tj EMC ET EMC")
    with pytest.raises(Exception, match="Unable to collect MCID") as error:
        McidTextCollector(runner=ActualTextRunner()).collect(page, 0)
    assert "ActualText" in str(error.value.__cause__)


def test_pdfdocencoding_actual_text_is_valid_pdf_text_string():
    from tagged_pdf_extractor.infrastructure.africa_actual_text import ActualTextRunner
    page=_in_memory_page(b"/P <</MCID 7>> BDC BT /F1 12 Tf /Span <</ActualText (0)>> BDC (X) Tj EMC ET EMC")
    result=McidTextCollector(runner=ActualTextRunner()).collect(page,0)
    assert ''.join(result.parts_by_mcid[7]) == "0"


def test_whitespace_decoded_glyph_keeps_positive_typography_and_bbox_evidence():
    from tagged_pdf_extractor.infrastructure.africa_actual_text import ActualTextRunner
    page=_in_memory_page(b"/P <</MCID 7>> BDC BT /F1 12 Tf 1 0 0 1 20 40 Tm /Span <</ActualText (0)>> BDC ( ) Tj EMC ET EMC")
    runner=ActualTextRunner(); result=McidTextCollector(runner=runner).collect(page,0)
    assert result.styles_by_mcid[7][0].font_name == "Helvetica"
    assert result.styles_by_mcid[7][0].font_size == 12
    assert result.bboxes_by_mcid[7][0] is not None
    assert runner.evidence[0]["source_runs"][0]["font_name"] == "Helvetica"


def test_arabic_page_opt_in_keeps_latin_page_unchanged():
    from tagged_pdf_extractor.infrastructure.africa_actual_text import ActualTextRunner
    page=_in_memory_page(b"/P <</MCID 7>> BDC BT /F1 12 Tf /Span <</ActualText (0)>> BDC (X) Tj EMC ET EMC")
    runner=ActualTextRunner(arabic_pages_only=True)
    result=McidTextCollector(runner=runner).collect(page,0)
    assert ''.join(result.parts_by_mcid[7]) == "X"
    assert runner.evidence == []

def test_actual_text_cannot_change_mcid_owner():
    from tagged_pdf_extractor.infrastructure.africa_actual_text import ActualTextRunner
    page=_in_memory_page(b"/P <</MCID 7>> BDC /Span <</ActualText (0)>> BDC /Span <</MCID 8>> BDC BT /F1 12 Tf (X) Tj ET EMC EMC EMC")
    with pytest.raises(Exception) as error:
        McidTextCollector(runner=ActualTextRunner()).collect(page,0)
    assert "MCID owners" in str(error.value.__cause__)
