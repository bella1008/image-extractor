from collections.abc import Callable
from importlib import import_module
import math
from typing import Any

from tagged_pdf_extractor.domain.models import BBox


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


def _effective_font_size(
    font_size: Any, text_matrix: Any, current_matrix: Any
) -> float | None:
    try:
        normalized_size = float(font_size)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(normalized_size) or normalized_size <= 0:
        return None

    try:
        tm = [float(value) for value in text_matrix[:6]]
        cm = [float(value) for value in current_matrix[:6]]
        if len(tm) != 6 or len(cm) != 6:
            raise ValueError
        combined_c = tm[2] * cm[0] + tm[3] * cm[2]
        combined_d = tm[2] * cm[1] + tm[3] * cm[3]
        scale_y = math.hypot(combined_c, combined_d)
    except (TypeError, ValueError, OverflowError, IndexError):
        return normalized_size

    effective_size = normalized_size * scale_y
    if not math.isfinite(effective_size) or effective_size <= 0:
        return None
    return effective_size


def _text_run_bbox(
    value: str,
    font: Any,
    font_size: Any,
    text_scale: Any,
    character_spacing: Any,
    text_matrix: Any,
    current_matrix: Any,
) -> BBox | None:
    try:
        normalized_size = float(font_size)
        normalized_text_scale = float(text_scale)
        normalized_character_spacing = float(character_spacing)
        tm = [float(item) for item in text_matrix[:6]]
        cm = [float(item) for item in current_matrix[:6]]
        if len(tm) != 6 or len(cm) != 6:
            return None
        if not all(
            math.isfinite(item)
            for item in (
                normalized_size,
                normalized_text_scale,
                normalized_character_spacing,
                *tm,
                *cm,
            )
        ):
            return None
        if normalized_size <= 0 or normalized_text_scale <= 0:
            return None

        scale_x = tm[0] * cm[0] + tm[1] * cm[2]
        rotate_x = tm[0] * cm[1] + tm[1] * cm[3]
        rotate_y = tm[2] * cm[0] + tm[3] * cm[2]
        scale_y = tm[2] * cm[1] + tm[3] * cm[3]
        left = tm[4] * cm[0] + tm[5] * cm[2] + cm[4]
        bottom = tm[4] * cm[1] + tm[5] * cm[3] + cm[5]
        if rotate_x != 0 or rotate_y != 0 or scale_x <= 0 or scale_y <= 0:
            return None

        get_text_width = getattr(font, "get_text_width", None)
        if not callable(get_text_width):
            return None
        glyph_width = float(get_text_width(value))
        width = (
            (glyph_width / 1000.0 * normalized_size)
            + normalized_character_spacing * len(value)
        ) * normalized_text_scale * scale_x
        height = normalized_size * scale_y
        right = left + width
        top = bottom + height
        bbox = (left, bottom, right, top)
        if not all(math.isfinite(item) for item in bbox):
            return None
        if right <= left or top <= bottom:
            return None
        return bbox
    except Exception:
        return None


class PypdfOperationTextRunner:
    """Run pypdf text state over original page operations."""

    def run(
        self,
        page: Any,
        *,
        on_boundary: Callable[[bytes, list[Any]], None],
        on_text: Callable[[str, str | None, float | None, BBox | None], None],
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
            geometry_ambiguous = False
            character_spacing: float | None = 0.0
            unmodeled_geometry_state = {
                b"Tw": False,
                b"Ts": False,
            }
            geometry_state_stack: list[
                tuple[float | None, dict[bytes, bool]]
            ] = []

            def visitor(
                value: str,
                current_matrix: Any,
                text_matrix: Any,
                _font_resource: Any,
                font_size: Any,
            ) -> None:
                nonlocal geometry_ambiguous
                if value:
                    font = extractor.font
                    font_name = getattr(font, "name", None)
                    if font_name is not None:
                        font_name = str(font_name).removeprefix("/")
                    normalized_font_size = _effective_font_size(
                        font_size, text_matrix, current_matrix
                    )
                    bbox = None
                    if (
                        not geometry_ambiguous
                        and character_spacing is not None
                        and not any(
                            unmodeled_geometry_state.values()
                        )
                    ):
                        bbox = _text_run_bbox(
                            value,
                            font,
                            font_size,
                            getattr(extractor, "char_scale", 1.0),
                            character_spacing,
                            text_matrix,
                            current_matrix,
                        )
                    geometry_ambiguous = False
                    _invoke_callback(
                        on_text, value, font_name, normalized_font_size, bbox
                    )

            extractor.initialize_extraction(
                (0, 90, 180, 270), visitor, font_resources, fonts
            )

            def process_position_change(
                operator: bytes, operands: list[Any]
            ) -> None:
                nonlocal geometry_ambiguous
                extractor._flush_text()
                geometry_ambiguous = True
                extractor.process_operation(operator, operands)
                extractor._flush_text()
                geometry_ambiguous = False

            for operands, operator in operations:
                if operator in (b"BMC", b"BDC", b"EMC"):
                    extractor._flush_text()
                    _invoke_callback(on_boundary, operator, operands)
                elif operator in (b"q", b"Q"):
                    extractor._flush_text()
                    if operator == b"q":
                        geometry_state_stack.append(
                            (character_spacing, unmodeled_geometry_state.copy())
                        )
                    elif geometry_state_stack:
                        (
                            character_spacing,
                            unmodeled_geometry_state,
                        ) = geometry_state_stack.pop()
                    extractor.process_operation(operator, operands)
                    extractor.memo_cm = extractor.cm_matrix.copy()
                    extractor.memo_tm = extractor.tm_matrix.copy()
                elif operator == b"Tc":
                    extractor._flush_text()
                    try:
                        candidate_spacing = float(operands[0])
                        character_spacing = (
                            candidate_spacing
                            if math.isfinite(candidate_spacing)
                            else None
                        )
                    except (IndexError, TypeError, ValueError, OverflowError):
                        character_spacing = None
                    extractor.process_operation(operator, operands)
                elif operator == b"Tz":
                    if extractor.text:
                        geometry_ambiguous = True
                    extractor.process_operation(operator, operands)
                elif operator in unmodeled_geometry_state:
                    try:
                        state_is_active = float(operands[0]) != 0.0
                    except (IndexError, TypeError, ValueError, OverflowError):
                        state_is_active = True
                    if extractor.text and (
                        unmodeled_geometry_state[operator] or state_is_active
                    ):
                        geometry_ambiguous = True
                    unmodeled_geometry_state[operator] = state_is_active
                    extractor.process_operation(operator, operands)
                elif operator == b"'":
                    process_position_change(b"T*", [])
                    extractor.process_operation(b"Tj", operands)
                elif operator == b'"' and len(operands) >= 3:
                    extractor._flush_text()
                    unmodeled_geometry_state[b"Tw"] = (
                        float(operands[0]) != 0.0
                    )
                    try:
                        candidate_spacing = float(operands[1])
                        character_spacing = (
                            candidate_spacing
                            if math.isfinite(candidate_spacing)
                            else None
                        )
                    except (TypeError, ValueError, OverflowError):
                        character_spacing = None
                    extractor.process_operation(b"Tw", [operands[0]])
                    extractor.process_operation(b"Tc", [operands[1]])
                    process_position_change(b"T*", [])
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
                    process_position_change(b"Td", operands)
                elif operator in (b"Td", b"Tm", b"T*"):
                    process_position_change(operator, operands)
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
