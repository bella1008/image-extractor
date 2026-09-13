# Combined PDF execution and viewer implementation plan

> Execute in the existing isolated xml-review-v2 worktree using test-driven development and verification-before-completion. User has authorized continuous implementation; review checkpoints are internal unless a business choice is required.

**Goal:** One PDF execution produces one combined result folder that a local viewer can validate and download.

**Architecture:** Reuse checked observation services and combined report validation. Separate the fresh-directory wrapper from the exporter body so the workflow can own the output directory. Preserve old reader contracts and add JSON-only checklist completion v2.

**Tech stack:** Python, pytest, Streamlit AppTest, existing Artifact Tool workbook backend.

## 1. Explain the standard document

- [x] Write `docs/architecture/review-document-explained_kr.md` with flow, responsibilities, examples and human review boundaries.
- [x] Link from README and architecture reference; record progress in TODO.

## 2. JSON-only checklist runs and combined execution

- [x] Add `tests/test_combined_review_run.py`. Real observation services consume `checked_bundle`; replace only extraction I/O and workbook authoring for focused tests. Assert report counts 59/14, matching receipt hashes, no HTML, reuse zero extractions, fresh input one extraction, existing output preserved, changed PDF and failed child blocked.
- [x] Run `.venv/Scripts/python.exe -m pytest tests/test_combined_review_run.py -q` and confirm missing feature failures.
- [x] Add `ReviewRequest.include_html=True`; false writes `review-observation-run/2` with only observation.json. Reader accepts exact artifact sets by version. Update combined source capture/validation to accept both.
- [x] Separate `export_combined_review` fresh-directory wrapper and `_export_into_reserved_directory` body. Add workflow-lock checks to archival reader.
- [x] Implement `src/combined_review_run.py`: frozen request, reserve folder, workflow lock, snapshot PDF/mapping/DB sources, extract once or reuse bundle, call both services into `_internal`, export into root, recheck inputs before removing lock; on exception retain failure record and withdraw completion.
- [x] Add `scripts/run_combined_review_v2.py` with PDF/output/bundle/mapping/draft/master/node options. Preserve environment defaults from the current combined CLI.
- [x] Re-run new tests and existing combined/checklist/item service tests.

## 3. Local viewer

- [x] Add `tests/test_combined_review_ui.py`: AppTest starts empty; real combined fixture shows 59/14 rows and two downloads; changed/missing files and changed path remove results; deferred download checks current bytes.
- [x] Confirm tests fail before adding `scripts/combined_review_app.py`.
- [x] Build thin UI with a single folder input, fixed labels, plain source text, separate counts and two tables. Use the verified presentation view and exclude reviewer notes from read-only tables. No raw source Markdown rendering.
- [x] Reuse launcher by adding an explicit `--combined` switch; existing default item app remains unchanged. Validate launcher routing and localhost binding.
- [x] Run focused UI tests, then root suite and compileall for existing src/tests/scripts.

## 4. Real output and review

- [x] Run actual ZC PDF via the new command with existing workbook backend. Verify report integrity and original extraction XML/MD equality to prior confirmed run. Verify new UI with AppTest against real output.
- [x] Request independent code review; address correctness findings with regression tests.
- [x] Document exact commands, output path, tests and remaining human validation. Keep work on this branch without merge or publication.
