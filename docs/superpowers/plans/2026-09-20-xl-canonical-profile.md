# XL Canonical Profile Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Register the source-verified XL profile in canonical metadata and prove the existing XL extractor can produce a lossless ReviewDocument from the real PDF.

**Architecture:** Add one `XL_ENG` row to the canonical JSON and its CSV/XLSX human-review mirrors. Remove the now-redundant extraction-only override, then run profile lookup, real-PDF XML extraction, semantic-preservation, receipt, and regression checks. Keep the user's `samples/SUG_RAW` folder reorganization outside this change.

**Tech Stack:** Python 3.12+, pytest, JSON/CSV, `@oai/artifact-tool`, tagged PDF XML extractor, ReviewDocument adapter.

---

### Task 1: Lock the XL profile contract with a failing test

**Files:**
- Modify: `tests/xml_v2/test_integrated_extractor.py`

- [x] Add a test that loads `XL_ENG` from the canonical repository and asserts `INDIA`, buyer `XL`, language `ENG`, `A3`, and one language.
- [x] Run the focused test and verify it fails because `XL_ENG` is absent.

### Task 2: Register XL in every canonical metadata representation

**Files:**
- Modify: `metadata/pdf_profile_mapping/pdf_profile_mapping.json`
- Modify: `metadata/pdf_profile_mapping/pdf_profile_mapping.csv`
- Modify: `metadata/pdf_profile_mapping/pdf_profile_mapping.xlsx`
- Modify: `samples/tagged_pdf_xml_poc/config/review_profile_overrides.json`

- [x] Insert the alphabetically placed `XL_ENG` row with `region=INDIA`, `buyer_codes=XL`, `languages=ENG`, `doc_type=A3`, and `language_count=1`.
- [x] Preserve the XLSX sheet, styles, dimensions, and existing cells while extending the data by one row.
- [x] Remove the temporary XL extraction-only override and keep the override file valid.
- [x] Run the focused profile test and verify it passes.

### Task 3: Prove the existing XL extractor and adapter end to end

**Files:**
- Modify: `tests/xml_v2/test_integrated_extractor.py`

- [x] Add a real-PDF test that locates the XL PDF recursively, extracts XML/Markdown, creates ReviewDocument, and checks profile context and semantic preservation.
- [x] Run the test against the registered profile and make no extractor/adapter behavior change because the existing implementation passes.
- [x] Run `scripts/audit_xml_integration.py --tokens XL_ENG` into a new evidence folder and require `technical_pass`.

### Task 4: Update status and evidence without granting human approval

**Files:**
- Modify: `TODO.md`
- Modify: `docs/migration/2026-09-20-xml-integration_kr.md`
- Modify: `docs/migration/buyer-language-validation-ledger_kr.md`
- Create: a dated XL integration evidence JSON/output folder under `outputs/`

- [x] Record that canonical registration and technical preservation passed.
- [x] Keep XML extraction technical verification separate from human PDF/content approval.
- [x] Do not claim checklist-agent support for XL; this task validates extraction and ReviewDocument only.

### Task 5: Run regression and scope checks

**Files:**
- Test only; no unrelated sample-folder edits.

- [x] Compare JSON, CSV, and XLSX row values and ordering.
- [x] Inspect and render the changed XLSX range; confirm the added row matches existing formatting.
- [x] Run focused XML v2 tests, relevant profile/extractor tests, the root test suite, and compileall for the existing source/test/script trees.
- [x] Confirm the XL change does not modify or stage the user's existing `samples/SUG_RAW` reorganization.
