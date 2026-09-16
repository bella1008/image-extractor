from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, replace
import math
import re

from tagged_pdf_extractor.domain.models import (
    ContentFragment,
    Diagnostic,
    HeadingPromotion,
    NumberedHeadingSeriesAudit,
    StructureElement,
    TaggedDocument,
)
from tagged_pdf_extractor.domain.text_joining import join_text_parts
from tagged_pdf_extractor.domain.profile_scope import parse_source_token


_NUMBERED_LABEL = re.compile(r"^(?:0[1-9]|[1-9][0-9])$")
_PROMOTION_REASON = "numbered_chapter_structure_sequence_typography"
_MIN_SERIES_CANDIDATES = 2
_MAX_LABEL_BODY_RELATIVE_DIFFERENCE = 0.10
_MIN_HEADING_BODY_RATIO = 1.5
_POLICY_BOUNDARY_REL_TOLERANCE = 1e-12
NUMBERED_HEADING_TYPOGRAPHY_DIAGNOSTIC_CODES = frozenset(
    {
        "numbered_heading_typography_insufficient",
        "numbered_heading_label_body_size_mismatch",
        "numbered_heading_font_ratio_below_threshold",
    }
)
_OWNED_DIAGNOSTIC_CODES = frozenset(
    {
        "numbered_heading_sequence_invalid",
        "numbered_heading_series_count_mismatch",
    }
) | NUMBERED_HEADING_TYPOGRAPHY_DIAGNOSTIC_CODES


@dataclass(frozen=True)
class _ElementVisit:
    element: StructureElement
    child_path: tuple[int, ...]


@dataclass(frozen=True)
class _Candidate:
    element: StructureElement
    child_path: tuple[int, ...]
    visit_index: int
    label_element: StructureElement
    body_element: StructureElement
    label: str
    title: str
    language: str | None


def promote_numbered_chapter_headings(document: TaggedDocument) -> TaggedDocument:
    visits, candidates = _scan_document(document)
    candidate_series = _group_series(candidates)
    audits: list[NumberedHeadingSeriesAudit] = []
    promotions: list[HeadingPromotion] = []
    diagnostics = [
        diagnostic
        for diagnostic in document.diagnostics
        if diagnostic.code not in _OWNED_DIAGNOSTIC_CODES
    ]

    for series_index, series in enumerate(candidate_series):
        labels = tuple(candidate.label for candidate in series)
        expected_labels = _expected_labels(labels)
        valid_sequence = (
            len(series) >= _MIN_SERIES_CANDIDATES and labels == expected_labels
        )
        audits.append(
            NumberedHeadingSeriesAudit(
                series_index=series_index,
                labels=labels,
                valid_sequence=valid_sequence,
            )
        )
        if not valid_sequence:
            diagnostics.append(
                Diagnostic(
                    severity="error",
                    code="numbered_heading_sequence_invalid",
                    message="Numbered chapter heading sequence is invalid.",
                    context={
                        "series_index": series_index,
                        "document_language": document.language,
                        "actual_labels": labels,
                        "expected_labels": expected_labels,
                        "candidate_evidence": tuple(
                            _candidate_evidence(candidate)
                            for candidate in series
                        ),
                    },
                )
            )
            continue

        next_series_start = _next_series_start(candidate_series, series_index, visits)
        body_font_size = _series_body_font_size(
            visits,
            series[0].visit_index,
            next_series_start,
            candidates,
        )
        body_font_names = _series_body_font_names(
            visits,
            series[0].visit_index,
            next_series_start,
            candidates,
        )
        for candidate in series:
            promotion, diagnostic = _evaluate_typography(
                candidate,
                series_index,
                body_font_size,
                body_font_names,
                document.language,
            )
            if promotion is not None:
                promotions.append(promotion)
            if diagnostic is not None:
                diagnostics.append(diagnostic)

    valid_audits = [audit for audit in audits if audit.valid_sequence]
    consistency = _series_consistency(valid_audits)
    if consistency is False:
        diagnostics.append(
            Diagnostic(
                severity="error",
                code="numbered_heading_series_count_mismatch",
                message="Numbered chapter heading series counts do not match.",
                context={
                    "document_language": document.language,
                    "series_counts": tuple(
                        len(audit.labels) for audit in valid_audits
                    ),
                    "labels_by_series": tuple(
                        audit.labels for audit in valid_audits
                    ),
                    "series_evidence": tuple(
                        {
                            "series_index": index,
                            "count": len(candidate_series[index]),
                            "labels": tuple(
                                candidate.label
                                for candidate in candidate_series[index]
                            ),
                            "candidates": tuple(
                                _candidate_evidence(candidate)
                                for candidate in candidate_series[index]
                            ),
                        }
                        for index, audit in enumerate(audits)
                        if audit.valid_sequence
                    ),
                },
            )
        )

    return replace(
        document,
        diagnostics=tuple(diagnostics),
        heading_promotions=tuple(promotions),
        numbered_heading_series=tuple(audits),
        numbered_heading_series_consistent=consistency,
    )


def _scan_document(
    document: TaggedDocument,
) -> tuple[list[_ElementVisit], list[_Candidate]]:
    visits: list[_ElementVisit] = []
    candidates: list[_Candidate] = []

    def visit_children(
        children: tuple[StructureElement | ContentFragment, ...],
        parent_path: tuple[int, ...],
        inherited_language: str | None,
    ) -> None:
        for child_index, child in enumerate(children):
            child_path = (*parent_path, child_index)
            if not isinstance(child, StructureElement):
                continue
            language = child.language or inherited_language
            visit_index = len(visits)
            visits.append(_ElementVisit(child, child_path))
            candidate = _as_candidate(
                child, child_path, visit_index, language=language,
                compact_numeric_label=(document.raw_children is not None
                    and parse_source_token(document.source_path.name) in {"AFRICA_L05", "TK_ARA", "MENA_L02"}
                    and language == "ARA"),
            )
            if candidate is not None:
                candidates.append(candidate)
            visit_children(child.children, child_path, language)

    visit_children(document.children, (), document.language)
    return visits, candidates


def _as_candidate(
    element: StructureElement,
    child_path: tuple[int, ...],
    visit_index: int,
    *,
    language: str | None,
    compact_numeric_label: bool = False,
) -> _Candidate | None:
    if element.semantic_role != "list_item":
        return None
    label_children = tuple(
        child
        for child in element.children
        if isinstance(child, StructureElement) and child.semantic_role == "label"
    )
    body_children = tuple(
        child
        for child in element.children
        if isinstance(child, StructureElement) and child.semantic_role == "list_body"
    )
    if len(label_children) != 1 or len(body_children) != 1:
        return None
    label = _normalized_text(label_children[0])
    if compact_numeric_label:
        # Two PDF-authored digits in separate RTL spans form one chapter label.
        # Sequence and relative typography must still pass the existing gate.
        compact = "".join(label.split())
        if re.fullmatch(r"0[1-9]", compact):
            label = compact
    title = _normalized_text(body_children[0])
    if _NUMBERED_LABEL.fullmatch(label) is None or not title:
        return None
    return _Candidate(
        element=element,
        child_path=child_path,
        visit_index=visit_index,
        label_element=label_children[0],
        body_element=body_children[0],
        label=label,
        title=title,
        language=language,
    )


def _normalized_text(element: StructureElement) -> str:
    parts: list[str] = []

    def collect(children: tuple[StructureElement | ContentFragment, ...]) -> None:
        for child in children:
            if isinstance(child, ContentFragment):
                parts.extend(child.text_parts)
            else:
                collect(child.children)

    collect(element.children)
    joined, _ = join_text_parts(tuple(parts))
    return " ".join(joined.split())


def _group_series(candidates: list[_Candidate]) -> list[list[_Candidate]]:
    series: list[list[_Candidate]] = []
    current: list[_Candidate] = []
    for candidate in candidates:
        if candidate.label == "01":
            if current:
                series.append(current)
            current = [candidate]
        else:
            current.append(candidate)
    if current:
        series.append(current)
    return series


def _expected_labels(labels: tuple[str, ...]) -> tuple[str, ...]:
    count = max(_MIN_SERIES_CANDIDATES, len(labels))
    return tuple(f"{number:02d}" for number in range(1, count + 1))


def _next_series_start(
    series: list[list[_Candidate]], series_index: int, visits: list[_ElementVisit]
) -> int:
    if series_index + 1 < len(series):
        return series[series_index + 1][0].visit_index
    return len(visits)


def _series_body_font_size(
    visits: list[_ElementVisit],
    start: int,
    end: int,
    candidates: list[_Candidate],
) -> float | None:
    excluded_paths = tuple(
        candidate.child_path
        for candidate in candidates
        if start <= candidate.visit_index < end
    )
    samples: list[tuple[float, int]] = []
    for visit in visits[start:end]:
        if visit.element.semantic_role != "paragraph":
            continue
        if any(_is_at_or_below(visit.child_path, path) for path in excluded_paths):
            continue
        samples.extend(
            _style_samples_excluding(
                visit.element,
                visit.child_path,
                excluded_paths,
            )
        )
    return _weighted_median(samples)


def _series_body_font_names(
    visits: list[_ElementVisit],
    start: int,
    end: int,
    candidates: list[_Candidate],
) -> tuple[str, ...]:
    excluded_paths = tuple(
        candidate.child_path
        for candidate in candidates
        if start <= candidate.visit_index < end
    )
    names: list[str] = []
    for visit in visits[start:end]:
        if visit.element.semantic_role != "paragraph":
            continue
        if any(_is_at_or_below(visit.child_path, path) for path in excluded_paths):
            continue
        names.extend(
            _font_names_excluding(
                visit.element,
                visit.child_path,
                excluded_paths,
            )
        )
    return _unique_names(names)


def _is_at_or_below(path: tuple[int, ...], ancestor: tuple[int, ...]) -> bool:
    return path[: len(ancestor)] == ancestor


def _style_samples(element: StructureElement) -> list[tuple[float, int]]:
    samples: list[tuple[float, int]] = []

    def collect(children: tuple[StructureElement | ContentFragment, ...]) -> None:
        for child in children:
            if isinstance(child, StructureElement):
                collect(child.children)
                continue
            for text, style in zip(child.text_parts, child.text_styles):
                size = style.font_size
                if (
                    text
                    and size is not None
                    and math.isfinite(size)
                    and size > 0
                ):
                    samples.append((size, len(text)))

    collect(element.children)
    return samples


def _style_samples_excluding(
    element: StructureElement,
    element_path: tuple[int, ...],
    excluded_paths: tuple[tuple[int, ...], ...],
) -> list[tuple[float, int]]:
    samples: list[tuple[float, int]] = []

    def collect(
        children: tuple[StructureElement | ContentFragment, ...],
        parent_path: tuple[int, ...],
    ) -> None:
        for child_index, child in enumerate(children):
            child_path = (*parent_path, child_index)
            if any(_is_at_or_below(child_path, path) for path in excluded_paths):
                continue
            if isinstance(child, StructureElement):
                collect(child.children, child_path)
                continue
            for text, style in zip(child.text_parts, child.text_styles):
                size = style.font_size
                if (
                    text
                    and size is not None
                    and math.isfinite(size)
                    and size > 0
                ):
                    samples.append((size, len(text)))

    collect(element.children, element_path)
    return samples


def _font_names(element: StructureElement) -> list[str]:
    names: list[str] = []

    def collect(children: tuple[StructureElement | ContentFragment, ...]) -> None:
        for child in children:
            if isinstance(child, StructureElement):
                collect(child.children)
                continue
            for text, style in zip(child.text_parts, child.text_styles):
                if text and _valid_style_size(style.font_size) and style.font_name:
                    names.append(style.font_name)

    collect(element.children)
    return names


def _font_names_excluding(
    element: StructureElement,
    element_path: tuple[int, ...],
    excluded_paths: tuple[tuple[int, ...], ...],
) -> list[str]:
    names: list[str] = []

    def collect(
        children: tuple[StructureElement | ContentFragment, ...],
        parent_path: tuple[int, ...],
    ) -> None:
        for child_index, child in enumerate(children):
            child_path = (*parent_path, child_index)
            if any(_is_at_or_below(child_path, path) for path in excluded_paths):
                continue
            if isinstance(child, StructureElement):
                collect(child.children, child_path)
                continue
            for text, style in zip(child.text_parts, child.text_styles):
                if text and _valid_style_size(style.font_size) and style.font_name:
                    names.append(style.font_name)

    collect(element.children, element_path)
    return names


def _valid_style_size(size: float | None) -> bool:
    return size is not None and math.isfinite(size) and size > 0


def _unique_names(names: Iterator[str] | list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(names))


def _weighted_median(samples: list[tuple[float, int]]) -> float | None:
    if not samples:
        return None
    ordered = sorted(samples)
    threshold = sum(weight for _, weight in ordered) / 2
    cumulative = 0
    for size, weight in ordered:
        cumulative += weight
        if cumulative >= threshold:
            return size
    raise AssertionError("weighted median samples must have positive total weight")


def _evaluate_typography(
    candidate: _Candidate,
    series_index: int,
    body_font_size: float | None,
    body_font_names: tuple[str, ...],
    document_language: str | None,
) -> tuple[HeadingPromotion | None, Diagnostic | None]:
    label_font_size = _weighted_median(_style_samples(candidate.label_element))
    list_body_font_size = _weighted_median(_style_samples(candidate.body_element))
    context = {
        "series_index": series_index,
        "document_language": document_language,
        **_candidate_evidence(candidate),
        "label_font_size": label_font_size,
        "list_body_font_size": list_body_font_size,
        "body_font_size": body_font_size,
    }
    if (
        body_font_size is None
        or label_font_size is None
        or list_body_font_size is None
    ):
        return None, Diagnostic(
            "error",
            "numbered_heading_typography_insufficient",
            "Numbered chapter heading typography is incomplete.",
            context,
        )

    relative_difference = abs(label_font_size - list_body_font_size) / max(
        label_font_size, list_body_font_size
    )
    heading_font_size = min(label_font_size, list_body_font_size)
    ratio = heading_font_size / body_font_size
    if _strictly_above_policy_boundary(
        relative_difference, _MAX_LABEL_BODY_RELATIVE_DIFFERENCE
    ):
        return None, Diagnostic(
            "error",
            "numbered_heading_label_body_size_mismatch",
            "Numbered chapter label and title font sizes do not match.",
            {
                **context,
                "heading_font_size": heading_font_size,
                "relative_difference": relative_difference,
                "font_size_ratio": ratio,
            },
        )
    if _strictly_below_policy_boundary(ratio, _MIN_HEADING_BODY_RATIO):
        return None, Diagnostic(
            "error",
            "numbered_heading_font_ratio_below_threshold",
            "Numbered chapter heading font ratio is below the threshold.",
            {
                **context,
                "heading_font_size": heading_font_size,
                "font_size_ratio": ratio,
            },
        )
    return (
        HeadingPromotion(
            child_path=candidate.child_path,
            level=2,
            label=candidate.label,
            title=candidate.title,
            series_index=series_index,
            heading_font_size=heading_font_size,
            body_font_size=body_font_size,
            font_size_ratio=ratio,
            promotion_reason=_PROMOTION_REASON,
            heading_font_names=_unique_names(
                [
                    *_font_names(candidate.label_element),
                    *_font_names(candidate.body_element),
                ]
            ),
            body_font_names=body_font_names,
        ),
        None,
    )


def _candidate_page(candidate: _Candidate) -> int | None:
    if candidate.element.page_index is not None:
        return candidate.element.page_index
    return next(_descendant_fragment_pages(candidate.element), None)


def _candidate_evidence(candidate: _Candidate) -> dict[str, object]:
    page_indices = _unique_in_order(
        (
            *((candidate.element.page_index,) if candidate.element.page_index is not None else ()),
            *_descendant_fragment_pages(candidate.element),
        )
    )
    mcids = _unique_in_order(_descendant_fragment_mcids(candidate.element))
    return {
        "language": candidate.language,
        "page_index": _candidate_page(candidate),
        "page_indices": page_indices,
        "mcid": mcids[0] if mcids else None,
        "mcids": mcids,
        "label": candidate.label,
        "child_path": candidate.child_path,
    }


def _descendant_fragment_pages(element: StructureElement) -> Iterator[int]:
    for child in element.children:
        if isinstance(child, ContentFragment):
            yield child.page_index
        else:
            yield from _descendant_fragment_pages(child)


def _descendant_fragment_mcids(element: StructureElement) -> Iterator[int]:
    for child in element.children:
        if isinstance(child, ContentFragment):
            if child.mcid is not None:
                yield child.mcid
        else:
            yield from _descendant_fragment_mcids(child)


def _unique_in_order(values: Iterator[int] | tuple[int, ...]) -> tuple[int, ...]:
    return tuple(dict.fromkeys(values))


def _strictly_above_policy_boundary(value: float, boundary: float) -> bool:
    return value > boundary and not math.isclose(
        value,
        boundary,
        rel_tol=_POLICY_BOUNDARY_REL_TOLERANCE,
        abs_tol=0.0,
    )


def _strictly_below_policy_boundary(value: float, boundary: float) -> bool:
    return value < boundary and not math.isclose(
        value,
        boundary,
        rel_tol=_POLICY_BOUNDARY_REL_TOLERANCE,
        abs_tol=0.0,
    )


def _series_consistency(
    audits: list[NumberedHeadingSeriesAudit],
) -> bool | None:
    if len(audits) < 2:
        return None
    counts = {len(audit.labels) for audit in audits}
    return len(counts) == 1
