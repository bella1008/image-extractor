# Python review delivery implementation plan

> **For agentic workers:** Use executing-plans task by task. Existing user authorization covers implementation in the current isolated xml-review-v2 worktree.

**Goal:** Generate the current combined review workbook on Python-only reviewer PCs and prepare a portable pilot ZIP.

**Architecture:** A presentation writer consumes the existing v2 view. The existing service owns source validation and completion publication. UI/CLI default to Python; explicitly configured Node calls remain compatible. A bounded release builder includes only runtime dependencies and frozen metadata.

**Tech Stack:** Python 3.12, openpyxl 3.1.5, Streamlit 1.63.0, unchanged tagged PDF XML package.

## 1. Writer

- [x] Add `tests/test_combined_python_workbook.py`: exact cells/types, 4 sheets, Summary12, panes/filters/widths, literal formula text, empty evidence, invalid cells/height, no overwrite and changed input rejection.
- [x] Observe failures before implementation: `.venv/Scripts/python.exe -m pytest tests/test_combined_python_workbook.py -q`.
- [x] Implement `src/combined_review_workbook.py`: `write_combined_workbook(view_path, output_dir, expected_hash)` validates view, writes strings explicitly as strings, formats from the current contract, stages output and publishes without overwrite.
- [x] Route `combined_review_service._run_builder` to Python when both Node arguments are omitted. Keep source/receipt validation in the existing service.

## 2. Runtime entry points

- [x] Default `CombinedReviewRequest.node_executable/node_modules` to None, remove UI dependence on local developer environment variables, make CLI Node flags optional as a pair.
- [x] Verify UI input with no Node, full real Python service output, CLI error for incomplete Node pair, and historical saved workbook reads.
- [x] Preserve report/view JSON and test existing workflow failure guards.

## 3. Delivery

- [x] Add `scripts/build_review_pilot.py`, a local ZIP builder using runtime import closure and explicit data files; exclude Git, legacy GridCell entry points, PDFs, outputs, caches and Node.
- [x] Add Python 3.12 local setup/start scripts and Korean instructions under `deployment/review-pilot/`.
- [x] Verify ZIP content, source hash identity, no overwrites, missing inputs, and relocation into a Korean/spaced folder.
- [x] Run a real ZC PDF through the relocated package, validate the report, compare retained text and row values, and run UI AppTest.

## 4. Handoff

- [x] Compare Python workbook against `outputs/checklist_reviewer_zc_20260914_v2/review_report.xlsx`; inspect rendered affected sheets.
- [x] Run focused tests, compileall src/tests/scripts (apps absent), pip check, diff check.
- [x] Update README/TODO and deployment evidence with commands, ZIP location, limitations and test results; preserve the original baseline commits.
