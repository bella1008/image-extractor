import pytest

from tagged_pdf_extractor.domain.africa_rtl import pure_rtl_line, restore_rtl_glyph_lines
from tagged_pdf_extractor.domain.models import ContentFragment, Diagnostic, StructureElement, TextStyle
from tagged_pdf_extractor.infrastructure.africa_glyphs import RtlGlyphObserver


def line(glyphs, mcid=1):
    return {"pending_mark": False, "runs": [{"mcid": mcid, "glyphs": glyphs,
            "actual_text": False, "axis_aligned": True}]}


def restore(fragments, lines):
    parent = StructureElement("P", "paragraph", language="ARA", children=tuple(fragments))
    diagnostic = Diagnostic("warning", "africa_rtl_glyph_source", "source", {"page_index": 30, "lines": lines})
    return restore_rtl_glyph_lines((parent,), (diagnostic,))[0][0]


@pytest.mark.parametrize("glyphs", [["A", "ن"], ["1", "ن"], ["١", "ن"], ["(", "ن"], ["\ufffd", "ن"]])
def test_mixed_or_uncertain_glyph_lines_are_not_reversed(glyphs):
    assert not pure_rtl_line(line(glyphs))


@pytest.mark.parametrize("field,value", [("actual_text", True), ("axis_aligned", False), ("mcid", None)])
def test_unsupported_source_evidence_is_not_reversed(field, value):
    evidence = line(["ن"])
    evidence["runs"][0][field] = value
    assert not pure_rtl_line(evidence)


def test_multi_codepoint_combining_glyph_is_not_codepoint_reversed():
    fragment = ContentFragment(30, 1, ("بُّتجن",))
    result = restore([fragment], [line(["ب", "\u0651\u064f", "ن", "ج", "ت"])])
    assert result.children[0].text == "تجن\u0651\u064fب"
    assert fragment.text == "بُّتجن"


def test_layout_newline_style_does_not_override_actual_glyph_style():
    fragment = ContentFragment(30, 1, ("\n", "بُّتجن"), text_styles=(TextStyle("source", 1), TextStyle("source", 7)))
    result = restore([fragment], [line(["ب", "\u0651\u064f", "ن", "ج", "ت"])])
    assert result.children[0].text == "تجن\u0651\u064fب"
    assert result.children[0].text_styles == (TextStyle("source", 7),)


def test_source_sentence_period_can_follow_reconstructed_arabic_word():
    fragment = ContentFragment(30, 1, ("م الشاشة.ّتعت",))
    glyphs = [".", "ة", "ش", "ا", "ش", "ل", "ا", " ", "م", "\u0651", "ت", "ع", "ت"]
    assert restore([fragment], [line(glyphs)]).children[0].text == "تعت\u0651م الشاشة."


def test_mcid_spanning_multiple_source_lines_is_left_for_review():
    fragment = ContentFragment(30, 1, ("ب تجن",))
    result = restore([fragment], [line(["ب"]), line(["ن", "ج", "ت"])])
    assert result.children[0] is fragment


def test_partial_mcid_evidence_never_drops_unobserved_text():
    fragment = ContentFragment(30, 1, ("ب تجن 12",))
    assert restore([fragment], [line(["ب", "ن", "ج", "ت"]) ]).children[0] is fragment


def test_cross_mcid_reorder_requires_source_word_spacing():
    evidence = line(["ن", "ج"], 1)
    evidence["runs"].append({**evidence["runs"][0], "mcid": 2, "glyphs": ["ت"]})
    fragments = [ContentFragment(30, 1, ("جن",)), ContentFragment(30, 2, ("ت",))]
    assert restore(fragments, [evidence]).children == tuple(fragments)


def test_cross_mcid_reorder_is_local_to_one_contiguous_parent():
    evidence = line(["ب", " "], 1)
    evidence["runs"].append({**evidence["runs"][0], "mcid": 2, "glyphs": ["ن", "ج", "ت"]})
    fragments = [ContentFragment(30, 1, (" ب",)), ContentFragment(30, 3, ("middle",)), ContentFragment(30, 2, ("تجن",))]
    assert [f.mcid for f in restore(fragments, [evidence]).children] == [1, 3, 2]


def test_cross_mcid_reorder_requires_every_fragment_to_be_reconstructable():
    evidence = line(["ب", "ت", " "], 1)
    evidence["runs"].append({**evidence["runs"][0], "mcid": 2, "glyphs": ["ن"]})
    fragments = [ContentFragment(30, 1, ("ب", "ت"), text_styles=(TextStyle("a",7),TextStyle("b",7))),
                 ContentFragment(30, 2, ("ن",))]
    assert [f.mcid for f in restore(fragments, [evidence]).children] == [1, 2]


class Font:
    name = "source"
    character_map = {"m": "\u0651\u064f", "b": "ب", "n": "ن"}


def observe(observer, codes, y, x=0):
    observer._observe(codes, [codes.encode()], [1, 0, 0, 1, 0, 0], [7, 0, 0, 7, x, y], Font(), 1)


def test_combining_baseline_excursion_requires_return_to_same_baseline():
    observer = RtlGlyphObserver()
    observe(observer, "b", 100)
    observe(observer, "m", 99.5)
    observe(observer, "n", 100)
    observer._finish()
    assert len(observer.lines) == 1 and not observer.lines[0]["pending_mark"]
    assert observer.lines[0]["runs"][1]["glyphs"] == ["\u0651\u064f"]


def test_real_line_change_never_joins_a_pending_combining_glyph():
    observer = RtlGlyphObserver()
    observe(observer, "b", 100)
    observe(observer, "m", 99.5)
    observe(observer, "n", 90)
    observer._finish()
    assert len(observer.lines) == 2 and observer.lines[0]["pending_mark"]


def test_explicit_text_matrix_reset_prevents_same_y_column_merge():
    observer = RtlGlyphObserver()
    observe(observer, "b", 100)
    observer._before_operation(b"Tm", [7, 0, 0, 7, 200, 100])
    observe(observer, "n", 100)
    observer._finish()
    assert len(observer.lines) == 2


def test_backwards_horizontal_placement_does_not_reverse_source_chunks():
    observer = RtlGlyphObserver()
    observe(observer, "b", 100, x=300)
    observer._before_operation(b"Td", [-200/7, 0])
    observe(observer, "n", 100, x=100)
    observer._finish()
    assert len(observer.lines) == 2
