"""PDF-operation proof for the reviewed UA Wi-Fi decimal."""
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from pypdf import PdfReader
from tagged_pdf_extractor.domain.models import Diagnostic
from tagged_pdf_extractor.domain.ua_sheet import SOURCE_SHA,ua_scope
from tagged_pdf_extractor.infrastructure.africa_glyphs import RtlGlyphObserver

def add_ua_source_evidence(document,profile):
    if not ua_scope(profile):
        return document
    digest=sha256(Path(document.source_path).read_bytes()).hexdigest()
    if digest!=SOURCE_SHA:
        raise ValueError('UA source revision needs review')
    reader=PdfReader(document.source_path)
    if len(reader.pages)!=2:
        raise ValueError('UA source page count needs review')
    runs=[r for line in RtlGlyphObserver().collect(reader.pages[1]) for r in line['runs'] if r['mcid']==1142]
    return replace(document,source_sha256=digest,diagnostics=(*document.diagnostics,
        Diagnostic('warning','ua_source_operations','Original UA PDF operations for Wi-Fi decimal spacing.',{'sha256':digest,'page_index':1,'mcid':1142,'runs':runs})))
