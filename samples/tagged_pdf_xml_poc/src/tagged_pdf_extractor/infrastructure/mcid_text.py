from dataclasses import dataclass
from numbers import Integral
from typing import Any

from tagged_pdf_extractor.domain.models import Diagnostic
from tagged_pdf_extractor.infrastructure.pypdf_operation_text import (
    PypdfOperationTextError,
    PypdfOperationTextRunner,
)


def _get_object(value: Any) -> Any:
    get_object = getattr(value, "get_object", None)
    if not callable(get_object):
        return value
    try:
        return get_object()
    except Exception:
        return value


def _mapping_value(mapping: Any, key: Any) -> Any:
    mapping = _get_object(mapping)
    get = getattr(mapping, "get", None)
    if not callable(get):
        return None
    try:
        return _get_object(get(key))
    except Exception:
        return None


def _resolve_properties(page: Any, operand: Any) -> Any:
    properties = _get_object(operand)
    if callable(getattr(properties, "get", None)):
        return properties
    resources = _mapping_value(page, "/Resources")
    named_properties = _mapping_value(resources, "/Properties")
    return _mapping_value(named_properties, properties)


def _resolve_xobject(page: Any, operand: Any) -> Any:
    get_inherited = getattr(page, "get_inherited", None)
    if callable(get_inherited):
        try:
            resources = _get_object(
                get_inherited(key="/Resources", default=None)
            )
        except Exception:
            resources = None
    else:
        resources = _mapping_value(page, "/Resources")
    xobjects = _mapping_value(resources, "/XObject")
    xobject = _mapping_value(xobjects, operand)
    if not callable(getattr(xobject, "get", None)):
        return None
    return xobject


def _safe_repr(value: Any) -> str:
    try:
        return repr(value)
    except Exception:
        return f"<unrepresentable {type(value).__name__}>"


@dataclass(frozen=True)
class McidTextResult:
    parts_by_mcid: dict[int, tuple[str, ...]]
    seen_mcids: frozenset[int]
    diagnostics: tuple[Diagnostic, ...]


class McidTextCollector:
    def __init__(self, runner: PypdfOperationTextRunner | None = None) -> None:
        self.runner = runner or PypdfOperationTextRunner()

    def collect(self, page: Any, page_index: int) -> McidTextResult:
        stack: list[int | None] = []
        parts: dict[int, list[str]] = {}
        seen_mcids: set[int] = set()
        diagnostics: list[Diagnostic] = []

        def on_boundary(operator: bytes, operands: list[Any]) -> None:
            if operator in (b"BMC", b"BDC"):
                mcid = None
                if len(operands) > 1:
                    properties = _resolve_properties(page, operands[1])
                    raw_mcid = _mapping_value(properties, "/MCID")
                    if raw_mcid is not None:
                        if isinstance(raw_mcid, Integral) and not isinstance(
                            raw_mcid, bool
                        ):
                            mcid = int(raw_mcid)
                            seen_mcids.add(mcid)
                        else:
                            diagnostics.append(
                                Diagnostic(
                                    severity="warning",
                                    code="invalid_mcid",
                                    message="MCID must be an integer",
                                    context={
                                        "page_index": page_index,
                                        "value_type": type(raw_mcid).__name__,
                                        "value_repr": _safe_repr(raw_mcid),
                                    },
                                )
                            )
                stack.append(mcid if mcid is not None else (stack[-1] if stack else None))
            elif operator == b"EMC":
                if stack:
                    stack.pop()
                else:
                    diagnostics.append(
                        Diagnostic(
                            severity="warning",
                            code="unbalanced_emc",
                            message="EMC without matching BMC/BDC",
                            context={"page_index": page_index},
                        )
                    )

        def on_text(value: str) -> None:
            if value and stack and stack[-1] is not None:
                parts.setdefault(stack[-1], []).append(value)

        def on_xobject(operand: Any) -> None:
            if not stack or stack[-1] is None:
                return

            context = {
                "page_index": page_index,
                "operand_repr": _safe_repr(operand),
            }
            xobject = _resolve_xobject(page, operand)
            if xobject is None:
                diagnostics.append(
                    Diagnostic(
                        severity="warning",
                        code="tagged_xobject_unresolved",
                        message="Tagged XObject reference could not be resolved",
                        context=context,
                    )
                )
                return

            subtype = _mapping_value(xobject, "/Subtype")
            subtype_name = str(subtype) if subtype is not None else None
            if subtype_name == "/Image":
                return
            if subtype_name == "/Form":
                diagnostics.append(
                    Diagnostic(
                        severity="warning",
                        code="tagged_form_xobject_unsupported",
                        message="Form XObject under tagged content is unsupported",
                        context=context,
                    )
                )
                return

            diagnostics.append(
                Diagnostic(
                    severity="warning",
                    code="tagged_xobject_unsupported",
                    message="Tagged XObject subtype is unsupported",
                    context={**context, "subtype": subtype_name},
                )
            )

        try:
            self.runner.run(
                page,
                on_boundary=on_boundary,
                on_text=on_text,
                on_xobject=on_xobject,
            )
        except PypdfOperationTextError as exc:
            raise PypdfOperationTextError(
                f"Unable to collect MCID text on page index {page_index}"
            ) from exc
        if stack:
            diagnostics.append(
                Diagnostic(
                    severity="warning",
                    code="unclosed_marked_content",
                    message="BMC/BDC without matching EMC",
                    context={"page_index": page_index, "depth": len(stack)},
                )
            )
        return McidTextResult(
            parts_by_mcid={mcid: tuple(values) for mcid, values in parts.items()},
            seen_mcids=frozenset(seen_mcids),
            diagnostics=tuple(diagnostics),
        )
