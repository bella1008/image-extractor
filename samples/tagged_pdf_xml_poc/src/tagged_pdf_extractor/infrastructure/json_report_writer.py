from __future__ import annotations

import json
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
        ) + "\n"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(serialized, encoding="utf-8", newline="")

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
