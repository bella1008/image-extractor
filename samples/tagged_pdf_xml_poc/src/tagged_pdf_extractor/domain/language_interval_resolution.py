from __future__ import annotations

from dataclasses import dataclass

from tagged_pdf_extractor.domain.models import (
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
        if (
            not isinstance(self.observed_interval_count, int)
            or isinstance(self.observed_interval_count, bool)
            or self.observed_interval_count < 0
        ):
            raise ValueError("observed_interval_count must be a non-negative integer")
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
        elements = _structure_evidence(document)
        if profile.doc_type == "BOOK":
            return _resolve_book(profile, document, elements)
        heading_pages = _heading_pages(document, elements)
        return _resolve_sheet(profile, elements, heading_pages)
    except _ResolutionFailure as failure:
        return LanguageIntervalResolution(
            (),
            failure.observed_interval_count,
            Diagnostic("error", failure.code, failure.message, failure.context),
        )


class _ResolutionFailure(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        observed_interval_count: int,
        context: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.observed_interval_count = observed_interval_count
        self.context = context or {}


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
            0,
            {"child_path": path},
        )
    return value


def _heading_pages(
    document: TaggedDocument,
    elements: tuple[_ElementEvidence, ...],
) -> tuple[tuple[tuple[int, ...], int], ...]:
    by_path = {item.path: item for item in elements}
    heading_paths = {
        item.path for item in elements if item.element.semantic_role == "heading"
    }
    for promotion in document.heading_promotions:
        if promotion.child_path not in by_path:
            raise _ResolutionFailure(
                "language_interval_heading_path_missing",
                "A promoted heading path does not identify a StructureElement.",
                0,
                {"child_path": promotion.child_path},
            )
        heading_paths.add(promotion.child_path)

    if not heading_paths:
        raise _ResolutionFailure(
            "language_interval_heading_page_evidence_missing",
            "No source or promoted heading has page evidence.",
            0,
        )

    resolved: list[tuple[tuple[int, ...], int]] = []
    for path in sorted(heading_paths):
        pages = by_path[path].pages
        if not pages:
            raise _ResolutionFailure(
                "language_interval_heading_page_evidence_missing",
                "A source or promoted heading lacks page evidence.",
                0,
                {"child_path": path},
            )
        if len(pages) != 1:
            raise _ResolutionFailure(
                "language_interval_heading_page_evidence_ambiguous",
                "A source or promoted heading spans multiple physical pages.",
                0,
                {"child_path": path, "page_indices": tuple(sorted(pages))},
            )
        resolved.append((path, next(iter(pages))))
    return tuple(resolved)


def _resolve_book(
    profile: PdfProfile,
    document: TaggedDocument,
    elements: tuple[_ElementEvidence, ...],
) -> LanguageIntervalResolution:
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

    document_pages = {page for item in elements for page in item.pages}
    if not document_pages or bounds[-1].end_page_index > max(document_pages):
        raise _ResolutionFailure(
            "language_interval_bookmark_out_of_page",
            "Bookmark page bounds extend beyond observed document pages.",
            len(bounds),
        )

    heading_pages = _heading_pages(document, elements)
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
    bounds: tuple[object, ...],
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
    path_bounds: dict[int, tuple[tuple[int, ...], tuple[int, ...]]] = {}
    previous_end = -1
    for membership in expected_memberships:
        positions = tuple(
            index
            for index, (_, observed) in enumerate(memberships)
            if observed == membership
        )
        if not positions or positions[0] <= previous_end or any(
            memberships[index][1] != membership
            for index in range(positions[0], positions[-1] + 1)
        ):
            raise _ResolutionFailure(
                "language_interval_structure_ranges_invalid",
                "Structure paths do not prove ordered disjoint contiguous language ranges.",
                observed_interval_count,
                {"interval_ordinal": membership + 1},
            )
        path_bounds[membership] = (
            memberships[positions[0]][0],
            memberships[positions[-1]][0],
        )
        previous_end = positions[-1]
    return path_bounds
