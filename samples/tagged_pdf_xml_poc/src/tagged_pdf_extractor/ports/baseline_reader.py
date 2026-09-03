from pathlib import Path
from typing import Protocol


class BaselineReaderPort(Protocol):
    def read_text(self, pdf_path: Path) -> str: ...
