from __future__ import annotations

import json
import os
import tempfile
from dataclasses import fields, is_dataclass
from pathlib import Path
from typing import Any

from tagged_pdf_extractor.domain.models import QualityReport


class JsonReportWriter:
    def write(self, report: QualityReport, path: Path) -> None:
        payload = self.to_data(report)
        serialized = json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        )
        serialized = self._escape_surrogate_code_units(serialized) + "\n"
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="",
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
                temporary.write(serialized)

            parsed = json.loads(temporary_path.read_text(encoding="utf-8"))
            if parsed != payload:
                raise ValueError("JSON report round trip mismatch")
            os.replace(temporary_path, path)
            temporary_path = None
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    @staticmethod
    def _escape_surrogate_code_units(serialized: str) -> str:
        return "".join(
            f"\\u{ord(character):04x}"
            if 0xD800 <= ord(character) <= 0xDFFF
            else character
            for character in serialized
        )

    def to_data(self, value: Any) -> Any:
        return self._convert(value, path="report")

    def _convert(self, value: Any, *, path: str) -> Any:
        if is_dataclass(value) and not isinstance(value, type):
            return {
                item.name: self._convert(
                    getattr(value, item.name), path=f"{path}.{item.name}"
                )
                for item in fields(value)
            }
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, dict):
            converted: dict[str, Any] = {}
            for key, item in value.items():
                if not isinstance(key, str):
                    raise TypeError(
                        f"unsupported JSON key at {path}: "
                        f"expected str, got {type(key).__name__}"
                    )
                converted[key] = self._convert(item, path=f"{path}.{key}")
            return converted
        if isinstance(value, (tuple, list)):
            return [
                self._convert(item, path=f"{path}[{index}]")
                for index, item in enumerate(value)
            ]
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        raise TypeError(
            f"unsupported JSON value at {path}: {type(value).__name__}"
        )
