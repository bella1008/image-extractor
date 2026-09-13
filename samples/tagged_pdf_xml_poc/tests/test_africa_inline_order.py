from dataclasses import replace

import pytest

from tagged_pdf_extractor.domain.africa_inline_order import restore_inline_order
from tagged_pdf_extractor.domain.models import ContentFragment, Diagnostic, StructureElement


def reorder(items, *, language="ARA", role="paragraph", runs=None):
    children = tuple(ContentFragment(29, i, (text,)) for i, (text, _, _) in enumerate(items))
    if runs is None:
        runs = [{"mcid":i, "glyphs":list(text), "baseline_y":100,
                 "glyph_boxes":[[x,100,x+width,110]]} for i,(text,x,width) in enumerate(items)]
    parent = StructureElement("P",role,language=language,children=children)
    diag = Diagnostic("warning","africa_rtl_glyph_source","source",{"page_index":29,"lines":[{"runs":runs}]})
    result, evidence = restore_inline_order((parent,), (diag,))
    return result[0], evidence


def test_latin_island_in_arabic_line_preserves_its_left_to_right_word_order():
    result, _ = reorder([("شركة",210,20),("Samsung",100,40),("Electronics",140,60)])
    assert [f.text for f in result.children] == ["شركة","Samsung","Electronics"]


@pytest.mark.parametrize('latin', ['EC/1999/5', 'Samsung', 'B', 'Wireless One Connect'])
def test_source_period_left_of_latin_island_ends_arabic_sentence(latin):
    result, _ = reorder([('شركة', 210, 20), (' .', 98, 2), (latin, 100, 90)])
    assert [f.text for f in result.children] == ['شركة', latin, ' .']


def test_decimal_inside_latin_source_run_is_not_reversed():
    result, _ = reorder([('بتردد', 210, 20), ('5.925', 100, 30)])
    assert [f.text for f in result.children] == ['بتردد', '5.925']


def test_separate_contiguous_decimal_period_stays_inside_latin_number():
    result, _ = reorder([('بتردد', 210, 20), ('5', 100, 5), ('.', 105, 2), ('925', 107, 15)])
    assert [f.text for f in result.children] == ['بتردد', '5', '.', '925']


def test_period_between_distant_numbers_is_not_inferred_as_decimal():
    result, _ = reorder([('بتردد', 210, 20), ('5', 90, 5), ('.', 105, 2), ('925', 117, 15)])
    assert [f.text for f in result.children] == ['بتردد', '925', '.', '5']


def test_arabic_word_between_numbers_prevents_ltr_island_merging():
    result, _ = reorder([("40",100,10),("إلى",112,10),("10",124,10),("من",138,10)])
    assert [f.text for f in result.children] == ["من","10","إلى","40"]


@pytest.mark.parametrize("language", [None,"ENG","FRA","SPA","POR"])
def test_inline_rule_requires_explicit_arabic_node(language):
    result, evidence = reorder([("أ",100,10),("ب",120,10)],language=language)
    assert [f.mcid for f in result.children] == [0,1]
    assert not evidence.context["changes"]


def test_missing_geometry_leaves_whole_inline_container_unchanged():
    result, evidence = reorder([("أ",100,10),("ب",120,10)],runs=[])
    assert [f.mcid for f in result.children] == [0,1]
    assert evidence.context["skipped"]


def test_rtl_model_value_separator_keeps_label_before_resolution():
    result, _ = reorder([("7680 x 4320",100,45),("\u200f:",147,3),("QN9**H",153,30)])
    assert [f.mcid for f in result.children] == [2,1,0]


def test_explicit_rlm_slash_separates_latin_models_in_rtl_list():
    result, _ = reorder([("واط",90,10),("QN1EH",110,40),("/\u200f",151,3),("QN7*H",155,40)])
    assert [f.mcid for f in result.children] == [3,2,1,0]


def test_separate_rlm_keeps_source_slash_between_models():
    result, _ = reorder([('R8*H', 100, 20), ('/', 120, 3), ('\u200f', 123, 1), ('R9*H', 123, 20)])
    assert [f.text for f in result.children] == ['R9*H', '\u200f', '/', 'R8*H']


def test_url_slashes_without_rtl_marks_keep_latin_order():
    result, _ = reorder([('موقع', 210, 20), ('https:', 100, 30), ('/', 130, 3), ('/', 133, 3), ('samsung.com', 136, 60)])
    assert [f.text for f in result.children] == ['موقع', 'https:', '/', '/', 'samsung.com']


def test_contiguous_european_number_fragments_are_one_ltr_island():
    result, _ = reorder([("رقم",200,10),("12",100,10),("34",110,10)])
    assert [f.mcid for f in result.children] == [0,1,2]


def test_standalone_range_and_parenthesis_punctuation_is_a_rtl_boundary():
    result, _ = reorder([("بتردد",200,20),("5.925",160,20),(" - ",150,8),("7.125",128,20)])
    assert [f.mcid for f in result.children] == [0,1,2,3]
    result, _ = reorder([("واط",90,10),("20",110,10),("\u200f:)",122,5),("42",129,10),('"(\u200f',141,5),("S90H",148,20)])
    assert [f.mcid for f in result.children] == [5,4,3,2,1,0]
