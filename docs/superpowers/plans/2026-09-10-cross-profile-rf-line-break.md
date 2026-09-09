# Cross-Profile RF Source Line-Break Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve explicitly tagged comma-following RF line breaks for XU and any other structurally equivalent profile while keeping DoC typography formatting ZG-only.

**Architecture:** Run the existing fail-closed RF boundary detector for every tagged document, independently from profile dispatch. Continue using the existing ZG profile scope only for form-cluster heading and strong-label hints; the XML and Markdown writers remain passive consumers of validated hints.

**Tech Stack:** Python 3.13, immutable dataclasses, ElementTree XML output, pytest, pypdf/PyMuPDF tagged-PDF reader.

---

### Task 1: Prove Profile-Independent RF Detection and ZG-Only DoC Formatting

**Files:**
- Modify: `samples/tagged_pdf_xml_poc/tests/test_review_formatting.py`
- Modify: `samples/tagged_pdf_xml_poc/tests/test_output_bundle.py`

- [ ] **Step 1: Write the failing unit test**

Add an XU-like document containing one qualifying table-cell newline and a valid
form cluster. Assert that `apply_profile_review_formatting()` emits one
`LineBreakHint` but emits no form-cluster `TextDisplayHint` outside ZG.

```python
def test_xu_applies_source_line_break_without_zg_form_formatting() -> None:
    source = "BN68-24437C-01_SUG_Y26 TV ALL_XU_ENG_260129.0.pdf"
    document = _document(
        (_fragment("First specification,"), _newline(), _fragment("Second specification")),
        filename=source,
    )

    formatted = review_formatting.apply_profile_review_formatting(document)

    assert len(formatted.line_break_hints) == 1
    assert formatted.text_display_hints == ()
```

- [ ] **Step 2: Write the failing end-to-end bundle test**

Change the non-ZG output test so the synthetic XU/XY-style source still renders
`First specification,\nSecond specification`, while section-heading and
strong-label roles remain absent.

```python
assert len(semantic.findall(".//*[@display-role='preserved-line-break']")) == 1
assert "First specification,\n" in markdown
assert semantic.find(".//*[@display-role='section-heading']") is None
assert semantic.find(".//*[@display-role='strong-label']") is None
```

- [ ] **Step 3: Run the focused tests and verify RED**

Run:

```powershell
python -m pytest tests/test_review_formatting.py tests/test_output_bundle.py -q
```

Expected: the new non-ZG line-break assertions fail because
`apply_profile_review_formatting()` returns non-ZG documents unchanged.

### Task 2: Separate Generic RF Hints from Profile-Scoped Form Hints

**Files:**
- Modify: `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/domain/review_formatting.py`

- [ ] **Step 1: Implement the minimal orchestration split**

Compute RF hints before checking the ZG scope. For non-ZG documents, replace only
`line_break_hints` and preserve existing `text_display_hints`; for ZG, replace
both derived hint sets.

```python
def apply_profile_review_formatting(document: TaggedDocument) -> TaggedDocument:
    line_break_hints = detect_rf_line_break_hints(document.children)
    if not review_formatting_scope(document.source_path).enabled:
        return replace(document, line_break_hints=line_break_hints)
    return replace(
        document,
        line_break_hints=line_break_hints,
        text_display_hints=detect_form_cluster_hints(document),
    )
```

- [ ] **Step 2: Run focused tests and verify GREEN**

Run:

```powershell
python -m pytest tests/test_review_formatting.py tests/test_output_bundle.py -q
```

Expected: all focused tests pass; non-ZG output has preserved line breaks but no
ZG-only DoC formatting.

### Task 3: Add the Real XU RF Regression Gate

**Files:**
- Modify: `samples/tagged_pdf_xml_poc/tests/test_layout_regression.py`

- [ ] **Step 1: Strengthen the existing XU real-PDF test**

In `test_xu_retains_source_warranty_and_rf_model_structure`, assert that the real
semantic XML has 18 preserved line-break markers and that representative RF
frequency clauses are separate Markdown lines. Keep the existing Warranty heading
assertions.

```python
assert len(
    semantic_root.findall(".//*[@display-role='preserved-line-break']")
) == 18
assert "100 mW at 2.4 GHz - 2.4835 GHz,\n" in markdown
assert "200 mW at 5.15 GHz - 5.25 GHz,\n" in markdown
assert markdown.count("### Warranty Card") == 1
assert markdown.count("### WARRANTY CONDITIONS") == 1
```

- [ ] **Step 2: Run the real XU and ZG regression tests**

Run:

```powershell
python -m pytest tests/test_layout_regression.py -q -k "xu or zg"
```

Expected: XU and ZG tests pass; XU reports 18 and ZG retains 90 preserved source
line breaks.

### Task 4: Regenerate Reviewer Output and Complete Verification

**Files:**
- Modify: `TODO.md`
- Modify: `samples/tagged_pdf_xml_poc/README.md`
- Regenerate ignored artifact: `samples/tagged_pdf_xml_poc/outputs/cross_profile_readability_xu_260908/semantic_document.xml`
- Regenerate ignored artifact: `samples/tagged_pdf_xml_poc/outputs/cross_profile_readability_xu_260908/semantic_document.md`

- [ ] **Step 1: Document the completed dispatch split**

Update the RF follow-up entry to state that explicit comma-following table-cell
newlines are shared across profiles, with XU and ZG positive real-PDF evidence and
DoC typography still ZG-only.

- [ ] **Step 2: Regenerate the XU bundle using the existing layout-regression output command or fixture path**

Use the same extractor entry point and exact XU PDF that produced
`cross_profile_readability_xu_260908`; do not hand-edit XML or Markdown.

- [ ] **Step 3: Run the full POC suite**

Run:

```powershell
python -m pytest tests -q
```

Expected: zero failures; the only allowed skip is the existing Windows symlink
capability test.

- [ ] **Step 4: Run compile verification**

Run from the repository root:

```powershell
python -m compileall src tests scripts apps samples/tagged_pdf_xml_poc/src samples/tagged_pdf_xml_poc/tests
```

Expected: exit code 0.

- [ ] **Step 5: Inspect the generated XU RF block**

Confirm that the RF rows beginning near Markdown line 625 break only at the 18
PDF-authored comma boundaries and that `Warranty Card` and `WARRANTY CONDITIONS`
remain headings.

### Task 5: Commit and Integrate Safely

**Files:**
- Commit only the files listed above that are tracked by Git.

- [ ] **Step 1: Review the feature diff**

Run:

```powershell
git diff --check
git diff --stat
```

Expected: no whitespace errors and no unrelated files.

- [ ] **Step 2: Commit the implementation**

```powershell
git add docs/superpowers/specs/2026-09-10-cross-profile-rf-line-break-design.md docs/superpowers/plans/2026-09-10-cross-profile-rf-line-break.md samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/domain/review_formatting.py samples/tagged_pdf_xml_poc/tests/test_review_formatting.py samples/tagged_pdf_xml_poc/tests/test_output_bundle.py samples/tagged_pdf_xml_poc/tests/test_layout_regression.py samples/tagged_pdf_xml_poc/README.md TODO.md
git commit -m "fix: preserve cross-profile RF source line breaks"
```

- [ ] **Step 3: Integrate into main without overwriting unrelated work**

Verify the main worktree has no overlapping changes to the tracked files, then
fast-forward or cherry-pick the feature commit. If any overlap exists, stop and
resolve only the overlapping hunks; never copy the entire worktree over main.
