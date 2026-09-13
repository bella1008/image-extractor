"""Verified AFRICA mixed LTR/RTL BOOK structure; no translated headings."""
from collections import Counter
from dataclasses import replace
import unicodedata

from tagged_pdf_extractor.domain.models import (
    ContentFragment, Diagnostic, PdfProfile, StructureElement, TaggedDocument,
)


def africa_book_scope(profile: PdfProfile) -> bool:
    return (profile.source_token == "AFRICA_L05" and profile.doc_type == "BOOK"
            and profile.languages == ("ENG", "FRA", "SPA", "POR", "ARA"))


def _fragments(node):
    if isinstance(node, ContentFragment):
        yield node
    else:
        for child in node.children:
            yield from _fragments(child)


def prepare_africa_book(document: TaggedDocument, profile: PdfProfile) -> TaggedDocument:
    if not africa_book_scope(profile):
        return document
    if document.raw_children is not None:
        raise ValueError("AFRICA reading order was already prepared")
    bounds = document.bookmark_page_bounds
    if len(bounds) != 5:
        raise ValueError("AFRICA BOOK requires five observed bookmarks")
    # Exact titles observed in this source profile, not translated aliases.
    if tuple(b.source_title for b in bounds) != (
        "English", "Français", "Español", "Português", "العربية"
    ):
        raise ValueError("AFRICA bookmark language order requires source review")
    starts = [b.start_page_index for b in bounds]
    spans = [b - a for a, b in zip(starts[:3], starts[1:4])]
    if len(set(spans)) != 1 or spans[0] <= 0:
        raise ValueError("AFRICA LTR section extents need source review")
    arabic_counts = Counter()
    for root in document.children:
        for f in _fragments(root):
            arabic_counts[f.page_index] += sum(unicodedata.bidirectional(c) == "AL" for c in f.text)
    arabic_pages = sorted(p for p, n in arabic_counts.items() if n >= 15)
    if (not arabic_pages or arabic_pages != list(range(arabic_pages[0], arabic_pages[-1] + 1))
            or arabic_pages[-1] != starts[-1] + 1):
        raise ValueError("AFRICA Arabic bookmark/cover/script evidence is incomplete")
    por_end = starts[3] + spans[0] - 1
    if not por_end < arabic_pages[0]:
        raise ValueError("AFRICA LTR and RTL sections overlap")
    corrected = (*bounds[:3], replace(bounds[3], end_page_index=por_end),
                 replace(bounds[4], start_page_index=arabic_pages[0], end_page_index=arabic_pages[-1]))

    def annotate(node, path):
        if isinstance(node, ContentFragment):
            return node
        pages = {f.page_index for f in _fragments(node)}
        languages = [lang for lang, b in zip(profile.languages, corrected)
                     if pages and all(b.start_page_index <= p <= b.end_page_index for p in pages)]
        return replace(node, source_structure_path=path,
                       language=languages[0] if len(languages) == 1 else node.language,
                       children=tuple(annotate(c, (*path, i)) for i, c in enumerate(node.children)))

    annotated = tuple(annotate(c, (i,)) for i, c in enumerate(document.children))
    from tagged_pdf_extractor.domain.africa_rtl import restore_rtl_glyph_lines
    annotated, glyph_evidence = restore_rtl_glyph_lines(annotated, document.diagnostics)
    from tagged_pdf_extractor.domain.africa_numeric_text import restore_actual_text_decimals
    annotated, decimal_evidence = restore_actual_text_decimals(annotated, document.diagnostics)
    from tagged_pdf_extractor.domain.africa_inline_order import restore_inline_order
    annotated, inline_evidence = restore_inline_order(annotated, document.diagnostics)
    if len(annotated) != 1 or not isinstance(annotated[0], StructureElement):
        raise ValueError("AFRICA requires one source Document container")
    container = annotated[0]
    siblings = list(container.children)
    positions = []
    for i, child in enumerate(siblings):
        pages = {f.page_index for f in _fragments(child)}
        if pages & set(arabic_pages):
            if len(pages) != 1 or not pages <= set(arabic_pages):
                raise ValueError("AFRICA RTL source article crosses a page boundary")
            positions.append((i, next(iter(pages))))
    if ([p for _, p in positions] != arabic_pages or
            [i for i, _ in positions] != list(range(positions[0][0], positions[-1][0] + 1))):
        raise ValueError("AFRICA RTL source articles are not contiguous")
    begin, end = positions[0][0], positions[-1][0] + 1
    siblings[begin:end] = reversed(siblings[begin:end])
    evidence = Diagnostic("warning", "africa_book_rtl_source_order",
        "Semantic view reads Arabic pages backwards; Raw XML retains source order.",
        {"source_token": profile.source_token, "doc_type": profile.doc_type, "language": "ARA",
         "raw_bookmark_bounds": [(b.start_page_index, b.end_page_index) for b in bounds],
         "semantic_page_order": list(reversed(arabic_pages)),
         "source_article_paths": [(0, i) for i, _ in positions]})
    return replace(document, raw_children=document.children,
                   children=(replace(container, children=tuple(siblings)),),
                   bookmark_page_bounds=corrected, diagnostics=(*document.diagnostics, evidence, glyph_evidence, decimal_evidence, inline_evidence))
