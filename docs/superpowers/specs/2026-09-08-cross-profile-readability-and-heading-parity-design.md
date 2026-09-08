# Cross-Profile Readability and Heading Parity Design

## Goal

Improve tagged-PDF reviewer output without wording dictionaries or
buyer-language hardcoding by:

1. preserving real sentence boundaries while protecting spaced abbreviations;
2. recovering strongly evidenced continuation paragraphs between list runs;
3. detecting bold table subtitles when title and qualifier share one paragraph;
4. validating heading parity in every PDF whose canonical profile declares two
   or more languages.

The changes preserve source text. They add auditable display and validation
evidence for Markdown review and later sentence-oriented Excel export.

## Scope

The detection primitives are shared across profiles and scripts. A detector may
act only when all of its structural, typography, and geometry requirements are
available. Missing or ambiguous evidence leaves the current structure unchanged.

Initial real-PDF validation covers:

- `ZG XN ZT_L05` BOOK: ENG, DEU, FRA, ITA, DUT;
- `ZC_L02` A2: ENG and C-FRA;
- `LATIN_L02` A2: ENG and M-SPA;
- `KR_KOR` and one of `XY_ENG` or `XU_ENG` as single-language negative
  controls.

Heading parity applies to every canonical profile with `language_count >= 2`,
including BOOK, L02, and combined-language sheet profiles. Single-language PDFs
do not receive a cross-language parity result.

This work does not implement OCR, manual-code comparison, semantic translation,
localized-title dictionaries, checklist DB changes, or Excel export itself.

## MCID Geometry Evidence

`MCID` is a document-local marked-content identifier connecting a structure node
to visible PDF content. The reader currently retains its page, text, and text
style but not its text geometry.

Add optional geometry evidence for resolved text fragments:

```text
page_index
mcid
text_parts
text_styles
bbox = (left, top, right, bottom)
```

The infrastructure reader obtains the visible bounds while resolving the PDF
content stream. It must not infer text from raster pixels or OCR. If one MCID has
multiple visible runs, its bounding box is their union. A paragraph/list-body
box is the union of its resolved visible fragment boxes on one page.

Geometry is optional because valid tagged PDFs may not expose complete position
evidence. Detection that requires geometry fails closed when a fragment spans
multiple pages, has no finite box, or has ambiguous coordinates.

Raw XML and semantic XML serialize fragment boxes as source evidence. Markdown
does not display coordinates. Quality validation rejects malformed boxes but
does not fail extraction merely because optional geometry is absent.

## Sentence Boundary Policy

Sentence boundaries remain display evidence, not source-text mutation. Markdown
uses `<br>` inside one semantic block; later Excel export may consume the same
boundary evidence as separate sentence rows without writing the literal `<br>`.

Eligible containers are expanded from list bodies and table cells to ordinary
non-empty leaf body paragraphs. A leaf body paragraph contains only text and
inline descendants; it contains no list, table, figure, heading, label, caption,
or other block descendant.

The detector excludes:

- source or promoted headings;
- subtitles and strong labels;
- labels, captions, and figure text;
- URLs, email addresses, decimals, versions, standards, and dotted file/model
  tokens;
- any candidate whose next visible character is not a credible sentence start.

Spaced abbreviations such as `z. B.` and the NBSP equivalent are protected by a
Unicode-aware structural pattern for two or more single-letter dotted tokens.
The runtime rule contains no abbreviation word list and no language name.

Expected corrections include removing the false DEU split inside `z. B.` and
adding boundaries between the two real sentences in the reviewed DEU/FRA leaf
paragraphs.

## Continuation Paragraph Recovery

A standalone paragraph between two list runs may be rendered as a continuation
of the preceding list item only when every required condition holds:

- topology is `list -> paragraph -> list` among meaningful siblings;
- all three nodes belong to the same section, language interval, and page;
- the paragraph has a list-associated source role but no visible bullet, number,
  or heading marker;
- its typography tier matches the preceding list body;
- its left coordinate aligns with the preceding list-body text, not the list
  marker, within a scale-relative tolerance;
- its vertical gap from the preceding list body is consistent with the local
  list-line spacing and smaller than the gap to an independent block;
- the paragraph has complete, finite, single-page geometry;
- it does not overlap any heading, subtitle, strong-label, or existing list
  promotion evidence.

Topology alone is never sufficient. If any condition is unavailable or
ambiguous, the paragraph remains independent.

The semantic document records a continuation hint with the target paragraph,
preceding list item, source role, typography evidence, alignment delta, and gap
measurements. The raw structure remains unchanged. Markdown indents the paragraph
under the preceding bullet without adding a new bullet marker.

The reviewed FRA power-specification paragraph is the first positive sample.
Equivalent structures in the five ZG languages are checked without matching
their wording. ZC, LATIN, KR, and XY/XU provide false-positive controls before
the detector is accepted as shared behavior.

## Single-Paragraph Table Subtitle Recovery

The existing table-subtitle detector recognizes a figure cell followed by a text
cell whose bold title and qualifier are separate paragraph children. Extend it
to the alternate tagged layout where title and parenthesized qualifier occupy one
leaf paragraph separated by explicit source newline evidence.

The candidate must satisfy all existing figure-cell, following-body, typography,
length, and conflict checks. Additionally:

- the inline newline must divide two non-empty segments;
- the first segment must be stronger than the following body;
- the paragraph must contain no block descendant;
- the split must be supported by source newline evidence, not punctuation or
  wording;
- ambiguous mixed typography or multiple possible splits rejects the candidate.

Semantic XML records the subtitle span and qualifier boundary. Markdown renders
the title in bold and the qualifier on a separate line. The Italian disposal
title is the positive sample; the already-working separate-paragraph disposal
layout remains unchanged.

## Multilingual Heading Parity

Profile lookup uses the canonical `metadata/pdf_profile_mapping/
pdf_profile_mapping.json`. Folder names and document `/Lang` values are not
operational metadata.

For `language_count >= 2`, identify language intervals from existing structural
language evidence:

- BOOK uses bookmark-defined language sections/order;
- sheet and combined-language PDFs use their established page/language-section
  evidence and canonical profile order.

For each interval, build a wording-independent heading signature in document
order:

```text
(heading_level, heading_origin, numbered_label_or_null)
```

`heading_origin` distinguishes source-role headings from numbered promotions but
does not include localized text. Validation reports:

- expected and observed language interval counts;
- total heading count per language;
- heading-level sequence per language;
- heading-origin sequence per language;
- numbered-label sequence per language;
- missing or additional signature positions.

Hard gates require the expected language interval count, valid numbered sequence,
equal numbered-series count, and equal full heading signature across languages.
If a future verified source intentionally differs by language, it requires an
explicit profile exception supported by PDF evidence; the generic checker does
not silently weaken itself.

For the current ZG sample, the expected result is 26 headings per language with
level counts `H2=9`, `H3=8`, and `H4=9`. ZC and LATIN must demonstrate the same
in-file parity behavior for their respective two language intervals; their
absolute counts need not equal ZG.

## Architecture and Data Flow

1. PDF infrastructure resolves MCID text, style, and optional bounding boxes.
2. The tagged document retains geometry as immutable source evidence.
3. Reusable domain detectors produce sentence, continuation, and subtitle hints.
4. Profile metadata decides whether multilingual parity is applicable; it does
   not select localized wording rules.
5. Semantic XML serializes evidence and derived display hints.
6. Quality evaluation validates multilingual heading signatures and hint
   integrity.
7. Markdown renders only validated semantic evidence and does not re-detect PDF
   geometry or parse profile names.

Detection logic must remain outside the Markdown writer. Compatibility entry
points and the four required output artifacts remain unchanged.

## Failure and Safety Behavior

- Missing/invalid geometry: preserve the paragraph as independent.
- Ambiguous abbreviation: preserve the original joined text rather than insert a
  break.
- Ambiguous subtitle split: retain plain text.
- Missing profile or unknown multilingual interval: emit a diagnostic and fail
  the applicable parity gate; do not guess language boundaries.
- Duplicate, overlapping, unresolved, cross-page, or structurally conflicting
  hints stop atomic publication.
- Raw source text and raw structure are never rewritten to imitate the inferred
  display structure.

## Verification

TDD unit tests must first reproduce:

- `z. B.` and NBSP variants not splitting;
- two real sentences in an ordinary leaf paragraph splitting;
- headings, labels, URLs, model/standard tokens, and block-bearing paragraphs
  remaining excluded;
- a fully evidenced list continuation being linked;
- topology-only, misaligned, different-font, cross-page, and ambiguous paragraphs
  remaining independent;
- one-paragraph bold title/qualifier detection and rejection of ambiguous inline
  splits;
- multilingual interval count, complete heading signature, level sequence, and
  numbered-label mismatches failing their gates;
- single-language profiles remaining outside parity comparison.

Real-PDF regression regenerates ZG, ZC, and LATIN outputs, checks the identified
DEU/FRA/ITA lines, and verifies no false continuation or heading mismatch in the
negative controls. Final verification runs the complete POC suite and
`python -m compileall src tests scripts apps` from the repository root.
