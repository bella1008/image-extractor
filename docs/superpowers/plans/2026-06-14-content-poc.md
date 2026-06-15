# Content POC Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an ENG-only contents POC for the ZC_L02 sample that excludes cover cells and exports section/block review data for human inspection.

**Architecture:** Add a focused `src/content_poc.py` module parallel to `cover_poc.py`. It calls the existing filename/profile/structure/text extraction pipeline, filters to content cells, converts review items into content blocks, marks risky block types, and writes JSON, Markdown, Excel, and cell crop evidence.

**Tech Stack:** Python, PyMuPDF, openpyxl, existing flat `src` package.

---

### Task 1: Content POC Payload Helpers

**Files:**
- Create: `src/content_poc.py`
- Test: `tests/test_content_poc.py`

- [ ] **Step 1: Write failing tests**

Test output path creation, content-only filtering, block summaries, and review flags from a minimal extracted payload.

- [ ] **Step 2: Run test to verify failure**

Run: `python -m unittest tests.test_content_poc`

Expected: fail because `src.content_poc` does not exist.

- [ ] **Step 3: Implement minimal helpers**

Implement:

```python
make_output_paths(output_dir, source_token, language)
build_content_poc_payload(extracted)
build_content_markdown(payload)
write_content_poc_outputs(payload, paths)
```

- [ ] **Step 4: Run tests**

Run: `python -m unittest tests.test_content_poc`

Expected: pass.

### Task 2: Content POC Runtime

**Files:**
- Modify: `src/content_poc.py`
- Test: `tests/test_content_poc.py`

- [ ] **Step 1: Implement runtime**

Add:

```python
run_content_poc(pdf_path, output_dir, language="ENG", mapping_path=...)
```

It should write:

```text
content_poc.json
content_blocks.md
content_review.xlsx
crops/cell_*.png
```

- [ ] **Step 2: Verify ZC output**

Run:

```powershell
python -m src.content_poc "samples/SUG_RAW/TV_ZC/BN68-25100B-00_SUG_Y26 TV ALL_ZC_L02_260122.0.pdf" --language ENG --output-dir outputs/content_poc
```

### Task 3: Verification

- [ ] **Step 1: Run related tests**

Run:

```powershell
python -m unittest tests.test_content_poc tests.test_cover_poc tests.test_text_extractor_cover tests.test_excel_exporter
```

- [ ] **Step 2: Run syntax check**

Run:

```powershell
python -m compileall src tests
```

