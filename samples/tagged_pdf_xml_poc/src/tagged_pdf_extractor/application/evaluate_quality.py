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
_BIT_MASK_MEMORY_BUDGET_BYTES = 64 * 1024 * 1024
_SPARSE_MATCH_PAIR_BUDGET = 10_000_000


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
    ) -> None:
        self.baseline_length = baseline_length
        self.tagged_length = tagged_length
        self.mask_estimate = mask_estimate
        self.mask_budget = mask_budget
        self.match_pair_estimate = match_pair_estimate
        self.match_pair_budget = match_pair_budget
        super().__init__(
            "Exact LCS resource limits exceeded: "
            f"baseline_length={baseline_length}, tagged_length={tagged_length}, "
            f"mask_estimate={mask_estimate}, mask_budget={mask_budget}, "
            f"match_pair_estimate={match_pair_estimate}, "
            f"match_pair_budget={match_pair_budget}"
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

        unresolved = tuple(
            diagnostic
            for diagnostic in document.diagnostics
            if diagnostic.code == "unresolved_mcid"
        )
        hard_gates = {
            "is_marked": document.marked,
            "has_structure": traversal.element_count > 0,
            "has_heading": traversal.heading_count > 0,
            "has_body": traversal.body_count > 0,
            "xml_round_trip": xml_round_trip_ok,
            "resolved_references_reported": all(
                self._has_useful_mcid_context(diagnostic) for diagnostic in unresolved
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
            "unresolved_mcid_count": len(unresolved),
            "character_match_ratio": comparison.ratio,
            "comparison_mode": comparison.mode,
            "comparison_parameters": comparison.parameters,
            "tagged_character_count": len(normalized_tagged),
            "baseline_character_count": len(normalized_baseline),
            "special_characters": {
                character: {
                    "tagged": normalized_tagged.count(character),
                    "baseline": normalized_baseline.count(character),
                }
                for character in _SPECIAL_CHARACTERS
            },
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
            traversal.heading_count += child.semantic_role == "heading"
            is_body_role = child.semantic_role in _BODY_ROLES
            traversal.body_role_node_count += is_body_role
            traversal.unknown_role_count += child.semantic_role == "unknown"
            self._count_element_text_fields(child, traversal)
            element_path = f"{parent_path}/{child.semantic_role}[{child_index}]"
            element_has_text = self._walk(child.children, element_path, traversal)
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

        memory = QualityEvaluator._estimate_bit_mask_memory(indexed_text)
        indexed_counts = Counter(indexed_text)
        iterated_counts = Counter(iterated_text)
        match_pair_count = sum(
            count * iterated_counts.get(character, 0)
            for character, count in indexed_counts.items()
        )
        del indexed_counts, iterated_counts

        common_parameters = {
            "indexed_dimension": "shorter",
            "indexed_length": len(indexed_text),
            "iterated_length": len(iterated_text),
            **memory,
            "mask_memory_budget_bytes": _BIT_MASK_MEMORY_BUDGET_BYTES,
            "match_pair_count": match_pair_count,
            "sparse_match_pair_budget": _SPARSE_MATCH_PAIR_BUDGET,
        }
        if memory["estimated_mask_bytes"] <= _BIT_MASK_MEMORY_BUDGET_BYTES:
            return (
                QualityEvaluator._bit_parallel_lcs(indexed_text, iterated_text),
                "bit_parallel_lcs",
                {**common_parameters, "bitset_dimension": "shorter"},
            )
        if match_pair_count <= _SPARSE_MATCH_PAIR_BUDGET:
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
        )

    @staticmethod
    def _estimate_bit_mask_memory(indexed_text: str) -> dict[str, int]:
        """Measure the final mask table without retaining prepass state.

        Each mask's highest set bit is its character's final occurrence, so a
        one-bit integer at that position has the same runtime size as the final
        mask. ``sys.getsizeof(max_positions)`` supplies the dictionary table
        size for the same keys/cardinality. This prepass dictionary is released
        when the function returns, before the real masks are allocated.
        """
        max_positions: dict[str, int] = {}
        for position, character in enumerate(indexed_text):
            max_positions[character] = position
        dictionary_bytes = sys.getsizeof(max_positions)
        mask_value_bytes = sum(
            sys.getsizeof(1 << position) for position in max_positions.values()
        )
        mask_storage_bytes = dictionary_bytes + mask_value_bytes
        # The update expression retains the prior state and ``x`` while
        # creating shifted/subtraction intermediates. Four maximum-width ints
        # conservatively cover that concurrent working set.
        algorithm_working_bytes = 4 * sys.getsizeof(
            (1 << len(indexed_text)) - 1
        )
        return {
            "unique_character_count": len(max_positions),
            "mask_dictionary_bytes": dictionary_bytes,
            "mask_value_bytes": mask_value_bytes,
            "mask_storage_bytes": mask_storage_bytes,
            "algorithm_working_bytes": algorithm_working_bytes,
            "estimated_mask_bytes": mask_storage_bytes + algorithm_working_bytes,
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
    def _has_useful_mcid_context(diagnostic: Diagnostic) -> bool:
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
