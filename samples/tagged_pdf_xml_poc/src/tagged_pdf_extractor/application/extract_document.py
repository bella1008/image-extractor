from dataclasses import replace
from pathlib import Path
from tagged_pdf_extractor.application.evaluate_quality import QualityEvaluator
from tagged_pdf_extractor.domain.models import (
    ContentFragment,
    ExtractionArtifacts,
    MultilingualHeadingAudit,
    QualityReport,
    StructureElement,
    TaggedDocument,
)
from tagged_pdf_extractor.domain.language_interval_resolution import (
    resolve_language_intervals,
)
from tagged_pdf_extractor.domain.multilingual_heading_validation import (
    validate_multilingual_headings,
)
from tagged_pdf_extractor.domain.list_continuation_detection import (
    detect_list_continuation_hints,
)
from tagged_pdf_extractor.domain.numbered_heading_promotion import (
    promote_numbered_chapter_headings,
)
from tagged_pdf_extractor.domain.review_formatting import (
    apply_profile_review_formatting,
)
from tagged_pdf_extractor.domain.readability_formatting import (
    apply_readability_formatting,
)
from tagged_pdf_extractor.domain.subtitle_detection import detect_table_subtitles
from tagged_pdf_extractor.domain.role_mapping import is_heading_candidate
from tagged_pdf_extractor.domain.africa_book import prepare_africa_book
from tagged_pdf_extractor.domain.ce_book import prepare_ce_book
from tagged_pdf_extractor.domain.tk_sheet import prepare_tk_sheet
from tagged_pdf_extractor.domain.tk_arabic import prepare_tk_arabic
from tagged_pdf_extractor.domain.zw_sheet import prepare_zw_sheet, zw_scope
from tagged_pdf_extractor.domain.mena_sheet import prepare_mena_sheet
from tagged_pdf_extractor.domain.xl_sheet import prepare_xl_sheet
from tagged_pdf_extractor.domain.xt_sheet import prepare_xt_sheet
from tagged_pdf_extractor.domain.py_sheet import prepare_py_sheet
from tagged_pdf_extractor.domain.sq_mi_sheet import prepare_sq_mi_sheet
from tagged_pdf_extractor.domain.ua_sheet import prepare_ua_sheet
from tagged_pdf_extractor.domain.xd_sheet import prepare_xd_sheet
from tagged_pdf_extractor.domain.zw_source_text import restore_zw_text
from tagged_pdf_extractor.domain.zw_line_join import restore_zw_line_join
from tagged_pdf_extractor.domain.verified_paragraph_ownership import repair_verified_paragraph_ownership
from tagged_pdf_extractor.domain.profile_scope import parse_source_token
from tagged_pdf_extractor.ports.baseline_reader import BaselineReaderPort
from tagged_pdf_extractor.ports.output_writer import (
    OutputValidation,
    OutputWriterPort,
)
from tagged_pdf_extractor.ports.pdf_reader import TaggedPdfReaderPort
from tagged_pdf_extractor.ports.profile_repository import ProfileRepositoryPort


class ExtractDocument:
    def __init__(
        self,
        reader: TaggedPdfReaderPort,
        baseline_reader: BaselineReaderPort,
        evaluator: QualityEvaluator,
        writer: OutputWriterPort,
        profile_repository: ProfileRepositoryPort | None = None,
    ) -> None:
        self.reader = reader
        self.baseline_reader = baseline_reader
        self.evaluator = evaluator
        self.writer = writer
        self.profile_repository = profile_repository

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

        profile = (self.profile_repository.lookup(pdf_path)
                   if self.profile_repository is not None
                   and parse_source_token(pdf_path.name) in {"AFRICA_L05", "CE_L05", "TK_L02", "TK_ARA", "ZW_TPE", "MENA_L02", "XL_ENG", "XT_L02", "PY_ENRU", "SQ MI_HEAR", "UA_ENG", "XD_INS"} else None)
        profile_reader = getattr(self.reader, "read_for_profile", None)
        document = (profile_reader(pdf_path, profile) if profile is not None and callable(profile_reader)
                    else self.reader.read(pdf_path))
        if profile is not None:
            document = prepare_africa_book(document, profile)
            document = prepare_ce_book(document, profile)
            document = prepare_tk_sheet(document, profile)
            document = prepare_tk_arabic(document, profile)
            document = prepare_mena_sheet(document, profile)
            document = prepare_xl_sheet(document, profile)
            document = prepare_xt_sheet(document, profile)
            document = prepare_py_sheet(document, profile)
            document = prepare_sq_mi_sheet(document, profile)
            document = prepare_ua_sheet(document, profile)
            document = prepare_xd_sheet(document, profile)
            document = prepare_zw_sheet(document, profile)
            if zw_scope(profile):
                children, evidence = restore_zw_text(document.children, document.diagnostics)
                document = replace(document, children=children, diagnostics=(*document.diagnostics,evidence))
                children, evidence = restore_zw_line_join(document.children, document.diagnostics)
                document = replace(document, children=children, diagnostics=(*document.diagnostics,evidence))
        if (profile is None and self.profile_repository is not None
                and parse_source_token(pdf_path.name) in {"ZC_L02", "ZG XN ZT_L05", "XU_ENG"}):
            profile = self.profile_repository.lookup(pdf_path)
        document = repair_verified_paragraph_ownership(document, profile)
        document = promote_numbered_chapter_headings(document)
        profile_resolution = None
        if self.profile_repository is not None:
            if profile is None:
                profile = self.profile_repository.lookup(pdf_path)
            resolution = resolve_language_intervals(profile, document)
            profile_resolution = (profile, resolution)
        document = detect_table_subtitles(document)
        document = apply_profile_review_formatting(document)
        if profile_resolution is not None:
            profile, resolution = profile_resolution
            if resolution.diagnostic is None:
                audit = validate_multilingual_headings(
                    profile, resolution.intervals, document
                )
            else:
                audit = MultilingualHeadingAudit(
                    applicable=True,
                    passed=False,
                    expected_interval_count=profile.language_count,
                    observed_interval_count=resolution.observed_interval_count,
                    interval_count_matches=(
                        profile.language_count == resolution.observed_interval_count
                    ),
                    total_heading_count_matches=None,
                    heading_level_sequence_matches=None,
                    heading_origin_sequence_matches=None,
                    numbered_label_sequence_matches=None,
                    diagnostics=(resolution.diagnostic,),
                )
            document = replace(document, multilingual_heading_audit=audit)
        document = _detect_list_continuations(document)
        document = apply_readability_formatting(replace(document, readability_profile=profile))
        document = _remove_continuation_sentence_break_conflicts(document)
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


def _detect_list_continuations(document: TaggedDocument) -> TaggedDocument:
    source_heading_paths: list[tuple[int, ...]] = []

    def visit(
        children: tuple[StructureElement | ContentFragment, ...],
        parent_path: tuple[int, ...],
    ) -> None:
        for index, child in enumerate(children):
            if not isinstance(child, StructureElement):
                continue
            child_path = (*parent_path, index)
            if child.semantic_role == "heading" or is_heading_candidate(
                child.source_role
            ):
                source_heading_paths.append(child_path)
            visit(child.children, child_path)

    visit(document.children, ())
    heading_paths = tuple(
        sorted(
            {
                *source_heading_paths,
                *(
                    hint.child_path
                    for hint in document.text_display_hints
                    if hint.display_role == "section_heading"
                ),
            }
        )
    )
    existing = document.continuation_hints
    detected = detect_list_continuation_hints(
        document,
        heading_paths=heading_paths,
        promotion_paths=tuple(
            promotion.child_path for promotion in document.heading_promotions
        ),
        subtitle_paths=tuple(hint.child_path for hint in document.subtitle_hints),
        strong_label_paths=tuple(
            hint.child_path
            for hint in document.text_display_hints
            if hint.display_role == "strong_label"
        ),
        existing_continuation_paths=tuple(hint.child_path for hint in existing),
    )
    return replace(document, continuation_hints=(*existing, *detected))


def _remove_continuation_sentence_break_conflicts(
    document: TaggedDocument,
) -> TaggedDocument:
    continuation_paths = tuple(
        hint.child_path for hint in document.continuation_hints
    )
    if not continuation_paths:
        return document
    sentence_break_hints = tuple(
        hint
        for hint in document.sentence_break_hints
        if not any(
            _paths_overlap(hint.child_path, path) for path in continuation_paths
        )
    )
    return replace(document, sentence_break_hints=sentence_break_hints)


def _paths_overlap(left: tuple[int, ...], right: tuple[int, ...]) -> bool:
    return left[: len(right)] == right or right[: len(left)] == left
