ROLE_MAP = {
    "Document": "document",
    "document": "document",
    "Part": "part",
    "part": "part",
    "Art": "article",
    "article": "article",
    "Sect": "section",
    "section": "section",
    "Div": "division",
    "division": "division",
    "P": "paragraph",
    "paragraph": "paragraph",
    "L": "list",
    "list": "list",
    "LI": "list_item",
    "list_item": "list_item",
    "Lbl": "label",
    "label": "label",
    "LBody": "list_body",
    "list_body": "list_body",
    "Table": "table",
    "table": "table",
    "TR": "table_row",
    "table_row": "table_row",
    "TH": "table_header",
    "table_header": "table_header",
    "TD": "table_cell",
    "table_cell": "table_cell",
    "Figure": "figure",
    "figure": "figure",
    "Caption": "caption",
    "caption": "caption",
    "Span": "span",
    "span": "span",
    "Link": "link",
    "link": "link",
}


def map_role(source_role: str, role_map: dict[str, str]) -> tuple[str, int | None]:
    resolved = role_map.get(source_role, source_role)
    if resolved == "H":
        return "heading", None
    if len(resolved) == 2 and resolved[0] == "H" and resolved[1].isdigit():
        return "heading", int(resolved[1])
    if resolved == "Title":
        return "heading", 1
    return ROLE_MAP.get(resolved, "unknown"), None
