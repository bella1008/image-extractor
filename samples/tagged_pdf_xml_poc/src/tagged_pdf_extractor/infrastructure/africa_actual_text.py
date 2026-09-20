"""Opt-in PDF-authored ActualText support for the AFRICA BOOK review path."""
from dataclasses import dataclass, field
from typing import Any
import unicodedata
import re
from pypdf.generic import decode_pdfdocencoding

from tagged_pdf_extractor.infrastructure.pypdf_operation_text import (
    PypdfOperationTextError, PypdfOperationTextRunner,
)


@dataclass
class _Replacement:
    value: str
    depth: int
    runs: list[tuple] = field(default_factory=list)


class ActualTextRunner:
    def __init__(self, *, arabic_pages_only: bool = False) -> None:
        self.arabic_pages_only = arabic_pages_only
        self.evidence: list[dict[str, Any]] = []
        self.rtl_lines = []
        self.ltr_decimal_lines = []

    def run(self, page, *, on_boundary, on_text, on_xobject=None) -> None:
        events = []
        PypdfOperationTextRunner().run(
            page,
            on_boundary=lambda *args: events.append(("boundary", args)),
            on_text=lambda *args: events.append(("text", args)),
            on_xobject=lambda *args: events.append(("xobject", args)),
        )
        use_replacements = not self.arabic_pages_only or any(
            unicodedata.bidirectional(c) == "AL"
            for kind, args in events if kind == "text" for c in args[0]
        )
        if self.arabic_pages_only and use_replacements:
            from tagged_pdf_extractor.infrastructure.africa_glyphs import RtlGlyphObserver
            self.rtl_lines = RtlGlyphObserver().collect(page)
        elif self.arabic_pages_only and any(
                "Wi-Fi" in args[0] and re.search(r"\d[ \t]+[.,]\d", args[0])
                for kind, args in events if kind == "text"):
            from tagged_pdf_extractor.infrastructure.africa_glyphs import RtlGlyphObserver
            self.ltr_decimal_lines = RtlGlyphObserver().collect(page)
        depth = 0
        active = None
        mcids = []
        for kind, args in events:
            if kind == "boundary":
                op, operands = args
                if op in (b"BMC", b"BDC"):
                    depth += 1
                    props = operands[1] if len(operands) > 1 else {}
                    if not hasattr(props, "get"):
                        props = page.get("/Resources", {}).get("/Properties", {}).get(props, {})
                    mcid = props.get("/MCID", mcids[-1] if mcids else None)
                    if active and mcids and mcid != mcids[-1]:
                        raise PypdfOperationTextError("ActualText spans multiple MCID owners")
                    mcids.append(mcid)
                    if use_replacements and "/ActualText" in props and active is None:
                        value = props["/ActualText"]
                        if isinstance(value, bytes):
                            try:
                                value = (value[2:].decode("utf-16-be", errors="strict")
                                         if value.startswith(b"\xfe\xff") else decode_pdfdocencoding(value))
                            except (UnicodeError, ValueError) as exc:
                                raise PypdfOperationTextError("Invalid ActualText encoding") from exc
                        if not isinstance(value, str):
                            raise PypdfOperationTextError("Invalid ActualText value")
                        active = _Replacement(value, depth)
                elif op == b"EMC":
                    if active and active.depth == depth:
                        runs = active.runs
                        glyph_runs = [r for r in runs if r[0].strip("\r\n")]
                        styles = {(r[1], r[2]) for r in glyph_runs}
                        font, size = next(iter(styles)) if len(styles) == 1 else (None, None)
                        boxes = [r[3] for r in glyph_runs if r[3] is not None]
                        bbox = None
                        if boxes and len(boxes) == len(glyph_runs):
                            bbox = (min(b[0] for b in boxes), min(b[1] for b in boxes),
                                    max(b[2] for b in boxes), max(b[3] for b in boxes))
                        on_text(active.value, font, size, bbox)
                        self.evidence.append({"mcid": mcids[-1] if mcids else None,
                                              "decoded_glyph_text": "".join(r[0] for r in runs),
                                              "actual_text": active.value,
                                              "source_runs": [{"text": r[0], "font_name": r[1],
                                                               "font_size": r[2], "bbox": r[3]}
                                                              for r in runs]})
                        active = None
                    depth -= 1
                    if mcids:
                        mcids.pop()
                on_boundary(*args)
            elif kind == "text":
                if active:
                    active.runs.append(args)
                else:
                    on_text(*args)
            elif on_xobject:
                on_xobject(*args)
        if active:
            raise PypdfOperationTextError("Unclosed ActualText span")
