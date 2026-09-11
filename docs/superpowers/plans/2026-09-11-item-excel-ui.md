# Item result Excel and local UI implementation plan

> **For agentic workers:** Use subagent-driven-development and test-driven-development. Independent specification review precedes quality review.

**Goal:** Present the checked CHK-002 observation in a fresh result workbook and a small local Streamlit viewer, without changing decisions or the source DB.

**Architecture:** A pure display contract converts the already completed observation into Summary, Item Results and Source Evidence matrices. Artifact Tool writes the workbook; Python verifies every saved value and publishes an export receipt last. A thin Streamlit viewer calls checked readers and offers verified downloads; it never runs business rules or edits the authoring master. The existing PDF CLI remains the execution entry point in this first UI connection.

**Tech Stack:** Existing Python 3.12 environment, read-only openpyxl validation, bundled Artifact Tool/Node for workbook authoring, separately pinned Streamlit UI dependency.

## Scope and approved design

User approved continuation to result Excel and the user screen, using the prior approved `2026-09-11-item-review-and-evidence-display-design_kr.md` and Excel inventory. No repeated approval gate is needed for the already agreed result/description, source panel, stable item keys and current XML evidence. Three alternatives considered: importing legacy exporter (unnecessary coupling), rebuilding the whole app (too broad), additive checked result writer and thin viewer (selected).

- Existing 547-row service, extractor/Markdown, DB and item master remain unchanged.
- Only completed 14-item ZC ENG observations can be presented. No pass/fail, model approval, source edits or uploaded executable content.
- Summary preserves typed counts, current PDF/hash/receipt context, and a separate historical master-source section.
- Item Results uses stable key, exact required text, `검토 판정`, `설명`, current item evidence refs, current condition refs, and blank report reviewer note. No duplicate observation/reason user columns, no fifteenth parent row. Historical author notes are labeled separately from blank report notes.
- Source Evidence has one row per item/candidate association, with exact text, stable item key, kind, current node IDs/tags/pages, XML paths and full evidence JSON. Candidate text is not collapsed or silently clipped. Reject Excel-unrepresentable cells.
- Preserve blue D9EAF7 headers, amber FFF4CE pending/comment fields, filter and frozen headers, wrapped long text. No empty legacy sheets or business formulas.
- Use a new output directory, preserve source run, snapshot it before and after export; saved XLSX must exactly match the display contract, contain no formulas or external links, and have required sheets/panes/filter. Publish a receipt last; incomplete/changed outputs are rejected by the consumer.
- Authoring uses the bundled tool currently available on this workstation; its Node/module paths are explicitly configured, not silently downloaded or hardcoded to Bella. Lack of authoring runtime must not stop reading/downloading a previously completed workbook. Python-only report generation on colleague PCs is a separate deployment dependency decision, not claimed complete here.
- UI reads a user-entered completed run folder and an optional completed Excel export folder. No startup auto-run, no arbitrary HTML execution, no DB editor, no file deletion. Failed/mutated input clears stale results/downloads. Bind launcher to 127.0.0.1 and disable usage statistics; no public deployment.

## Task 1 — Excel view and checked export (main)

Files: `src/item_review_excel.py`, `scripts/build_item_review_excel.mjs`, `scripts/export_item_review_excel.py`, `tests/test_item_review_excel.py`.

- [x] RED: assert new `build_item_excel_view(report)` yields exactly three sheets, 14 item rows/26 evidence rows, exact current text/metadata, source separation and unchanged input; activated/oversize/illegal text rejected.
- [x] GREEN: create ordered scalar matrices with explicit header/width metadata. Use current candidate owner/part evidence only, retain complete evidence JSON, and keep counts numeric.
- [x] RED: `export_item_review_excel(run_dir, output_dir, node_executable, node_modules)` refuses stale source, existing output, failed authoring, malformed workbook, formulas and content mutation. `read_completed_item_excel(output_dir, run_dir)` rejects mismatched source receipt and modified bytes.
- [x] GREEN: run public Artifact Tool builder with argument list (no shell), validate saved workbook read-only, snapshot bytes, publish receipt last. Builder writes `.pending.xlsx` and exclusive link, recalculate/inspect/render each sheet, no automatic business decision.
- [x] Verify real completed source and render all three sheets. Compare all cells and preserve source hashes. Run `.venv/Scripts/python.exe -m pytest tests/test_item_review_excel.py -q`.

## Task 2 — Thin result screen (agent, alongside Excel work)

Files: `src/item_review_ui.py`, `scripts/item_review_app.py`, `scripts/start_item_review_ui.py`, `requirements-review-ui.txt`, `tests/test_item_review_ui.py`.

- [x] RED: completed reader errors never leave previous report/downloads, current/historical source distinguishable, 14 result/description rows, safe text display, no author proposal execution. Use actual checked fixtures where possible and official Streamlit AppTest.
- [x] GREEN: `load_item_review_screen(run_dir, excel_dir=None)` validates observation and optional Excel then returns `{report,json_bytes,html_bytes,excel_bytes}`. Revalidate source/output snapshots around every load, never trust stale session cache. UI loads only on request; current folder changes require reload; errors clear prior results. Show current source, metrics, table and collapsible raw evidence as text/JSON. Offer downloads only from checked bytes; Excel failure is explicit, not a stale download. Viewer need not run Node.
- [x] GREEN: launcher uses `sys.executable -m streamlit run ... --server.address 127.0.0.1 --browser.gatherUsageStats false`, no shell, optional port with validation. Pin separate UI dependency after installing/testing only in v2 .venv.
- [x] Verify `.venv/Scripts/python.exe -m pytest tests/test_item_review_ui.py -q` including AppTest. No extraction or authoring logic inside screen.

## Task 3 — End-to-end verification and checkpoint

- [x] Independently review specification, then quality, fix required findings with regression tests.
- [x] Run full root tests and compileall existing src/tests/scripts directories. Recheck original/main DB, frozen draft, item master, completed source.
- [x] Document commands, result workbook, read-only screen and dependencies/limits in `docs/migration/2026-09-11-item-excel-ui_kr.md`, README and TODO. Do not imply full deployment or final visual approval.
- [x] Save scoped Git checkpoint on existing codex/xml-review-v2; no merge, remote push or other worktree edits. This plan is included in that checkpoint; resolve its commit with `git log -1 --format=%H -- docs/superpowers/plans/2026-09-11-item-excel-ui.md`.

Final verification (2026-09-11): full root suite **492 passed in 104.92s**, including both real Artifact Tool integration tests. New coverage: Excel 32 and UI 25 tests. Compileall and pip check passed. Specification and quality reviewers approved after malformed receipt/report regression fixes. Real saved workbook cells and six rendered regions across three sheets were checked; actual completed-source AppTest showed 14 rows and three checked downloads. This is not browser visual sign-off or full PC deployment. Source DB, frozen draft, item master and extraction code were preserved.

Baseline: `c4b455ebbfc1a3c2f249de94aca36c04b8cd857c`; clean isolated linked worktree, existing v2 environment. Prior local-file browser policy denial remains in effect; do not bypass it to view old HTML. New Streamlit behavior is checked with its supported AppTest API; browser visual sign-off is separate.
