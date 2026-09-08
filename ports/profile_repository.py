from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from domain.models import PdfProfile


class ProfileRepositoryError(Exception):
    """Base error for canonical PDF profile repository failures."""


class ProfileMappingFileError(ProfileRepositoryError):
    """Raised when the injected profile mapping file cannot be read."""


class InvalidProfileMappingError(ProfileRepositoryError, ValueError):
    """Raised when the profile mapping document is malformed."""


class InvalidProfileRowError(InvalidProfileMappingError):
    """Raised when one profile mapping row violates the canonical schema."""


class DuplicateSourceTokenError(InvalidProfileMappingError):
    """Raised when multiple rows declare the same source token."""


class UnknownSourceTokenError(ProfileRepositoryError, LookupError):
    """Raised when a parsed PDF filename has no canonical profile."""


@runtime_checkable
class ProfileRepositoryPort(Protocol):
    def lookup(self, pdf_path: str | Path) -> PdfProfile:
        """Return the canonical profile identified by a PDF filename."""
        ...
