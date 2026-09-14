"""CE BOOK boundaries and numeric typography proven by tagged source evidence."""
from collections import defaultdict
from dataclasses import replace
import re

from tagged_pdf_extractor.domain.models import ContentFragment, Diagnostic, PdfProfile, TextDisplayHint
from tagged_pdf_extractor.domain.typography import typography_evidence


CE_LANGUAGES = ("RUS", "ENG", "KAZ", "MON", "KYR")
_BOOKMARK_TITLES = ("Русский", "English", "Қазақ", "Монгол", "Кыргызча")
# Exact extracted titles, never translated aliases.
_COVER_TITLES = (
    "Простое руководство пользователя", "Simple User Guide",
    "Стандартты пайдаланушы нұсқаулығы", "Хэрэглэгчийн хялбар гарын авлага",
    "Жөнөкөй колдонуучу нускамасы",
)


def ce_book_scope(profile: PdfProfile) -> bool:
    return (profile.source_token == "CE_L05" and profile.doc_type == "BOOK"
            and profile.languages == CE_LANGUAGES)


def fragments(node):
    if isinstance(node, ContentFragment):
        yield node
    else:
        for child in node.children:
            yield from fragments(child)


def elements(children):
    for node in children:
        if not isinstance(node, ContentFragment):
            yield node
            yield from elements(node.children)


def prepare_ce_book(document, profile):
    if not ce_book_scope(profile):
        return document
    if document.raw_children is not None:
        raise ValueError("CE BOOK source was already prepared")
    bounds = document.bookmark_page_bounds
    if tuple(b.source_title for b in bounds) != _BOOKMARK_TITLES:
        raise ValueError("CE bookmark language order requires source review")
    covers = [n for n in elements(document.children) if n.source_role == "Cover_Title"]
    titles = tuple(' '.join(''.join(f.text for f in fragments(n)).split()) for n in covers)
    pages = [{f.page_index for f in fragments(n)} for n in covers]
    if titles != _COVER_TITLES or pages != [{b.start_page_index - 1} for b in bounds]:
        raise ValueError("CE cover title/page evidence requires source review")
    contact_pages = {f.page_index for n in elements(document.children)
                     if n.source_role == "Cover_Description-7p"
                     and ' '.join(''.join(f.text for f in fragments(n)).split())
                     == "Связывайтесь с Samsung по всему миру" for f in fragments(n)}
    if len(contact_pages) != 1 or next(iter(contact_pages)) != bounds[-1].end_page_index:
        raise ValueError("CE Russian contact cover evidence requires source review")
    contact_page = next(iter(contact_pages))
    starts = [next(iter(p)) for p in pages]
    ends = [p - 1 for p in starts[1:]] + [contact_page - 1]
    if any(end <= start for start, end in zip(starts, ends)):
        raise ValueError("CE language extents require source review")
    corrected = tuple(replace(b, start_page_index=start, end_page_index=end)
                      for b, start, end in zip(bounds, starts, ends))

    def annotate(node, path):
        if isinstance(node, ContentFragment):
            return node
        source_pages = {f.page_index for f in fragments(node)}
        languages = [lang for lang, start, end in zip(CE_LANGUAGES, starts, ends)
                     if source_pages and all(start <= p <= end for p in source_pages)]
        language = 'RUS' if source_pages == contact_pages else (languages[0] if len(languages) == 1 else None)
        return replace(node, source_structure_path=path, language=language,
                       children=tuple(annotate(c, (*path, i)) for i, c in enumerate(node.children)))

    children = tuple(annotate(c, (i,)) for i, c in enumerate(document.children))
    children, numeric = _restore_decimal_spacing(children, document.diagnostics)
    evidence = Diagnostic('warning', 'ce_book_source_boundaries',
        'CE bookmarks start after each cover; semantic intervals include the verified cover and exclude the Russian contact page.',
        {'raw_bookmark_bounds': [(b.start_page_index, b.end_page_index) for b in bounds],
         'semantic_bounds': list(zip(starts, ends)), 'contact_page_index': contact_page,
         'contact_language': 'RUS', 'cover_titles': titles})
    prepared = replace(document, raw_children=document.children, children=children,
                       bookmark_page_bounds=corrected, diagnostics=(*document.diagnostics, evidence, numeric))
    from tagged_pdf_extractor.domain.ce_paragraph_ownership import repair_ce_paragraph_ownership
    prepared = repair_ce_paragraph_ownership(prepared, profile)
    return replace(prepared, text_display_hints=(*prepared.text_display_hints, *_standby_labels(prepared.children)))


def _standby_labels(children):
    """Keep the two source-only subtitles visible without inventing common headings."""
    titles = {'RUS':'Режим ожидания', 'KAZ':'Күту режимі'}
    hints = []
    paths = {}
    def index_paths(nodes, parent_path=()):
        for i, node in enumerate(nodes):
            if not isinstance(node, ContentFragment):
                paths[id(node)] = (*parent_path, i)
                index_paths(node.children, paths[id(node)])
    index_paths(children)
    for parent in elements(children):
        for title, body in zip(parent.children, parent.children[1:]):
            if (isinstance(title, ContentFragment) or isinstance(body, ContentFragment)
                    or title.source_role != 'Table-6_0' or body.source_role != 'Description-L'
                    or title.language not in titles or body.language != title.language
                    or ' '.join(''.join(f.text for f in fragments(title)).split()) != titles[title.language]):
                continue
            title_style, body_style = typography_evidence(title), typography_evidence(body)
            if (title_style is None or body_style is None
                    or title_style.font_size <= body_style.font_size
                    or title.source_structure_path is None):
                continue
            hints.append(TextDisplayHint(paths[id(title)], 'strong_label',
                title_style.font_weight, title_style.font_size, body_style.font_weight,
                body_style.font_size, 'ce_source_standby_subtitle_larger_than_following_body'))
    return tuple(hints)


def decimal_source_parts(fragment, runs):
    """Only remove a decimal-internal space absent from one PDF text operation."""
    if (not runs or any(r.get('actual_text') for r in runs)
            or len({r.get('operation_index') for r in runs}) != 1
            or runs[0].get('operation_index') is None):
        return None
    parts = tuple(re.sub(r'(?<=\d)[ \t]+(?=[.,]\d)', '', p) for p in fragment.text_parts)
    source = ''.join(''.join(r['glyphs']) for r in runs)
    if parts == fragment.text_parts or ''.join(parts).strip() != source.strip():
        return None
    return parts


def _restore_decimal_spacing(children, diagnostics):
    runs = defaultdict(list)
    for diagnostic in diagnostics:
        if diagnostic.code == 'ce_decimal_source':
            for item in diagnostic.context['fragments']:
                runs[item['page_index'], item['mcid']].extend(item['runs'])
    changes = []

    def visit(node, language=None):
        if not isinstance(node, ContentFragment):
            return replace(node, children=tuple(visit(c, node.language or language) for c in node.children))
        if language not in CE_LANGUAGES:
            return node
        key = node.page_index, node.mcid
        parts = decimal_source_parts(node, runs.get(key, []))
        if parts is None:
            return node
        changes.append({'page_index':key[0], 'mcid':key[1], 'language':language,
                        'source_parts':node.text_parts, 'parts':parts,
                        'operation_index':runs[key][0]['operation_index']})
        return replace(node, text_parts=parts)

    result = tuple(visit(c) for c in children)
    return result, Diagnostic('warning', 'ce_decimal_spacing',
        'Removed only decimal-internal spaces absent from the source text operation.', {'changes':changes})
