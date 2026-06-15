# ZC Navigation and Output Naming Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent quoted UI labels from being misclassified as navigation, and save content review Excel outputs with unique timestamped filenames that include the manual code.

**Architecture:** Tighten the navigation detector so it only recognizes explicit breadcrumb-style paths that include `>` separators, while leaving quoted UI labels as body text. Update the content POC output path builder to generate timestamped workbook names from the parsed manual code and source token, so multiple sample runs do not overwrite or collide.

**Tech Stack:** Python 3.12, PyMuPDF, openpyxl, unittest.

---

### Task 1: Restrict navigation detection to explicit breadcrumb paths

**Files:**
- Modify: `src/text_extractor.py`
- Test: `tests/test_content_poc.py`

- [ ] **Step 1: Write the failing test**

```python
def test_quoted_ui_label_does_not_become_navigation():
    payload = build_content_poc_payload(minimal_extracted_payload_with_troubleshooting_reference())
    blocks = [block for block in payload["blocks"] if block["section_heading"] == "Troubleshooting"]
    assert any(block["block_type"] == "body" and '\"Troubleshooting\"' in block["text"] for block in blocks)
    assert not any(block["block_type"] == "navigation_ui" and block["text"] == "Troubleshooting" for block in blocks)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_content_poc`
Expected: the quoted label is still classified as `navigation_ui`.

- [ ] **Step 3: Write minimal implementation**

```python
def is_navigation_fragment(line: str) -> bool:
    normalized = normalize_sentence(line)
    if ">" not in normalized:
        return False
    if normalized in {">", "(", ")"}:
        return True
    if normalized.startswith(">") or normalized.endswith(">"):
        return True
    return normalized in {
        "left directional button",
        "> left directional button >",
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_content_poc`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/text_extractor.py tests/test_content_poc.py
git commit -m "fix: tighten navigation detection"
```

### Task 2: Add timestamped workbook filenames with manual code

**Files:**
- Modify: `src/content_poc.py`
- Modify: `tests/test_content_poc.py`
- Modify: `tests/test_cover_poc.py`

- [ ] **Step 1: Write the failing test**

```python
def test_make_output_paths_includes_manual_code_and_timestamp():
    paths = make_output_paths(Path("outputs/content_poc"), "BN68-20834D-00", "ZC_L02", "ENG", timestamp="260615_2130")
    assert paths.xlsx_path.name == "BN68-20834D-00_ZC_L02_ENG_260615_2130_content_review.xlsx"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_content_poc`
Expected: `TypeError` because `make_output_paths` does not yet accept the new naming inputs.

- [ ] **Step 3: Write minimal implementation**

```python
def make_output_paths(
    output_dir: Path,
    manual_code: str,
    source_token: str,
    language: str,
    timestamp: str | None = None,
) -> ContentPocPaths:
    root = output_dir / f"{source_token}_{language}"
    stamp = timestamp or datetime.now().strftime("%y%m%d_%H%M")
    xlsx_name = f"{manual_code}_{source_token}_{language}_{stamp}_content_review.xlsx"
    return ContentPocPaths(
        root=root,
        json_path=root / "content_poc.json",
        markdown_path=root / "content_blocks.md",
        xlsx_path=root / xlsx_name,
        crop_dir=root / "crops",
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_content_poc tests.test_cover_poc`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/content_poc.py tests/test_content_poc.py tests/test_cover_poc.py
git commit -m "feat: timestamp content review workbook names"
```

### Task 3: Regenerate the ZC ENG sample outputs and verify filenames

**Files:**
- Regenerate outputs under: `outputs/content_poc_review_zc_eng_final_v3/`

- [ ] **Step 1: Run the POC for the three ZC ENG sample PDFs**

Run:
```bash
python -m src.content_poc samples/SUG_RAW/TV_ZC/BN68-20834D-00_SUG_Y25 TV ALL_ZC_L02_250710.0.pdf --output-dir outputs/content_poc_review_zc_eng_final_v3
python -m src.content_poc samples/SUG_RAW/TV_ZC/BN68-25100A-00_SUG_Y26 TV ALL_ZC_L02_251222.0.pdf --output-dir outputs/content_poc_review_zc_eng_final_v3
python -m src.content_poc samples/SUG_RAW/TV_ZC/BN68-25100B-00_SUG_Y26 TV ALL_ZC_L02_260122.0.pdf --output-dir outputs/content_poc_review_zc_eng_final_v3
```

- [ ] **Step 2: Verify each workbook name is unique and timestamped**

Expected pattern: `BN68-..._ZC_L02_ENG_YYMMDD_HHMM_content_review.xlsx`

- [ ] **Step 3: Commit**

```bash
git add outputs/content_poc_review_zc_eng_final_v3 src/content_poc.py src/text_extractor.py tests/test_content_poc.py tests/test_cover_poc.py
git commit -m "fix: refine zc navigation and workbook naming"
```

