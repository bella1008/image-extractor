from collections.abc import Callable
from importlib import import_module
import math
from typing import Any


class PypdfOperationTextError(RuntimeError):
    pass


def _load_pypdf_text_helpers() -> tuple[Any, Any, Any, Any]:
    try:
        font_module = import_module("pypdf._font")
        text_module = import_module("pypdf._text_extraction._text_extractor")
        generic_module = import_module("pypdf.generic")
        return (
            getattr(font_module, "Font"),
            getattr(text_module, "TextExtraction"),
            getattr(generic_module, "ContentStream"),
            getattr(generic_module, "NullObject"),
        )
    except (ImportError, AttributeError) as exc:
        raise PypdfOperationTextError(
            "Required private pypdf text helpers are unavailable"
        ) from exc


class _CallbackRaised(Exception):
    def __init__(self, error: BaseException) -> None:
        self.error = error
        self.cause = error.__cause__
        self.context = error.__context__
        self.suppress_context = error.__suppress_context__
        self.traceback = error.__traceback__


def _invoke_callback(callback: Callable[..., None], *args: Any) -> None:
    try:
        callback(*args)
    except BaseException as exc:
        raise _CallbackRaised(exc) from None


class PypdfOperationTextRunner:
    """Run pypdf text state over original page operations."""

    def run(
        self,
        page: Any,
        *,
        on_boundary: Callable[[bytes, list[Any]], None],
        on_text: Callable[[str, str | None, float | None], None],
        on_xobject: Callable[[Any], None] | None = None,
    ) -> None:
        callback_failure: _CallbackRaised | None = None
        try:
            Font, TextExtraction, ContentStream, NullObject = (
                _load_pypdf_text_helpers()
            )
            source_content = page.get("/Contents")
            if source_content is None:
                return
            source_content = source_content.get_object()
            if isinstance(source_content, NullObject):
                return

            resources = page.get_inherited(key="/Resources", default=None)
            if resources is None:
                raise KeyError("page has no inherited /Resources")
            get_resources_object = getattr(resources, "get_object", None)
            if callable(get_resources_object):
                resources = get_resources_object()

            font_resources: dict[str, Any] = {}
            fonts: dict[str, Any] = {}
            font_resource_dict = resources.get("/Font", {})
            get_font_dict_object = getattr(font_resource_dict, "get_object", None)
            if callable(get_font_dict_object):
                font_resource_dict = get_font_dict_object()
            for font_name in font_resource_dict:
                font_object = font_resource_dict[font_name].get_object()
                font_resources[font_name] = font_object
                font = Font.from_font_resource(font_object)
                if font.character_widths.get(font.space_char, 0) == 0:
                    font.space_width = 200.0
                fonts[font_name] = font

            content = (
                source_content
                if isinstance(source_content, ContentStream)
                else ContentStream(source_content, page.pdf, "bytes")
            )
            operations = tuple(content.operations)

            extractor = TextExtraction()

            def visitor(
                value: str,
                _cm: Any,
                _tm: Any,
                _font_resource: Any,
                font_size: Any,
            ) -> None:
                if value:
                    font = extractor.font
                    font_name = getattr(font, "name", None)
                    if font_name is not None:
                        font_name = str(font_name).removeprefix("/")
                    try:
                        normalized_font_size = float(font_size)
                    except (TypeError, ValueError, OverflowError):
                        normalized_font_size = None
                    if normalized_font_size is not None and (
                        not math.isfinite(normalized_font_size)
                        or normalized_font_size <= 0
                    ):
                        normalized_font_size = None
                    _invoke_callback(
                        on_text, value, font_name, normalized_font_size
                    )

            extractor.initialize_extraction(
                (0, 90, 180, 270), visitor, font_resources, fonts
            )

            for operands, operator in operations:
                if operator in (b"BMC", b"BDC", b"EMC"):
                    extractor._flush_text()
                    _invoke_callback(on_boundary, operator, operands)
                elif operator == b"'":
                    extractor.process_operation(b"T*", [])
                    extractor.process_operation(b"Tj", operands)
                elif operator == b'"' and len(operands) >= 3:
                    extractor.process_operation(b"Tw", [operands[0]])
                    extractor.process_operation(b"Tc", [operands[1]])
                    extractor.process_operation(b"T*", [])
                    extractor.process_operation(b"Tj", operands[2:])
                elif operator == b"TJ":
                    threshold = extractor._space_width * 0.95
                    for item in operands[0] if operands else ():
                        if isinstance(item, (str, bytes)):
                            extractor.process_operation(b"Tj", [item])
                        elif isinstance(item, (int, float)):
                            if (
                                abs(float(item)) >= threshold
                                and extractor.text
                                and not extractor.text.endswith(" ")
                            ):
                                extractor.process_operation(b"Tj", [" "])
                elif operator == b"TD" and len(operands) >= 2:
                    extractor.process_operation(b"TL", [-operands[1]])
                    extractor.process_operation(b"Td", operands)
                elif operator == b"Do":
                    extractor._flush_text()
                    if on_xobject is not None:
                        operand = operands[0] if operands else None
                        _invoke_callback(on_xobject, operand)
                else:
                    extractor.process_operation(operator, operands)

            extractor._flush_text()
        except _CallbackRaised as exc:
            callback_failure = exc
        except PypdfOperationTextError:
            raise
        except Exception as exc:
            raise PypdfOperationTextError(
                "Unable to run pypdf text extraction operations"
            ) from exc

        if callback_failure is not None:
            callback_error = callback_failure.error
            callback_error.__cause__ = callback_failure.cause
            callback_error.__context__ = callback_failure.context
            callback_error.__suppress_context__ = callback_failure.suppress_context
            callback_error.__traceback__ = callback_failure.traceback
            raise callback_error
