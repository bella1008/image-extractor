"""Observe the exact reviewed XL PDF text operation before repairing spacing."""
from dataclasses import replace
from hashlib import sha256
from pathlib import Path

from pypdf import PdfReader
from tagged_pdf_extractor.domain.models import Diagnostic
from tagged_pdf_extractor.domain.xl_sheet import SOURCE_SHA, xl_scope
from tagged_pdf_extractor.infrastructure.africa_glyphs import RtlGlyphObserver

def add_xl_source_evidence(document, profile):
    if not xl_scope(profile):
        return document
    digest = sha256(Path(document.source_path).read_bytes()).hexdigest()
    if digest != SOURCE_SHA:
        raise ValueError('XL source revision needs review')
    reader = PdfReader(document.source_path)
    if len(reader.pages) != 2:
        raise ValueError('XL source page count needs review')
    runs = [run for line in RtlGlyphObserver().collect(reader.pages[1])
            for run in line['runs'] if run['mcid'] in {881, 1054}]
    return replace(document, source_sha256=digest, diagnostics=(*document.diagnostics,
        Diagnostic('warning', 'xl_source_operations',
            'Original PDF operations for XL model weight and Wi-Fi decimal spacing.',
            {'sha256': digest, 'page_index': 1, 'mcids': [881, 1054], 'runs': runs})))
