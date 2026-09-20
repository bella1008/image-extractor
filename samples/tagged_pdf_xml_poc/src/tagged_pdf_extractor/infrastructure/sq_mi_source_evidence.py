"""Explicit SQ MI HEB/ARA source operations, including both RTL pages."""
from tagged_pdf_extractor.infrastructure.africa_actual_text import ActualTextRunner
from tagged_pdf_extractor.infrastructure.africa_glyphs import RtlGlyphObserver


class SqMiTextRunner(ActualTextRunner):
    def run(self, page, *, on_boundary, on_text, on_xobject=None):
        super().run(page, on_boundary=on_boundary, on_text=on_text, on_xobject=on_xobject)
        self.rtl_lines = RtlGlyphObserver().collect(page)
