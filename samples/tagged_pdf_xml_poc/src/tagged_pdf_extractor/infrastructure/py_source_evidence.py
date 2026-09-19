"""Operation evidence for the reviewed PY_ENRU source revision."""
from collections import defaultdict
from dataclasses import replace
from hashlib import sha256
import re
from pypdf import PdfReader
from tagged_pdf_extractor.domain.models import Diagnostic
from tagged_pdf_extractor.domain.py_sheet import SOURCE_SHA, py_scope, fragments
from tagged_pdf_extractor.infrastructure.africa_glyphs import RtlGlyphObserver


def add_py_source_evidence(document, profile):
    if not py_scope(profile):
        return document
    digest = sha256(document.source_path.read_bytes()).hexdigest()
    if digest != SOURCE_SHA:
        raise ValueError('PY source revision needs review')
    leaves = [f for n in document.children for f in fragments(n)]
    candidates = {(f.page_index, f.mcid) for f in leaves if
                  re.search(r'\d +[.,]', f.text)
                  or f.text.endswith(('network-', 'www.', 'ТВ-'))
                  or f.text.lstrip().startswith(('based smart services.', 'samsung.com', 'контроллер'))}
    records = []
    for page_index, page in enumerate(PdfReader(document.source_path).pages):
        grouped = defaultdict(list)
        for line in RtlGlyphObserver().collect(page):
            for run in line['runs']:
                if (page_index, run['mcid']) in candidates:
                    grouped[run['mcid']].append(run)
        records.extend({'page_index': page_index, 'mcid': mcid, 'runs': runs}
                       for mcid, runs in grouped.items())
    return replace(document, source_sha256=digest, diagnostics=(*document.diagnostics,
        Diagnostic('warning', 'py_source_operations', 'Original PDF operations for whitespace evidence.',
                   {'sha256': digest, 'fragments': records})))
