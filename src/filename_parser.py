from __future__ import annotations

from pathlib import Path

from src.models import ParsedManualFilename


class FilenameParseError(ValueError):
    """Raised when a manual PDF filename does not match the expected pattern."""


def parse_manual_filename(file_path: str | Path) -> ParsedManualFilename:
    path = Path(file_path)
    file_name = path.name
    stem = file_name.removesuffix(".pdf")
    if stem.endswith(".0"):
        stem = stem[:-2]

    parts = stem.split("_")
    if len(parts) < 6:
        raise FilenameParseError(
            f"Expected at least 6 underscore-separated parts in filename: {file_name}"
        )

    manual_code = parts[0].strip()
    manual_type = parts[1].strip()
    product_info = parts[2].strip()
    buyer_region_token = "_".join(parts[3:-2]).strip()
    language_token = parts[-2].strip()
    date_code = parts[-1].strip()

    if not buyer_region_token or not language_token:
        raise FilenameParseError(f"Missing buyer or language token in filename: {file_name}")

    source_token = f"{buyer_region_token}_{language_token}"
    return ParsedManualFilename(
        file_path=path,
        file_name=file_name,
        manual_code=manual_code,
        manual_type=manual_type,
        product_info=product_info,
        buyer_region_token=buyer_region_token,
        language_token=language_token,
        source_token=source_token,
        date_code=date_code,
    )
