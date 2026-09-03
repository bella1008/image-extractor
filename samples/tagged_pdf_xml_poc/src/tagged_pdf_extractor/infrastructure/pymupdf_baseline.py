from pathlib import Path

import pymupdf


class PyMuPdfBaselineReader:
    def read_text(self, pdf_path: Path) -> str:
        with pymupdf.open(pdf_path) as document:
            return "\n".join(page.get_text("text") for page in document)
