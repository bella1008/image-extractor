# Cross-Profile Readability and Heading Parity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add auditable MCID geometry, safer sentence boundaries, conservative list-continuation and inline-subtitle recovery, and multilingual heading-parity gates without buyer wording hardcoding.

**Architecture:** Keep PDF operation parsing in infrastructure, immutable evidence and detectors in domain modules, orchestration in `ExtractDocument`, and rendering as a consumer of validated hints only. Shared detectors fail closed when structure, typography, or geometry evidence is missing; canonical profile metadata controls only whether multilingual parity applies.

**Tech Stack:** Python 3.11+, pypdf 6.16.2, PyMuPDF, dataclasses, ElementTree, pytest.

---

## Preconditions and invariants

- Work in `C:\Users\bella\image-extractor\.worktrees\xml-markdown-review` on `feature/xml-markdown-review`.
- Run each test command from `samples/tagged_pdf_xml_poc`; run each Git command from the worktree root.
- Preserve the public CLI and all four output artifacts: `raw_structure.xml`, `semantic_document.xml`, `extraction_report.json`, and `semantic_document.md`.
- Do not add buyer names, localized phrases, translated headings, or abbreviation dictionaries to runtime detection.
- Do not alter raw source text or source-tree order. New interpretations are immutable hints/audits.
- Treat missing, non-finite, rotated/ambiguous, or cross-page geometry as insufficient evidence.
- Run `git diff --check` before every task commit.

### Task 1: Carry optional text-run geometry from pypdf operations into fragments

**Files:**

- Modify: `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/domain/models.py`
- Modify: `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/infrastructure/pypdf_operation_text.py`
- Modify: `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/infrastructure/mcid_text.py`
- Modify: `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/infrastructure/pypdf_reader.py`
- Test: `samples/tagged_pdf_xml_poc/tests/test_pypdf_operation_text.py`
- Test: `samples/tagged_pdf_xml_poc/tests/test_mcid_text.py`
- Test: `samples/tagged_pdf_xml_poc/tests/test_pypdf_reader.py`

- [ ] **Step 1: Write failing model and callback tests**

Add tests proving that geometry is optional, aligns one-to-one with `text_parts`, and rejects mismatched lengths:

```python
fragment = ContentFragment(
    page_index=0,
    mcid=7,
    text_parts=("first", "second"),
    text_bboxes=((10.0, 20.0, 30.0, 32.0), None),
)
assert fragment.bbox == (10.0, 20.0, 30.0, 32.0)

with pytest.raises(ValueError, match="text bounding boxes"):
    ContentFragment(0, 7, ("first", "second"), text_bboxes=((0, 0, 1, 1),))
```

Add operation-runner tests that capture a finite axis-aligned box for ordinary horizontal text and return `None` for unsupported/ambiguous geometry. The callback contract becomes:

```python
on_text(value, font_name, effective_font_size, bbox)
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_pypdf_operation_text.py tests/test_mcid_text.py tests/test_pypdf_reader.py -q
```

Expected: failures for the missing `text_bboxes` field and four-argument callback.

- [ ] **Step 3: Implement bounded geometry calculation**

Add the shared alias and fragment evidence:

```python
BBox = tuple[float, float, float, float]

@dataclass(frozen=True)
class ContentFragment:
    # existing fields
    text_bboxes: tuple[BBox | None, ...] = ()

    @property
    def bbox(self) -> BBox | None:
        return union_finite_bboxes(self.text_bboxes)
```

In `PypdfOperationTextRunner`, calculate a text-run box from the visitor's text matrix, current transformation matrix, font width, and font size. Keep the first implementation deliberately conservative:

- accept finite, positive, axis-aligned horizontal runs only;
- derive width from `extractor.font.get_text_width(value)` and the active text scale;
- normalize coordinate order to `(left, bottom, right, top)` consistently throughout the POC;
- return `None` for rotation/skew, missing font metrics, zero area, or exceptions;
- never block text extraction because geometry is unavailable.

Extend `McidTextResult` with `bboxes_by_mcid` and validate that MCID keys and part counts match text/style evidence. Thread the mapping through `TaggedPdfReader._content_fragment()` into `ContentFragment.text_bboxes`.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run the Step 2 command. Expected: all pass.

- [ ] **Step 5: Commit the geometry evidence slice**

```powershell
git diff --check
git add samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/domain/models.py samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/infrastructure/pypdf_operation_text.py samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/infrastructure/mcid_text.py samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/infrastructure/pypdf_reader.py samples/tagged_pdf_xml_poc/tests/test_pypdf_operation_text.py samples/tagged_pdf_xml_poc/tests/test_mcid_text.py samples/tagged_pdf_xml_poc/tests/test_pypdf_reader.py
git commit -m "feat: retain optional MCID text geometry"
```

### Task 2: Serialize and validate geometry without exposing it in Markdown

**Files:**

- Modify: `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/infrastructure/xml_writer.py`
- Modify: `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/domain/display_hint_validation.py`
- Test: `samples/tagged_pdf_xml_poc/tests/test_xml_writer.py`
- Test: `samples/tagged_pdf_xml_poc/tests/test_display_hint_validation.py`

- [ ] **Step 1: Write failing XML evidence tests**

Require raw and semantic fragments with a resolved union box to contain deterministic numeric attributes:

```xml
<text page-index="0" mcid="7" bbox="10,20,30,32">...</text>
```

Also test:

- optional geometry produces no `bbox` attribute;
- malformed, non-finite, inverted, or zero-area hint boxes fail validation;
- XML round trip does not change text or Markdown content;
- the Markdown file contains no coordinate strings solely because a box exists.

- [ ] **Step 2: Run XML tests and verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_xml_writer.py tests/test_display_hint_validation.py -q
```

- [ ] **Step 3: Implement deterministic evidence serialization**

Extend `_fragment_attributes()` to emit the union `bbox` using the existing `_format_number()` helper. Add a single domain validator for finite normalized boxes and reuse it for fragment and future hint geometry. Do not make absent fragment boxes a hard failure.

- [ ] **Step 4: Run focused tests and commit**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_xml_writer.py tests/test_display_hint_validation.py -q
git diff --check
git add samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/infrastructure/xml_writer.py samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/domain/display_hint_validation.py samples/tagged_pdf_xml_poc/tests/test_xml_writer.py samples/tagged_pdf_xml_poc/tests/test_display_hint_validation.py
git commit -m "feat: serialize auditable text geometry"
```

### Task 3: Expand sentence boundaries to safe leaf body paragraphs

**Files:**

- Modify: `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/domain/paragraph_eligibility.py`
- Modify: `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/domain/readability_formatting.py`
- Modify: `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/domain/display_hint_validation.py`
- Modify: `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/infrastructure/markdown_writer.py`
- Test: `samples/tagged_pdf_xml_poc/tests/test_readability_formatting.py`
- Test: `samples/tagged_pdf_xml_poc/tests/test_display_hint_validation.py`
- Test: `samples/tagged_pdf_xml_poc/tests/test_markdown_writer.py`

- [ ] **Step 1: Replace the old negative test with explicit positive and safety cases**

Add RED tests for:

```python
assert sentence_start_offsets("Erster Satz. Zweiter Satz.") == (13,)
assert sentence_start_offsets("comme par exemple z. B. dieses Modell") == ()
assert sentence_start_offsets("comme par exemple z.\u00a0B. dieses Modell") == ()
```

Prove an ordinary leaf `P` receives a `SentenceBreakHint`, while each of the following remains ineligible: a source/promoted heading, label, caption, figure text, subtitle, strong label, URL/email, decimal/version/standard/model token, and a paragraph containing block descendants.

- [ ] **Step 2: Run focused tests and verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_readability_formatting.py tests/test_display_hint_validation.py tests/test_markdown_writer.py -q
```

- [ ] **Step 3: Centralize leaf-body eligibility and abbreviation protection**

Make `paragraph_eligibility.py` the shared source for semantic XML validation and Markdown validation. Define a leaf body paragraph structurally, without matching wording. Extend the existing abbreviation guard with a Unicode-aware pattern for two or more single-letter dotted tokens separated by normal whitespace or NBSP. Keep sentence offsets as evidence on the existing text node; do not insert source newline characters.

Remove any duplicate eligibility decision from `markdown_writer.py`; the writer may validate the already-recorded reason and offsets but must not rediscover PDF structure differently.

- [ ] **Step 4: Verify semantic and rendering behavior**

Run the Step 2 command. Expected:

- `z. B.` and `z.\u00a0B.` stay on one line;
- genuine leaf-body sentence boundaries render as `<br>` in Markdown;
- XML text remains byte-for-byte equivalent after joining text nodes.

- [ ] **Step 5: Commit**

```powershell
git diff --check
git add samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/domain/paragraph_eligibility.py samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/domain/readability_formatting.py samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/domain/display_hint_validation.py samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/infrastructure/markdown_writer.py samples/tagged_pdf_xml_poc/tests/test_readability_formatting.py samples/tagged_pdf_xml_poc/tests/test_display_hint_validation.py samples/tagged_pdf_xml_poc/tests/test_markdown_writer.py
git commit -m "feat: split safe leaf body sentences"
```

### Task 4: Recover strongly evidenced list-continuation paragraphs

**Files:**

- Modify: `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/domain/models.py`
- Create: `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/domain/list_continuation_detection.py`
- Modify: `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/domain/display_hint_validation.py`
- Modify: `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/application/extract_document.py`
- Modify: `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/infrastructure/xml_writer.py`
- Modify: `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/infrastructure/markdown_writer.py`
- Create: `samples/tagged_pdf_xml_poc/tests/test_list_continuation_detection.py`
- Modify: `samples/tagged_pdf_xml_poc/tests/test_display_hint_validation.py`
- Modify: `samples/tagged_pdf_xml_poc/tests/test_xml_writer.py`
- Modify: `samples/tagged_pdf_xml_poc/tests/test_markdown_writer.py`

- [ ] **Step 1: Write the positive topology/evidence test**

Construct `list -> P -> list` meaningful siblings on one page. Give the standalone `P` the same list-associated source role, font tier, left edge, and local vertical spacing as the preceding list body. Assert a hint such as:

```python
ContinuationHint(
    child_path=(2, 1),
    preceding_list_item_path=(2, 0, 0),
    page_index=12,
    paragraph_bbox=(72.0, 410.0, 320.0, 422.0),
    list_body_bbox=(72.5, 426.0, 318.0, 438.0),
    left_delta=0.5,
    vertical_gap=4.0,
    reference_font_size=10.0,
)
```

- [ ] **Step 2: Write fail-closed negative tests**

Each condition must independently prevent a hint:

- topology without geometry;
- visible bullet/number/heading marker;
- different page or language interval;
- different typography tier;
- paragraph aligned to list marker instead of body;
- excessive/negative vertical gap;
- multi-page or non-finite geometry;
- overlap with heading promotion, subtitle, strong-label, or another continuation hint.

- [ ] **Step 3: Run new tests and verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_list_continuation_detection.py tests/test_display_hint_validation.py tests/test_xml_writer.py tests/test_markdown_writer.py -q
```

- [ ] **Step 4: Implement the shared detector and immutable hint**

Use scale-relative tolerances based on the local reference font size and list-line spacing. Do not use fixed page coordinates or buyer-specific constants. Run the detector after subtitle/text-display detection but before sentence-break detection so conflict exclusions are available.

Serialize the semantic target with an auditable `display-role="list-continuation"` plus predecessor path, source role, typography, left delta, and vertical gap. Raw XML keeps only source geometry. Markdown indents the paragraph under the preceding list item without inserting a new bullet. Keep the paragraph independent in the model tree.

- [ ] **Step 5: Verify and commit**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_list_continuation_detection.py tests/test_display_hint_validation.py tests/test_xml_writer.py tests/test_markdown_writer.py tests/test_output_bundle.py -q
git diff --check
git add samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/domain/models.py samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/domain/list_continuation_detection.py samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/domain/display_hint_validation.py samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/application/extract_document.py samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/infrastructure/xml_writer.py samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/infrastructure/markdown_writer.py samples/tagged_pdf_xml_poc/tests/test_list_continuation_detection.py samples/tagged_pdf_xml_poc/tests/test_display_hint_validation.py samples/tagged_pdf_xml_poc/tests/test_xml_writer.py samples/tagged_pdf_xml_poc/tests/test_markdown_writer.py
git commit -m "feat: recover evidenced list continuations"
```

### Task 5: Detect a bold table subtitle and qualifier inside one paragraph

**Files:**

- Modify: `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/domain/models.py`
- Modify: `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/domain/subtitle_detection.py`
- Modify: `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/domain/display_hint_validation.py`
- Modify: `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/infrastructure/xml_writer.py`
- Modify: `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/infrastructure/markdown_writer.py`
- Modify: `samples/tagged_pdf_xml_poc/tests/test_subtitle_detection.py`
- Modify: `samples/tagged_pdf_xml_poc/tests/test_display_hint_validation.py`
- Modify: `samples/tagged_pdf_xml_poc/tests/test_xml_writer.py`
- Modify: `samples/tagged_pdf_xml_poc/tests/test_markdown_writer.py`

- [ ] **Step 1: Add RED tests for the one-paragraph source layout**

Model a figure cell followed by a text cell whose first leaf paragraph contains `title + actual-text newline + qualifier`. Assert that `SubtitleHint` records exact offsets:

```python
SubtitleHint(
    child_path=(3, 1, 0),
    font_weight=600,
    comparison_body_font_weight=400,
    observed_line_count=2,
    title_end_offset=len(title),
    qualifier_start_offset=len(title + "\n"),
)
```

Add rejection tests for no explicit source newline, empty segment, multiple possible split points, mixed title typography, missing following body, and overlap with another display hint. Preserve tests for the already-working two-paragraph layout.

- [ ] **Step 2: Run focused tests and verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_subtitle_detection.py tests/test_display_hint_validation.py tests/test_xml_writer.py tests/test_markdown_writer.py -q
```

- [ ] **Step 3: Extend the current structural detector**

Add optional `title_end_offset` and `qualifier_start_offset` to `SubtitleHint`. Accept the inline form only when the existing figure/text-cell adjacency, following-body, strength, and length checks pass and exactly one source-newline boundary divides two non-empty inline segments. Do not split on parentheses or title wording.

Semantic XML records both offsets. Markdown bolds only the title segment and places the qualifier on the following visual line. The separate-paragraph representation must remain unchanged.

- [ ] **Step 4: Verify and commit**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_subtitle_detection.py tests/test_display_hint_validation.py tests/test_xml_writer.py tests/test_markdown_writer.py tests/test_output_bundle.py -q
git diff --check
git add samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/domain/models.py samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/domain/subtitle_detection.py samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/domain/display_hint_validation.py samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/infrastructure/xml_writer.py samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/infrastructure/markdown_writer.py samples/tagged_pdf_xml_poc/tests/test_subtitle_detection.py samples/tagged_pdf_xml_poc/tests/test_display_hint_validation.py samples/tagged_pdf_xml_poc/tests/test_xml_writer.py samples/tagged_pdf_xml_poc/tests/test_markdown_writer.py
git commit -m "feat: recover inline table subtitles"
```

### Task 6: Load canonical profile context and build multilingual heading signatures

**Files:**

- Modify: `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/domain/models.py`
- Create: `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/domain/multilingual_heading_validation.py`
- Create: `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/ports/profile_repository.py`
- Create: `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/infrastructure/json_profile_repository.py`
- Modify: `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/infrastructure/pypdf_reader.py`
- Modify: `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/application/extract_document.py`
- Modify: `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/cli.py`
- Create: `samples/tagged_pdf_xml_poc/tests/test_json_profile_repository.py`
- Create: `samples/tagged_pdf_xml_poc/tests/test_multilingual_heading_validation.py`
- Modify: `samples/tagged_pdf_xml_poc/tests/test_pypdf_reader.py`
- Modify: `samples/tagged_pdf_xml_poc/tests/test_cli.py`

- [ ] **Step 1: Write profile repository contract tests**

Load `metadata/pdf_profile_mapping/pdf_profile_mapping.json` and prove lookup uses the filename-derived `source_token`, not folder name or PDF `/Lang`. Return immutable context:

```python
PdfProfile(
    source_token="ZC_L02",
    doc_type="A2",
    languages=("ENG", "C-FRA"),
    language_count=2,
)
```

Test unknown and malformed profiles as explicit errors when parity would be required; single-language extraction may proceed with parity marked not applicable.

- [ ] **Step 2: Write heading-signature RED tests**

Create two or more language intervals and assert each signature entry contains only:

```python
(heading_level, heading_origin, numbered_label_or_none)
```

Prove the audit detects:

- expected versus observed interval-count mismatch;
- total heading-count mismatch;
- heading-level sequence mismatch;
- source/promoted origin mismatch;
- numbered-label sequence mismatch;
- matching localized wording differences passing;
- a single-language profile returning `applicable=False`.

- [ ] **Step 3: Define language intervals without text guessing**

For sheet/combined-language PDFs, use existing structural language sections/page evidence and canonical profile order. For BOOK, add immutable bookmark page bounds to the reader result, use bookmark order as the source of truth, and validate structural language markers against those intervals. Do not infer intervals from translated labels or document `/Lang`.

If interval evidence is missing or ambiguous for a canonical multilingual profile, return a failed audit with a diagnostic rather than fabricating boundaries.

- [ ] **Step 4: Implement repository injection without breaking compatibility**

Add an optional `ProfileRepositoryPort` to `ExtractDocument`. Existing unit fakes that omit it must retain current behavior unless explicitly exercising parity; `_build_use_case()` wires the canonical JSON repository. Resolve the metadata file from an injected path or repository-root search with a deterministic failure message, not from sample folder names.

Run parity after numbered heading promotion and before quality evaluation, storing `MultilingualHeadingAudit` on `TaggedDocument`.

- [ ] **Step 5: Run focused tests and commit**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_json_profile_repository.py tests/test_multilingual_heading_validation.py tests/test_pypdf_reader.py tests/test_cli.py tests/test_numbered_heading_promotion.py -q
git diff --check
git diff --exit-code -- metadata/pdf_profile_mapping/pdf_profile_mapping.json
git add samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/domain/models.py samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/domain/multilingual_heading_validation.py samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/ports/profile_repository.py samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/infrastructure/json_profile_repository.py samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/infrastructure/pypdf_reader.py samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/application/extract_document.py samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/cli.py samples/tagged_pdf_xml_poc/tests/test_json_profile_repository.py samples/tagged_pdf_xml_poc/tests/test_multilingual_heading_validation.py samples/tagged_pdf_xml_poc/tests/test_pypdf_reader.py samples/tagged_pdf_xml_poc/tests/test_cli.py
git commit -m "feat: audit multilingual heading parity"
```

Do not edit the canonical JSON in this task. The explicit `git diff --exit-code` check must pass before committing; otherwise investigate and restore only the accidental metadata edit.

### Task 7: Add parity hard gates and auditable report/XML output

**Files:**

- Modify: `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/application/evaluate_quality.py`
- Modify: `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/infrastructure/xml_writer.py`
- Modify: `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/infrastructure/output_bundle.py`
- Modify: `samples/tagged_pdf_xml_poc/tests/test_quality_evaluator.py`
- Modify: `samples/tagged_pdf_xml_poc/tests/test_xml_writer.py`
- Modify: `samples/tagged_pdf_xml_poc/tests/test_output_bundle.py`
- Modify: `samples/tagged_pdf_xml_poc/tests/acceptance_support.py`

- [ ] **Step 1: Write RED hard-gate tests**

For applicable profiles, require all of these gates:

```python
"multilingual_interval_count_valid"
"multilingual_heading_count_parity"
"multilingual_heading_level_parity"
"multilingual_heading_origin_parity"
"multilingual_numbered_label_parity"
```

Single-language profiles set these gates to `True` with report metrics marking them `not_applicable`, so the global fixed hard-gate schema remains stable. Update the fixed-gate assertions and acceptance helper intentionally.

- [ ] **Step 2: Add report and XML audit tests**

Require `extraction_report.json` to expose expected/observed intervals, per-language heading totals, level/origin/numbered sequences, and mismatch positions. Semantic XML may include the derived audit in a document-level metadata node; Markdown must not invent or compare signatures.

- [ ] **Step 3: Implement gates and diagnostics**

An applicable missing/ambiguous profile or interval fails the interval gate. Any signature mismatch fails only the corresponding parity gate and includes interval ordinals and signature positions in diagnostics. Never compare localized heading text.

- [ ] **Step 4: Run focused tests and commit**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_quality_evaluator.py tests/test_xml_writer.py tests/test_output_bundle.py tests/test_cli.py -q
git diff --check
git add samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/application/evaluate_quality.py samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/infrastructure/xml_writer.py samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/infrastructure/output_bundle.py samples/tagged_pdf_xml_poc/tests/test_quality_evaluator.py samples/tagged_pdf_xml_poc/tests/test_xml_writer.py samples/tagged_pdf_xml_poc/tests/test_output_bundle.py samples/tagged_pdf_xml_poc/tests/acceptance_support.py
git commit -m "feat: gate multilingual heading parity"
```

### Task 8: Add representative real-PDF regression gates and regenerate review artifacts

**Files:**

- Modify: `samples/tagged_pdf_xml_poc/tests/test_layout_regression.py`
- Modify: `samples/tagged_pdf_xml_poc/tests/readability_assertions.py`
- Modify: `samples/tagged_pdf_xml_poc/README.md`
- Modify: `TODO.md`
- Generate: `samples/tagged_pdf_xml_poc/outputs/cross_profile_readability_zg_260908/`
- Generate: `samples/tagged_pdf_xml_poc/outputs/cross_profile_readability_zc_260908/`
- Generate: `samples/tagged_pdf_xml_poc/outputs/cross_profile_readability_latin_260908/`
- Generate: `samples/tagged_pdf_xml_poc/outputs/cross_profile_readability_kr_260908/`
- Generate: `samples/tagged_pdf_xml_poc/outputs/cross_profile_readability_xu_260908/`

- [ ] **Step 1: Correct/add required sample discovery**

Use the verified repository paths:

```text
samples/SUG_RAW/TV_ZG/BN68-25448A-00_SUG_Y26 TV ALL_ZG XN ZT_L05_260204.0.pdf
samples/SUG_RAW/TV_ZC/BN68-25100B-00_SUG_Y26 TV ALL_ZC_L02_260122.0.pdf
samples/SUG_RAW/TV_LATIN/BN68-24972A-00_SUG_Y26 TV ALL_LATIN_L02_250105.0.pdf
samples/SUG_RAW/TV_KR/BN68-25108A-00_SUG_Y26 TV ALL_KR_KOR_251218.0.pdf
samples/SUG_RAW/TV_XU/BN68-24437C-01_SUG_Y26 TV ALL_XU_ENG_260129.0.pdf
```

Required-sample mode must fail loudly if ZG, ZC, LATIN, KR, or XU is absent. Do not silently skip a missing required PDF.

- [ ] **Step 2: Add real-PDF assertions before regeneration**

For ZG assert:

- no sentence break inside all normal/NBSP `z. B.` occurrences;
- reviewed DEU and FRA multi-sentence leaf paragraphs have boundaries;
- FRA continuation target has exactly one continuation hint and remains source text-equivalent;
- ITA/DEU one-paragraph disposal subtitle has title/qualifier offsets and bold-title Markdown;
- 5 language intervals each have 26 headings with `H2=9`, `H3=8`, `H4=9` and equal full signatures.

For ZC and LATIN assert two intervals and matching full signatures. For KR and XU assert parity is not applicable and there are no false list-continuation or inline-subtitle hints outside structures that independently satisfy every detector condition.

- [ ] **Step 3: Run representative integration tests**

```powershell
$env:TAGGED_PDF_REQUIRE_SAMPLES='1'
.\.venv\Scripts\python.exe -m pytest tests/test_layout_regression.py tests/test_zc_integration.py -q
```

Expected: all five real PDFs run; no required sample is skipped.

- [ ] **Step 4: Regenerate the five output bundles**

Run the CLI once for each exact PDF path with `--overwrite` and the five output directories above. Record each status and report path. Do not reuse stale outputs.

- [ ] **Step 5: Inspect the human-review Markdown and machine evidence**

Check the known ZG passages in the newly generated file rather than relying on old line numbers, because added `<br>` lines move positions. Search by text fragments for:

- DEU `z. B.` passages previously near lines 849/929;
- DEU two-sentence passages previously near 957/1113;
- FRA passage previously near 1530 and continuation previously near 1580;
- ITA disposal title previously near 2862.

Also compare XML and Markdown text normalization, ensure all five reports have the intended status, and confirm coordinate evidence appears only in XML/report—not human Markdown.

- [ ] **Step 6: Update docs and commit the regression slice**

Document the shared evidence policy, five validation profiles, output paths, and any intentionally unsupported geometry. Mark this active TODO item complete only after all gates pass and manual spot checks are recorded.

```powershell
git diff --check
git add samples/tagged_pdf_xml_poc/tests/test_layout_regression.py samples/tagged_pdf_xml_poc/tests/readability_assertions.py samples/tagged_pdf_xml_poc/README.md TODO.md
git commit -m "test: gate cross-profile readability extraction"
```

The five regenerated output directories are intentionally ignored review artifacts. Leave them on disk for human inspection and report their exact paths in the handoff; do not force-add them to Git.

### Task 9: Full verification and independent review

**Files:**

- Review: all files changed since `a8a2e00`

- [ ] **Step 1: Run the complete POC suite**

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Expected: no failures. The Windows symlink capability test may remain the one documented skip; required real-PDF tests must not be skipped.

- [ ] **Step 2: Run repository compilation target**

From the repository root:

```powershell
python -m compileall src tests scripts apps
.\samples\tagged_pdf_xml_poc\.venv\Scripts\python.exe -m compileall samples/tagged_pdf_xml_poc/src samples/tagged_pdf_xml_poc/tests
```

Expected: exit code 0 for both commands.

- [ ] **Step 3: Run cleanliness and accidental-hardcoding checks**

```powershell
git diff --check a8a2e00..HEAD
rg -n "ZG XN ZT_L05|ZC_L02|LATIN_L02|KR_KOR|XU_ENG|Correct Disposal|Declaration of Conformity|z\. B\." samples/tagged_pdf_xml_poc/src
git status --short
```

Expected: no runtime buyer/phrase hardcoding added by this work; sample names may occur only in tests/docs. Generated caches and virtual environments remain ignored.

- [ ] **Step 4: Request an independent code review**

Use `superpowers:requesting-code-review` against `a8a2e00..HEAD`. The reviewer must check fail-closed geometry, source-text preservation, detector/writer responsibility boundaries, profile metadata usage, fixed hard-gate schema, and representative PDF coverage.

- [ ] **Step 5: Address findings with tests, then rerun Steps 1–3**

Any behavioral fix starts with a reproducing test. Do not declare completion from a partial suite or stale output bundle.

- [ ] **Step 6: Final verification commit if review changes were needed**

```powershell
git diff --check
git add <reviewed-files-only>
git commit -m "fix: address cross-profile extraction review"
```
