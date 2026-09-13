# Combined Review Report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Track steps below. User approved implementation; do not request another routine approval.

**Goal:** Create one checked four-sheet ZC observation workbook without changing either original observation or activating the DB.

**Architecture:** Verify and snapshot both completed observations and the same source XML archive. Build a self-contained combined JSON, then a pure display view, then a workbook. Publish a completion receipt last. Existing single-item UI/export remains supported.

**Tech Stack:** Python 3.12, pytest, read-only openpyxl checks, bundled Node/Artifact Tool authoring. Existing isolated worktree `codex/xml-review-v2` only.

## Task 1 — Archive and combined data validation

Files: create `src/review_source_archive.py`, `src/combined_review_model.py`, `tests/test_combined_review_model.py`; change `scripts/prepare_review_report.py` only to retain its public import through the extracted source helper.

- [x] Write model tests first using complete existing test fixtures and a minimal bounded XML archive. Verify RED with `.venv/Scripts/python.exe -m pytest tests/test_combined_review_model.py -q`.
- [x] Move the existing XML metadata parser into `parse_archived_source(report, receipt_bytes, xml_bytes, extraction_bytes)` and retain `load_archived_source(report)` as its checked filesystem wrapper. Existing `scripts.prepare_review_report.load_archived_source` remains available.
- [x] Implement `build_combined_report(checklist, items, source_archive, source_runs)` and `validate_combined_report(report)`. The latter returns the existing checklist view after rebuilding nodes from archived XML. JSON fields: schema_version=`combined-review-report/1`, decision_status=`not_evaluated`, activation_status=`draft_only`, checklist, items, source_archive, source_runs, summary.
- [x] Require source receipt bytes/hash, PDF/XML hashes, entire context, ZC_L02/ENG review scope, exactly one applicable CHK-002 parent, fixed 14 keys/text and unchanged draft states. Validate all node ownership and evidence references for both reports. Reject different or missing identity values rather than normalizing them away.
- [x] Recompute counts from rows. `summary` contains parent_check_count, child_item_count, checklist_evidence_count, item_evidence_count, excluded_count, rule_count. Do not add a combined rule count.
- [x] Test deep-copy/no-mutation, parent absent/duplicate/non-applicable, same-name different hashes, mismatched context, unknown/mismatched nodes, wrong child keys/text, altered summary and archive. Run existing report-view/item suites with the new tests.

## Task 2 — Four-sheet presentation and reusable backend

Files: create `src/combined_review_view.py`, `tests/test_combined_review_view.py`, `scripts/build_combined_review_excel.mjs`; mechanically share the existing authoring body in `scripts/review_workbook_backend.mjs` while preserving `scripts/build_item_review_excel.mjs` CLI. No DB/service/UI edits in this task.

- [x] RED: assert `build_combined_review_view(report)['sheets']` names are exactly Summary, Checklist Results, Item Results, Source Evidence; 11 summary data rows; checklist parents unchanged, child sheet identical to current item view, all evidence retained and linked by parent/key.
- [x] Implement pure view using `validate_combined_report(report)` and `build_item_excel_view(report['items'])`. Schema `combined-review-excel-view/1`, same draft/decision flags as item view. Reuse `_cell` validation.
- [x] Checklist fields: check_id, section_heading, language, required_text, evidence_excerpt, Korean result, description, pdf_pages, reviewer_note. Append Item Results referral only to parent's display description.
- [x] Source Evidence fields: check ID, item key, kind, source text, node IDs, tags, page, XML paths, complete supplementary detail JSON. General rows keep blank item key. General detail retains complete node_details/evidence and remaining context, without duplicating the flat fields already displayed in adjacent columns; item detail retains full window JSON. Untouched originals remain in the combined JSON. No E#### columns or silent truncation.
- [x] Backend takes explicit schema, exact sheet order, output filename and preview config from a trusted wrapper. Preserve literal values, native filters/freeze, exclusive publication, content hash checks, long-row refusal, render/check/export. Use report-specific table names and locate note/result columns by header.
- [x] Run view and existing backend tests; inspect saved cells and rendered ranges during real integration. Separate review of specification and code quality before completion.

## Task 3 — Transactional export, archival read, CLI

Files: create `src/combined_review_service.py`, `scripts/export_combined_review.py`, `tests/test_combined_review_service.py`.

- [x] RED: `export_combined_review(checklist_dir, item_dir, output_dir, node_executable, node_modules)` creates one fresh directory; refusal preserves existing files; `read_completed_combined_review(output_dir)` returns report/json_bytes/excel_bytes without opening old inputs.
- [x] Snapshot each original observation receipt and all its declared files. Use existing readers, strengthen only this new boundary with duplicate-JSON-key, exact artifact set and before/after checks. Snapshot source receipt/XML/report bytes from both sources and require equality of shared identity.
- [x] Store exact original observation JSON and completion JSON strings inside source_runs, with legacy HTML retained internally for old receipt verification. Archive source XML/report/receipt as strings so saved data can rebuild source metadata without historical files. Do not create HTML files.
- [x] Write `review_report.json`, `review_report_view.json`, `review_report.xlsx` using exclusive creation. Invoke bundled backend explicitly, then reuse read-only workbook validator for every saved cell. Publish `review_report_complete.json` last via pending file + no-overwrite link, recheck all snapshots around publication; failure withdraws own receipt and writes `review_report_failed.json`.
- [x] Reader verifies exact three artifacts, all hashes, state, rebuilt combined model/view, workbook full-cell contract and snapshot stability. No partial/failed run can be served.
- [x] CLI: `python -m scripts.export_combined_review CHECKLIST_DIR ITEM_DIR --output NEW_DIR`, explicit Node env overrides as in item exporter; no installer/network/PDF execution.
- [x] Test source/output mutation at generation/publication/read, partial receipts, duplicates, retry refusal, archived source paths removed and malicious formula-looking text. Verify test doubles only replace the external authoring process, not validation.

## Task 4 — Actual sample, documentation, review and checkpoint

- [x] Generate `outputs/combined_review_zc_20260913_r2/` from the two approved prior run folders. Run the spreadsheet operation marker exactly once before first authoring command this turn.
- [x] Confirm 59 parents / 14 children / 40+26 evidence / 488 excluded internal / 547 original rules, no HTML, 12 Summary rows, complete values and preserved item sheet. Inspect every sheet's readable previews.
- [x] Run focused suites, then `$env:PYTHONPATH=(Resolve-Path samples/tagged_pdf_xml_poc/src).Path; .venv/Scripts/python.exe -m pytest tests -q` with real backend env enabled. Run compileall and pip check, independent spec review followed by quality review, fix actionable issues and reverify.
- [x] Update README.md/TODO.md and create `docs/migration/2026-09-13-combined-review-report_kr.md` with command, limitations and actual evidence. Record local Git checkpoint. No merge/push, other worktree changes, DB activation, UI redesign or PC deployment.

## Baseline and execution notes

Baseline focused report-view/item-export suite: 52 passed, 2 optional backend skips. Prior complete root verification: 503 passed. Full root suite will be rerun with both backend variables enabled after implementation.

Initial real generation in `outputs/combined_review_zc_20260913/` correctly failed before authoring: redundant detail JSON and one-path-per-line display exceeded Excel's row-height limit (Source Evidence rows 4/6/7). The failed folder is retained for diagnosis, not served. Preserve information across columns plus compact supplementary JSON, keep all 66 rows, and use a fresh `_r2` result folder. No font shrinking, content truncation or workbook overwrite.

Independent spec review found aggregate-text, empty-leaf-evidence, pending-state and missing-field bypasses. Each was reproduced with coherently re-hashed input snapshots, fixed in the new combined boundary, and covered by regression tests. Existing observation semantics and source DBs were not modified. Final spec review approved Tasks 1–3; final code-quality review and full verification are recorded below when finished.

Final verification: 558 root tests passed, including four real Artifact Tool authoring integrations; 55 added tests. Compileall src/tests/scripts and pip check passed; apps/ does not exist here. Real combined archive reader and every saved cell passed, original input snapshots and existing item sheet unchanged. Ten rendered ranges across four sheets (including longest evidence rows) inspected. Independent final quality review: no actionable findings; 53 non-authoring focused tests independently passed, two real cases intentionally deselected by reviewer because root exercised them. XML POC full suite not rerun. Local checkpoint only; retain worktree and branch, no merge/push/cleanup or business activation.
