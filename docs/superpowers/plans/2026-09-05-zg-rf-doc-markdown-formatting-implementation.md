# ZG RF and DoC Markdown Formatting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve PDF-authored RF line breaks and render DoC title/label hierarchy for the verified ZG BOOK profile while proving no behavior change for ZC, ZA, XY, or KR.

**Architecture:** Keep profile selection, typography analysis, display-hint detection, semantic XML serialization, and Markdown rendering separate. Detection is reusable and wording-independent, but a local source-token dispatch policy initially activates it only for `ZG XN ZT_L05 -> BOOK`; the Markdown writer only consumes validated semantic XML evidence.

**Tech Stack:** Python 3.11+, frozen dataclasses, `pypdf`, PyMuPDF, `xml.etree.ElementTree`, pytest.

---

## File Map

- Create `src/tagged_pdf_extractor/domain/profile_scope.py`: parse the standard filename source token and decide whether ZG BOOK review formatting is enabled.
- Create `src/tagged_pdf_extractor/domain/typography.py`: reusable relative font-weight/size evidence shared by subtitle and form-cluster detection.
- Create `src/tagged_pdf_extractor/domain/review_formatting.py`: orchestrate ZG-scoped RF boundary and form-cluster hint detection.
- Modify `src/tagged_pdf_extractor/domain/models.py`: add immutable line-break and text-display hint records to `TaggedDocument`.
- Modify `src/tagged_pdf_extractor/domain/subtitle_detection.py`: consume shared typography helpers without breaking compatibility imports.
- Modify `src/tagged_pdf_extractor/application/extract_document.py`: invoke profile-scoped review formatting after numbered-heading and subtitle detection.
- Modify `src/tagged_pdf_extractor/infrastructure/xml_writer.py`: validate/serialize display evidence only into semantic XML.
- Modify `src/tagged_pdf_extractor/infrastructure/markdown_writer.py`: render section headings, bold labels, and approved inline line breaks.
- Modify `src/tagged_pdf_extractor/application/evaluate_quality.py`: retain display-hint audit metrics if required by output validation.
- Add/modify focused tests for each module and end-to-end output behavior.
- Extend real-sample regression coverage to required XY ENG and KR KOR negative controls.

### Task 1: Profile Scope and Shared Typography Evidence

**Files:**
- Create: `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/domain/profile_scope.py`
- Create: `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/domain/typography.py`
- Modify: `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/domain/subtitle_detection.py`
- Test: `samples/tagged_pdf_xml_poc/tests/test_profile_scope.py`
- Test: `samples/tagged_pdf_xml_poc/tests/test_typography.py`
- Test: `samples/tagged_pdf_xml_poc/tests/test_subtitle_detection.py`

- [x] **Step 1: Write failing source-token dispatch tests**

Cover standard ZG, ZC, ZA, XY, and KR filenames, malformed names, mixed filename casing, and paths containing misleading parent-folder names. The parser must use only the filename segment between `_ALL_` and the trailing `_<YYMMDD>.<revision>.pdf` token.

```python
def test_only_verified_zg_book_source_token_enables_formatting() -> None:
    assert review_formatting_scope(
        Path("BN68-25448A-00_SUG_Y26 TV ALL_ZG XN ZT_L05_260204.0.pdf")
    ) == ProfileScope("ZG XN ZT_L05", "BOOK", True)
    assert not review_formatting_scope(
        Path("BN68-25031B-00_SUG_Y26 TV ALL_XY_ENG_251229.0.pdf")
    ).enabled
```

- [x] **Step 2: Run the profile tests and verify RED**

Run: `.\.venv\Scripts\python -m pytest tests/test_profile_scope.py -q`

Expected: collection/import failure because `profile_scope.py` does not exist.

- [x] **Step 3: Implement the local profile policy**

Use a strict anchored regular expression and an immutable result:

```python
@dataclass(frozen=True)
class ProfileScope:
    source_token: str | None
    doc_type: str | None
    enabled: bool

def review_formatting_scope(source_path: Path) -> ProfileScope:
    token = parse_source_token(source_path.name)
    if token == "ZG XN ZT_L05":
        return ProfileScope(token, "BOOK", True)
    return ProfileScope(token, None, False)
```

The ZG source token is dispatch metadata, not content matching. Do not import the root application or metadata repository.

- [x] **Step 4: Write failing shared typography tests**

Test weighted median font weight and size, visible-character weighting, line-count evidence, missing styles, unknown font names, and strict font-token boundaries. Preserve `normalize_font_weight` as an importable name from `subtitle_detection.py` for compatibility.

- [x] **Step 5: Implement `TypographyEvidence` and refactor subtitle detection**

```python
@dataclass(frozen=True)
class TypographyEvidence:
    font_weight: int
    font_size: float
    observed_lines: frozenset[tuple[int, int]]

def typography_evidence(element: StructureElement) -> TypographyEvidence | None:
    ...
```

Move only reusable evidence code. Do not change existing Correct Disposal subtitle decisions.

- [x] **Step 6: Run focused tests and commit**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_profile_scope.py tests/test_typography.py tests/test_subtitle_detection.py -q
.\.venv\Scripts\python -m compileall src tests
```

Expected: all focused tests pass and existing subtitle tests remain unchanged.

Commit: `Add profile scope and shared typography evidence`

### Task 2: ZG-Scoped RF Line-Break Hint Detection

**Files:**
- Modify: `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/domain/models.py`
- Create: `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/domain/review_formatting.py`
- Test: `samples/tagged_pdf_xml_poc/tests/test_review_formatting.py`

- [x] **Step 1: Add a failing immutable hint-model test**

```python
hint = LineBreakHint(
    child_path=(0, 1, 0, 2),
    reason="source_actual_text_newline_after_comma_in_table_cell",
)
assert hint.child_path == (0, 1, 0, 2)
```

Add `line_break_hints` to `TaggedDocument` with an empty tuple default so all existing constructors remain compatible.

- [x] **Step 2: Add failing detector tests**

Build synthetic structures proving all four required conditions:

- ancestor chain contains `table_cell` and `paragraph`;
- target is an inline structure element with `actual_text="\n"`;
- previous visible sibling ends with a comma;
- following visible sibling is non-empty.

Also prove rejection for an ordinary comma with no newline element, a newline outside a table cell, a non-comma newline, empty adjacent content, malformed paths, ZC/ZA/XY/KR filenames, and parent folders containing `ZG` while the filename is XY.

- [x] **Step 3: Run detector tests and verify RED**

Run: `.\.venv\Scripts\python -m pytest tests/test_review_formatting.py -q`

Expected: failures for missing models/detector.

- [x] **Step 4: Implement minimal path-aware detection**

```python
def apply_profile_review_formatting(document: TaggedDocument) -> TaggedDocument:
    scope = review_formatting_scope(document.source_path)
    if not scope.enabled:
        return document
    return replace(
        document,
        line_break_hints=detect_rf_line_break_hints(document.children),
        text_display_hints=detect_form_cluster_hints(document),
    )
```

Traversal must use structural child indices exactly as XML serialization does. Detection must inspect source `actual_text`; it must never search for RF wording, model patterns, units, or frequency syntax.

- [x] **Step 5: Run focused tests and commit**

Run: `.\.venv\Scripts\python -m pytest tests/test_review_formatting.py tests/test_subtitle_detection.py -q`

Expected: all pass.

Commit: `Detect ZG source-authored RF line breaks`

### Task 3: Conservative Form-Cluster Heading and Bold-Label Detection

**Files:**
- Modify: `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/domain/models.py`
- Modify: `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/domain/review_formatting.py`
- Test: `samples/tagged_pdf_xml_poc/tests/test_review_formatting.py`

- [x] **Step 1: Add failing text-display hint tests**

Use one immutable hint type with explicit roles:

```python
@dataclass(frozen=True)
class TextDisplayHint:
    child_path: tuple[int, ...]
    display_role: Literal["section_heading", "strong_label"]
    font_weight: int
    font_size: float
    comparison_body_font_weight: int
    comparison_body_font_size: float
    reason: str
```

Test duplicate paths, overlap with numbered headings/subtitles, and invalid roles at serialization boundaries.

- [x] **Step 2: Add a complete synthetic cluster RED test**

The fixture must include one structural section with:

- one unique strongest short opening paragraph;
- at least three middle-tier short direct labels;
- weaker direct detail paragraphs after each label;
- one table with at least two cells, each beginning with a middle-tier label followed by weaker detail paragraphs.

Assert one `section_heading` hint for the opening paragraph and `strong_label` hints for direct and table-cell labels.

- [x] **Step 3: Add conservative rejection tests**

Independently remove or corrupt each required signal: unique strongest tier, three label/body groups, relative weight order, relative size order, table evidence, weaker following detail, short-text bound, style evidence, source-role heading conflict, numbered promotion conflict, subtitle conflict, and ZG profile scope. Each fixture must produce no new hints.

- [x] **Step 4: Implement cluster-level validation before label decisions**

The detector must first validate the complete section. It must compare tiers relatively and use typography evidence weighted by visible characters. Only after cluster acceptance may it emit label hints. Table-cell labels require a weaker following paragraph in the same cell; direct labels require weaker following detail before the next accepted label/block boundary.

Do not include `Declaration`, `Manufacturer`, `EMC`, `Safety`, `Radio`, translations, language codes, or model values in runtime matching.

- [x] **Step 5: Run focused tests and commit**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_review_formatting.py tests/test_numbered_heading_promotion.py tests/test_subtitle_detection.py -q
```

Expected: all pass, with existing heading/subtitle behavior unchanged.

Commit: `Detect ZG form headings and strong labels`

### Task 4: Semantic XML, Markdown, and Atomic Validation

**Files:**
- Modify: `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/application/extract_document.py`
- Modify: `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/infrastructure/xml_writer.py`
- Modify: `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/infrastructure/markdown_writer.py`
- Modify: `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/application/evaluate_quality.py`
- Test: `samples/tagged_pdf_xml_poc/tests/test_xml_writer.py`
- Test: `samples/tagged_pdf_xml_poc/tests/test_markdown_writer.py`
- Test: `samples/tagged_pdf_xml_poc/tests/test_output_bundle.py`
- Test: `samples/tagged_pdf_xml_poc/tests/test_quality_evaluator.py`

- [x] **Step 1: Add semantic/raw XML RED tests**

Assert semantic XML attributes such as:

```xml
<paragraph display-role="section-heading" display-level="2" ...>
<paragraph display-role="strong-label" ...>
<span display-role="preserved-line-break" ... actual-text="&#10;">
```

Raw XML must contain none of these display attributes and must retain original text/`actual-text` values.

- [x] **Step 2: Add validation RED tests**

Reject unresolved, duplicate, non-structural, mistyped, negative-index, and overlapping paths. Reject a form heading/label that overlaps a numbered heading, source-role heading, subtitle, or line-break target of the wrong element type. Prove failed validation leaves all existing bundle outputs untouched.

- [x] **Step 3: Implement semantic-only serialization and pipeline wiring**

Invoke `apply_profile_review_formatting` after numbered promotion and existing subtitle detection. Centralize hint target validation so automatic and manually supplied hints obey identical invariants.

- [x] **Step 4: Add Markdown RED tests**

Assert:

- `section-heading` renders once as `## ...`;
- `strong-label` renders once as `**...**` with emphasis escaping;
- an approved inline boundary inserts a physical Markdown newline;
- an ordinary comma remains inline;
- nested table indentation is retained;
- candidate headings and display headings do not duplicate text;
- `render_text` and written output are byte-identical.

- [x] **Step 5: Implement evidence-only Markdown rendering**

The writer must not parse filenames, fonts, buyer tokens, titles, or commas. It renders only semantic XML display attributes. Preserve current punctuation joining everywhere without an approved boundary.

- [x] **Step 6: Run focused tests and commit**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_xml_writer.py tests/test_markdown_writer.py tests/test_output_bundle.py tests/test_quality_evaluator.py -q
.\.venv\Scripts\python -m compileall src tests
```

Expected: all pass.

Commit: `Render ZG RF and form display evidence`

### Task 5: ZG, ZC, ZA, XY, and KR Real-Sample Gates

**Files:**
- Modify: `samples/tagged_pdf_xml_poc/tests/acceptance_support.py`
- Modify: `samples/tagged_pdf_xml_poc/tests/test_layout_regression.py`
- Modify: `samples/tagged_pdf_xml_poc/tests/test_zc_integration.py`

- [x] **Step 1: Register required XY and KR sample overrides**

Add `TAGGED_PDF_XY_SAMPLE` and `TAGGED_PDF_KR_SAMPLE` resolution using the exact user-provided worktree paths as available fallbacks. Required-sample mode must fail rather than silently skip when an explicitly required sample is missing.

- [x] **Step 2: Add ZG real-sample assertions**

Verify without Markdown line-number dependencies:

- every eligible RF comma boundary becomes a separate line in source order;
- all five language sections and both repeated DoC forms per language produce exactly ten level-2 form headings;
- validated middle-tier direct/table labels are bold and their detail lines remain separate;
- no runtime assertion depends on English/localized DoC titles for detection, while expected rendered text may be used as regression output evidence;
- numbered headings and Correct Disposal output are unchanged.

- [x] **Step 3: Add ZC/ZA/XY/KR negative controls**

Extract all four PDFs and assert zero ZG profile line-break hints, zero form-cluster heading hints, and zero form-cluster strong-label hints. Retain their existing heading and text-quality assertions. For XY and KR, also assert output bundle creation and non-empty Markdown.

- [x] **Step 4: Run all five required sample regressions**

Set:

```powershell
$env:TAGGED_PDF_REQUIRE_SAMPLES='1'
$env:TAGGED_PDF_ZC_SAMPLE='<verified ZC path>'
$env:TAGGED_PDF_ZA_SAMPLE='<verified ZA path>'
$env:TAGGED_PDF_ZG_SAMPLE='<verified ZG path>'
$env:TAGGED_PDF_XY_SAMPLE='C:\Users\bella\image-extractor\.worktrees\xml-markdown-review\samples\SUG_RAW\TV_XY\BN68-25031B-00_SUG_Y26 TV ALL_XY_ENG_251229.0.pdf'
$env:TAGGED_PDF_KR_SAMPLE='C:\Users\bella\image-extractor\.worktrees\xml-markdown-review\samples\SUG_RAW\TV_KR\BN68-25108A-00_SUG_Y26 TV ALL_KR_KOR_251218.0.pdf'
```

Run: `.\.venv\Scripts\python -m pytest tests/test_zc_integration.py tests/test_layout_regression.py -q`

Expected: all five samples pass with no skips.

- [x] **Step 5: Commit**

Commit: `Gate ZG formatting against XY and KR`

### Task 6: Full Verification and Reviewer Output Regeneration

**Files:**
- Verify: `samples/tagged_pdf_xml_poc/src/`
- Verify: `samples/tagged_pdf_xml_poc/tests/`
- Generate ignored artifacts under: `samples/tagged_pdf_xml_poc/outputs/`

- [x] **Step 1: Run the complete required-sample suite**

With all five environment variables from Task 5, run:

```powershell
.\.venv\Scripts\python -m pytest tests -q
```

Expected: zero failures and no sample skips; only the documented Windows symlink skip may remain.

- [x] **Step 2: Run compile and no-hardcoding audits**

```powershell
.\.venv\Scripts\python -m compileall src tests
python -m compileall src tests scripts apps
rg -n "Declaration of Conformity|Manufacturer|Product Details|applicable standards|Correct Disposal|RF max transmitter|QN990H" src
```

Expected: both compile commands exit zero; the source audit finds no content-title/model matching in runtime code.

- [x] **Step 3: Regenerate review bundles**

Generate fresh ignored outputs:

- `outputs/structured_markdown_zg_rf_doc_260905`
- `outputs/structured_markdown_xy_guard_260905`
- `outputs/structured_markdown_kr_guard_260905`

Each must contain `semantic_document.md`, `semantic_document.xml`, `raw_structure.xml`, and `extraction_report.json`.

- [x] **Step 4: Inspect representative Markdown and semantic evidence**

Confirm ZG RF lines, all DoC headings/labels, nested table indentation, and Correct Disposal text. Confirm XY/KR have no ZG-only display attributes. Confirm generated outputs remain Git-ignored.

- [x] **Step 5: Final independent review and branch handoff**

Review the complete implementation diff against the design, fix all Critical/Important findings, rerun affected tests, and report exact output paths and verification counts.
