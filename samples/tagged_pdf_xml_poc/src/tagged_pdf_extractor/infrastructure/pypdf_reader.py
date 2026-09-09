from __future__ import annotations

from collections.abc import Mapping, Sequence
from numbers import Integral
from pathlib import Path
from typing import Any

from pypdf import PdfReader
from pypdf.errors import LimitReachedError, PdfReadError
from pypdf.generic import Destination, NullObject

from tagged_pdf_extractor.domain.models import (
    BBox,
    BookmarkPageBounds,
    ContentFragment,
    Diagnostic,
    StructureElement,
    TaggedDocument,
    TextStyle,
)
from tagged_pdf_extractor.domain.role_mapping import map_role
from tagged_pdf_extractor.infrastructure.mcid_text import McidTextCollector
from tagged_pdf_extractor.infrastructure.pypdf_operation_text import (
    PypdfOperationTextError,
)


class TaggedPdfError(RuntimeError):
    pass


class _BookmarkEvidenceError(Exception):
    def __init__(self, reason: str, exception_type: str | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.exception_type = exception_type


class TaggedPdfReader:
    def __init__(self, collector: McidTextCollector | None = None) -> None:
        self.collector = collector or McidTextCollector()

    @staticmethod
    def resolve(value: Any) -> Any:
        current = value
        seen_objects: set[int] = set()
        seen_references: set[str] = set()
        while True:
            if current is None or isinstance(current, NullObject):
                return None
            get_object = getattr(current, "get_object", None)
            if not callable(get_object):
                return current
            reference = TaggedPdfReader.object_ref(current)
            try:
                resolved = get_object()
            except Exception as exc:
                subject = reference or type(current).__name__
                raise TaggedPdfError(f"Failed to dereference {subject}: {exc}") from exc
            if resolved is current:
                return current
            if id(current) in seen_objects or (
                reference is not None and reference in seen_references
            ):
                subject = reference or type(current).__name__
                raise TaggedPdfError(f"Dereference cycle detected at {subject}")
            seen_objects.add(id(current))
            if reference is not None:
                seen_references.add(reference)
            current = resolved

    @staticmethod
    def object_ref(value: Any) -> str | None:
        if value is None:
            return None
        ref = value
        if not hasattr(ref, "idnum"):
            ref = getattr(value, "indirect_reference", None)
        if ref is None or not hasattr(ref, "idnum"):
            return None
        return f"{ref.idnum} {getattr(ref, 'generation', 0)} R"

    def read(self, pdf_path: Path) -> TaggedDocument:
        reader = PdfReader(str(pdf_path))
        catalog = self.resolve(reader.trailer["/Root"])
        mark_info = self.resolve(catalog.get("/MarkInfo"))
        marked_value = self.resolve(mark_info.get("/Marked")) if mark_info else False
        marked = (
            marked_value
            if isinstance(marked_value, bool)
            else getattr(marked_value, "value", False) is True
        )

        raw_struct_root = catalog.get("/StructTreeRoot")
        if raw_struct_root is None:
            raise TaggedPdfError("PDF has no /StructTreeRoot")
        struct_root = self.resolve(raw_struct_root)
        if struct_root is None:
            raise TaggedPdfError("PDF has no /StructTreeRoot")

        pages = list(reader.pages)
        page_indexes = {
            reference: index
            for index, page in enumerate(pages)
            if (reference := self.object_ref(page)) is not None
        }
        mcid_text: dict[int, dict[int, tuple[str, ...]]] = {}
        mcid_styles: dict[int, dict[int, tuple[TextStyle, ...]]] = {}
        mcid_bboxes: dict[int, dict[int, tuple[BBox | None, ...]]] = {}
        seen_mcids: dict[int, frozenset[int]] = {}
        diagnostics: list[Diagnostic] = []
        for index, page in enumerate(pages):
            try:
                result = self.collector.collect(page, index)
            except PypdfOperationTextError as exc:
                raise TaggedPdfError(
                    f"Failed to decode tagged text on page index {index}: {exc}"
                ) from exc
            mcid_text[index] = result.parts_by_mcid
            mcid_styles[index] = result.styles_by_mcid
            mcid_bboxes[index] = result.bboxes_by_mcid
            seen_mcids[index] = result.seen_mcids
            diagnostics.extend(result.diagnostics)

        role_map = self._read_role_map(struct_root.get("/RoleMap"))
        children = self._walk_kids(
            struct_root.get("/K"),
            inherited_page_index=None,
            page_indexes=page_indexes,
            mcid_text=mcid_text,
            mcid_styles=mcid_styles,
            mcid_bboxes=mcid_bboxes,
            seen_mcids=seen_mcids,
            role_map=role_map,
            diagnostics=diagnostics,
            active_refs=set(),
        )
        language = self._optional_string(catalog.get("/Lang"))
        bookmark_page_bounds = self._read_bookmark_page_bounds(
            reader, len(pages), diagnostics
        )
        return TaggedDocument(
            source_path=pdf_path,
            marked=marked,
            language=language,
            role_map=tuple(sorted(role_map.items())),
            children=tuple(children),
            diagnostics=tuple(diagnostics),
            bookmark_page_bounds=bookmark_page_bounds,
        )

    def _read_bookmark_page_bounds(
        self,
        reader: PdfReader,
        page_count: int,
        diagnostics: list[Diagnostic],
    ) -> tuple[BookmarkPageBounds, ...]:
        if not self._has_outline_attribute(reader):
            return ()
        try:
            outline = reader.outline
        except (PdfReadError, LimitReachedError) as exc:
            return self._bookmark_evidence_failure(
                diagnostics,
                _BookmarkEvidenceError(
                    "pypdf_outline_read_error", type(exc).__name__
                ),
            )

        if outline is None or (
            self._is_outline_sequence(outline) and len(outline) == 0
        ):
            return ()

        try:
            destinations = self._top_level_destinations(outline)
            starts = self._destination_starts(reader, destinations, page_count)
        except _BookmarkEvidenceError as exc:
            return self._bookmark_evidence_failure(diagnostics, exc)

        return tuple(
            BookmarkPageBounds(
                ordinal=index + 1,
                start_page_index=start,
                end_page_index=(
                    starts[index + 1] - 1
                    if index + 1 < len(starts)
                    else page_count - 1
                ),
                source_title=(
                    destination.title
                    if isinstance(destination.title, str)
                    else None
                ),
            )
            for index, (destination, start) in enumerate(zip(destinations, starts))
        )

    @staticmethod
    def _has_outline_attribute(reader: PdfReader) -> bool:
        if "outline" in vars(reader):
            return True
        return any("outline" in base.__dict__ for base in type(reader).__mro__)

    @staticmethod
    def _bookmark_evidence_failure(
        diagnostics: list[Diagnostic], error: _BookmarkEvidenceError
    ) -> tuple[BookmarkPageBounds, ...]:
        context = {"reason": error.reason}
        if error.exception_type is not None:
            context["exception_type"] = error.exception_type
        diagnostics.append(
            Diagnostic(
                severity="warning",
                code="invalid_bookmark_page_bounds",
                message=(
                    "Top-level PDF outline could not produce unambiguous "
                    "bookmark page bounds"
                ),
                context=context,
            )
        )
        return ()

    @staticmethod
    def _destination_starts(
        reader: PdfReader,
        destinations: tuple[Destination, ...],
        page_count: int,
    ) -> tuple[int, ...]:
        starts: list[int] = []
        for destination in destinations:
            try:
                page_index = reader.get_destination_page_number(destination)
            except (PdfReadError, LimitReachedError) as exc:
                raise _BookmarkEvidenceError(
                    "pypdf_destination_resolution_error", type(exc).__name__
                ) from exc
            if not isinstance(page_index, Integral) or isinstance(page_index, bool):
                raise _BookmarkEvidenceError("destination_page_unresolved")
            start = int(page_index)
            if start < 0 or start >= page_count:
                raise _BookmarkEvidenceError("destination_page_out_of_range")
            if starts and start <= starts[-1]:
                raise _BookmarkEvidenceError("destination_pages_not_increasing")
            starts.append(start)
        return tuple(starts)

    @classmethod
    def _top_level_destinations(cls, outline: Any) -> tuple[Destination, ...]:
        return cls._validate_outline_level(outline)

    @classmethod
    def _validate_outline_level(cls, outline: Any) -> tuple[Destination, ...]:
        if not cls._is_outline_sequence(outline):
            raise _BookmarkEvidenceError("outline_not_sequence")
        if len(outline) == 0:
            raise _BookmarkEvidenceError("empty_child_outline")

        destinations: list[Destination] = []
        child_list_allowed = False
        for item in outline:
            if isinstance(item, Destination):
                destinations.append(item)
                child_list_allowed = True
                continue
            if cls._is_outline_sequence(item):
                if not child_list_allowed:
                    raise _BookmarkEvidenceError("unattached_child_outline")
                cls._validate_outline_level(item)
                child_list_allowed = False
                continue
            raise _BookmarkEvidenceError("invalid_outline_item")
        if not destinations:
            raise _BookmarkEvidenceError("outline_has_no_destinations")
        return tuple(destinations)

    @staticmethod
    def _is_outline_sequence(value: Any) -> bool:
        return isinstance(value, Sequence) and not isinstance(
            value, (str, bytes, bytearray)
        )

    def _read_role_map(self, value: Any) -> dict[str, str]:
        role_map = self.resolve(value)
        if not isinstance(role_map, Mapping):
            return {}
        return {
            str(self.resolve(key)).lstrip("/"): str(self.resolve(mapped)).lstrip("/")
            for key, mapped in role_map.items()
        }

    def _walk_kids(
        self,
        kids: Any,
        inherited_page_index: int | None,
        page_indexes: dict[str, int],
        mcid_text: dict[int, dict[int, tuple[str, ...]]],
        mcid_styles: dict[int, dict[int, tuple[TextStyle, ...]]],
        mcid_bboxes: dict[int, dict[int, tuple[BBox | None, ...]]],
        seen_mcids: dict[int, frozenset[int]],
        role_map: dict[str, str],
        diagnostics: list[Diagnostic],
        active_refs: set[str],
    ) -> list[StructureElement | ContentFragment]:
        if kids is None:
            return []
        reference = self.object_ref(kids)
        resolved = self.resolve(kids)
        if resolved is None:
            return []
        if self._is_kid_sequence(resolved):
            if reference is not None:
                self._enter_reference(reference, active_refs)
            try:
                children: list[StructureElement | ContentFragment] = []
                for child in resolved:
                    children.extend(
                        self._walk_kid(
                            child,
                            inherited_page_index,
                            page_indexes,
                            mcid_text,
                            mcid_styles,
                            mcid_bboxes,
                            seen_mcids,
                            role_map,
                            diagnostics,
                            active_refs,
                        )
                    )
                return children
            finally:
                if reference is not None:
                    active_refs.remove(reference)
        return self._walk_kid(
            kids,
            inherited_page_index,
            page_indexes,
            mcid_text,
            mcid_styles,
            mcid_bboxes,
            seen_mcids,
            role_map,
            diagnostics,
            active_refs,
        )

    def _walk_kid(
        self,
        kid: Any,
        inherited_page_index: int | None,
        page_indexes: dict[str, int],
        mcid_text: dict[int, dict[int, tuple[str, ...]]],
        mcid_styles: dict[int, dict[int, tuple[TextStyle, ...]]],
        mcid_bboxes: dict[int, dict[int, tuple[BBox | None, ...]]],
        seen_mcids: dict[int, frozenset[int]],
        role_map: dict[str, str],
        diagnostics: list[Diagnostic],
        active_refs: set[str],
    ) -> list[StructureElement | ContentFragment]:
        reference = self.object_ref(kid)
        if reference is not None:
            self._enter_reference(reference, active_refs)
        try:
            resolved = self.resolve(kid)
            if self._is_kid_sequence(resolved):
                children: list[StructureElement | ContentFragment] = []
                for child in resolved:
                    children.extend(
                        self._walk_kid(
                            child,
                            inherited_page_index,
                            page_indexes,
                            mcid_text,
                            mcid_styles,
                            mcid_bboxes,
                            seen_mcids,
                            role_map,
                            diagnostics,
                            active_refs,
                        )
                    )
                return children

            if isinstance(resolved, Integral) and not isinstance(resolved, bool):
                return [
                    self._content_fragment(
                        inherited_page_index,
                        int(resolved),
                        reference,
                        mcid_text,
                        mcid_styles,
                        mcid_bboxes,
                        seen_mcids,
                        diagnostics,
                    )
                ]

            if isinstance(resolved, Mapping):
                type_name = self._name(resolved.get("/Type"))
                if type_name == "OBJR":
                    diagnostics.append(
                        Diagnostic(
                            severity="warning",
                            code="unsupported_objr",
                            message="OBJR structure kid is unsupported",
                            context={
                                "page_index": self._diagnostic_page_index(
                                    inherited_page_index
                                ),
                                "object_ref": reference,
                            },
                        )
                    )
                    return []

                if type_name == "MCR" or "/MCID" in resolved:
                    page_index = self._page_index(
                        resolved.get("/Pg"),
                        inherited_page_index,
                        page_indexes,
                        diagnostics,
                        reference,
                    )
                    mcid = self._mcid(resolved.get("/MCID"))
                    raw_stream = resolved.get("/Stm")
                    stream = self.resolve(raw_stream)
                    if stream is not None:
                        stream_reference = (
                            self.object_ref(raw_stream) or self.object_ref(stream)
                        )
                        stored_page_index = self._diagnostic_page_index(page_index)
                        diagnostics.append(
                            Diagnostic(
                                severity="warning",
                                code="unsupported_stream_mcr",
                                message="Stream-owned MCR is unsupported",
                                context={
                                    "page_index": stored_page_index,
                                    "mcid": mcid,
                                    "object_ref": reference,
                                    "stream_object_ref": stream_reference,
                                },
                            )
                        )
                        return [
                            ContentFragment(
                                page_index=stored_page_index,
                                mcid=mcid,
                                text_parts=(),
                                object_ref=reference,
                            )
                        ]
                    return [
                        self._content_fragment(
                            page_index,
                            mcid,
                            reference,
                            mcid_text,
                            mcid_styles,
                            mcid_bboxes,
                            seen_mcids,
                            diagnostics,
                        )
                    ]

                if "/S" in resolved:
                    page_index = self._page_index(
                        resolved.get("/Pg"),
                        inherited_page_index,
                        page_indexes,
                        diagnostics,
                        reference,
                    )
                    source_role = self._name(resolved.get("/S")) or ""
                    semantic_role, heading_level = map_role(source_role, role_map)
                    children = self._walk_kids(
                        resolved.get("/K"),
                        page_index,
                        page_indexes,
                        mcid_text,
                        mcid_styles,
                        mcid_bboxes,
                        seen_mcids,
                        role_map,
                        diagnostics,
                        active_refs,
                    )
                    return [
                        StructureElement(
                            source_role=source_role,
                            semantic_role=semantic_role,
                            heading_level=heading_level,
                            object_ref=reference,
                            page_index=page_index,
                            title=self._optional_string(resolved.get("/T")),
                            language=self._optional_string(resolved.get("/Lang")),
                            alternate_text=self._optional_string(
                                resolved.get("/Alt")
                            ),
                            actual_text=self._optional_string(
                                resolved.get("/ActualText")
                            ),
                            attributes=self._attributes(resolved.get("/A")),
                            children=tuple(children),
                        )
                    ]

            diagnostics.append(
                Diagnostic(
                    severity="warning",
                    code="unsupported_structure_kid",
                    message="Unsupported structure kid was skipped",
                    context={
                        "value_type": type(resolved).__name__,
                        "value_repr": self._safe_repr(resolved),
                        "object_ref": reference,
                    },
                )
            )
            return []
        finally:
            if reference is not None:
                active_refs.remove(reference)

    def _content_fragment(
        self,
        page_index: int | None,
        mcid: int | None,
        reference: str | None,
        mcid_text: dict[int, dict[int, tuple[str, ...]]],
        mcid_styles: dict[int, dict[int, tuple[TextStyle, ...]]],
        mcid_bboxes: dict[int, dict[int, tuple[BBox | None, ...]]],
        seen_mcids: dict[int, frozenset[int]],
        diagnostics: list[Diagnostic],
    ) -> ContentFragment:
        stored_page_index = self._diagnostic_page_index(page_index)
        page_parts = mcid_text.get(page_index, {}) if page_index is not None else {}
        if mcid is not None and mcid in page_parts:
            text_parts = page_parts[mcid]
            text_styles = mcid_styles[page_index][mcid]
            text_bboxes = mcid_bboxes[page_index][mcid]
        elif (
            page_index is not None
            and mcid is not None
            and mcid in seen_mcids.get(page_index, frozenset())
        ):
            text_parts = ()
            text_styles = ()
            text_bboxes = ()
        else:
            text_parts = ()
            text_styles = ()
            text_bboxes = ()
            diagnostics.append(
                Diagnostic(
                    severity="warning",
                    code="unresolved_mcid",
                    message="Could not resolve MCID text",
                    context={
                        "page_index": stored_page_index,
                        "mcid": mcid,
                        "object_ref": reference,
                    },
                )
            )
        return ContentFragment(
            page_index=stored_page_index,
            mcid=mcid,
            text_parts=tuple(text_parts),
            object_ref=reference,
            text_styles=tuple(text_styles),
            text_bboxes=tuple(text_bboxes),
        )

    def _page_index(
        self,
        page: Any,
        inherited_page_index: int | None,
        page_indexes: dict[str, int],
        diagnostics: list[Diagnostic],
        owner_reference: str | None,
    ) -> int | None:
        if page is None:
            return inherited_page_index
        reference = self.object_ref(page)
        resolved_page = self.resolve(page)
        if resolved_page is None:
            if reference is None:
                return inherited_page_index
            diagnostics.append(
                Diagnostic(
                    severity="warning",
                    code="unresolved_page_reference",
                    message="Page reference could not be resolved",
                    context={
                        "page_object_ref": reference,
                        "object_ref": owner_reference,
                    },
                )
            )
            return None
        reference = self.object_ref(resolved_page) or reference
        if reference is not None and reference in page_indexes:
            return page_indexes[reference]
        diagnostics.append(
            Diagnostic(
                severity="warning",
                code="unresolved_page_reference",
                message="Page reference is not present in the PDF page tree",
                context={
                    "page_object_ref": reference,
                    "object_ref": owner_reference,
                },
            )
        )
        return None

    def _attributes(self, value: Any) -> tuple[tuple[str, str], ...]:
        active_refs: set[str] = set()
        reference = self.object_ref(value)
        self._enter_attribute_reference(reference, active_refs)
        try:
            attributes = self.resolve(value)
            if attributes is None:
                return ()
            if isinstance(attributes, Mapping):
                return self._attribute_mapping_pairs(attributes, "", active_refs)
            if self._is_kid_sequence(attributes):
                pairs: list[tuple[str, str]] = []
                for index, item in enumerate(attributes):
                    item_reference = self.object_ref(item)
                    self._enter_attribute_reference(item_reference, active_refs)
                    try:
                        resolved_item = self.resolve(item)
                        prefix = f"[{index}]"
                        if isinstance(resolved_item, Mapping):
                            pairs.extend(
                                self._attribute_mapping_pairs(
                                    resolved_item, prefix, active_refs
                                )
                            )
                        else:
                            pairs.append(
                                (
                                    f"{prefix}/A",
                                    self._stable_resolved_value(
                                        resolved_item, active_refs
                                    ),
                                )
                            )
                    finally:
                        if item_reference is not None:
                            active_refs.remove(item_reference)
                return tuple(pairs)
            return (("/A", self._stable_resolved_value(attributes, active_refs)),)
        finally:
            if reference is not None:
                active_refs.remove(reference)

    def _attribute_mapping_pairs(
        self,
        mapping: Mapping[Any, Any],
        prefix: str,
        active_refs: set[str],
    ) -> tuple[tuple[str, str], ...]:
        return tuple(
            (
                f"{prefix}{self.resolve(key)}",
                self._stable_value(item, active_refs),
            )
            for key, item in mapping.items()
        )

    def _stable_value(self, value: Any, active_refs: set[str]) -> str:
        reference = self.object_ref(value)
        self._enter_attribute_reference(reference, active_refs)
        try:
            return self._stable_resolved_value(self.resolve(value), active_refs)
        finally:
            if reference is not None:
                active_refs.remove(reference)

    def _stable_resolved_value(
        self, resolved: Any, active_refs: set[str]
    ) -> str:
        if isinstance(resolved, Mapping):
            pairs = (
                (str(self.resolve(key)), self._stable_value(item, active_refs))
                for key, item in resolved.items()
            )
            return "{" + ", ".join(f"{key}: {item}" for key, item in pairs) + "}"
        if self._is_kid_sequence(resolved):
            return "[" + ", ".join(
                self._stable_value(item, active_refs) for item in resolved
            ) + "]"
        return str(resolved)

    @staticmethod
    def _enter_attribute_reference(
        reference: str | None, active_refs: set[str]
    ) -> None:
        if reference is None:
            return
        if reference in active_refs:
            raise TaggedPdfError(f"Attribute cycle detected at {reference}")
        active_refs.add(reference)

    def _optional_string(self, value: Any) -> str | None:
        if value is None:
            return None
        resolved = self.resolve(value)
        return None if resolved is None else str(resolved)

    def _name(self, value: Any) -> str | None:
        text = self._optional_string(value)
        return text.lstrip("/") if text is not None else None

    def _mcid(self, value: Any) -> int | None:
        resolved = self.resolve(value)
        if isinstance(resolved, Integral) and not isinstance(resolved, bool):
            return int(resolved)
        return None

    @staticmethod
    def _diagnostic_page_index(page_index: int | None) -> int:
        return page_index if page_index is not None else -1

    @staticmethod
    def _is_kid_sequence(value: Any) -> bool:
        return isinstance(value, Sequence) and not isinstance(
            value, (str, bytes, bytearray)
        )

    @staticmethod
    def _enter_reference(reference: str, active_refs: set[str]) -> None:
        if reference in active_refs:
            raise TaggedPdfError(f"Structure cycle detected at {reference}")
        active_refs.add(reference)

    @staticmethod
    def _safe_repr(value: Any) -> str:
        try:
            return repr(value)
        except Exception:
            return f"<unrepresentable {type(value).__name__}>"
