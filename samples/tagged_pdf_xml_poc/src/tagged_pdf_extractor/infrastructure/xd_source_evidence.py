"""Read original XD PDF operators as proof for two spacing repairs."""
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from pypdf import PdfReader
from tagged_pdf_extractor.domain.models import Diagnostic
from tagged_pdf_extractor.domain.xd_sheet import SOURCE_SHA, xd_scope
from tagged_pdf_extractor.infrastructure.africa_glyphs import RtlGlyphObserver

def add_xd_source_evidence(document,profile):
    if not xd_scope(profile): return document
    digest = sha256(Path(document.source_path).read_bytes()).hexdigest()
    if digest != SOURCE_SHA: raise ValueError('XD source revision needs review')
    reader = PdfReader(document.source_path)
    if len(reader.pages) != 2: raise ValueError('XD source pages need review')
    runs = [dict(run,page_index=page) for page,mcids in ((0,{447,*range(80)}),(1,{1076}))
            for line in RtlGlyphObserver().collect(reader.pages[page]) for run in line['runs'] if run['mcid'] in mcids]
    return replace(document,source_sha256=digest,diagnostics=(*document.diagnostics,
        Diagnostic('warning','xd_source_operations','Original XD PDF URL and Wi-Fi decimal operations.',{'sha256':digest,'runs':runs})))
