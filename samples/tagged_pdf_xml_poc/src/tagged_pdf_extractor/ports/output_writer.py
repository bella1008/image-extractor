from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Protocol

from tagged_pdf_extractor.domain.models import (
    ExtractionArtifacts,
    QualityReport,
    TaggedDocument,
)


@dataclass(frozen=True)
class OutputValidation:
    semantic_join_decisions: tuple[Mapping[str, Any], ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "semantic_join_decisions",
            tuple(
                MappingProxyType(dict(decision))
                for decision in self.semantic_join_decisions
            ),
        )


class OutputWriterPort(Protocol):
    def validate(self, document: TaggedDocument) -> OutputValidation: ...

    def write(
        self,
        document: TaggedDocument,
        report: QualityReport,
        output_dir: Path,
        overwrite: bool = False,
    ) -> ExtractionArtifacts: ...
