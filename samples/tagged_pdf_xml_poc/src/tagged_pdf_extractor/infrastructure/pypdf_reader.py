from __future__ import annotations

from collections.abc import Mapping, Sequence
from numbers import Integral
from pathlib import Path
from typing import Any

from pypdf import PdfReader

from tagged_pdf_extractor.domain.models import (
    ContentFragment,
    Diagnostic,
    StructureElement,
    TaggedDocument,
)
from tagged_pdf_extractor.domain.role_mapping import map_role
from tagged_pdf_extractor.infrastructure.mcid_text import McidTextCollector


class TaggedPdfError(RuntimeError):
    pass


class TaggedPdfReader:
    def __init__(self, collector: McidTextCollector | None = None) -> None:
        self.collector = collector or McidTextCollector()

    @staticmethod
    def resolve(value: Any) -> Any:
        get_object = getattr(value, "get_object", None)
        if not callable(get_object):
            return value
        try:
            return get_object()
        except Exception as exc:
            reference = TaggedPdfReader.object_ref(value)
            subject = reference or type(value).__name__
            raise TaggedPdfError(f"Failed to dereference {subject}: {exc}") from exc

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
        diagnostics: list[Diagnostic] = []
        for index, page in enumerate(pages):
            result = self.collector.collect(page, index)
            mcid_text[index] = result.parts_by_mcid
            diagnostics.extend(result.diagnostics)

        role_map = self._read_role_map(struct_root.get("/RoleMap"))
        children = self._walk_kids(
            struct_root.get("/K"),
            inherited_page_index=None,
            page_indexes=page_indexes,
            mcid_text=mcid_text,
            role_map=role_map,
            diagnostics=diagnostics,
            active_refs=set(),
        )
        language = self._optional_string(catalog.get("/Lang"))
        return TaggedDocument(
            source_path=pdf_path,
            marked=marked,
            language=language,
            role_map=tuple(sorted(role_map.items())),
            children=tuple(children),
            diagnostics=tuple(diagnostics),
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
        role_map: dict[str, str],
        diagnostics: list[Diagnostic],
        active_refs: set[str],
    ) -> list[StructureElement | ContentFragment]:
        if kids is None:
            return []
        reference = self.object_ref(kids)
        resolved = self.resolve(kids)
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
                        resolved.get("/Pg"), inherited_page_index, page_indexes
                    )
                    mcid = self._mcid(resolved.get("/MCID"))
                    return [
                        self._content_fragment(
                            page_index,
                            mcid,
                            reference,
                            mcid_text,
                            diagnostics,
                        )
                    ]

                if "/S" in resolved:
                    page_index = self._page_index(
                        resolved.get("/Pg"), inherited_page_index, page_indexes
                    )
                    source_role = self._name(resolved.get("/S")) or ""
                    semantic_role, heading_level = map_role(source_role, role_map)
                    children = self._walk_kids(
                        resolved.get("/K"),
                        page_index,
                        page_indexes,
                        mcid_text,
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
        diagnostics: list[Diagnostic],
    ) -> ContentFragment:
        stored_page_index = self._diagnostic_page_index(page_index)
        page_parts = mcid_text.get(page_index, {}) if page_index is not None else {}
        if mcid is not None and mcid in page_parts:
            text_parts = page_parts[mcid]
        else:
            text_parts = ()
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
        )

    def _page_index(
        self,
        page: Any,
        inherited_page_index: int | None,
        page_indexes: dict[str, int],
    ) -> int | None:
        if page is None:
            return inherited_page_index
        reference = self.object_ref(page)
        resolved_page = self.resolve(page)
        reference = self.object_ref(resolved_page) or reference
        return page_indexes.get(reference) if reference is not None else None

    def _attributes(self, value: Any) -> tuple[tuple[str, str], ...]:
        attributes = self.resolve(value)
        if attributes is None:
            return ()
        if isinstance(attributes, Mapping):
            pairs = [
                (str(self.resolve(key)), self._stable_value(item))
                for key, item in attributes.items()
            ]
            return tuple(sorted(pairs))
        if self._is_kid_sequence(attributes):
            pairs: list[tuple[str, str]] = []
            for item in attributes:
                resolved_item = self.resolve(item)
                if isinstance(resolved_item, Mapping):
                    pairs.extend(
                        (str(self.resolve(key)), self._stable_value(nested_value))
                        for key, nested_value in resolved_item.items()
                    )
                else:
                    pairs.append(("/A", self._stable_value(resolved_item)))
            return tuple(sorted(pairs))
        return (("/A", self._stable_value(attributes)),)

    def _stable_value(self, value: Any) -> str:
        resolved = self.resolve(value)
        if isinstance(resolved, Mapping):
            pairs = sorted(
                (str(self.resolve(key)), self._stable_value(item))
                for key, item in resolved.items()
            )
            return "{" + ", ".join(f"{key}: {item}" for key, item in pairs) + "}"
        if self._is_kid_sequence(resolved):
            return "[" + ", ".join(self._stable_value(item) for item in resolved) + "]"
        return str(resolved)

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
