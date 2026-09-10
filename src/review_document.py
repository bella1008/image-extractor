"""Immutable v2 review data; independent of PDF readers, legacy extraction and UI.

Constructing a document does not certify extraction quality. Bundle and language
gates must pass before a downstream evaluator may use it for review decisions.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
import math
import re


def _required_text(value: object, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _language(value: object) -> None:
    if not isinstance(value, str) or re.fullmatch(r"[A-Z]+(?:-[A-Z]+)*", value) is None:
        raise ValueError("language must be a canonical uppercase ASCII code")


def _tuple_of(value: object, member_type: type | tuple[type, ...], name: str) -> None:
    if not isinstance(value, tuple) or not all(isinstance(item, member_type) for item in value):
        raise ValueError(f"{name} must be a tuple of the declared member type")


@dataclass(frozen=True)
class DocumentContext:
    manual_code: str
    source_token: str
    region: str
    buyer_codes: tuple[str, ...]
    doc_type: str
    expected_languages: tuple[str, ...]
    language_variant: str | None = None

    def __post_init__(self) -> None:
        for name in ("manual_code", "source_token", "region"):
            _required_text(getattr(self, name), name)
        if self.doc_type not in ("A2", "A3", "BOOK"):
            raise ValueError("doc_type must be A2, A3 or BOOK")
        for name in ("buyer_codes", "expected_languages"):
            values = getattr(self, name)
            _tuple_of(values, str, name)
            if not values or len(set(values)) != len(values):
                raise ValueError(f"{name} must be non-empty and unique")
            for value in values:
                _required_text(value, name)
        for language in self.expected_languages:
            _language(language)
        if self.language_variant is not None:
            _required_text(self.language_variant, "language_variant")


@dataclass(frozen=True)
class SourceEvidence:
    xml_path: str
    page_index: int | None = None
    mcid: int | None = None
    object_ref: str | None = None
    bbox: tuple[float, float, float, float] | None = None

    def __post_init__(self) -> None:
        _required_text(self.xml_path, "xml_path")
        for name in ("page_index", "mcid"):
            value = getattr(self, name)
            if value is not None and (type(value) is not int or value < 0):
                raise ValueError(f"{name} must be a non-negative integer or None")
        if self.object_ref is not None:
            _required_text(self.object_ref, "object_ref")
        if self.bbox is not None:
            if (not isinstance(self.bbox, tuple) or len(self.bbox) != 4
                    or any(type(value) not in (int, float) or not math.isfinite(value)
                           for value in self.bbox)):
                raise ValueError("bbox must be a tuple of four finite numbers")
            x0, y0, x1, y1 = self.bbox
            if x0 > x1 or y0 > y1:
                raise ValueError("bbox bounds must be ordered")


@dataclass(frozen=True)
class ReviewRole:
    """A classification plus provenance; not an automatic approval."""

    name: str
    rule_id: str
    evidence_paths: tuple[str, ...]

    def __post_init__(self) -> None:
        _required_text(self.name, "role name")
        _required_text(self.rule_id, "rule_id")
        _tuple_of(self.evidence_paths, str, "evidence_paths")
        if not self.evidence_paths:
            raise ValueError("review role requires evidence_paths")
        for path in self.evidence_paths:
            _required_text(path, "evidence path")


@dataclass(frozen=True)
class ReviewNode:
    node_id: str
    structure_type: str
    content: tuple[str | ReviewNode, ...]
    language: str | None = None
    source_role: str | None = None
    attributes: tuple[tuple[str, str], ...] = ()
    evidence: tuple[SourceEvidence, ...] = ()
    review_roles: tuple[ReviewRole, ...] = ()

    def __post_init__(self) -> None:
        _required_text(self.node_id, "node_id")
        _required_text(self.structure_type, "structure_type")
        _tuple_of(self.content, (str, ReviewNode), "content")
        _tuple_of(self.evidence, SourceEvidence, "evidence")
        _tuple_of(self.review_roles, ReviewRole, "review_roles")
        if self.language is not None:
            _language(self.language)
        if self.source_role is not None:
            _required_text(self.source_role, "source_role")
        _tuple_of(self.attributes, tuple, "attributes")
        names: set[str] = set()
        for pair in self.attributes:
            if len(pair) != 2 or not all(isinstance(value, str) for value in pair):
                raise ValueError("attributes must contain string name/value pairs")
            _required_text(pair[0], "attribute name")
            if pair[0] in names:
                raise ValueError("duplicate attribute name")
            names.add(pair[0])

    @property
    def text_content(self) -> str:
        """Return ordered text without adding separators or normalizing source text.

        This is a display convenience, not a cross-cell or cross-language match
        window. Evaluators must select appropriate structural boundaries first.
        """
        parts: list[str] = []
        pending: list[str | ReviewNode] = list(reversed(self.content))
        while pending:
            item = pending.pop()
            if isinstance(item, str):
                parts.append(item)
            else:
                pending.extend(reversed(item.content))
        return "".join(parts)


@dataclass(frozen=True)
class ReviewDocument:
    context: DocumentContext
    roots: tuple[ReviewNode, ...]
    schema_version: str = "review-document/1"

    def __post_init__(self) -> None:
        if not isinstance(self.context, DocumentContext):
            raise ValueError("context must be a DocumentContext")
        _tuple_of(self.roots, ReviewNode, "roots")
        if self.schema_version != "review-document/1":
            raise ValueError("unsupported ReviewDocument schema_version")
        seen: set[str] = set()
        for node in self.iter_nodes():
            if node.node_id in seen:
                raise ValueError(f"duplicate node_id: {node.node_id}")
            seen.add(node.node_id)

    def iter_nodes(self) -> Iterator[ReviewNode]:
        """Yield source hierarchy in preorder, retaining root and child order."""
        pending = list(reversed(self.roots))
        while pending:
            node = pending.pop()
            yield node
            pending.extend(item for item in reversed(node.content) if isinstance(item, ReviewNode))
