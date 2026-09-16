"""Observe the verified Taiwan PDF's stroke/fill text, without changing raw tags."""
from dataclasses import replace
from hashlib import sha256
from pathlib import Path

from pypdf import PdfReader

from tagged_pdf_extractor.domain.models import Diagnostic
from tagged_pdf_extractor.infrastructure.africa_glyphs import RtlGlyphObserver

SOURCE_SHA = '37e8ef8c16b250463c4a57f5efc199a0f65bd8f9a1e10eacc5562b727f82e99f'

class ZwGlyphObserver(RtlGlyphObserver):
    def __init__(self):
        super().__init__()
        self.render_mode = 0
        self.render_stack = []

    def _before_operation(self, operator, operands):
        if operator == b'q':
            self.render_stack.append(self.render_mode)
        elif operator == b'Q' and self.render_stack:
            self.render_mode = self.render_stack.pop()
        elif operator == b'Tr':
            self.render_mode = int(operands[0])
        super()._before_operation(operator, operands)

    def _observe(self, *args):
        super()._observe(*args)
        if self.runs:
            self.runs[-1]['render_mode'] = self.render_mode

def add_zw_source_evidence(document, profile):
    if (profile.source_token, profile.doc_type, profile.languages) != ('ZW_TPE','A3',('TPE',)):
        return document
    digest = sha256(Path(document.source_path).read_bytes()).hexdigest()
    if digest != SOURCE_SHA:
        return document
    reader = PdfReader(str(document.source_path))
    fragments = []
    for page_index, page in enumerate(reader.pages):
        grouped = {}
        for line in ZwGlyphObserver().collect(page):
            for run in line['runs']:
                if run['mcid'] is not None:
                    grouped.setdefault(run['mcid'], []).append(run)
        fragments.extend({'page_index':page_index,'mcid':mcid,'runs':runs}
                         for mcid,runs in grouped.items())
    return replace(document, source_sha256=digest, diagnostics=(*document.diagnostics,
        Diagnostic('warning','zw_source_operations',
                   'Original glyph operations and text rendering modes for verified Taiwan source.',
                   {'sha256':digest,'fragments':fragments})))
