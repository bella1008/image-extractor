from dataclasses import dataclass
from numbers import Integral
from typing import Any

from tagged_pdf_extractor.domain.models import Diagnostic


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


def _safe_repr(value: Any) -> str:
    try:
        return repr(value)
    except Exception:
        return f"<unrepresentable {type(value).__name__}>"


@dataclass(frozen=True)
class McidTextResult:
    parts_by_mcid: dict[int, tuple[str, ...]]
    diagnostics: tuple[Diagnostic, ...]


class McidTextCollector:
    def collect(self, page: Any, page_index: int) -> McidTextResult:
        stack: list[int | None] = []
        parts: dict[int, list[str]] = {}
        diagnostics: list[Diagnostic] = []

        def before(operator: Any, operands: Any, _cm: Any, _tm: Any) -> None:
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

        def visit_text(
            text: str,
            _cm: Any,
            _tm: Any,
            _font: Any,
            _size: Any,
        ) -> None:
            if text and stack and stack[-1] is not None:
                parts.setdefault(stack[-1], []).append(text)

        page.extract_text(visitor_operand_before=before, visitor_text=visit_text)
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
            diagnostics=tuple(diagnostics),
        )
