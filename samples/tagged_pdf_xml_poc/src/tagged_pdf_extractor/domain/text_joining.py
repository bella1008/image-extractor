import re


_WORD_OR_CLOSING = re.compile(r"[\w\)\]\}]$", re.UNICODE)
_WORD_OR_OPENING = re.compile(r"^[\w\(\[\{]", re.UNICODE)


def join_text_parts(
    parts: tuple[str, ...],
) -> tuple[str, tuple[dict[str, object], ...]]:
    if not parts:
        return "", ()

    result = parts[0]
    decisions: list[dict[str, object]] = []

    for boundary, next_part in enumerate(parts[1:]):
        if result and result[-1].isspace():
            result = result.rstrip() + " " + next_part.lstrip()
            action = "normalize_existing_space"
        elif next_part and next_part[0].isspace():
            result = result + " " + next_part.lstrip()
            action = "trim_left"
        elif (
            _WORD_OR_CLOSING.search(result) is not None
            and _WORD_OR_OPENING.search(next_part) is not None
        ):
            result = result + " " + next_part
            action = "insert_space"
        else:
            result = result + next_part
            action = "keep_adjacent"

        decisions.append({"boundary": boundary, "action": action})

    return result, tuple(decisions)
