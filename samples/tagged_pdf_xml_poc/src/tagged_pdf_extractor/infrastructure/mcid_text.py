from dataclasses import dataclass
from typing import Any

from tagged_pdf_extractor.domain.models import Diagnostic


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
                if operator == b"BDC" and len(operands) > 1:
                    properties = operands[1]
                    if hasattr(properties, "get") and properties.get("/MCID") is not None:
                        mcid = int(properties["/MCID"])
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
        return McidTextResult(
            parts_by_mcid={mcid: tuple(values) for mcid, values in parts.items()},
            diagnostics=tuple(diagnostics),
        )
