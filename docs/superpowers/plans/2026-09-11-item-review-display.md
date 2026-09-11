# Item Review and Evidence Display Implementation Plan

> **For agentic workers:** Use subagent-driven-development for the independent report mapping task and TDD for every behavior change. The user approved the design and requested continuous execution, so do not insert routine approval pauses.

**Goal:** Produce an item-level CHK-002 migration proposal and a revised, source-traceable report without activating the DB or changing source extraction.

**Architecture:** Preserve the checked observation snapshot and its original 547 rules. A pure report mapper owns human descriptions and source references. A separate item proposal model stores explicit stable keys and exact source slices; no generic newline-to-requirement conversion or automatic condition approval.

**Tech Stack:** Python/pytest, immutable checked XML bundle, frozen Excel-exported JSON, development-only Artifact Tool workbook builder.

## Task 1: Concise report mapping (independent implementer)

Files: `src/review_report_view.py`, `scripts/prepare_review_report.py`, `tests/test_review_report_view.py`, focused additions in `tests/xml_v2/test_xml_adapter.py`.

- [x] Write failing tests asserting `observation` and `reason` are absent from displayed columns, `description` retains found/candidate/fragment/unsupported distinctions, results stay needs_review, and original report equals its deep copy.
- [x] Add `build_report_view(report, *, document=None, source=None)` support. Preserve diagnostics and summary counts outside displayed columns. With a document, map parts/owners and existing visual references to real node type/ID/evidence. Reject unknown IDs rather than invent tags. Without one mark enrichment unavailable.
- [x] Enrich `prepare_view` using the completed snapshot's recorded receipt and hashed semantic XML/extraction report. Validate those bytes before use, recover the source filename from the checked extraction report, and verify receipt/inputs did not change while mapping. Keep snapshot reader semantics unchanged. Tests: corrupted XML/receipt/report, missing source, same filename different hash, changed completion, original frozen values.
- [x] Run `python -m pytest tests/test_review_report_view.py tests/xml_v2/test_xml_adapter.py -q`, report red/green evidence, then spec and quality review. Parent owns workbook builder and does not share these edits.

## Task 2: Item proposal and source audit (parent)

Files: `src/checklist_item_proposal.py`, `tests/test_checklist_item_proposal.py`, `scripts/prepare_item_proposal.py`.

- [x] Write failing tests for explicit keys and exact source character slices: reconstruction includes untouched separators; preserve quantities/conditions/scope; duplicate keys, gaps, overlapping slices and approval attempts fail. Input order is not the stable key. One source rule may map to multiple items, each with multiple evidence nodes.
- [x] Implement a non-runtime proposal builder. Require original Excel-exported parent rules, store immutable original parent text and all source fields, store source offsets and exact item text, keep proposal_state pending and condition_state unverified. Candidate evidence is separate from business applicability.
- [x] Inspect actual ZC ENG XML package scope and create an explicit 14-item manifest using source wording, not generated runtime translations. Compare within checked heading/language boundaries; retain all candidate source references and quantity/condition warnings without approving them.
- [x] Generate a read-only structural inventory over all frozen rules: item-list split candidates, table-method/structure candidates, others requiring definition. Label mechanical categories as triage, never business decisions.
- [x] Verify original source digests and all 14 slices against frozen parent. Generate a separate proposal JSON/artifact input, not a hand-edited runtime checklist JSON. CLI refuses existing output and verifies source snapshot changes.

## Task 3: Revised workbook and integration

Files: `scripts/build_review_report_prototype.mjs`, docs/migration guide, `TODO.md`.

- [x] Update the existing development builder for view v2, Korean 판정/설명 headers, metadata source panel, node IDs/types/pages. Use summary counts from preserved diagnostics, not a removed column. Add item proposal as a distinct review area; do not double-count child rows in the original rule totals.
- [x] Create one new workbook with the approved report display and CHK-002 proposal detail. Retain original workbook. No runtime XLSX dependency changes.
- [x] Recalculate, inspect, render every changed sheet and verify all exported cell values, source hashes, exact strings, filters/panes, formula caches and pending states.
- [x] Independent spec review then quality review; repair important findings with regression tests. Run full root tests and compileall, recheck original DB digests, document actual limitations and save a separate v2 recovery commit.

## Acceptance boundaries

No DB activation, no changed approved wording, no inferred mandatory items/model conditions, no GridCell fallback, no source XML/MD edits, no main worktree edits. If a real item condition decision is necessary, collect the exact evidence into the proposal instead of inventing it. Producing the non-active proposal does not require that decision first.

## Execution record

Tasks 1–3 implemented and independently reviewed. The code/test/real-source steps above are complete; no DB activation was attempted. The source slices are proposal records and not a finalized editable Excel master. Creating that master and its Excel→JSON activation path remains a separate milestone.

- Baseline: clean codex/xml-review-v2 at c6f8535, 285 tests passed.
- TDD: missing item module/runner reproduced before implementation; 17 item tests pass, including real 14-item/12-star case and source mutation before/during publication.
- Spec review found unrelated existing owner IDs were accepted in report mapping. Seven red regression cases reproduced it; actual ownership validation fixed them. Independent re-review passed.
- Final v2 full suite: 333 passed. Report/archive focused suite: 89 passed. compileall passed.
- Workbook: six sheets rendered; 59 checklist, 40 evidence, 488 excluded, 14 item and 547 inventory rows fully reconciled. Summary source hashes and cached count59 verified. Existing workbook and original master preserved.
- Final inputs: outputs/review_item_layout_20260911/report_view_verified.json and item_proposal.json. Output: same folder/review_report_prototype.xlsx.
- Independent spec and quality reviews found no remaining important actionable issues. Save only this worktree's recovery commit; no merge/push/deployment.
