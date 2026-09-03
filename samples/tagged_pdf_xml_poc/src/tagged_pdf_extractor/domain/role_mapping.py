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


def map_role(source_role: str, role_map: dict[str, str]) -> tuple[str, int | None]:
    resolved = role_map.get(source_role, source_role)
    if resolved == "H":
        return "heading", None
    if len(resolved) == 2 and resolved[0] == "H" and resolved[1] in "123456":
        return "heading", int(resolved[1])
    if resolved == "Title":
        return "heading", 1
    return ROLE_MAP.get(resolved, "unknown"), None
