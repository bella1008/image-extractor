# Item master draft and export implementation plan

> **For agentic workers:** Use subagent-driven-development for implementation and two-stage review. Preserve the isolated v2 worktree.

**Goal:** Provide a separate editable CHK-002 parent/14-child Excel authoring draft and a fail-closed Excel-to-JSON export, without activating rules or changing frozen DBs.

**Architecture:** A verified proposal supplies immutable source fields and evidence. Excel owns editable proposed model rules, supporting references and reviewer notes. The exporter preserves those proposals separately from source observations and always emits draft-only, unknown-applicability data. Parent is lineage, not a second executable requirement. This is a one-parent pilot, not a replacement for the 547-row DB.

**Tech Stack:** Python/openpyxl read-only exporter and pytest; bundled Artifact Tool for authoring only.

## Contract

- Stable identity is parent check_id + item_key, never XML node ID or Excel row number.
- Keep the entire original 17-field parent, all 14 source wording slices, actual XML text, quantities, parentheticals, source markers and 12 condition associations.
- Source evidence belongs to the exact PDF/XML hashes. No inference that unstarred items are unconditional.
- Editable fields: proposed_model_rule, proposal_evidence, reviewer_note. These are human proposals, never executable expressions or approvals.
- Keep condition_state=unverified and model_applicability=unknown even when a proposed rule is filled in. Do not expose an approved switch in this milestone.
- Missing/duplicate/extra item keys, unknown sheets/columns, formulas/errors, source text or provenance changes must stop export. Row reordering may be accepted using stable keys. No whitespace normalization of source text.
- Workbook and verified seed must be checked before and after reading. Export to a fresh file atomically; no overwrite or partial published JSON. Pin seed hash externally in the export command. Hashes detect accidental change, not authenticate business approval.
- Preserve frozen Excel/JSON and active ReviewService. No GridCell imports or Markdown parsing.

## Task 1 — Python contract and exporter

Files: src/checklist_item_master.py, scripts/export_item_master.py, scripts/prepare_item_master.py, tests/test_checklist_item_master.py.

- [x] Write failing tests for source-preserving workbook tables, editable-field round trip, draft-only output, malformed inputs and no-overwrite publication.
- [x] Run `.venv/Scripts/python.exe -m pytest tests/test_checklist_item_master.py -q`; confirm missing functionality fails.
- [x] Implement `build_master_seed(proposal)` and strict workbook-table validation; reuse checked proposal generation for preparation. Seed includes sheet headers/records so the builder and exporter share one contract.
- [x] Implement `export_item_master(workbook, seed, output, expected_seed_sha256=...)`; read Excel with data_only=False, reject formulas/errors, retain all source fields, validate stable keys and publish through exclusive atomic linking.
- [x] Rerun focused tests and obtain independent spec and quality review.

## Task 2 — Author the real master and validate

Files: scripts/build_item_master.mjs; metadata/checklist_v2/item_master_drafts/20260911/; outputs/item_master_20260911/.

- [x] Generate seed from the completed ZC run and actual source PDF with existing checked proposal logic.
- [x] Build one Excel file from seed sheets using bundled Artifact Tool. Make editable fields amber, source fields neutral, provide concise Korean instructions, filters and stable-key freeze panes.
- [x] Render every sheet and inspect saved cells. Validate all parent, item and evidence values through exporter.
- [x] Demonstrate permitted notes round trip and invalid source edits fail in automated tests, preserving unknown applicability.
- [x] Save versioned seed/master/generated JSON separately from the frozen DB. The source of exported JSON is Excel, not hand-written rules.

## Task 3 — Verify and hand off

Files: TODO.md, README.md, docs/migration/2026-09-11-item-master_kr.md.

- [x] Run full `.venv/Scripts/python.exe -m pytest tests -q` and compileall for src/tests/scripts.
- [x] Recheck original master Excel/JSON hashes. Explain pilot versus full DB and editable versus source fields, with exact CLI usage.
- [x] Save a scoped Git checkpoint, keep worktree and do not merge or remove old code.

Baseline: 5949efabccbb595b32e64fda6ccf35365098b192, clean isolated worktree; 333 tests passed before implementation.

Execution record: new focused tests 29 passed; combined proposal/master 46 passed; full root v2 suite 362 passed in 41.43s. Compileall src/tests/scripts passed; apps absent. Separate XML POC suite not rerun because extraction code unchanged. Independent spec and final quality reviews found no blocking issues. Real seed independently reproduced from checked XML/PDF/frozen Excel. Every saved cell matched the seed except the explicitly editable fields; initial editable fields are blank. All five sheets rendered and inspected; Items C2 / other sheets A2 panes, filters, amber input fields verified. Original legacy master XLSX/JSON hashes unchanged. No runtime activation, merge, or worktree cleanup.
