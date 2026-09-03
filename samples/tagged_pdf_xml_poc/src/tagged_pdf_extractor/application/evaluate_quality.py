from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher
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
_EXACT_COMPARISON_THRESHOLD = 8_192
_COMPARISON_CHUNK_SIZE = 2_048
_COMPARISON_WINDOW_MARGIN = 256


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
        (
            character_match_ratio,
            metric_mode,
            chunk_size,
            window_margin,
        ) = self._character_match_ratio(
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
            "unknown_role_count": traversal.unknown_role_count,
            "empty_element_count": traversal.empty_element_count,
            "unresolved_mcid_count": len(unresolved),
            "character_match_ratio": character_match_ratio,
            "character_match_metric_mode": metric_mode,
            "character_match_chunk_size": chunk_size,
            "character_match_window_margin": window_margin,
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
            traversal.body_count += child.semantic_role in _BODY_ROLES
            traversal.unknown_role_count += child.semantic_role == "unknown"
            self._count_element_text_fields(child, traversal)
            element_path = f"{parent_path}/{child.semantic_role}[{child_index}]"
            element_has_text = self._walk(child.children, element_path, traversal)
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
    ) -> tuple[float, str, int | None, int | None]:
        if not baseline_text:
            return (1.0 if not tagged_text else 0.0), "exact", None, None
        if max(len(baseline_text), len(tagged_text)) > _EXACT_COMPARISON_THRESHOLD:
            matched = QualityEvaluator._chunked_matched_size(
                baseline_text, tagged_text
            )
            return (
                matched / len(baseline_text),
                "chunked_window",
                _COMPARISON_CHUNK_SIZE,
                _COMPARISON_WINDOW_MARGIN,
            )
        matched = sum(
            block.size
            for block in SequenceMatcher(
                None, baseline_text, tagged_text, autojunk=False
            ).get_matching_blocks()
        )
        return matched / len(baseline_text), "exact", None, None

    @staticmethod
    def _chunked_matched_size(baseline_text: str, tagged_text: str) -> int:
        matched = 0
        tagged_length = len(tagged_text)
        maximum_window_size = _COMPARISON_CHUNK_SIZE + (
            2 * _COMPARISON_WINDOW_MARGIN
        )
        for start in range(0, len(baseline_text), _COMPARISON_CHUNK_SIZE):
            baseline_chunk = baseline_text[start : start + _COMPARISON_CHUNK_SIZE]
            midpoint = start + (len(baseline_chunk) / 2)
            predicted_midpoint = round(
                midpoint * tagged_length / len(baseline_text)
            )
            window_size = min(tagged_length, maximum_window_size)
            window_start = max(
                0,
                min(
                    predicted_midpoint - (window_size // 2),
                    tagged_length - window_size,
                ),
            )
            tagged_window = tagged_text[
                window_start : window_start + window_size
            ]
            matched += sum(
                block.size
                for block in SequenceMatcher(
                    None, baseline_chunk, tagged_window, autojunk=False
                ).get_matching_blocks()
            )
        return matched

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
