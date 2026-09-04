from __future__ import annotations

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


_NUMBERED_LABEL = re.compile(r"^(?:0[1-9]|[1-9][0-9])$")
_PROMOTION_REASON = "numbered_chapter_structure_sequence_typography"


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


def promote_numbered_chapter_headings(document: TaggedDocument) -> TaggedDocument:
    visits, candidates = _scan_document(document)
    candidate_series = _group_series(candidates)
    audits: list[NumberedHeadingSeriesAudit] = []
    promotions: list[HeadingPromotion] = []
    diagnostics = list(document.diagnostics)

    for series_index, series in enumerate(candidate_series):
        labels = tuple(candidate.label for candidate in series)
        expected_labels = _expected_labels(labels)
        valid_sequence = len(series) >= 2 and labels == expected_labels
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
                        "actual_labels": labels,
                        "expected_labels": expected_labels,
                        "candidate_evidence": tuple(
                            {
                                "page_index": _candidate_page(candidate),
                                "child_path": candidate.child_path,
                            }
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
        for candidate in series:
            promotion, diagnostic = _evaluate_typography(
                candidate, series_index, body_font_size
            )
            if promotion is not None:
                promotions.append(promotion)
            if diagnostic is not None:
                diagnostics.append(diagnostic)

    consistency = _series_consistency(audits)
    if consistency is False:
        diagnostics.append(
            Diagnostic(
                severity="error",
                code="numbered_heading_series_count_mismatch",
                message="Numbered chapter heading series counts do not match.",
                context={
                    "series_counts": tuple(len(audit.labels) for audit in audits),
                    "labels_by_series": tuple(audit.labels for audit in audits),
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
    ) -> None:
        for child_index, child in enumerate(children):
            child_path = (*parent_path, child_index)
            if not isinstance(child, StructureElement):
                continue
            visit_index = len(visits)
            visits.append(_ElementVisit(child, child_path))
            candidate = _as_candidate(child, child_path, visit_index)
            if candidate is not None:
                candidates.append(candidate)
            visit_children(child.children, child_path)

    visit_children(document.children, ())
    return visits, candidates


def _as_candidate(
    element: StructureElement,
    child_path: tuple[int, ...],
    visit_index: int,
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
    return " ".join("".join(parts).split())


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
    count = max(2, len(labels))
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
    candidate: _Candidate, series_index: int, body_font_size: float | None
) -> tuple[HeadingPromotion | None, Diagnostic | None]:
    label_font_size = _weighted_median(_style_samples(candidate.label_element))
    list_body_font_size = _weighted_median(_style_samples(candidate.body_element))
    context = {
        "series_index": series_index,
        "label": candidate.label,
        "child_path": candidate.child_path,
        "page_index": _candidate_page(candidate),
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
    if relative_difference > 0.10:
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
    if ratio < 1.5:
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
        ),
        None,
    )


def _candidate_page(candidate: _Candidate) -> int | None:
    if candidate.element.page_index is not None:
        return candidate.element.page_index
    for fragment in _descendant_fragments(candidate.element):
        return fragment.page_index
    return None


def _descendant_fragments(
    element: StructureElement,
) -> tuple[ContentFragment, ...]:
    fragments: list[ContentFragment] = []
    for child in element.children:
        if isinstance(child, ContentFragment):
            fragments.append(child)
        else:
            fragments.extend(_descendant_fragments(child))
    return tuple(fragments)


def _series_consistency(
    audits: list[NumberedHeadingSeriesAudit],
) -> bool | None:
    if len(audits) < 2:
        return None
    counts = {len(audit.labels) for audit in audits}
    return len(counts) == 1
