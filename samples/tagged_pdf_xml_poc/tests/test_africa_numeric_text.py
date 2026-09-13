from tagged_pdf_extractor.domain.africa_numeric_text import decimal_source_text
from tagged_pdf_extractor.domain.models import ContentFragment
import pytest


def evidence(gap=0):
    return [{"glyphs":list("6.4"),"actual_text":False,"glyph_boxes":[[0,100,6,107]]},
            {"glyphs":["\t"],"actual_text":True,"glyph_boxes":[[6+gap,100,8+gap,107]]},
            {"glyphs":["5"],"actual_text":False,"glyph_boxes":[[8+gap,100,10+gap,107]]}]


def test_decimal_joins_only_the_exact_source_glyph_and_actual_text_sequence():
    assert decimal_source_text(ContentFragment(29,802,("6.4","2","5")),evidence(),["2"]) == "6.425"


@pytest.mark.parametrize("parts,replacements,gap", [
    (("6.4","2","5"),[],0), (("6.4","2","5"),["3"],0),
    (("6.4","2","5"),["2"],4), (("6.4 ","2","5"),["2"],0),
    (("6.4","2.5"),["2"],0), (("6.4","2","5"),["2","5"],0),
])
def test_uncertain_or_changed_decimal_evidence_is_rejected(parts,replacements,gap):
    assert decimal_source_text(ContentFragment(29,802,parts),evidence(gap),replacements) is None


@pytest.mark.parametrize("source,operations,actual,expected", [
    ("Wi-Fi 7.125", [9,9], False, ("Wi-Fi 7.125",)),
    ("Wi-Fi 7 .125", [9,9], False, None),
    ("Wi-Fi 7.125", [9,10], False, None),
    ("Wi-Fi 7.125", [None,None], False, None),
    ("Wi-Fi 7.126", [9,9], False, None),
    ("Wi-Fi 7.125", [9,9], True, None),
])
def test_ltr_decimal_requires_exact_single_operation_source(source,operations,actual,expected):
    from tagged_pdf_extractor.domain.africa_numeric_text import ltr_decimal_source_parts
    runs = [{"glyphs":list(source[:7]),"operation_index":operations[0],"actual_text":actual},
            {"glyphs":list(source[7:]),"operation_index":operations[1],"actual_text":actual}]
    assert ltr_decimal_source_parts(ContentFragment(6,743,("Wi-Fi 7 .125",)),runs) == expected


def test_ltr_decimal_does_not_join_parts_or_modify_other_spaces():
    from tagged_pdf_extractor.domain.africa_numeric_text import ltr_decimal_source_parts
    run = {"glyphs":list("Wi-Fi 7.125 GHz"),"operation_index":9,"actual_text":False}
    assert ltr_decimal_source_parts(ContentFragment(6,743,("Wi-Fi 7 ",".125 GHz",)),[run]) is None
    run["glyphs"]=list("Wi-Fi 7.125  GHz")
    assert ltr_decimal_source_parts(ContentFragment(6,743,("Wi-Fi 7 .125  GHz",)),[run]) == ("Wi-Fi 7.125  GHz",)
