"""Fail-closed exception for a visually verified, fingerprinted source difference."""
from collections import Counter

from tagged_pdf_extractor.domain.africa_book import africa_book_scope
from tagged_pdf_extractor.domain.models import ContentFragment, HeadingCountSourceException
from tagged_pdf_extractor.domain.role_mapping import heading_candidate_level

VERIFIED_SHA256 = "cdc2123f2e1dde2f46314a9ef31bda0bdfb4b4455ff26436838004d65e05c848"
JORDAN_HEADINGS = (
    ("ENG", (0, 2, 0, 14), "Recommendation - Jordan Only", 6),
    ("ARA", (0, 12, 0, 14), "توصيات - الأردن فقط", 29),
)


def verified_jordan_difference(profile, document, signatures, mismatches):
    if not africa_book_scope(profile) or document.source_sha256 != VERIFIED_SHA256:
        return None
    if tuple(s.language for s in signatures) != profile.languages:
        return None
    if [len(s.entries) for s in signatures] != [22, 21, 21, 21, 22]:
        return None
    if any(s.entries[:21] != signatures[0].entries[:21] for s in signatures):
        return None
    if signatures[-1].entries != signatures[0].entries:
        return None
    if [(m.language, m.position, m.component, m.observed) for m in mismatches] != [
        (lang, 21, "count", None) for lang in ("FRA", "SPA", "POR")
    ] or any(m.expected != signatures[0].entries[-1] for m in mismatches):
        return None

    def walk(node):
        yield node
        if not isinstance(node, ContentFragment):
            for child in node.children:
                yield from walk(child)

    nodes = [n for child in document.children for n in walk(child)]
    by_path = {n.source_structure_path: n for n in nodes if not isinstance(n, ContentFragment)}
    evidence = []
    for language, path, wording, page in JORDAN_HEADINGS:
        heading = by_path.get(path)
        wrapper = by_path.get((*path[:-1], 15))
        table = by_path.get((*path[:-1], 15, 0))
        if heading is None or table is None or wrapper is None:
            return None
        fragments = [n for n in walk(heading) if isinstance(n, ContentFragment)]
        text = " ".join(" ".join(n.text for n in fragments).split())
        if (text != wording or heading.language != language
                or heading_candidate_level(heading.source_role) != 3
                or {n.page_index for n in fragments} != {page}):
            return None
        counts = Counter(n.semantic_role for n in walk(wrapper) if not isinstance(n, ContentFragment))
        if any(counts[role] != count for role, count in {
            "paragraph": 6, "table": 1, "table_row": 2, "table_cell": 2, "figure": 1,
        }.items()):
            return None
        if table.semantic_role != "table" or len(table.children) != 2:
            return None
        if any(row.semantic_role != "table_row" or len(row.children) != 1
               or row.children[0].semantic_role != "table_cell" for row in table.children):
            return None
        evidence.append((language, path, text))

    # The other source sections end before the Jordan heading and layout table.
    for language, page in (("FRA", 12), ("SPA", 18), ("POR", 24)):
        ending = [n for n in by_path.values() if n.language == language
                  and len(n.children) == 14
                  and {f.page_index for f in walk(n) if isinstance(f, ContentFragment)} == {page}]
        if len(ending) != 1:
            return None
    return HeadingCountSourceException("africa_observed_jordan_only", VERIFIED_SHA256,
                                       tuple(evidence), mismatches)
