from pathlib import Path
from tagged_pdf_extractor.application.evaluate_quality import QualityEvaluator
from tagged_pdf_extractor.domain.models import (
    ExtractionArtifacts,
    QualityReport,
    TaggedDocument,
)
from tagged_pdf_extractor.domain.numbered_heading_promotion import (
    promote_numbered_chapter_headings,
)
from tagged_pdf_extractor.ports.baseline_reader import BaselineReaderPort
from tagged_pdf_extractor.ports.output_writer import (
    OutputValidation,
    OutputWriterPort,
)
from tagged_pdf_extractor.ports.pdf_reader import TaggedPdfReaderPort


class ExtractDocument:
    def __init__(
        self,
        reader: TaggedPdfReaderPort,
        baseline_reader: BaselineReaderPort,
        evaluator: QualityEvaluator,
        writer: OutputWriterPort,
    ) -> None:
        self.reader = reader
        self.baseline_reader = baseline_reader
        self.evaluator = evaluator
        self.writer = writer

    def run(
        self,
        pdf_path: Path,
        output_dir: Path,
        overwrite: bool = False,
    ) -> tuple[TaggedDocument, QualityReport, ExtractionArtifacts]:
        pdf_path = Path(pdf_path)
        output_dir = Path(output_dir)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF source does not exist: {pdf_path}")
        if not pdf_path.is_file():
            raise IsADirectoryError(f"PDF source is not a file: {pdf_path}")

        document = self.reader.read(pdf_path)
        document = promote_numbered_chapter_headings(document)
        baseline = self.baseline_reader.read_text(pdf_path)
        validation = self.writer.validate(document)
        if not isinstance(validation, OutputValidation):
            raise TypeError("output writer returned invalid XML validation proof")
        report = self.evaluator.evaluate(
            document,
            baseline,
            xml_round_trip_ok=True,
        )
        if tuple(validation.semantic_join_decisions) != report.join_decisions:
            raise ValueError(
                "validated semantic XML join decisions do not match quality report"
            )
        artifacts = self.writer.write(
            document,
            report,
            output_dir,
            overwrite,
        )
        return document, report, artifacts
