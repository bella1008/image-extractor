from __future__ import annotations

from dataclasses import dataclass

from tagged_pdf_extractor.domain.models import (
    BookmarkPageBounds,
    ContentFragment,
    Diagnostic,
    LanguageIntervalEvidence,
    PdfProfile,
    StructureElement,
    TaggedDocument,
)


@dataclass(frozen=True)
class LanguageIntervalResolution:
    intervals: tuple[LanguageIntervalEvidence, ...]
    observed_interval_count: int
    diagnostic: Diagnostic | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.intervals, tuple) or not all(
            isinstance(interval, LanguageIntervalEvidence)
            for interval in self.intervals
        ):
            raise ValueError(
                "intervals must be a tuple of LanguageIntervalEvidence values"
            )
        if (
            not isinstance(self.observed_interval_count, int)
            or isinstance(self.observed_interval_count, bool)
            or self.observed_interval_count < 0
        ):
            raise ValueError("observed_interval_count must be a non-negative integer")
        if self.diagnostic is not None and not isinstance(self.diagnostic, Diagnostic):
            raise ValueError("diagnostic must be a Diagnostic or None")
        if self.diagnostic is None:
            if self.observed_interval_count != len(self.intervals):
                raise ValueError("successful resolution count must match its intervals")
        elif self.intervals:
            raise ValueError("failed resolution cannot contain fabricated intervals")


@dataclass(frozen=True)
class _ElementEvidence:
    path: tuple[int, ...]
    element: StructureElement
    pages: frozenset[int]


def resolve_language_intervals(
    profile: PdfProfile,
    document: TaggedDocument,
) -> LanguageIntervalResolution:
    """Resolve canonical language intervals from structural page evidence only."""
    try:
        if profile.language_count == 1:
            return LanguageIntervalResolution((), 0)
        if profile.doc_type == "BOOK":
            bounds = _validated_book_bounds(profile, document)
            try:
                elements = _structure_evidence(document)
                return _resolve_book(profile, bounds, document, elements)
            except _ResolutionFailure as failure:
                if failure.observed_interval_count is not None:
                    raise
                raise failure.with_observed_interval_count(len(bounds)) from failure
        elements = _structure_evidence(document)
        heading_pages = _heading_pages(document, elements)
        return _resolve_sheet(profile, elements, heading_pages)
    except _ResolutionFailure as failure:
        return LanguageIntervalResolution(
            (),
            failure.observed_interval_count or 0,
            Diagnostic("error", failure.code, failure.message, failure.context),
        )


class _ResolutionFailure(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        observed_interval_count: int | None,
        context: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.observed_interval_count = observed_interval_count
        self.context = context or {}

    def with_observed_interval_count(self, count: int) -> _ResolutionFailure:
        if self.observed_interval_count is not None:
            return self
        return _ResolutionFailure(self.code, self.message, count, self.context)


def _structure_evidence(document: TaggedDocument) -> tuple[_ElementEvidence, ...]:
    found: list[_ElementEvidence] = []

    def visit(
        children: tuple[StructureElement | ContentFragment, ...],
        parent_path: tuple[int, ...],
    ) -> frozenset[int]:
        subtree_pages: set[int] = set()
        for index, child in enumerate(children):
            child_path = (*parent_path, index)
            if isinstance(child, ContentFragment):
                subtree_pages.add(_valid_page_index(child.page_index, child_path))
                continue
            child_pages: set[int] = set()
            if child.page_index is not None:
                child_pages.add(_valid_page_index(child.page_index, child_path))
            child_pages.update(visit(child.children, child_path))
            frozen_pages = frozenset(child_pages)
            found.append(_ElementEvidence(child_path, child, frozen_pages))
            subtree_pages.update(child_pages)
        return frozenset(subtree_pages)

    visit(document.children, ())
    return tuple(sorted(found, key=lambda item: item.path))


def _valid_page_index(value: object, path: tuple[int, ...]) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise _ResolutionFailure(
            "language_interval_page_evidence_invalid",
            "Document structure contains invalid page evidence.",
            None,
            {"child_path": path},
        )
    return value


def _heading_pages(
    document: TaggedDocument,
    elements: tuple[_ElementEvidence, ...],
    known_interval_count: int | None = None,
) -> tuple[tuple[tuple[int, ...], int], ...]:
    by_path = {item.path: item for item in elements}
    heading_paths = {
        item.path for item in elements if item.element.semantic_role == "heading"
    }
    missing_promotion_paths = tuple(
        promotion.child_path
        for promotion in document.heading_promotions
        if promotion.child_path not in by_path
    )
    heading_paths.update(
        promotion.child_path
        for promotion in document.heading_promotions
        if promotion.child_path in by_path
    )

    first_evidence_failure: tuple[str, str, dict[str, object]] | None = None
    resolved: list[tuple[tuple[int, ...], int]] = []
    for path in sorted(heading_paths):
        pages = by_path[path].pages
        if not pages:
            if first_evidence_failure is None:
                first_evidence_failure = (
                    "language_interval_heading_page_evidence_missing",
                    "A source or promoted heading lacks page evidence.",
                    {"child_path": path},
                )
            continue
        if len(pages) > 1:
            if first_evidence_failure is None:
                first_evidence_failure = (
                    "language_interval_heading_page_evidence_ambiguous",
                    "A source or promoted heading spans multiple physical pages.",
                    {"child_path": path, "page_indices": tuple(sorted(pages))},
                )
            continue
        resolved.append((path, next(iter(pages))))

    observed_count = (
        known_interval_count
        if known_interval_count is not None
        else len({page for _, page in resolved})
    )
    if missing_promotion_paths:
        raise _ResolutionFailure(
            "language_interval_heading_path_missing",
            "A promoted heading path does not identify a StructureElement.",
            observed_count,
            {"child_path": missing_promotion_paths[0]},
        )
    if first_evidence_failure is not None:
        code, message, context = first_evidence_failure
        raise _ResolutionFailure(code, message, observed_count, context)
    if not heading_paths:
        raise _ResolutionFailure(
            "language_interval_heading_page_evidence_missing",
            "No source or promoted heading has page evidence.",
            observed_count,
        )
    return tuple(resolved)


def _validated_book_bounds(
    profile: PdfProfile,
    document: TaggedDocument,
) -> tuple[BookmarkPageBounds, ...]:
    bounds = document.bookmark_page_bounds
    if not bounds:
        raise _ResolutionFailure(
            "language_interval_bookmark_bounds_missing",
            "BOOK interval resolution requires raw bookmark page bounds.",
            0,
        )
    if len(bounds) != profile.language_count:
        raise _ResolutionFailure(
            "language_interval_bookmark_count_mismatch",
            "Bookmark count does not match the canonical language count.",
            len(bounds),
            {
                "expected_interval_count": profile.language_count,
                "observed_interval_count": len(bounds),
            },
        )
    if tuple(item.ordinal for item in bounds) != tuple(
        range(1, len(bounds) + 1)
    ) or any(
        previous.end_page_index >= current.start_page_index
        for previous, current in zip(bounds, bounds[1:])
    ):
        raise _ResolutionFailure(
            "language_interval_bookmark_order_invalid",
            "Bookmark page bounds must be strictly increasing in ordinal order.",
            len(bounds),
        )
    return bounds


def _resolve_book(
    profile: PdfProfile,
    bounds: tuple[BookmarkPageBounds, ...],
    document: TaggedDocument,
    elements: tuple[_ElementEvidence, ...],
) -> LanguageIntervalResolution:

    heading_pages = _heading_pages(document, elements, len(bounds))
    for path, page in heading_pages:
        memberships = tuple(
            index
            for index, bound in enumerate(bounds)
            if bound.start_page_index <= page <= bound.end_page_index
        )
        if len(memberships) != 1:
            raise _ResolutionFailure(
                "language_interval_heading_outside_bounds",
                "A heading is not contained in exactly one bookmark interval.",
                len(bounds),
                {"child_path": path, "page_index": page},
            )

    memberships = tuple(
        (item.path, _book_membership(item.pages, bounds)) for item in elements
    )
    path_bounds = _contiguous_path_bounds(
        memberships,
        tuple(range(len(bounds))),
        len(bounds),
    )
    intervals = tuple(
        LanguageIntervalEvidence(
            language=language,
            start_page_index=bound.start_page_index,
            end_page_index=bound.end_page_index,
            start_path=path_bounds[index][0],
            end_path=path_bounds[index][1],
            evidence_origin="bookmark",
        )
        for index, (language, bound) in enumerate(zip(profile.languages, bounds))
    )
    return LanguageIntervalResolution(intervals, len(intervals))


def _book_membership(
    pages: frozenset[int],
    bounds: tuple[BookmarkPageBounds, ...],
) -> int | None:
    if not pages:
        return None
    memberships = {
        index
        for page in pages
        for index, bound in enumerate(bounds)
        if bound.start_page_index <= page <= bound.end_page_index
    }
    if len(memberships) != 1:
        return None
    membership = next(iter(memberships))
    bound = bounds[membership]
    if all(bound.start_page_index <= page <= bound.end_page_index for page in pages):
        return membership
    return None


def _resolve_sheet(
    profile: PdfProfile,
    elements: tuple[_ElementEvidence, ...],
    heading_pages: tuple[tuple[tuple[int, ...], int], ...],
) -> LanguageIntervalResolution:
    pages = tuple(sorted({page for _, page in heading_pages}))
    if len(pages) != profile.language_count:
        raise _ResolutionFailure(
            "language_interval_heading_page_count_mismatch",
            "Distinct heading-bearing page count does not match the canonical language count.",
            len(pages),
            {
                "expected_interval_count": profile.language_count,
                "heading_page_indices": pages,
            },
        )

    page_to_index = {page: index for index, page in enumerate(pages)}
    memberships = tuple(
        (
            item.path,
            page_to_index[next(iter(item.pages))]
            if len(item.pages) == 1 and next(iter(item.pages)) in page_to_index
            else None,
        )
        for item in elements
    )
    path_bounds = _contiguous_path_bounds(
        memberships,
        tuple(range(len(pages))),
        len(pages),
    )
    intervals = tuple(
        LanguageIntervalEvidence(
            language=language,
            start_page_index=page,
            end_page_index=page,
            start_path=path_bounds[index][0],
            end_path=path_bounds[index][1],
            evidence_origin="structural_language_section",
        )
        for index, (language, page) in enumerate(zip(profile.languages, pages))
    )
    return LanguageIntervalResolution(intervals, len(intervals))


def _contiguous_path_bounds(
    memberships: tuple[tuple[tuple[int, ...], int | None], ...],
    expected_memberships: tuple[int, ...],
    observed_interval_count: int,
) -> dict[int, tuple[tuple[int, ...], tuple[int, ...]]]:
    membership_evidence = tuple(
        item for item in memberships if item[1] is not None
    )
    path_bounds: dict[int, tuple[tuple[int, ...], tuple[int, ...]]] = {}
    previous_end = -1
    for membership in expected_memberships:
        positions = tuple(
            index
            for index, (_, observed) in enumerate(membership_evidence)
            if observed == membership
        )
        if not positions or positions[0] <= previous_end or any(
            membership_evidence[index][1] != membership
            for index in range(positions[0], positions[-1] + 1)
        ):
            raise _ResolutionFailure(
                "language_interval_structure_ranges_invalid",
                "Structure paths do not prove ordered disjoint contiguous language ranges.",
                observed_interval_count,
                {"interval_ordinal": membership + 1},
            )
        path_bounds[membership] = (
            membership_evidence[positions[0]][0],
            membership_evidence[positions[-1]][0],
        )
        previous_end = positions[-1]
    return path_bounds
