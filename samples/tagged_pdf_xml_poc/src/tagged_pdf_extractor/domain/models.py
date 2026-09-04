from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal


@dataclass(frozen=True)
class Diagnostic:
    severity: Literal["warning", "error"]
    code: str
    message: str
    context: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TextStyle:
    font_name: str | None
    font_size: float | None


@dataclass(frozen=True)
class ContentFragment:
    page_index: int
    mcid: int | None
    text_parts: tuple[str, ...]
    object_ref: str | None = None
    text_styles: tuple[TextStyle, ...] = ()

    @property
    def text(self) -> str:
        return "".join(self.text_parts)


@dataclass(frozen=True)
class StructureElement:
    source_role: str
    semantic_role: str
    heading_level: int | None = None
    object_ref: str | None = None
    page_index: int | None = None
    title: str | None = None
    language: str | None = None
    alternate_text: str | None = None
    actual_text: str | None = None
    attributes: tuple[tuple[str, str], ...] = ()
    children: tuple[StructureElement | ContentFragment, ...] = ()


@dataclass(frozen=True)
class TaggedDocument:
    source_path: Path
    marked: bool
    language: str | None
    role_map: tuple[tuple[str, str], ...]
    children: tuple[StructureElement | ContentFragment, ...]
    diagnostics: tuple[Diagnostic, ...] = ()


@dataclass(frozen=True)
class QualityReport:
    status: Literal["pass", "fail"]
    metrics: dict[str, Any]
    hard_gates: dict[str, bool]
    diagnostics: tuple[Diagnostic, ...]
    join_decisions: tuple[dict[str, Any], ...] = ()
    source_path: Path | None = None
    language: str | None = None
    marked: bool | None = None
    role_map: tuple[tuple[str, str], ...] = ()
    source_role_counts: dict[str, int] = field(default_factory=dict)
    heading_hierarchy: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class ExtractionArtifacts:
    raw_xml: Path
    semantic_xml: Path
    report_json: Path
    semantic_markdown: Path
