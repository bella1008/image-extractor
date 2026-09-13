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
