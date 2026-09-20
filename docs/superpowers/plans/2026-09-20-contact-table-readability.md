# Contact table and review readability implementation plan

**Goal:** Correct the MENA review display defects with shared, evidence-gated rules and expose consistent per-language structure counts in a consolidated review page.

**Architecture:** Add one domain classifier for cover contact sections and one domain detector for model-code line groups. Keep source-specific sheet repair modules responsible only for source topology repairs. Serialize the resulting audit attributes through the existing semantic XML path and make the Markdown writer honor them with strict validation. Reuse `review_document.json` language statistics for HTML counts.

**Tech stack:** Python 3.12, pytest, dataclasses, ElementTree, existing tagged-PDF reader/writers, HTML review scripts.

### Task 1: Cover contact evidence and rendering

- Add failing synthetic and real-sample tests for ASIA, MENA, SQ MI, XH, and ZG contact sections plus negative non-contact tables.
- Add failing Markdown tests proving that only `review-table-kind=cover-contact` preserves paragraph boundaries with `<br>`.
- Implement structural contact classification, table attributes, and typography-gated title hints.
- Wire the classifier into `ExtractDocument` after profile review formatting so existing hints are preserved.

### Task 2: Cross-profile sentence breaks

- Add a failing MENA-style inline navigation test outside the previously enabled profiles.
- Generalize use of validated inline-icon paths in sentence detection.
- Run existing URL, abbreviation, ambiguous figure, and representative buyer readability tests.

### Task 3: Model-code line groups

- Add failing tests for multi-baseline model-code cells and negative prose/dimension/incomplete-geometry cases.
- Add strict semantic metadata for reviewed model line starts.
- Add writer validation and `<br>` rendering tests for English and RTL fragment layouts.

### Task 4: Consolidated review counts

- Add a failing renderer test with two buyers and multiple languages.
- Implement a reusable pending-review index renderer using existing language statistics.
- Generate a new index that links all pending buyer review pages and includes heading/table/figure counts.

### Task 5: Extraction and regression verification

- Re-extract MENA to a new output folder and generate semantic XML, Markdown, preview HTML, reports, and review bundle.
- Confirm the contact title, contact cell paragraph boundaries, `The screen dims.` paragraph, and model rows against the PDF/source evidence.
- Re-extract or inspect ASIA, ZG, XH, and SQ MI representative outputs and verify no non-contact table receives contact behavior.
- Run focused tests, the complete POC suite, root public-import compatibility tests, and compileall.
- Review the final diff, preserve all existing user changes, and create one local commit with the verified implementation and documentation.
