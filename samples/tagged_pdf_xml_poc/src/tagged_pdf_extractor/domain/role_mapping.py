import re


ROLE_MAP = {
    "Document": "document",
    "Part": "part",
    "Art": "article",
    "Sect": "section",
    "Div": "division",
    "P": "paragraph",
    "L": "list",
    "LI": "list_item",
    "Lbl": "label",
    "LBody": "list_body",
    "Table": "table",
    "TR": "table_row",
    "TH": "table_header",
    "TD": "table_cell",
    "Figure": "figure",
    "Caption": "caption",
    "Span": "span",
    "Link": "link",
}
_HEADING_CANDIDATE = re.compile(
    r"heading(?:(?P<level>[1-6])(?=$|\D)|$)", re.IGNORECASE
)
_TITLE_CANDIDATE = re.compile(r"(?:^|[_-])title$", re.IGNORECASE)


def heading_candidate_level(source_role: str) -> int | None:
    match = _HEADING_CANDIDATE.search(source_role)
    return int(match.group("level")) if match and match.group("level") else None


def is_heading_candidate(source_role: str) -> bool:
    return bool(
        _HEADING_CANDIDATE.search(source_role)
        or _TITLE_CANDIDATE.search(source_role)
    )


def map_role(source_role: str, role_map: dict[str, str]) -> tuple[str, int | None]:
    resolved = role_map.get(source_role, source_role)
    if resolved == "H":
        return "heading", None
    if len(resolved) == 2 and resolved[0] == "H" and resolved[1] in "123456":
        return "heading", int(resolved[1])
    if resolved == "Title":
        return "heading", 1
    return ROLE_MAP.get(resolved, "unknown"), None
