from __future__ import annotations

import re
import sys
import unicodedata
from bisect import bisect_left
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from tagged_pdf_extractor.domain.models import (
    ContentFragment,
    Diagnostic,
    QualityReport,
    StructureElement,
    TaggedDocument,
)
from tagged_pdf_extractor.domain.quality_diagnostics import (
    EXTRACTION_LOSS_DIAGNOSTIC_CODES,
    UNRESOLVED_REFERENCE_DIAGNOSTIC_CODES,
)
from tagged_pdf_extractor.domain.text_joining import join_text_parts


_BODY_ROLES = frozenset(
    {
        "paragraph",
        "list",
        "list_item",
        "label",
        "list_body",
        "table",
        "table_row",
        "table_header",
        "table_cell",
        "figure",
        "caption",
        "span",
        "link",
    }
)
_SPECIAL_CHARACTERS = ">→/&:[]()"
_WHITESPACE = re.compile(r"\s+")
_HEADING_CANDIDATE = re.compile(
    r"heading(?:(?P<level>[1-6])(?=$|\D)|$)", re.IGNORECASE
)
_TITLE_CANDIDATE = re.compile(r"(?:^|[_-])title$", re.IGNORECASE)
_BIT_MASK_MEMORY_BUDGET_BYTES = 64 * 1024 * 1024
_SPARSE_MATCH_PAIR_BUDGET = 10_000_000
_SPARSE_MEMORY_BUDGET_BYTES = 16 * 1024 * 1024
_PREPASS_MEMORY_BUDGET_BYTES = 64 * 1024 * 1024
_PREPASS_CHECK_INTERVAL = 1_024


class QualityEvaluationLimitError(RuntimeError):
    def __init__(
        self,
        *,
        baseline_length: int,
        tagged_length: int,
        mask_estimate: int,
        mask_budget: int,
        match_pair_estimate: int,
        match_pair_budget: int,
        sparse_memory_estimate: int = 0,
        sparse_memory_budget: int = _SPARSE_MEMORY_BUDGET_BYTES,
        prepass_memory_estimate: int = 0,
        prepass_memory_budget: int = _PREPASS_MEMORY_BUDGET_BYTES,
        reason: str = "exact_backend_resource_budget",
    ) -> None:
        self.baseline_length = baseline_length
        self.tagged_length = tagged_length
        self.mask_estimate = mask_estimate
        self.mask_budget = mask_budget
        self.match_pair_estimate = match_pair_estimate
        self.match_pair_budget = match_pair_budget
        self.sparse_memory_estimate = sparse_memory_estimate
        self.sparse_memory_budget = sparse_memory_budget
        self.prepass_memory_estimate = prepass_memory_estimate
        self.prepass_memory_budget = prepass_memory_budget
        self.reason = reason
        super().__init__(
            f"Exact LCS resource limit exceeded ({reason}): "
            f"baseline_length={baseline_length}, tagged_length={tagged_length}, "
            f"mask_estimate={mask_estimate}, mask_budget={mask_budget}, "
            f"match_pair_estimate={match_pair_estimate}, "
            f"match_pair_budget={match_pair_budget}, "
            f"sparse_memory_estimate={sparse_memory_estimate}, "
            f"sparse_memory_budget={sparse_memory_budget}, "
            f"prepass_memory_estimate={prepass_memory_estimate}, "
            f"prepass_memory_budget={prepass_memory_budget}"
        )


def _is_xml_10_character(character: str) -> bool:
    code_point = ord(character)
    return (
        code_point in {0x09, 0x0A, 0x0D}
        or 0x20 <= code_point <= 0xD7FF
        or 0xE000 <= code_point <= 0xFFFD
        or 0x10000 <= code_point <= 0x10FFFF
    )


@dataclass
class _Traversal:
    element_count: int = 0
    fragment_count: int = 0
    heading_count: int = 0
    body_count: int = 0
    body_role_node_count: int = 0
    unknown_role_count: int = 0
    empty_element_count: int = 0
    tagged_fragments: list[str] = field(default_factory=list)
    join_decisions: list[dict[str, Any]] = field(default_factory=list)
    forbidden_xml_control_count: int = 0
    forbidden_xml_control_field_count: int = 0
    source_role_counts: Counter[str] = field(default_factory=Counter)
    heading_hierarchy: list[dict[str, Any]] = field(default_factory=list)

    def count_text_field(self, value: str | None) -> None:
        if value is None:
            return
        count = sum(not _is_xml_10_character(character) for character in value)
        self.forbidden_xml_control_count += count
        self.forbidden_xml_control_field_count += count > 0


@dataclass(frozen=True)
class _Comparison:
    ratio: float
    mode: str
    parameters: dict[str, Any]


class QualityEvaluator:
    def evaluate(
        self,
        document: TaggedDocument,
        baseline_text: str,
        xml_round_trip_ok: bool,
    ) -> QualityReport:
        traversal = _Traversal()
        traversal.count_text_field(str(document.source_path))
        traversal.count_text_field(document.language)
        for source_role, mapped_role in document.role_map:
            traversal.count_text_field(source_role)
            traversal.count_text_field(mapped_role)

        self._walk(document.children, "", traversal)
        tagged_text = " ".join(
            fragment for fragment in traversal.tagged_fragments if fragment
        )
        normalized_tagged = self._normalize_for_measurement(tagged_text)
        normalized_baseline = self._normalize_for_measurement(baseline_text)
        comparison = self._character_match_ratio(
            normalized_tagged, normalized_baseline
        )

        reference_counts = Counter(
            diagnostic.code
            for diagnostic in document.diagnostics
            if diagnostic.code in UNRESOLVED_REFERENCE_DIAGNOSTIC_CODES
        )
        unresolved = tuple(
            diagnostic
            for diagnostic in document.diagnostics
            if diagnostic.code in UNRESOLVED_REFERENCE_DIAGNOSTIC_CODES
        )
        extraction_loss_counts = Counter(
            diagnostic.code
            for diagnostic in document.diagnostics
            if diagnostic.code in EXTRACTION_LOSS_DIAGNOSTIC_CODES
        )
        special_characters = {
            character: {
                "tagged": normalized_tagged.count(character),
                "baseline": normalized_baseline.count(character),
                "count_preserved": (
                    normalized_baseline.count(character) == 0
                    or normalized_tagged.count(character)
                    >= normalized_baseline.count(character)
                ),
            }
            for character in _SPECIAL_CHARACTERS
        }
        hard_gates = {
            "is_marked": document.marked,
            "has_structure": traversal.element_count > 0,
            "has_heading": traversal.heading_count > 0,
            "has_body": traversal.body_count > 0,
            "xml_round_trip": xml_round_trip_ok,
            "resolved_references": not unresolved,
            "resolved_references_reported": all(
                self._has_useful_reference_context(diagnostic)
                for diagnostic in unresolved
            ),
            "no_known_text_loss": not extraction_loss_counts,
            "special_character_counts_preserved": all(
                result["count_preserved"]
                for result in special_characters.values()
            ),
        }
        metrics = {
            "element_count": traversal.element_count,
            "fragment_count": traversal.fragment_count,
            "heading_count": traversal.heading_count,
            "body_count": traversal.body_count,
            "body_role_node_count": traversal.body_role_node_count,
            "unknown_role_count": traversal.unknown_role_count,
            "empty_element_count": traversal.empty_element_count,
            "unresolved_mcid_count": reference_counts["unresolved_mcid"],
            "unresolved_page_reference_count": reference_counts[
                "unresolved_page_reference"
            ],
            "unsupported_objr_count": reference_counts["unsupported_objr"],
            "unresolved_reference_count": sum(reference_counts.values()),
            "extraction_loss_diagnostic_counts": {
                code: extraction_loss_counts[code]
                for code in EXTRACTION_LOSS_DIAGNOSTIC_CODES
            },
            "extraction_loss_diagnostic_total": sum(
                extraction_loss_counts.values()
            ),
            "character_match_ratio": comparison.ratio,
            "comparison_mode": comparison.mode,
            "comparison_parameters": comparison.parameters,
            "tagged_character_count": len(normalized_tagged),
            "baseline_character_count": len(normalized_baseline),
            "special_characters": special_characters,
            "forbidden_xml_control_count": traversal.forbidden_xml_control_count,
            "forbidden_xml_control_field_count": (
                traversal.forbidden_xml_control_field_count
            ),
        }
        return QualityReport(
            status="pass" if all(hard_gates.values()) else "fail",
            metrics=metrics,
            hard_gates=hard_gates,
            diagnostics=document.diagnostics,
            join_decisions=tuple(traversal.join_decisions),
            source_path=document.source_path,
            language=document.language,
            marked=document.marked,
            role_map=tuple(sorted(document.role_map)),
            source_role_counts=dict(sorted(traversal.source_role_counts.items())),
            heading_hierarchy=tuple(traversal.heading_hierarchy),
        )

    def _walk(
        self,
        children: tuple[StructureElement | ContentFragment, ...],
        parent_path: str,
        traversal: _Traversal,
    ) -> bool:
        has_descendant_text = False
        for child_index, child in enumerate(children):
            if isinstance(child, ContentFragment):
                traversal.fragment_count += 1
                for text_part in child.text_parts:
                    traversal.count_text_field(text_part)
                text, decisions = join_text_parts(child.text_parts)
                traversal.tagged_fragments.append(text)
                has_descendant_text = has_descendant_text or bool(text.strip())
                for decision in decisions:
                    traversal.join_decisions.append(
                        {
                            "page_index": child.page_index,
                            "mcid": child.mcid,
                            "element_path": parent_path or "/",
                            "fragment_child_index": child_index,
                            **decision,
                        }
                    )
                continue

            traversal.element_count += 1
            traversal.source_role_counts[child.source_role] += 1
            traversal.heading_count += child.semantic_role == "heading"
            is_body_role = child.semantic_role in _BODY_ROLES
            traversal.body_role_node_count += is_body_role
            traversal.unknown_role_count += child.semantic_role == "unknown"
            self._count_element_text_fields(child, traversal)
            element_path = f"{parent_path}/{child.semantic_role}[{child_index}]"
            fragment_start = len(traversal.tagged_fragments)
            heading_entry_index: int | None = None
            if child.semantic_role == "heading" or self._is_heading_candidate(
                child.source_role
            ):
                heading_entry_index = len(traversal.heading_hierarchy)
                traversal.heading_hierarchy.append({})
            element_has_text = self._walk(child.children, element_path, traversal)
            if heading_entry_index is not None:
                match = _HEADING_CANDIDATE.search(child.source_role)
                candidate_level = (
                    int(match.group("level"))
                    if match and match.group("level")
                    else None
                )
                traversal.heading_hierarchy[heading_entry_index] = {
                    "structure_path": element_path,
                    "source_role": child.source_role,
                    "semantic_role": child.semantic_role,
                    "level": (
                        child.heading_level
                        if child.semantic_role == "heading"
                        else candidate_level
                    ),
                    "joined_text": " ".join(
                        text
                        for text in traversal.tagged_fragments[fragment_start:]
                        if text
                    ),
                    "title": child.title,
                    "classification": (
                        "heading"
                        if child.semantic_role == "heading"
                        else "source_role_candidate"
                    ),
                }
            traversal.body_count += is_body_role and element_has_text
            traversal.empty_element_count += not element_has_text
            has_descendant_text = has_descendant_text or element_has_text
        return has_descendant_text

    @staticmethod
    def _count_element_text_fields(
        element: StructureElement, traversal: _Traversal
    ) -> None:
        for value in (
            element.source_role,
            element.semantic_role,
            element.object_ref,
            element.title,
            element.language,
            element.alternate_text,
            element.actual_text,
        ):
            traversal.count_text_field(value)
        for name, value in element.attributes:
            traversal.count_text_field(name)
            traversal.count_text_field(value)

    @staticmethod
    def _normalize_for_measurement(text: str) -> str:
        return _WHITESPACE.sub(" ", unicodedata.normalize("NFC", text)).strip()

    @staticmethod
    def _character_match_ratio(
        tagged_text: str, baseline_text: str
    ) -> _Comparison:
        matched, mode, parameters = QualityEvaluator._exact_lcs_length(
            baseline_text, tagged_text
        )
        return _Comparison(
            ratio=(
                matched / len(baseline_text)
                if baseline_text
                else 1.0 if not tagged_text else 0.0
            ),
            mode=mode,
            parameters=parameters,
        )

    @staticmethod
    def _exact_lcs_length(
        baseline_text: str, tagged_text: str
    ) -> tuple[int, str, dict[str, Any]]:
        """Select a resource-bounded exact LCS backend for every input size.

        Full-document ``SequenceMatcher(autojunk=False)`` took about 224 seconds
        on the POC sample, while bounded alignment windows proved inexact after
        insertions and deletions. A bigint bitset is used when its measured mask
        estimate fits the memory budget. Otherwise exact sparse
        Hunt-Szymanski/LIS is used only when its match-pair operation count fits
        a fixed budget; no approximate fallback is permitted.
        """
        if len(baseline_text) <= len(tagged_text):
            indexed_text, iterated_text = baseline_text, tagged_text
        else:
            indexed_text, iterated_text = tagged_text, baseline_text

        memory = QualityEvaluator._estimate_bit_mask_memory(
            indexed_text,
            baseline_length=len(baseline_text),
            tagged_length=len(tagged_text),
        )
        indexed_counts, count_prepass_bytes = QualityEvaluator._count_characters(
            indexed_text,
            baseline_length=len(baseline_text),
            tagged_length=len(tagged_text),
        )
        # One Counter is sufficient for the exact pair count. Scanning the
        # other string avoids retaining two potentially large maps at once.
        match_pair_count = sum(
            indexed_counts.get(character, 0) for character in iterated_text
        )
        sparse_memory = QualityEvaluator._estimate_sparse_memory(
            indexed_counts,
            indexed_length=len(indexed_text),
            iterated_length=len(iterated_text),
        )
        del indexed_counts

        common_parameters = {
            "indexed_dimension": "shorter",
            "indexed_length": len(indexed_text),
            "iterated_length": len(iterated_text),
            **memory,
            "mask_memory_budget_bytes": _BIT_MASK_MEMORY_BUDGET_BYTES,
            "prepass_memory_peak_bytes": max(
                memory["prepass_memory_bytes"], count_prepass_bytes
            ),
            "prepass_memory_budget_bytes": _PREPASS_MEMORY_BUDGET_BYTES,
            "match_pair_count": match_pair_count,
            "sparse_match_pair_budget": _SPARSE_MATCH_PAIR_BUDGET,
            **sparse_memory,
            "sparse_memory_budget_bytes": _SPARSE_MEMORY_BUDGET_BYTES,
        }
        if memory["estimated_mask_bytes"] <= _BIT_MASK_MEMORY_BUDGET_BYTES:
            return (
                QualityEvaluator._bit_parallel_lcs(indexed_text, iterated_text),
                "bit_parallel_lcs",
                {**common_parameters, "bitset_dimension": "shorter"},
            )
        if (
            match_pair_count <= _SPARSE_MATCH_PAIR_BUDGET
            and sparse_memory["estimated_sparse_bytes"]
            <= _SPARSE_MEMORY_BUDGET_BYTES
        ):
            return (
                QualityEvaluator._sparse_lcs(indexed_text, iterated_text),
                "sparse_lcs",
                {**common_parameters, "fallback_reason": "bit_mask_memory_bound"},
            )
        raise QualityEvaluationLimitError(
            baseline_length=len(baseline_text),
            tagged_length=len(tagged_text),
            mask_estimate=memory["estimated_mask_bytes"],
            mask_budget=_BIT_MASK_MEMORY_BUDGET_BYTES,
            match_pair_estimate=match_pair_count,
            match_pair_budget=_SPARSE_MATCH_PAIR_BUDGET,
            sparse_memory_estimate=sparse_memory["estimated_sparse_bytes"],
            sparse_memory_budget=_SPARSE_MEMORY_BUDGET_BYTES,
        )

    @staticmethod
    def _estimate_bit_mask_memory(
        indexed_text: str,
        *,
        baseline_length: int | None = None,
        tagged_length: int | None = None,
    ) -> dict[str, int]:
        """Measure the final mask table without retaining prepass state.

        Each mask's highest set bit is its character's final occurrence, so a
        one-bit integer at that position has the same runtime size as the final
        mask. ``sys.getsizeof(max_positions)`` supplies the dictionary table
        size for the same keys/cardinality. This prepass dictionary is released
        when the function returns, before the real masks are allocated.
        """
        max_positions: dict[str, int] = {}
        key_bytes = 0
        position_value_bytes = 0
        peak_prepass_bytes = 0
        for position, character in enumerate(indexed_text):
            previous = max_positions.get(character)
            if previous is None:
                key_bytes += sys.getsizeof(character)
            else:
                position_value_bytes -= sys.getsizeof(previous)
            max_positions[character] = position
            position_value_bytes += sys.getsizeof(position)
            if (position + 1) % _PREPASS_CHECK_INTERVAL == 0:
                peak_prepass_bytes = QualityEvaluator._guard_prepass_memory(
                    max_positions,
                    key_bytes,
                    position_value_bytes,
                    (
                        baseline_length
                        if baseline_length is not None
                        else len(indexed_text)
                    ),
                    (
                        tagged_length
                        if tagged_length is not None
                        else len(indexed_text)
                    ),
                )
        peak_prepass_bytes = max(
            peak_prepass_bytes,
            QualityEvaluator._guard_prepass_memory(
                max_positions,
                key_bytes,
                position_value_bytes,
                (
                    baseline_length
                    if baseline_length is not None
                    else len(indexed_text)
                ),
                tagged_length if tagged_length is not None else len(indexed_text),
            ),
        )
        dictionary_bytes = sys.getsizeof(max_positions)
        mask_value_bytes = sum(
            sys.getsizeof(1 << position) for position in max_positions.values()
        )
        mask_storage_bytes = dictionary_bytes + key_bytes + mask_value_bytes
        # The update expression retains the prior state and ``x`` while
        # creating shifted/subtraction intermediates. Four maximum-width ints
        # conservatively cover that concurrent working set.
        algorithm_working_bytes = 4 * sys.getsizeof(
            (1 << len(indexed_text)) - 1
        )
        return {
            "unique_character_count": len(max_positions),
            "mask_dictionary_bytes": dictionary_bytes,
            "mask_key_bytes": key_bytes,
            "mask_value_bytes": mask_value_bytes,
            "mask_storage_bytes": mask_storage_bytes,
            "algorithm_working_bytes": algorithm_working_bytes,
            "estimated_mask_bytes": mask_storage_bytes + algorithm_working_bytes,
            "prepass_memory_bytes": peak_prepass_bytes,
        }

    @staticmethod
    def _guard_prepass_memory(
        mapping: dict[str, int],
        key_bytes: int,
        value_bytes: int,
        baseline_length: int,
        tagged_length: int,
    ) -> int:
        estimate = sys.getsizeof(mapping) + key_bytes + value_bytes
        if estimate > _PREPASS_MEMORY_BUDGET_BYTES:
            raise QualityEvaluationLimitError(
                baseline_length=baseline_length,
                tagged_length=tagged_length,
                mask_estimate=0,
                mask_budget=_BIT_MASK_MEMORY_BUDGET_BYTES,
                match_pair_estimate=0,
                match_pair_budget=_SPARSE_MATCH_PAIR_BUDGET,
                prepass_memory_estimate=estimate,
                prepass_memory_budget=_PREPASS_MEMORY_BUDGET_BYTES,
                reason="prepass_memory_budget",
            )
        return estimate

    @staticmethod
    def _count_characters(
        text: str,
        *,
        baseline_length: int,
        tagged_length: int,
    ) -> tuple[Counter[str], int]:
        counts: Counter[str] = Counter()
        key_bytes = 0
        value_bytes = 0
        peak_bytes = 0
        for position, character in enumerate(text):
            previous = counts.get(character, 0)
            if previous == 0:
                key_bytes += sys.getsizeof(character)
            else:
                value_bytes -= sys.getsizeof(previous)
            current = previous + 1
            counts[character] = current
            value_bytes += sys.getsizeof(current)
            if (position + 1) % _PREPASS_CHECK_INTERVAL == 0:
                peak_bytes = QualityEvaluator._guard_prepass_memory(
                    counts,
                    key_bytes,
                    value_bytes,
                    baseline_length,
                    tagged_length,
                )
        peak_bytes = max(
            peak_bytes,
            QualityEvaluator._guard_prepass_memory(
                counts,
                key_bytes,
                value_bytes,
                baseline_length,
                tagged_length,
            ),
        )
        return counts, peak_bytes

    @staticmethod
    def _estimate_sparse_memory(
        counts: Counter[str], *, indexed_length: int, iterated_length: int
    ) -> dict[str, int]:
        """Conservatively bound all owned Hunt-Szymanski structures.

        Position lists use a two-times slot allowance plus 16 slots per list,
        which safely exceeds CPython's normal append overallocation. Position
        integers and a worst-case increasing-tails list are counted separately.
        The temporary Counter is released before any of these structures are
        allocated, so it is reported as prepass memory rather than concurrent
        sparse storage.
        """
        empty_list_bytes = sys.getsizeof([])
        pointer_bytes = sys.getsizeof([None]) - empty_list_bytes
        position_lists_bytes = sum(
            empty_list_bytes + (2 * count + 16) * pointer_bytes
            for count in counts.values()
        )
        dictionary_bytes = sys.getsizeof(counts)
        key_bytes = sum(sys.getsizeof(character) for character in counts)
        position_integer_bytes = indexed_length * sys.getsizeof(
            max(0, indexed_length - 1)
        )
        tails_length = min(indexed_length, iterated_length)
        tails_bytes = (
            empty_list_bytes
            + (2 * tails_length + 16) * pointer_bytes
            + tails_length * sys.getsizeof(max(0, indexed_length - 1))
        )
        estimated = (
            dictionary_bytes
            + key_bytes
            + position_lists_bytes
            + position_integer_bytes
            + tails_bytes
        )
        return {
            "sparse_positions_dictionary_bytes": dictionary_bytes,
            "sparse_key_bytes": key_bytes,
            "sparse_position_lists_bytes": position_lists_bytes,
            "sparse_position_integer_bytes": position_integer_bytes,
            "sparse_increasing_tails_bytes": tails_bytes,
            "estimated_sparse_bytes": estimated,
        }

    @staticmethod
    def _build_bit_masks(indexed_text: str) -> dict[str, int]:
        masks: dict[str, int] = {}
        for index, character in enumerate(indexed_text):
            masks[character] = masks.get(character, 0) | (1 << index)
        return masks

    @staticmethod
    def _bit_parallel_lcs(indexed_text: str, iterated_text: str) -> int:
        masks = QualityEvaluator._build_bit_masks(indexed_text)
        state = 0
        for character in iterated_text:
            x = masks.get(character, 0) | state
            state = x & ~(x - ((state << 1) | 1))
        return state.bit_count()

    @staticmethod
    def _sparse_lcs(indexed_text: str, iterated_text: str) -> int:
        positions: dict[str, list[int]] = {}
        for index, character in enumerate(indexed_text):
            positions.setdefault(character, []).append(index)

        increasing_tails: list[int] = []
        for character in iterated_text:
            for position in reversed(positions.get(character, ())):
                insertion_index = bisect_left(increasing_tails, position)
                if insertion_index == len(increasing_tails):
                    increasing_tails.append(position)
                else:
                    increasing_tails[insertion_index] = position
        return len(increasing_tails)

    @staticmethod
    def _is_heading_candidate(source_role: str) -> bool:
        return bool(
            _HEADING_CANDIDATE.search(source_role)
            or _TITLE_CANDIDATE.search(source_role)
        )

    @staticmethod
    def _has_useful_reference_context(diagnostic: Diagnostic) -> bool:
        if diagnostic.code != "unresolved_mcid":
            return bool(diagnostic.context)
        page_index = diagnostic.context.get("page_index")
        mcid = diagnostic.context.get("mcid")
        return (
            isinstance(page_index, int)
            and not isinstance(page_index, bool)
            and page_index >= 0
            and isinstance(mcid, int)
            and not isinstance(mcid, bool)
            and mcid >= 0
        )
