from __future__ import annotations

from dataclasses import dataclass, replace
import math
import re
import unicodedata

from tagged_pdf_extractor.domain.models import (
    ContentFragment,
    InlineIconHint,
    SentenceBreakHint,
    StructureElement,
    TaggedDocument,
)
from tagged_pdf_extractor.domain.inline_icon_policy import (
    GENERIC_INLINE_ICON_REASON,
    NAVIGATION_ROUTE_INLINE_ICON_REASON,
    inline_icon_ratio_limits,
    parse_unambiguous_bbox,
)
from tagged_pdf_extractor.domain.paragraph_eligibility import (
    is_nonempty_inline_paragraph,
)
from tagged_pdf_extractor.domain.text_joining import join_text_parts


_INLINE_ROLES = frozenset({"span", "link"})
_FLOW_CONTAINER_ROLES = frozenset({"list_body", "table_cell"})
_FLOW_BARRIER_ROLES = frozenset(
    {"list", "table", "heading", "caption", "label", "figure"}
)
_INLINE_ICON_SUBTREE_BARRIER_ROLES = frozenset(
    {"heading", "caption", "label", "figure"}
)
_TERMINATORS = frozenset(".!?")
_CLOSING_CHARACTERS = frozenset("\"'”’»›)]}")
_OPENING_CHARACTERS = frozenset("\"'“‘«‹([{")
_CLOSING_PUNCTUATION_CATEGORIES = frozenset({"Pe", "Pf"})
_OPENING_PUNCTUATION_CATEGORIES = frozenset({"Ps", "Pi"})

_URL_PATTERN = re.compile(r"\b(?:https?://|www\.)[^\s<>{}\[\]]+", re.IGNORECASE)
_EMAIL_PATTERN = re.compile(
    r"(?<![\w.+-])[\w.+-]+@[\w-]+(?:\.[\w-]+)+",
    re.UNICODE,
)
_DOTTED_TOKEN_PATTERN = re.compile(
    r"(?<![\w-])[\w-]+(?:\.[\w-]+)+",
    re.UNICODE,
)
_COMPACT_ABBREVIATION_PATTERN = re.compile(
    r"(?<!\w)(?:[^\W\d_]\.){2,}",
    re.UNICODE,
)

_SOURCE_BOUNDARY = object()
_BLOCK_BOUNDARY = object()


@dataclass(frozen=True)
class _FragmentText:
    child_path: tuple[int, ...]
    text: str


@dataclass(frozen=True)
class _InlineFlowFragment:
    child_path: tuple[int, ...]
    fragment: ContentFragment


@dataclass(frozen=True)
class _InlineFlowFigure:
    child_path: tuple[int, ...]
    figure: StructureElement


@dataclass(frozen=True)
class _NavigationRouteEvidence:
    separator_count: int
    parenthesized: bool
    reference_font_size: float


def detect_sentence_break_hints(
    document: TaggedDocument,
) -> tuple[SentenceBreakHint, ...]:
    line_break_paths = {hint.child_path for hint in document.line_break_hints}
    subtitle_linked_body_paths = set(
        verified_subtitle_linked_body_paths(document)
    )
    offsets_by_path: dict[tuple[int, ...], set[int]] = {}

    for flow in _eligible_flows(
        document.children,
        line_break_paths,
        subtitle_linked_body_paths,
    ):
        text, locations = _join_flow(flow)
        for start in sentence_start_offsets(text):
            location = locations[start]
            if location is None:
                continue
            child_path, local_offset = location
            offsets_by_path.setdefault(child_path, set()).add(local_offset)

    return tuple(
        SentenceBreakHint(
            child_path=child_path,
            offsets=tuple(sorted(offsets)),
        )
        for child_path, offsets in sorted(offsets_by_path.items())
    )


def detect_inline_icon_hints(
    document: TaggedDocument,
) -> tuple[InlineIconHint, ...]:
    hints_by_path: dict[tuple[int, ...], InlineIconHint] = {}
    for flow in _inline_icon_flows(document.children):
        for index, item in enumerate(flow):
            if not isinstance(item, _InlineFlowFigure):
                continue
            hint = _inline_icon_hint(flow, index, item)
            if hint is not None:
                hints_by_path.setdefault(hint.child_path, hint)
    return tuple(hints_by_path[path] for path in sorted(hints_by_path))


def apply_readability_formatting(document: TaggedDocument) -> TaggedDocument:
    return replace(
        document,
        sentence_break_hints=detect_sentence_break_hints(document),
        inline_icon_hints=detect_inline_icon_hints(document),
    )


def _inline_icon_flows(
    children: tuple[StructureElement | ContentFragment, ...],
) -> tuple[tuple[_InlineFlowFragment | _InlineFlowFigure, ...], ...]:
    flows: list[tuple[_InlineFlowFragment | _InlineFlowFigure, ...]] = []

    def visit(
        siblings: tuple[StructureElement | ContentFragment, ...],
        parent_path: tuple[int, ...],
    ) -> None:
        for index, child in enumerate(siblings):
            if not isinstance(child, StructureElement):
                continue
            child_path = (*parent_path, index)
            role = child.semantic_role
            if role in _INLINE_ICON_SUBTREE_BARRIER_ROLES:
                continue

            if role == "paragraph":
                tokens = _inline_icon_tokens(child.children, child_path)
                if _BLOCK_BOUNDARY not in tokens:
                    flow = tuple(
                        token
                        for token in tokens
                        if isinstance(
                            token, (_InlineFlowFragment, _InlineFlowFigure)
                        )
                    )
                    if flow:
                        flows.append(flow)
            elif role == "list_body":
                flows.extend(
                    _inline_icon_segments(
                        _inline_icon_tokens(child.children, child_path)
                    )
                )

            visit(child.children, child_path)

    visit(children, ())
    return tuple(flows)


def _inline_icon_tokens(
    siblings: tuple[StructureElement | ContentFragment, ...],
    parent_path: tuple[int, ...],
) -> tuple[_InlineFlowFragment | _InlineFlowFigure | object, ...]:
    tokens: list[_InlineFlowFragment | _InlineFlowFigure | object] = []
    for index, child in enumerate(siblings):
        child_path = (*parent_path, index)
        if isinstance(child, ContentFragment):
            tokens.append(_InlineFlowFragment(child_path, child))
        elif child.semantic_role in _INLINE_ROLES:
            tokens.extend(_inline_icon_tokens(child.children, child_path))
        elif child.semantic_role == "figure":
            tokens.append(_InlineFlowFigure(child_path, child))
        else:
            tokens.append(_BLOCK_BOUNDARY)
    return tuple(tokens)


def _inline_icon_segments(
    tokens: tuple[_InlineFlowFragment | _InlineFlowFigure | object, ...],
) -> tuple[tuple[_InlineFlowFragment | _InlineFlowFigure, ...], ...]:
    segments: list[tuple[_InlineFlowFragment | _InlineFlowFigure, ...]] = []
    current: list[_InlineFlowFragment | _InlineFlowFigure] = []
    for token in tokens:
        if isinstance(token, (_InlineFlowFragment, _InlineFlowFigure)):
            current.append(token)
        elif current:
            segments.append(tuple(current))
            current = []
    if current:
        segments.append(tuple(current))
    return tuple(segments)


def _inline_icon_hint(
    flow: tuple[_InlineFlowFragment | _InlineFlowFigure, ...],
    index: int,
    candidate: _InlineFlowFigure,
) -> InlineIconHint | None:
    figure = candidate.figure
    if (
        not isinstance(figure.page_index, int)
        or isinstance(figure.page_index, bool)
        or figure.page_index < 0
        or _has_visible_figure_text(figure)
    ):
        return None

    bbox = _figure_bbox(figure)
    if bbox is None:
        return None

    adjacent = tuple(
        fragment
        for fragment in (
            _adjacent_visible_fragment(flow, index, -1),
            _adjacent_visible_fragment(flow, index, 1),
        )
        if fragment is not None
        and fragment.fragment.page_index == figure.page_index
    )
    if not adjacent:
        return None

    same_page_segment = _same_page_segment(flow, index, figure.page_index)
    route_evidence = _navigation_route_evidence(
        same_page_segment,
        same_page_segment.index(candidate),
    )
    reason = GENERIC_INLINE_ICON_REASON
    if route_evidence is not None:
        reason = NAVIGATION_ROUTE_INLINE_ICON_REASON
        reference_font_size = route_evidence.reference_font_size
    else:
        reference_font_size = _flow_reference_font_size(same_page_segment)
        if reference_font_size is None:
            return None

    width = bbox[2] - bbox[0]
    height = bbox[3] - bbox[1]
    width_ratio = width / reference_font_size
    height_ratio = height / reference_font_size
    max_width_ratio, max_height_ratio = inline_icon_ratio_limits(reason)
    if (
        width_ratio > max_width_ratio
        or height_ratio > max_height_ratio
    ):
        return None

    return InlineIconHint(
        child_path=candidate.child_path,
        page_index=figure.page_index,
        bbox=bbox,
        reference_font_size=reference_font_size,
        width_ratio=width_ratio,
        height_ratio=height_ratio,
        reason=reason,
        route_separator_count=(
            route_evidence.separator_count
            if route_evidence is not None
            else None
        ),
        route_parenthesized=(
            route_evidence.parenthesized
            if route_evidence is not None
            else None
        ),
    )


def _same_page_segment(
    flow: tuple[_InlineFlowFragment | _InlineFlowFigure, ...],
    candidate_index: int,
    page_index: int,
) -> tuple[_InlineFlowFragment | _InlineFlowFigure, ...]:
    start = candidate_index
    while start > 0 and _flow_item_page_index(flow[start - 1]) == page_index:
        start -= 1
    end = candidate_index + 1
    while end < len(flow) and _flow_item_page_index(flow[end]) == page_index:
        end += 1
    return flow[start:end]


def _flow_item_page_index(
    item: _InlineFlowFragment | _InlineFlowFigure,
) -> int | None:
    if isinstance(item, _InlineFlowFragment):
        return item.fragment.page_index
    return item.figure.page_index


def _navigation_route_evidence(
    segment: tuple[_InlineFlowFragment | _InlineFlowFigure, ...],
    candidate_index: int,
) -> _NavigationRouteEvidence | None:
    nearest = tuple(
        fragment
        for fragment in (
            _adjacent_visible_fragment(segment, candidate_index, -1),
            _adjacent_visible_fragment(segment, candidate_index, 1),
        )
        if fragment is not None
    )
    if not nearest or not any(
        _is_navigation_separator_adjacent(item.fragment.text)
        for item in nearest
    ):
        return None

    separator_count = sum(
        item.fragment.text.count(">")
        for item in segment
        if isinstance(item, _InlineFlowFragment)
    )
    if separator_count < 2:
        return None

    reference_font_size = _flow_reference_font_size(segment)
    if reference_font_size is None:
        return None

    before = "".join(
        item.fragment.text
        for item in segment[:candidate_index]
        if isinstance(item, _InlineFlowFragment)
    )
    after = "".join(
        item.fragment.text
        for item in segment[candidate_index + 1 :]
        if isinstance(item, _InlineFlowFragment)
    )
    parenthesized = before.rfind("(") > before.rfind(")") and ")" in after
    return _NavigationRouteEvidence(
        separator_count=separator_count,
        parenthesized=parenthesized,
        reference_font_size=reference_font_size,
    )


def _is_navigation_separator_adjacent(text: str) -> bool:
    stripped = text.strip()
    return stripped.startswith(">") or stripped.endswith(">")


def _flow_reference_font_size(
    segment: tuple[_InlineFlowFragment | _InlineFlowFigure, ...],
) -> float | None:
    weights: list[tuple[float, int]] = []
    for item in segment:
        if not isinstance(item, _InlineFlowFragment):
            continue
        if _visible_character_count(item.fragment.text) == 0:
            continue
        fragment_weights = _visible_font_size_weights(item.fragment)
        if fragment_weights is None:
            return None
        weights.extend(fragment_weights)
    if not weights:
        return None

    largest_font_size = max(font_size for font_size, _ in weights)
    credible_weights = tuple(
        (font_size, weight)
        for font_size, weight in weights
        if font_size >= largest_font_size * 0.5
    )
    return _weighted_median(credible_weights)


def _adjacent_visible_fragment(
    flow: tuple[_InlineFlowFragment | _InlineFlowFigure, ...],
    figure_index: int,
    direction: int,
) -> _InlineFlowFragment | None:
    index = figure_index + direction
    while 0 <= index < len(flow):
        item = flow[index]
        if isinstance(item, _InlineFlowFigure):
            return None
        if _visible_character_count(item.fragment.text) > 0:
            return item
        index += direction
    return None


def _has_visible_figure_text(element: StructureElement) -> bool:
    if (
        element.actual_text is not None
        and _visible_character_count(element.actual_text) > 0
    ):
        return True
    for child in element.children:
        if isinstance(child, ContentFragment):
            if _visible_character_count(child.text) > 0:
                return True
        elif _has_visible_figure_text(child):
            return True
    return False


def _figure_bbox(
    figure: StructureElement,
) -> tuple[float, float, float, float] | None:
    return parse_unambiguous_bbox(figure.attributes)


def _visible_font_size_weights(
    fragment: ContentFragment,
) -> tuple[tuple[float, int], ...] | None:
    if len(fragment.text_parts) != len(fragment.text_styles):
        return None

    weights: list[tuple[float, int]] = []
    for text, style in zip(fragment.text_parts, fragment.text_styles):
        visible_count = _visible_character_count(text)
        if visible_count == 0:
            continue
        font_size = style.font_size
        if (
            font_size is None
            or isinstance(font_size, bool)
            or not isinstance(font_size, (int, float))
        ):
            return None
        try:
            numeric_font_size = float(font_size)
        except (OverflowError, TypeError, ValueError):
            return None
        if not math.isfinite(numeric_font_size) or numeric_font_size <= 0:
            return None
        weights.append((numeric_font_size, visible_count))
    return tuple(weights) or None


def _visible_character_count(text: str) -> int:
    return sum(not character.isspace() for character in text)


def _weighted_median(weights: tuple[tuple[float, int], ...]) -> float:
    ordered = sorted(weights)
    total_weight = sum(weight for _, weight in ordered)
    lower_rank = (total_weight + 1) // 2
    upper_rank = (total_weight + 2) // 2
    lower = _weighted_rank_value(ordered, lower_rank)
    upper = _weighted_rank_value(ordered, upper_rank)
    return (lower + upper) / 2.0


def _weighted_rank_value(
    ordered: list[tuple[float, int]], rank: int
) -> float:
    cumulative = 0
    for value, weight in ordered:
        cumulative += weight
        if cumulative >= rank:
            return value
    raise ValueError("weighted rank exceeds total weight")


def _eligible_flows(
    children: tuple[StructureElement | ContentFragment, ...],
    line_break_paths: set[tuple[int, ...]],
    subtitle_linked_body_paths: set[tuple[int, ...]],
) -> tuple[tuple[_FragmentText, ...], ...]:
    flows: list[tuple[_FragmentText, ...]] = []

    def visit(
        siblings: tuple[StructureElement | ContentFragment, ...],
        parent_path: tuple[int, ...],
        ancestors: tuple[str, ...],
    ) -> None:
        for index, child in enumerate(siblings):
            if not isinstance(child, StructureElement):
                continue
            child_path = (*parent_path, index)
            if child.semantic_role == "list_body":
                flows.extend(
                    _direct_list_body_flows(
                        child,
                        child_path,
                        line_break_paths,
                    )
                )
            if child.semantic_role == "paragraph" and (
                _eligible_paragraph_context(ancestors)
                or child_path in subtitle_linked_body_paths
            ):
                flows.extend(
                    _leaf_paragraph_flows(
                        child,
                        child_path,
                        line_break_paths,
                    )
                )
            visit(
                child.children,
                child_path,
                (*ancestors, child.semantic_role),
            )

    visit(children, (), ())
    return tuple(flows)


def is_verified_subtitle_table_wrapper_pair(
    *,
    wrapper_role: str | None,
    meaningful_wrapper_child_roles: tuple[str | None, ...],
    following_role: str | None,
    table_contains_verified_subtitle: bool,
    following_is_nonempty_inline_leaf: bool,
) -> bool:
    """Return whether adjacent nodes match the approved subtitle/body topology."""
    return (
        wrapper_role == "paragraph"
        and meaningful_wrapper_child_roles == ("table",)
        and following_role == "paragraph"
        and table_contains_verified_subtitle
        and following_is_nonempty_inline_leaf
    )


def verified_subtitle_linked_body_paths(
    document: TaggedDocument,
) -> tuple[tuple[int, ...], ...]:
    subtitle_paths = {hint.child_path for hint in document.subtitle_hints}
    if not subtitle_paths:
        return ()

    body_paths: set[tuple[int, ...]] = set()

    def visit(
        siblings: tuple[StructureElement | ContentFragment, ...],
        parent_path: tuple[int, ...],
        ancestors: tuple[str, ...],
    ) -> None:
        for index, wrapper in enumerate(siblings):
            if not isinstance(wrapper, StructureElement):
                continue
            wrapper_path = (*parent_path, index)
            if (
                not any(role in _FLOW_BARRIER_ROLES for role in ancestors)
                and index + 1 < len(siblings)
            ):
                following = siblings[index + 1]
                meaningful = tuple(
                    (child_index, child)
                    for child_index, child in enumerate(wrapper.children)
                    if _is_meaningful_wrapper_child(child)
                )
                child_roles = tuple(
                    child.semantic_role
                    if isinstance(child, StructureElement)
                    else None
                    for _, child in meaningful
                )
                table_path = (
                    (*wrapper_path, meaningful[0][0])
                    if child_roles == ("table",)
                    else None
                )
                table_has_subtitle = table_path is not None and any(
                    len(path) > len(table_path)
                    and path[: len(table_path)] == table_path
                    for path in subtitle_paths
                )
                following_path = (*parent_path, index + 1)
                following_is_leaf = (
                    isinstance(following, StructureElement)
                    and is_nonempty_inline_paragraph(following)
                )
                if is_verified_subtitle_table_wrapper_pair(
                    wrapper_role=wrapper.semantic_role,
                    meaningful_wrapper_child_roles=child_roles,
                    following_role=(
                        following.semantic_role
                        if isinstance(following, StructureElement)
                        else None
                    ),
                    table_contains_verified_subtitle=table_has_subtitle,
                    following_is_nonempty_inline_leaf=following_is_leaf,
                ):
                    body_paths.add(following_path)
            visit(
                wrapper.children,
                wrapper_path,
                (*ancestors, wrapper.semantic_role),
            )

    visit(document.children, (), ())
    return tuple(sorted(body_paths))


def _is_meaningful_wrapper_child(
    child: StructureElement | ContentFragment,
) -> bool:
    if isinstance(child, ContentFragment):
        return bool(child.text.strip())
    if child.semantic_role in _INLINE_ROLES:
        return bool(child.actual_text and child.actual_text.strip()) or any(
            _is_meaningful_wrapper_child(descendant)
            for descendant in child.children
        )
    return True


def _eligible_paragraph_context(ancestors: tuple[str, ...]) -> bool:
    for role in reversed(ancestors):
        if role in _FLOW_CONTAINER_ROLES:
            return True
        if role in _FLOW_BARRIER_ROLES:
            return False
    return False


def _direct_list_body_flows(
    body: StructureElement,
    body_path: tuple[int, ...],
    line_break_paths: set[tuple[int, ...]],
) -> tuple[tuple[_FragmentText, ...], ...]:
    tokens = _inline_tokens(body.children, body_path, line_break_paths)
    return _segments(tokens)


def _leaf_paragraph_flows(
    paragraph: StructureElement,
    paragraph_path: tuple[int, ...],
    line_break_paths: set[tuple[int, ...]],
) -> tuple[tuple[_FragmentText, ...], ...]:
    tokens = _inline_tokens(
        paragraph.children,
        paragraph_path,
        line_break_paths,
    )
    if _BLOCK_BOUNDARY in tokens:
        return ()
    return _segments(tokens)


def _inline_tokens(
    siblings: tuple[StructureElement | ContentFragment, ...],
    parent_path: tuple[int, ...],
    line_break_paths: set[tuple[int, ...]],
) -> tuple[_FragmentText | object, ...]:
    tokens: list[_FragmentText | object] = []
    for index, child in enumerate(siblings):
        child_path = (*parent_path, index)
        if isinstance(child, ContentFragment):
            text, _ = join_text_parts(child.text_parts)
            if text:
                tokens.append(_FragmentText(child_path, text))
            continue
        if child_path in line_break_paths:
            tokens.append(_SOURCE_BOUNDARY)
            continue
        if child.semantic_role in _INLINE_ROLES:
            tokens.extend(
                _inline_tokens(child.children, child_path, line_break_paths)
            )
            continue
        tokens.append(_BLOCK_BOUNDARY)
    return tuple(tokens)


def _segments(
    tokens: tuple[_FragmentText | object, ...],
) -> tuple[tuple[_FragmentText, ...], ...]:
    segments: list[tuple[_FragmentText, ...]] = []
    current: list[_FragmentText] = []
    for token in tokens:
        if isinstance(token, _FragmentText):
            current.append(token)
            continue
        if current:
            segments.append(tuple(current))
            current = []
    if current:
        segments.append(tuple(current))
    return tuple(segments)


def _join_flow(
    fragments: tuple[_FragmentText, ...],
) -> tuple[str, tuple[tuple[tuple[int, ...], int] | None, ...]]:
    characters: list[str] = []
    locations: list[tuple[tuple[int, ...], int] | None] = []
    for fragment in fragments:
        if (
            characters
            and fragment.text
            and _needs_synthetic_space(characters[-1], fragment.text[0])
        ):
            characters.append(" ")
            locations.append(None)
        characters.extend(fragment.text)
        locations.extend(
            (fragment.child_path, offset)
            for offset in range(len(fragment.text))
        )
    return "".join(characters), tuple(locations)


def _needs_synthetic_space(
    previous_character: str,
    next_character: str,
) -> bool:
    _, decisions = join_text_parts((previous_character, next_character))
    return decisions[0]["action"] == "insert_space"


def sentence_start_offsets(text: str) -> tuple[int, ...]:
    protected = _protected_terminators(text)
    starts: list[int] = []
    for index, character in enumerate(text):
        if character not in _TERMINATORS or protected[index]:
            continue
        start = _next_sentence_start(text, index)
        if start is not None:
            starts.append(start)
    return tuple(starts)


def _next_sentence_start(text: str, terminator_index: int) -> int | None:
    cursor = terminator_index + 1
    while cursor < len(text) and _is_closing_punctuation(text[cursor]):
        cursor += 1
    while cursor < len(text) and text[cursor].isspace():
        cursor += 1
    if cursor >= len(text):
        return None

    visible_start = cursor
    while cursor < len(text) and _is_opening_punctuation(text[cursor]):
        cursor += 1
    if cursor >= len(text) or not _valid_sentence_initial(text[cursor]):
        return None
    return visible_start


def _is_closing_punctuation(character: str) -> bool:
    return (
        character in _CLOSING_CHARACTERS
        or unicodedata.category(character) in _CLOSING_PUNCTUATION_CATEGORIES
    )


def _is_opening_punctuation(character: str) -> bool:
    return (
        character in _OPENING_CHARACTERS
        or unicodedata.category(character) in _OPENING_PUNCTUATION_CATEGORIES
    )


def _valid_sentence_initial(character: str) -> bool:
    return (
        character.isupper()
        or character.isdigit()
        or unicodedata.category(character) == "Lo"
    )


def _protected_terminators(text: str) -> tuple[bool, ...]:
    protected = [False] * len(text)

    for match in _URL_PATTERN.finditer(text):
        end = _url_protected_end(text, match.start(), match.end())
        _mark_terminators(text, protected, match.start(), end)

    for pattern in (_EMAIL_PATTERN, _COMPACT_ABBREVIATION_PATTERN):
        for match in pattern.finditer(text):
            _mark_terminators(text, protected, match.start(), match.end())

    for match in _DOTTED_TOKEN_PATTERN.finditer(text):
        token = match.group()
        components = token.split(".")
        uppercase_extension = (
            len(components) == 2
            and all(component.isalpha() for component in components)
            and len(components[1]) >= 2
            and components[1].isupper()
        )
        if (
            token.count(".") >= 2
            or any(character.isdigit() for character in token)
            or uppercase_extension
        ):
            _mark_terminators(text, protected, match.start(), match.end())

    for index in range(1, len(text) - 1):
        if (
            text[index] == "."
            and text[index - 1].isdigit()
            and text[index + 1].isdigit()
        ):
            protected[index] = True

    _protect_compact_single_period_tokens(text, protected)
    _protect_initials(text, protected)
    return tuple(protected)


def _protect_compact_single_period_tokens(
    text: str,
    protected: list[bool],
) -> None:
    """Protect short title/code-like words whose trailing period is ambiguous."""

    for period_index, character in enumerate(text):
        if character != "." or protected[period_index]:
            continue
        token_start = period_index
        while token_start > 0 and text[token_start - 1].isalpha():
            token_start -= 1
        token = text[token_start:period_index]
        if not 1 <= len(token) <= 3:
            continue
        if token_start > 0 and (
            text[token_start - 1].isalnum() or text[token_start - 1] == "_"
        ):
            continue
        first = token[0]
        if (
            len(token) >= 2
            and first.isupper()
            and all(character.islower() for character in token[1:])
        ):
            protected[period_index] = True
            continue
        following = period_index + 1
        while following < len(text) and text[following].isspace():
            following += 1
        if (
            len(token) == 1
            and unicodedata.category(first) == "Lo"
            and following < len(text)
            and text[following].isdigit()
        ):
            protected[period_index] = True


def _url_protected_end(text: str, start: int, end: int) -> int:
    while end > start and _is_external_url_closer(text, start, end):
        end -= 1
    while end > start and text[end - 1] in ".,!?;:":
        end -= 1
    return end


def _is_external_url_closer(text: str, start: int, end: int) -> bool:
    character = text[end - 1]
    if not _is_closing_punctuation(character):
        return False
    if character != ")":
        return True
    candidate = text[start:end]
    return candidate.count(")") > candidate.count("(")


def _mark_terminators(
    text: str,
    protected: list[bool],
    start: int,
    end: int,
) -> None:
    for index in range(start, end):
        if text[index] in _TERMINATORS:
            protected[index] = True


def _protect_initials(text: str, protected: list[bool]) -> None:
    initial_periods: set[int] = set()
    for index, character in enumerate(text):
        if character != "." or index == 0:
            continue
        initial = text[index - 1]
        if not initial.isalpha() or not initial.isupper():
            continue
        if index >= 2 and (text[index - 2].isalnum() or text[index - 2] == "_"):
            continue
        initial_periods.add(index)

    for index in initial_periods:
        following = index + 1
        while following < len(text) and text[following].isspace():
            following += 1
        if following + 1 in initial_periods:
            protected[index] = True
            protected[following + 1] = True
            continue
        if following >= len(text) or not text[following].isupper():
            continue
        preceding = index - 2
        while preceding >= 0 and text[preceding].isspace():
            preceding -= 1
        if preceding < 0 or not text[preceding].isdigit():
            protected[index] = True
