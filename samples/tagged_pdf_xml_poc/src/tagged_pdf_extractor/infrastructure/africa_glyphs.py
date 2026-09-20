"""Observe source glyph owners before pypdf flushes RTL text at MCID boundaries.

No Unicode translation or codepoint reversal: a ToUnicode glyph may encode a
multi-codepoint combining sequence, which must stay intact.
"""
import math
import unicodedata as ud

from pypdf._text_extraction import get_text_operands

from tagged_pdf_extractor.infrastructure.pypdf_operation_text import PypdfOperationTextRunner


class RtlGlyphObserver(PypdfOperationTextRunner):
    def __init__(self):
        self.lines = []
        self.runs = []
        self.stack = []
        self.baseline = None
        self.pending_mark = False
        self.last_letter_x = None
        self.operation_index = -1
        self.cursor = 0.0
        self.cursor_known = True
        self.char_spacing = 0.0
        self.text_scale = 1.0
        self.source_font_size = 1.0
        self.word_spacing = 0.0
        self.unmodeled = {b"Tw": False, b"Ts": False}
        self.graphics_stack = []
        self.tj_offsets = []
        self.tj_trailing = 0.0

    def _finish(self):
        if self.runs:
            self.lines.append({"runs": self.runs, "pending_mark": self.pending_mark})
        self.runs = []
        self.baseline = None
        self.pending_mark = False
        self.last_letter_x = None

    def _before_operation(self, operator, operands):
        self.operation_index += 1
        if operator in (b"BT", b"Tm", b"Td", b"TD", b"T*", b"'", b'"'):
            self.cursor = 0.0
            self.cursor_known = True
        if operator == b"q":
            self.graphics_stack.append((self.char_spacing, self.text_scale, self.source_font_size, self.word_spacing, self.unmodeled.copy()))
        elif operator == b"Q" and self.graphics_stack:
            self.char_spacing, self.text_scale, self.source_font_size, self.word_spacing, self.unmodeled = self.graphics_stack.pop()
        elif operator == b"Tf":
            self.source_font_size = float(operands[1])
        elif operator == b"Tc":
            self.char_spacing = float(operands[0])
        elif operator == b"Tz":
            self.text_scale = float(operands[0]) / 100
        elif operator in self.unmodeled:
            self.unmodeled[operator] = float(operands[0]) != 0
            if operator == b"Tw":
                self.word_spacing = float(operands[0])
        elif operator == b'"':
            self.unmodeled[b"Tw"] = float(operands[0]) != 0
            self.word_spacing = float(operands[0])
            self.char_spacing = float(operands[1])
        self.tj_offsets = []
        self.tj_trailing = 0.0
        if operator == b"TJ":
            adjustment = 0.0
            for item in operands[0]:
                if isinstance(item, (str, bytes)):
                    if item:
                        self.tj_offsets.append(adjustment)
                        adjustment = 0.0
                else:
                    adjustment -= float(item) / 1000
            self.tj_trailing = adjustment
            if not self.tj_offsets:
                self.cursor += adjustment * self.source_font_size * self.text_scale
                self.tj_trailing = 0.0
        if operator in (b"BT", b"ET", b"Tm", b"Do", b"q", b"Q", b"cm"):
            self._finish()
        if operator in (b"BMC", b"BDC"):
            props = operands[1] if len(operands) > 1 else {}
            inherited = self.stack[-1] if self.stack else (None, False)
            if not hasattr(props, "get"):
                # Unresolved property names cannot authorize a repair.
                self.stack.append((None, True))
            else:
                self.stack.append((props.get("/MCID", inherited[0]),
                                   inherited[1] or "/ActualText" in props))
        elif operator == b"EMC" and self.stack:
            self.stack.pop()

    def _load_helpers(self):
        Font, Base, ContentStream, Null = super()._load_helpers()
        observer = self

        class ObservedExtraction(Base):
            def _handle_tj(self, text, operands, cm_matrix, tm_matrix,
                           font_resource, font, orientations, font_size,
                           rtl_dir, visitor_text, actual_str_size):
                codes, literal = get_text_operands(
                    operands, cm_matrix, tm_matrix, font, orientations)
                if not literal:
                    observer._observe(codes, operands, cm_matrix, tm_matrix, font, font_size)
                return super()._handle_tj(text, operands, cm_matrix, tm_matrix,
                    font_resource, font, orientations, font_size, rtl_dir,
                    visitor_text, actual_str_size)

        return Font, ObservedExtraction, ContentStream, Null

    def _observe(self, codes, operands, cm, tm, font, font_size):
        glyphs = [font.character_map.get(c, c) for c in codes]
        value = "".join(glyphs)
        if not value:
            return
        baseline = float(tm[4] * cm[1] + tm[5] * cm[3] + cm[5])
        origin_x = float(tm[4] * cm[0] + tm[5] * cm[2] + cm[4])
        marks_only = all(ud.bidirectional(c) == "NSM" for c in value)
        contains_letters = any(ud.bidirectional(c) == "AL" for c in value)
        if (contains_letters and self.last_letter_x is not None
                and origin_x < self.last_letter_x - 1e-7):
            self._finish()
        if self.baseline is not None and not math.isclose(baseline, self.baseline, abs_tol=1e-7):
            if marks_only:
                self.pending_mark = True
            else:
                self._finish()
        else:
            self.pending_mark = False
        if self.baseline is None:
            self.baseline = baseline
        if contains_letters:
            self.last_letter_x = origin_x
        mcid, actual = self.stack[-1] if self.stack else (None, False)
        axis_aligned = (tm[1] == tm[2] == cm[1] == cm[2] == 0
                        and tm[0] > 0 and tm[3] > 0 and cm[0] > 0 and cm[3] > 0)
        if self.tj_offsets:
            self.cursor += self.tj_offsets.pop(0) * font_size * self.text_scale
        boxes = []
        simple_space = (getattr(font, "sub_type", None) in {"TrueType", "Type1", "Type3"}
                        and isinstance(operands[0], bytes) and len(operands[0]) == len(codes))
        for index, code in enumerate(codes):
            # PDF widths are keyed by original character codes, not ToUnicode text.
            source_code = chr(operands[0][index]) if simple_space else code
            space_advance = self.word_spacing if source_code == " " and simple_space else 0.0
            advance = (font.get_text_width(source_code) / 1000 * font_size + self.char_spacing + space_advance) * self.text_scale
            left = origin_x + self.cursor * tm[0] * cm[0]
            right = left + advance * tm[0] * cm[0]
            boxes.append([left, baseline, right, baseline + font_size * tm[3] * cm[3]])
            self.cursor += advance
        if not self.tj_offsets:
            self.cursor += self.tj_trailing * font_size * self.text_scale
            self.tj_trailing = 0.0
        # Tw affects space codes only. An unknown advance stays unknown until
        # an explicit text-position operation resets the cursor.
        if self.unmodeled[b"Tw"] and not simple_space and (" " in codes
                or isinstance(operands[0], bytes) and b" " in operands[0]):
            self.cursor_known = False
        if (not axis_aligned or self.unmodeled[b"Ts"] or not self.cursor_known
                or not all(math.isfinite(v) for box in boxes for v in box)):
            boxes = None
        self.runs.append({"mcid": mcid, "glyphs": glyphs, "actual_text": actual,
            "axis_aligned": axis_aligned, "baseline_y": baseline,
            "glyph_boxes": boxes,
            "text_matrix": list(tm), "current_matrix": list(cm),
            "font_name": str(font.name), "font_size": font_size,
            "operation_index": self.operation_index,
            "raw_hex": operands[0].hex() if isinstance(operands[0], bytes) else None})

    def collect(self, page):
        self.run(page, on_boundary=lambda *args: None, on_text=lambda *args: None)
        self._finish()
        return self.lines
