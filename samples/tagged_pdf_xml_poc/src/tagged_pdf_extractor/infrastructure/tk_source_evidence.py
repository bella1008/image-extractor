"""Read TK source operations to prove synthetic whitespace repairs."""
from collections import defaultdict
from dataclasses import replace
from hashlib import sha256
import re
from pypdf import PdfReader
from tagged_pdf_extractor.domain.models import Diagnostic
from tagged_pdf_extractor.domain.tk_sheet import tk_l02_scope, fragments
from tagged_pdf_extractor.infrastructure.africa_glyphs import RtlGlyphObserver

def add_tk_source_evidence(document,profile):
    if not tk_l02_scope(profile):return document
    leaves=[f for n in document.children for f in fragments(n)]
    candidates={(f.page_index,f.mcid) for f in leaves if
        re.search(r'\d +[.,]|https?:/ /',f.text)
        or f.text.endswith(('network-','ecodesign_','www.','www.samsung.'))
        or f.text.lstrip().startswith(('based smart services.','energy','samsung.com/','com/global/ecodesign_energy'))}
    evidence=[]
    for page,p in enumerate(PdfReader(document.source_path).pages):
        runs=defaultdict(list)
        for line in RtlGlyphObserver().collect(p):
            for run in line['runs']:
                if (page,run['mcid']) in candidates:runs[run['mcid']].append(run)
        evidence.extend({'page_index':page,'mcid':mcid,'runs':values} for mcid,values in runs.items())
    return replace(document,source_sha256=sha256(document.source_path.read_bytes()).hexdigest(),
        diagnostics=(*document.diagnostics,Diagnostic('warning','tk_source_operations',
            'PDF text operations used for whitespace evidence.',{'fragments':evidence})))
