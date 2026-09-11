# Item observation service implementation plan

> **For agentic workers:** Use subagent-driven-development and test-driven-development; independently review specification and code quality before checkpointing.

**Goal:** Connect the approved CHK-002 item master to fresh XML evidence searches, producing an independently completed JSON/HTML run with no business approval.

**Architecture:** Validate the Excel-derived draft against the pinned seed and current Excel, then rebuild the 14 stable item definitions. Search the target ReviewDocument through the existing bounded item-observation logic. Separate historical master evidence from new target evidence. A dedicated service/CLI is additive to the existing 547-row service.

**Tech Stack:** Python 3.12, existing XML adapter/gate, read-only Excel validation, pytest, escaped offline HTML.

## Approved scope and decisions

This implements the already approved item-review design and user's instruction to continue technical connection without routine confirmation. No new model rules or business approvals are inferred.

- ZC_L02 / A2 / ENG CHK-002 pilot only. Unsupported document profiles fail closed.
- Validate draft JSON by reproducing the existing Excel export and comparing the complete payload. Pin seed SHA256 `2229a46be82d9f7b3a6aa316c079eea93f15481050d2e44020c850ddfc73e268` independently of input files. Reject hand-edited or stale JSON, changed Excel/seed, missing/extra/duplicate items and activation changes.
- Search current XML, never the master source evidence/node IDs. Exact whole list-body comparison with existing whitespace/leading-source-asterisk policy; do not mix Power Box with Power Box Cable or Remote Control with Standard Remote Control.
- Each row keeps source_check_id, item_key, required_text, current candidates/condition_candidates, result=needs_review, description, model_applicability=unknown, condition_state=unverified, author_proposal (the three inert editable fields).
- Internal observation distinguishes found (one candidate), ambiguous (multiple), not_found (zero within an examined scope), and not_examined (unusable heading/scope). None is an operational Pass/Fail. Scope failure is not missing wording.
- Summary counts 14 children only, not the historical parent. Keep original parent identity/source for lineage, not a fifteenth requirement. Preserve the existing 547-rule results.
- Report contains target_source (current PDF/XML hashes and receipt reference) separately from master_source (historical source metadata). All displayed node IDs and condition text come from the current target.
- Fresh output directory; write JSON and escaped offline HTML; revalidate inputs and exact output bytes before publishing a completion receipt atomically. Keep failed directories for diagnosis; consumers reject incomplete, failed or changed artifacts.
- No XLSX authoring, source extraction changes, Markdown parsing, new legacy GridCell imports, UI deployment, DB activation or old code deletion.

## Task 1 — Checked item connection and execution

Files: `src/item_review.py`, `src/item_review_service.py`, `scripts/run_item_review_v2.py`, `tests/test_item_review.py`, `tests/test_item_review_service.py`. Small tested reuse/refactor of `src/checklist_item_master.py` is allowed only if necessary to avoid duplicate validation.

- [x] Write failing tests for fresh target evidence, missing/duplicate matches, unsupported/missing headings, stable keys and unchanged proposals/unknown applicability.
- [x] Run `.venv/Scripts/python.exe -m pytest tests/test_item_review.py tests/test_item_review_service.py -q` and record expected missing-feature failures.
- [x] Implement `load_checked_item_master`, `observe_item_master`, `ItemReviewRequest`, `run_item_review`, `read_completed_item_review` and CLI. Reuse existing exporter, item proposal observer and XML gate; implement tested completion publication in the dedicated service without changing the legacy service.
- [x] Test full input integrity, source/target distinction, changed-input races, failed render, incomplete/mutated output rejection and no-overwrite behavior. Real checked ZC baseline yields 14 found/12 condition-linked items with 14 needs_review.

## Task 2 — Offline result rendering

Files: `src/item_review_report.py`, `tests/test_item_review_report.py`.

- [x] Write failing renderer tests for result+description, all item rows, current source panel, historical source separation, empty evidence, exact text, author proposals labeled as inert, and HTML escaping/no remote resources.
- [x] Implement `render_item_review_html(report)` with a compact summary, item result table and per-item current evidence details. Keep whitespace with CSS and do not link arbitrary text as URLs.
- [x] Rerun focused tests. Generate a real report and record the explicit visual limit: browser policy blocked local-file navigation; no workaround attempted, actual visual sign-off remains pending.

## Task 3 — Verification and checkpoint

Files: `docs/migration/2026-09-11-item-observation-service_kr.md`, `README.md`, `TODO.md`.

- [x] Run one new PDF extraction end-to-end and one checked-bundle reuse; compare XML/MD bytes to the preserved baseline and compare target item results across modes.
- [x] Obtain independent spec review, fix any findings, then code quality review. Both reviewers reported no required fixes and independently ran 73 focused tests.
- [x] Run focused tests, full root suite, and compileall for existing src/tests/scripts directories. Recheck original DB and item-master hashes.
- [x] Document executable commands, current support, source versus target evidence, results and remaining approval boundaries. Save a scoped Git checkpoint and retain this worktree without merge.

Baseline: `e1a6f3c5abeb55293505c7efe4a49d7185aae8f5`; clean isolated `codex/xml-review-v2`.

Execution evidence (2026-09-11): baseline 362 root tests passed; final 435 root tests passed in 57.23s; 73 focused item tests passed independently; compileall passed. Renderer RED: 12 missing-module failures, then corrected a multiline return concatenation defect and an overbroad escaping-test assertion; final 12 renderer tests passed. Real fresh/reuse reports agree on every item, 14 found / 12 condition candidates / 14 needs_review. Independent spec reviewer reproduced every item from each checked XML and reported no required fixes. Original main DB, frozen 547-row draft, item master and extractor remain unchanged. New artifact paths and visual limitation are recorded in the Korean execution guide.
