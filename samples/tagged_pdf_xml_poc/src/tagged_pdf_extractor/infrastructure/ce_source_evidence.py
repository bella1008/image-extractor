"""Read source text operations for CE Wi-Fi numeric labels; no OCR or rewriting."""
from collections import defaultdict
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
import re

from pypdf import PdfReader

from tagged_pdf_extractor.domain.ce_book import ce_book_scope, elements, fragments
from tagged_pdf_extractor.domain.models import Diagnostic
from tagged_pdf_extractor.infrastructure.africa_glyphs import RtlGlyphObserver


def add_ce_source_evidence(document, profile):
    if not ce_book_scope(profile):
        return document
    candidates = {(f.page_index, f.mcid) for n in elements(document.children)
                  if n.semantic_role == 'paragraph' and n.source_role == 'Description-L-head'
                  and 'Wi-Fi' in ''.join(f.text for f in fragments(n))
                  for f in fragments(n) if re.search(r'\d[ \t]+[.,]\d', f.text)}
    reader = PdfReader(document.source_path)
    evidence = []
    for page_index in sorted({p for p, _ in candidates}):
        runs = defaultdict(list)
        for line in RtlGlyphObserver().collect(reader.pages[page_index]):
            for run in line['runs']:
                if (page_index, run['mcid']) in candidates:
                    runs[run['mcid']].append(run)
        for mcid, values in runs.items():
            evidence.append({'page_index':page_index, 'mcid':mcid, 'runs':values})
    return replace(document, source_sha256=sha256(Path(document.source_path).read_bytes()).hexdigest(),
                   diagnostics=(*document.diagnostics, Diagnostic('warning', 'ce_decimal_source',
                       'CE numeric-label source operation evidence.', {'fragments':evidence})))
