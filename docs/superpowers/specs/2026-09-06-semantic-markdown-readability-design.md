# Semantic Markdown Readability Design

**Date:** 2026-09-06
**Project:** `samples/tagged_pdf_xml_poc`
**Status:** Approved for implementation planning

## Purpose

Improve human readability of `semantic_document.md` without changing the PDF-observed semantic hierarchy. Preserve sentence boundaries within one bullet or table cell, distinguish small inline icons from ordinary figures, and retain meaningful source list labels such as `※`.

## Scope

### Included

- Insert display-only sentence breaks inside eligible paragraphs, list bodies, and table-cell paragraphs while retaining their existing semantic containers.
- Protect URLs, email addresses, decimal numbers, version strings, abbreviations, and other period-containing tokens from false sentence splits.
- Render a small figure embedded in a sentence as `[아이콘]` when structural position and relative geometry establish it as inline.
- Keep non-inline, large, or uncertain empty figures as `[그림: 텍스트 없음]`.
- Preserve the meaningful source footnote label `※` as `※ 설명` without adding a Markdown bullet that is absent from the PDF.
- Preserve spacing around an inline `※` reference, for example `UK ※ 2025-10-31`.
- Apply the generic rules independently of buyer and language when the same structural evidence is present.
- Use ZG as the positive sample and ZC, ZA, XY, and KR as regression controls.

### Excluded

- Naming icons such as Home or Settings.
- OCR or visual icon recognition.
- An icon catalog or image-similarity matching.
- Splitting one source list item into multiple list items.
- Splitting one source table cell into multiple rows or cells.
- Changing the PDF source text or the established numbered-heading, RF-line-break, subtitle, or Declaration-of-Conformity rules.
- Escaping bracketed model labels solely to alter editor syntax-highlighting color.

## Evidence From the Reviewed ZG Output

### Sentence display

The French safety item beginning `Veillez à brancher correctement...` is one tagged `list_item > list_body` containing four sentences. Raw fragments retain physical page-wrap lines, but those wraps do not coincide with sentence boundaries. The German battery-disposal example is one `table_cell > paragraph` containing three sentences with the same mismatch.

Therefore, physical fragment boundaries are provenance evidence but are not sentence boundaries. Sentence display breaks must be inferred conservatively from joined visible text.

### Footnote label

The explanatory line beginning `Cette adresse n'est pas...` is tagged as:

```text
list_item
  label: ※
  list_body: Cette adresse n'est pas...
```

The current Markdown writer intentionally replaces arbitrary non-ordered labels with `-` to suppress broken bullet glyphs such as `Ł` and `Œ`. That policy also removes the meaningful `※` label. The correction must distinguish semantic note markers from ordinary or corrupted bullet glyphs.

### Model-label color

The five bracketed model labels use the same PDF typography: `SamsungOne-600`, size `6.5`, RGB `(35, 31, 32)`, and the same source role. The Markdown writer also emits the same plain bracket syntax for all five. The editor colors the first two differently because their bracket contents contain no spaces and are tokenized as link-like Markdown syntax. This is not source formatting and does not require extraction changes.

## Design Decisions

### 1. Preserve containers and add display-only sentence boundaries

Sentence formatting must never create a new `list_item`, `table_row`, `table_cell`, or semantic paragraph. The Markdown representation may place continuation text on new indented lines, but all continuation lines remain attached to the original list item or table cell.

The sentence detector operates only on visible text from one eligible semantic text container. It emits boundaries after terminal punctuation when the following non-space text can begin another sentence. It must not split after a period that belongs to a protected token, including:

- URLs and email addresses;
- decimal values;
- dotted versions and standards such as `V2.2.3`;
- initials and compact abbreviations;
- ellipses;
- model codes and file-like tokens.

If a boundary is ambiguous, no break is emitted. Existing source-authored display breaks take precedence and must not be duplicated.

Markdown uses an explicit `<br>` plus an indented continuation where needed. This is more reliable than invisible trailing spaces and keeps a single bullet or cell visibly intact across Markdown viewers.

### 2. Classify inline icons without naming them

A figure is eligible for `[아이콘]` only when all of the following are true:

- it occurs among inline children of a paragraph or list body rather than as the sole block in a figure/table cell;
- visible text occurs immediately before or after it in the same text flow;
- page and BBox evidence are available;
- its height and width are small relative to the surrounding observed text line and do not resemble a standalone illustration.

The exact relative geometry thresholds are fixed in code and tested with positive and negative examples; they are not changed per buyer or language. Alternate text may be retained as evidence but is not rendered as an icon name.

An eligible figure renders `[아이콘]`. A standalone, large, evidence-incomplete, or ambiguous figure retains `[그림: 텍스트 없음]`. This is deliberately conservative: a false generic figure is preferable to a false icon.

### 3. Preserve meaningful note markers separately from list bullets

The Markdown list-label analyzer distinguishes three classes:

1. native ordered labels, rendered with the established ordered-list behavior;
2. verified semantic note markers such as `※`, rendered literally before the body without `-`;
3. ordinary bullets, corrupt glyphs, and arbitrary labels, rendered using the existing structural `-` fallback.

This classification is symbol-based, not language- or buyer-specific. The body remains attached to the original semantic `list_item` even when the Markdown display begins with `※` instead of a Markdown list marker.

Inline spacing normalization must preserve a visible separator around `※` when adjacent fragments otherwise collapse, while leaving punctuation and model-code text unchanged.

### 4. Keep decisions auditable

Sentence and inline-icon display decisions are derived before Markdown rendering and exposed as validated Semantic XML display evidence. The Markdown writer consumes that evidence and does not inspect the PDF or guess from a filename.

Evidence records include the target structure path, display role/reason, source page, MCID/object reference when available, and geometry for icon decisions. Raw XML remains unchanged.

## Data Flow

1. Tagged PDF extraction preserves raw structure, fragments, MCIDs, object references, pages, BBoxes, and source text.
2. Semantic construction preserves the source hierarchy and child order.
3. Generic readability analysis identifies conservative sentence boundaries, eligible inline icons, and meaningful note labels.
4. Display-hint validation rejects contradictory, overlapping, or structurally ineligible hints.
5. Semantic XML records validated display evidence without changing raw XML.
6. The Markdown writer renders sentence continuations, `[아이콘]`, generic figure markers, and `※` labels from Semantic XML.

## Failure Handling

- Ambiguous sentence punctuation stays on one line.
- Missing geometry or surrounding text keeps a figure generic.
- Conflicting display hints fail validation before output publication.
- Unsupported list labels continue to use the existing safe structural bullet.
- No source text may disappear or be duplicated.
- Failure in readability enhancement must not corrupt or partially replace an existing output bundle.

## Verification

### Focused unit tests

- Four sentences remain one French list item and render as four visual lines.
- Three sentences remain one German table-cell paragraph and render as three visual lines.
- URLs, emails, decimals, standards, versions, abbreviations, and ellipses are not split incorrectly.
- Existing source-authored RF breaks are neither removed nor duplicated.
- A small figure between text fragments renders `[아이콘]`.
- Standalone, large, uncertain, and geometry-incomplete figures remain `[그림: 텍스트 없음]`.
- A `※` list label renders once as `※ 설명`, while `Ł`, `Œ`, and ordinary bullet markers remain suppressed or structurally normalized as before.
- An inline `※` reference retains readable spacing.
- Semantic XML receives validated evidence and raw XML remains byte-for-byte free of display attributes.

### Sample regression gates

- Regenerate ZG and verify ENG, DEU, FRA, ITA, and DUT examples.
- Regenerate ZC, ZA, XY, and KR and confirm no false icon promotion or structural sentence splitting.
- Keep existing numbered headings, subtitles, RF breaks, Declaration-of-Conformity hierarchy, complex tables, and output-bundle safety tests passing.
- Run the complete POC test suite and repository compile checks required by `AGENTS.md`.

## Completion Output

Regenerate review bundles for ZG, ZC, ZA, XY, and KR. Provide the five `semantic_document.md` paths and call out the exact ZG lines for the four-sentence bullet, multi-sentence table cell, inline icons, and `※` footnote so they can be inspected manually.
