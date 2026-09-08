from __future__ import annotations

from tagged_pdf_extractor.domain.heading_promotion_validation import (
    HeadingPromotionTracker,
)
from tagged_pdf_extractor.domain.models import (
    ContentFragment,
    Diagnostic,
    HeadingPromotion,
    HeadingMismatchPosition,
    HeadingSignatureEntry,
    LanguageHeadingSignature,
    LanguageIntervalEvidence,
    MultilingualHeadingAudit,
    PdfProfile,
    StructureElement,
    TaggedDocument,
)


def validate_multilingual_headings(
    profile: PdfProfile,
    intervals: tuple[LanguageIntervalEvidence, ...],
    document: TaggedDocument,
) -> MultilingualHeadingAudit:
    """Build and compare wording-independent heading signatures by language."""
    if profile.language_count == 1:
        return MultilingualHeadingAudit(
            applicable=False,
            passed=True,
            expected_interval_count=1,
            observed_interval_count=0,
            interval_count_matches=None,
            total_heading_count_matches=None,
            heading_level_sequence_matches=None,
            heading_origin_sequence_matches=None,
            numbered_label_sequence_matches=None,
        )

    expected_count = profile.language_count
    observed_count = len(intervals)
    if observed_count != expected_count:
        return _failed_interval_audit(
            expected_count,
            observed_count,
            "multilingual_heading_interval_count_mismatch",
            "Observed language interval count does not match the canonical profile.",
            {"expected_languages": profile.languages},
            interval_count_matches=False,
        )

    observed_languages = tuple(interval.language for interval in intervals)
    if observed_languages != profile.languages:
        return _failed_interval_audit(
            expected_count,
            observed_count,
            "multilingual_heading_interval_languages_invalid",
            "Language intervals must occur once each in canonical profile order.",
            {
                "expected_languages": profile.languages,
                "observed_languages": observed_languages,
            },
        )

    if not _ordered_nonoverlapping(intervals):
        return _failed_interval_audit(
            expected_count,
            observed_count,
            "multilingual_heading_interval_bounds_invalid",
            "Language interval page and path bounds must be ordered and non-overlapping.",
            {"intervals": intervals},
        )

    elements = _walk_elements(document.children)
    try:
        promotion_tracker = HeadingPromotionTracker(document.heading_promotions)
        promotion_by_path: dict[tuple[int, ...], HeadingPromotion] = {}
        for path, element in elements:
            promotion = promotion_tracker.apply(path, element)
            if promotion is not None:
                promotion_by_path[path] = promotion
        promotion_tracker.assert_all_applied()
    except ValueError as error:
        return _failed_interval_audit(
            expected_count,
            observed_count,
            "multilingual_heading_promotion_paths_invalid",
            str(error),
            {"promotion_count": len(document.heading_promotions)},
        )

    signatures: list[LanguageHeadingSignature] = []
    for interval in intervals:
        bounded_elements = tuple(
            (path, element)
            for path, element in elements
            if _path_in_interval(path, interval)
        )
        if not bounded_elements:
            return _failed_interval_audit(
                expected_count,
                observed_count,
                "multilingual_heading_interval_empty",
                "Language interval does not contain document structure.",
                {"language": interval.language, "interval": interval},
            )
        try:
            entries = _signature_entries(
                bounded_elements, promotion_by_path, interval
            )
        except ValueError as error:
            return _failed_interval_audit(
                expected_count,
                observed_count,
                "multilingual_heading_evidence_invalid",
                str(error),
                {"language": interval.language},
            )
        signatures.append(LanguageHeadingSignature(interval.language, interval, entries))

    comparisons = _compare_signatures(tuple(signatures))
    passed = all(comparisons[:4])
    return MultilingualHeadingAudit(
        applicable=True,
        passed=passed,
        expected_interval_count=expected_count,
        observed_interval_count=observed_count,
        interval_count_matches=True,
        total_heading_count_matches=comparisons[0],
        heading_level_sequence_matches=comparisons[1],
        heading_origin_sequence_matches=comparisons[2],
        numbered_label_sequence_matches=comparisons[3],
        signatures=tuple(signatures),
        mismatch_positions=comparisons[4],
    )


def _walk_elements(
    children: tuple[StructureElement | ContentFragment, ...],
) -> tuple[tuple[tuple[int, ...], StructureElement], ...]:
    found: list[tuple[tuple[int, ...], StructureElement]] = []

    def visit(
        siblings: tuple[StructureElement | ContentFragment, ...],
        parent_path: tuple[int, ...],
    ) -> None:
        for index, child in enumerate(siblings):
            if not isinstance(child, StructureElement):
                continue
            child_path = (*parent_path, index)
            found.append((child_path, child))
            visit(child.children, child_path)

    visit(children, ())
    return tuple(found)


def _ordered_nonoverlapping(
    intervals: tuple[LanguageIntervalEvidence, ...],
) -> bool:
    return all(
        previous.start_page_index <= current.start_page_index
        and previous.end_page_index <= current.end_page_index
        and previous.end_path < current.start_path
        and not _is_at_or_below(current.start_path, previous.end_path)
        for previous, current in zip(intervals, intervals[1:])
    )


def _path_in_interval(
    path: tuple[int, ...], interval: LanguageIntervalEvidence
) -> bool:
    return interval.start_path <= path and (
        path <= interval.end_path or _is_at_or_below(path, interval.end_path)
    )


def _is_at_or_below(path: tuple[int, ...], ancestor: tuple[int, ...]) -> bool:
    return path[: len(ancestor)] == ancestor


def _signature_entries(
    elements: tuple[tuple[tuple[int, ...], StructureElement], ...],
    promotion_by_path: dict[tuple[int, ...], HeadingPromotion],
    interval: LanguageIntervalEvidence,
) -> tuple[HeadingSignatureEntry, ...]:
    entries: list[HeadingSignatureEntry] = []
    for path, element in elements:
        promotion = promotion_by_path.get(path)
        is_source_heading = element.semantic_role == "heading"
        if promotion is not None and is_source_heading:
            raise ValueError(f"heading at {path} has both source and promoted origins")
        if is_source_heading:
            page_indices = _element_page_indices(element)
            _validate_heading_pages(page_indices, interval, path)
            if element.heading_level is None:
                raise ValueError(f"source heading at {path} lacks a heading level")
            entries.append(
                HeadingSignatureEntry(element.heading_level, "source", None)
            )
        elif promotion is not None:
            page_indices = _element_page_indices(element)
            _validate_heading_pages(page_indices, interval, path)
            entries.append(
                HeadingSignatureEntry(
                    promotion.level,
                    "promoted",
                    promotion.label,
                )
            )
    return tuple(entries)


def _element_page_indices(element: StructureElement) -> tuple[int, ...]:
    found: list[int] = []
    if element.page_index is not None:
        found.append(element.page_index)
    stack = list(element.children)
    while stack:
        child = stack.pop(0)
        if isinstance(child, ContentFragment):
            found.append(child.page_index)
        else:
            if child.page_index is not None:
                found.append(child.page_index)
            stack[0:0] = child.children
    return tuple(dict.fromkeys(found))


def _validate_heading_pages(
    page_indices: tuple[int, ...],
    interval: LanguageIntervalEvidence,
    path: tuple[int, ...],
) -> None:
    if not page_indices or not all(
        interval.start_page_index <= page_index <= interval.end_page_index
        for page_index in page_indices
    ):
        raise ValueError(
            f"heading at {path} lacks page evidence within its language interval"
        )


def _compare_signatures(
    signatures: tuple[LanguageHeadingSignature, ...],
) -> tuple[bool, bool, bool, bool, tuple[HeadingMismatchPosition, ...]]:
    reference = signatures[0].entries
    counts_match = True
    levels_match = True
    origins_match = True
    labels_match = True
    mismatches: list[HeadingMismatchPosition] = []
    for signature in signatures[1:]:
        observed = signature.entries
        if len(reference) != len(observed):
            counts_match = False
            common_count = min(len(reference), len(observed))
            largest_count = max(len(reference), len(observed))
            for position in range(common_count, largest_count):
                mismatches.append(
                    HeadingMismatchPosition(
                        signature.language,
                        position,
                        "count",
                        reference[position] if position < len(reference) else None,
                        observed[position] if position < len(observed) else None,
                    )
                )
        for position, (expected, actual) in enumerate(zip(reference, observed)):
            if expected.heading_level != actual.heading_level:
                levels_match = False
                mismatches.append(
                    HeadingMismatchPosition(
                        signature.language, position, "level", expected, actual
                    )
                )
            if expected.heading_origin != actual.heading_origin:
                origins_match = False
                mismatches.append(
                    HeadingMismatchPosition(
                        signature.language, position, "origin", expected, actual
                    )
                )
            if (
                expected.heading_origin == "promoted"
                and actual.heading_origin == "promoted"
                and expected.numbered_label != actual.numbered_label
            ):
                labels_match = False
                mismatches.append(
                    HeadingMismatchPosition(
                        signature.language, position, "numbered_label", expected, actual
                    )
                )
    return counts_match, levels_match, origins_match, labels_match, tuple(mismatches)


def _failed_interval_audit(
    expected_count: int,
    observed_count: int,
    code: str,
    message: str,
    context: dict[str, object],
    *,
    interval_count_matches: bool = True,
) -> MultilingualHeadingAudit:
    return MultilingualHeadingAudit(
        applicable=True,
        passed=False,
        expected_interval_count=expected_count,
        observed_interval_count=observed_count,
        interval_count_matches=interval_count_matches,
        total_heading_count_matches=None,
        heading_level_sequence_matches=None,
        heading_origin_sequence_matches=None,
        numbered_label_sequence_matches=None,
        diagnostics=(Diagnostic("error", code, message, context),),
    )
