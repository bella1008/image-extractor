# Semantic Markdown and Verified Icon Review Design

**Date:** 2026-09-05  
**Project:** `samples/tagged_pdf_xml_poc`  
**Status:** Approved for implementation planning

## Purpose

Make `semantic_document.md` preserve the useful paragraph, list, and nested-list structure already present in `semantic_document.xml`. Also replace verified recurring icon-only figures with conservative human-readable labels without guessing unknown icons.

The existing `01`, `02`, and later numbered chapter-heading promotion is already user-verified for the current ZC, ZA, and ZG samples. This work must not change that policy or its output.

## Scope

### Included

- Preserve paragraph, list, nested-list, table-row, and table-cell boundaries when rendering complex tables to Markdown.
- Keep the existing pipe-table output for simple rectangular tables whose cells contain only simple text.
- Render complex table rows as readable Markdown blocks instead of flattening every descendant into `- 행 N: ...`.
- Detect subtitle-like first paragraphs from structural and typographic evidence rather than title wording.
- Render the two current ZG `Correct Disposal...` titles as bold subtitles, separated from their parenthetical qualifier and following body paragraphs.
- Classify only verified recurring icon-only figures and render labels such as `[아이콘: 홈]` or `[아이콘: 설정]`.
- Preserve source evidence for icon decisions.
- Regenerate ZC, ZA, and ZG review Markdown for human inspection.

### Excluded and deferred

- Tesseract installation and OCR integration.
- Extraction of the visible document-code prefix from image/vector content.
- Automatic comparison of the filename document code with the PDF-visible document code and version.
- Detailed hierarchy extraction for `Declaration of Conformity`.
- Arbitrary or open-ended icon recognition.
- Changes to the verified numbered chapter-heading promotion policy.

## Design Decisions

### 1. Semantic XML remains the source of rendering structure

The Markdown writer must consume the existing semantic element order. It must not reconstruct lists or paragraphs from a flattened text string when the XML already contains explicit child elements.

The semantic XML may be enriched with auditable typography summaries needed for display decisions, but existing source text, MCID, object reference, page, BBox, and hierarchy evidence must remain intact.

### 2. Simple and complex tables use different renderers

A simple rectangular table with simple text cells continues to use a Markdown pipe table.

A table is complex when a cell contains multiple paragraphs, a list, a nested list, a table, a figure mixed with text, or another block-level child. Complex rows are rendered as structured Markdown blocks. For example:

```markdown
- 행 1:

  **Subtitle**

  Qualifier paragraph

  Body paragraph

  - Item 1
  - Item 2
    - Nested item
```

For multi-cell rows, each cell is emitted under an indented `열 N` marker in source order. A single-cell row emits its content directly under `행 N` and does not receive a redundant cell marker. Empty cells remain visible as `[빈 셀]` so that column position is not silently lost.

### 3. Subtitle detection does not hardcode language text

Runtime logic must not test for literal strings such as `Correct Disposal`.

A paragraph can receive a subtitle display hint only when all of these conditions hold:

- it is the leading text paragraph in a structured table cell;
- the same cell contains a second direct paragraph immediately after it;
- its normalized text is at most 160 characters and occupies at most two observed PDF lines;
- its weighted-median observed PDF font weight is at least one normalized weight step, or 100 numeric weight units, stronger than the immediately following paragraph;
- all text fragments used for the comparison have resolved page and font evidence.

Font family names are audit evidence, not hardcoded business rules. Common style names such as `Regular`, `Medium`, `Semibold`, and `Bold`, and numeric suffixes such as `400`, `600`, and `700`, are normalized into ordered weight steps. The decision compares relative weight within the same local cell, so the same rule can work with another language or font family. If either paragraph has mixed or unresolved typography, paragraphs remain separate but the first paragraph is not automatically bolded.

This is a Markdown display hint, not promotion to a document heading. It must not add the paragraph to the numbered heading hierarchy.

### 4. Icon recognition is conservative and evidence-backed

Icon recognition is separate from OCR and from the generic Markdown table renderer.

An icon catalog contains only human-verified recurring icons. Each catalog entry includes a semantic label and normalized visual fingerprint/template evidence. Empty tagged figures are cropped using their page and BBox evidence and compared only with catalog entries.

- A named label is emitted only when exactly one catalog entry satisfies its human-approved match threshold and ambiguity margin; it renders `[아이콘: <이름>]`.
- An icon-like crop without a reliable match renders `[아이콘: 확인 필요]`.
- A figure that is not established as an icon remains `[그림: 텍스트 없음]`.

Every decision retains page index, BBox, MCID, object reference when available, match method, score, catalog version, and evidence crop path. The source filename or nearby sentence must not be used to guess the icon name.

Match thresholds and ambiguity margins are versioned catalog data established from positive and negative sample crops; they are not learned or loosened during a production run. The first catalog covers only icons confirmed in the current review samples. New icons require separate human verification before entering the catalog.

## Data Flow

1. The tagged PDF reader extracts structure, source references, text, and available typography evidence.
2. Semantic construction preserves child order and attaches normalized paragraph typography summaries where evidence is sufficient.
3. The optional verified-icon resolver evaluates eligible empty figures and attaches an auditable display result.
4. The Markdown writer selects the simple-table or complex-table path.
5. The complex renderer recursively emits paragraphs, lists, nested lists, figures, and nested tables in source order.
6. A subtitle display hint renders bold text without changing the semantic heading hierarchy.
7. Output validation compares semantic content and rendered output before publication.

## Failure Handling

- Unsupported complex content must stay visible in source order; it must not silently collapse into one line or disappear.
- Duplicate or missing rendered source text blocks fail Markdown publication.
- Unresolved typography leaves content as separate plain paragraphs instead of inventing a subtitle.
- Low-confidence icon matches never receive a named label.
- Missing crop or geometry evidence leaves the existing generic figure marker and records a diagnostic.
- The absence of Tesseract is not an extraction failure in this phase because document-code OCR is explicitly deferred.

## Verification

### Unit tests

- Multi-paragraph table cells remain separate.
- Lists inside table cells retain individual items.
- Nested lists retain parent-child indentation.
- Mixed figures, paragraphs, and lists preserve source order.
- Simple rectangular tables still render as pipe tables.
- Relative font-weight evidence can produce a bold subtitle without checking title wording.
- Missing or ambiguous font evidence does not produce a bold subtitle.
- Known icon matches, unknown icon-like crops, and ordinary empty figures produce three distinct outputs.
- Existing Markdown escaping and atomic publication tests continue to pass.

### Sample regression tests

- ZC package contents remain individual items.
- ZC title-plus-three-bullet content remains structurally separated.
- ZG two-item lists and the two-item list containing three nested dash items remain distinct.
- ZG bracketed model/frequency content retains paragraph and line boundaries where represented in the semantic source.
- ZG EMC, Safety, and Radio groups retain their child-item boundaries.
- Both current ZG `Correct Disposal...` title paragraphs render bold and remain separate from qualifiers and body paragraphs through the generic subtitle rule.
- ZC, ZA, and ZG numbered chapter headings remain unchanged from their user-verified results.

### Completion checks

- Run the focused Markdown, typography, icon, output-bundle, and layout regression tests.
- Run the full POC test suite.
- Run `python -m compileall src tests` inside the POC.
- Run the repository verification target `python -m compileall src tests scripts apps`.
- Regenerate the ZC, ZA, and ZG review outputs and provide their Markdown paths for human inspection.

## Rollout Order

1. Implement and verify recursive complex-table Markdown rendering.
2. Add relative typography evidence and generic subtitle display hints.
3. Regenerate ZC, ZA, and ZG Markdown and inspect structural regressions.
4. Add the small verified icon catalog and conservative resolver.
5. Regenerate outputs again and inspect icon labels and fallbacks.
6. Leave OCR/document-code comparison and `Declaration of Conformity` hierarchy as separately tracked follow-up work.
