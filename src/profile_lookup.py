from __future__ import annotations

from pathlib import Path

from src.filename_parser import parse_manual_filename
from src.models import ProfileLookupResult
from src.profile_repository import PdfProfileRepository


class ProfileLookupService:
    def __init__(self, repository: PdfProfileRepository) -> None:
        self.repository = repository

    def lookup_for_file(self, file_path: str | Path) -> ProfileLookupResult:
        parsed = parse_manual_filename(file_path)
        profile = self.repository.get(parsed.source_token)
        return ProfileLookupResult(parsed_filename=parsed, profile=profile)
