from __future__ import annotations

from dataclasses import dataclass, replace
import re
import unicodedata

from tagged_pdf_extractor.domain.models import (
    ContentFragment,
    InlineIconHint,
    SentenceBreakHint,
    StructureElement,
    TaggedDocument,
)
from tagged_pdf_extractor.domain.text_joining import join_text_parts


_INLINE_ROLES = frozenset({"span", "link"})
_FLOW_CONTAINER_ROLES = frozenset({"list_body", "table_cell"})
_FLOW_BARRIER_ROLES = frozenset(
    {"list", "table", "heading", "caption", "label", "figure"}
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


def detect_sentence_break_hints(
    document: TaggedDocument,
) -> tuple[SentenceBreakHint, ...]:
    line_break_paths = {hint.child_path for hint in document.line_break_hints}
    offsets_by_path: dict[tuple[int, ...], set[int]] = {}

    for flow in _eligible_flows(document.children, line_break_paths):
        text, locations = _join_flow(flow)
        for start in _sentence_starts(text):
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
    return ()


def apply_readability_formatting(document: TaggedDocument) -> TaggedDocument:
    return replace(
        document,
        sentence_break_hints=detect_sentence_break_hints(document),
        inline_icon_hints=detect_inline_icon_hints(document),
    )


def _eligible_flows(
    children: tuple[StructureElement | ContentFragment, ...],
    line_break_paths: set[tuple[int, ...]],
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
            if child.semantic_role == "paragraph" and _eligible_paragraph_context(
                ancestors
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


def _sentence_starts(text: str) -> tuple[int, ...]:
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
        end = match.end()
        while end > match.start() and text[end - 1] in ".,!?;:":
            end -= 1
        _mark_terminators(text, protected, match.start(), end)

    for pattern in (_EMAIL_PATTERN, _COMPACT_ABBREVIATION_PATTERN):
        for match in pattern.finditer(text):
            _mark_terminators(text, protected, match.start(), match.end())

    for match in _DOTTED_TOKEN_PATTERN.finditer(text):
        token = match.group()
        components = token.split(".")
        uppercase_pair = len(components) == 2 and all(
            component.isalpha() and component.isupper()
            for component in components
        )
        if (
            token.count(".") >= 2
            or any(character.isdigit() for character in token)
            or uppercase_pair
        ):
            _mark_terminators(text, protected, match.start(), match.end())

    for index in range(1, len(text) - 1):
        if (
            text[index] == "."
            and text[index - 1].isdigit()
            and text[index + 1].isdigit()
        ):
            protected[index] = True

    _protect_initials(text, protected)
    return tuple(protected)


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
