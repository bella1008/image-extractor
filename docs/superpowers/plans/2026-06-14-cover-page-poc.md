# Cover Page POC Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a cover-page-only POC for the ZC English SUG sample so extracted text, regions, tables, and image evidence can be reviewed.

**Architecture:** Add a focused `src/cover_poc.py` module that calls existing filename/profile/structure/text extraction code, then writes cover-only JSON, Markdown, XLSX, and PNG crops. Keep the existing flat `src/` package and avoid changing the general extraction pipeline beyond using its current cover output.

**Tech Stack:** Python, PyMuPDF, openpyxl, existing `src` modules.

---

### Task 1: Cover POC Output Model

**Files:**
- Create: `src/cover_poc.py`
- Test: `tests/test_cover_poc.py`

- [ ] **Step 1: Write failing tests**

Test that the module can build deterministic output paths, sanitize region names for crop files, and render cover Markdown from a cover page dictionary.

- [ ] **Step 2: Run tests to verify failure**

Run: `python -m unittest tests.test_cover_poc`

Expected: fail because `src.cover_poc` does not exist.

- [ ] **Step 3: Implement minimal helpers**

Implement:

```python
make_output_paths(output_dir, source_token, language)
safe_region_slug(region)
build_cover_review_markdown(payload)
```

- [ ] **Step 4: Run tests**

Run: `python -m unittest tests.test_cover_poc`

Expected: pass.

### Task 2: Cover POC Generator

**Files:**
- Modify: `src/cover_poc.py`
- Test: `tests/test_cover_poc.py`

- [ ] **Step 1: Write failing tests**

Test that `build_cover_poc_payload()` returns cover schema, schema validation, markdown, and region rows from a minimal extracted-text payload.

- [ ] **Step 2: Implement generator**

Implement:

```python
run_cover_poc(pdf_path, output_dir, language="ENG", mapping_path=...)
```

It should write:

```text
cover_poc.json
cover_poc.md
cover_regions.xlsx
cover_page.png
regions/region_XX_<type>.png
```

- [ ] **Step 3: Run tests**

Run: `python -m unittest tests.test_cover_poc tests.test_text_extractor_cover tests.test_excel_exporter`

Expected: pass.

### Task 3: Generate ZC POC Artifacts

**Files:**
- Output only under: `outputs/cover_poc/ZC_L02_ENG/`

- [ ] **Step 1: Execute POC**

Run:

```powershell
python -m src.cover_poc "samples/SUG_RAW/TV_ZC/BN68-25100B-00_SUG_Y26 TV ALL_ZC_L02_260122.0.pdf" --language ENG --output-dir outputs/cover_poc/ZC_L02_ENG
```

- [ ] **Step 2: Verify artifacts**

Run:

```powershell
Get-ChildItem outputs/cover_poc/ZC_L02_ENG -Recurse
```

Expected: JSON, Markdown, XLSX, page PNG, and region PNGs exist.

