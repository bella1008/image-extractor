from pathlib import Path
from typing import Protocol

from tagged_pdf_extractor.domain.models import TaggedDocument


class TaggedPdfReaderPort(Protocol):
    def read(self, pdf_path: Path) -> TaggedDocument: ...
