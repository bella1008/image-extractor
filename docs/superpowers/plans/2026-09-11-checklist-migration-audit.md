# Checklist migration audit implementation plan

User direction: proceed carefully because checklist migration changes review decisions.
Execute inline. Keep all writes in xml-review-v2 and preserve the original v1 master.

## Acceptance boundary

Build a reproducible audit and a non-active v2 master draft first. Do not connect a
draft DB to automatic Pass/Fail evaluation before resolving
legacy structural constraints and matching behavior. All 547 original rows and
17 source fields must survive a reversible mapping. Approval and migration
verification are separate states; no row becomes verified in this milestone.

Observed source: main master Excel/JSON match the recovery hashes at commit
`4b001ff9a1a4f8ef91bed75a8ab314f4189d9476`. The frozen exporter trims scalar cells,
normalizes scope aliases and splits scope/exclude_scope/language. Reproduce those
rules only for the v1 synchronization check; preserve original cell text in the draft.

User clarification on 2026-09-11: source_token records where a candidate was extracted.
Manually authored rules may be blank. Rename it source_reference_token, preserve
blanks, and never use it as an applicability filter. v1 `ChecklistRule` does not load it.
`metadata_matches` uses scope/exclude_scope against region and PDF source_token,
plus language/doc_type. Report the hypothetical narrowing if the source_token
column is treated as an additional restriction. Do not introduce that restriction.

## Steps

- [x] Write focused tests for exact field/row preservation, duplicate IDs, unexpected
  columns/formulas/types, JSON drift, row order, approval preservation, source-token
  scope narrowing, language/exclusion/doc_type boundaries and non-active draft export.
- [x] Implement `src/checklist_migration.py`: read-only Excel input, v1 JSON sync,
  reversible v2 field mapping, profile applicability inventory, evidence-file audit.
- [x] Implement `scripts/audit_checklist_migration.py`: immutable input hashes before/
  after, fresh output directory, audit JSON and no change to source master.
- [x] Create one draft workbook with Artifact Tool: Summary, Checklist_V2,
  Migration_Audit, Scope_Differences. Use original text values, filterable rows and
  separate pending/excluded migration states. Scope differences are diagnostic.
- [x] Read the produced draft Excel back, compare every mapped value to the original
  Excel, then export non-active draft JSON from that Excel. Never hand-author the
  checklist JSON from Markdown or from a rewritten rule list.
- [x] Independently check v1 sync against the frozen exporter, counts/IDs/statuses,
  source hashes, scope effects and worksheet export round trip. Render all sheets.
- [x] Run focused tests, root suite, compileall for src/tests/scripts and diff checks.
- [x] Record evidence, unresolved choices and continuation instructions. Retain the
  branch/worktree and create a checkpoint commit for the audited draft stage.

Field mapping: status → approval_status; source_token → source_reference_token;
section_heading → legacy_section_heading; block_type → legacy_block_type.
Every other field and row order stays unchanged. These legacy columns preserve
information and are not new v2 selector definitions. Unknown migration compatibility
remains pending; non-approved rows are retained and marked excluded in audit only.

Verification commands:

```powershell
python -m pytest tests/test_checklist_migration.py -q
python -m pytest tests -q
python -m compileall -q src tests scripts
git diff --check
```

Workbook authoring is a development utility using the bundled Artifact Tool. It
does not add a Node dependency to the Python review application's runtime.

Validation: 169 passed, 6 subtests passed; 31 migration tests. Frozen v1 exporter
547-row equality and metadata applicability 39,931-case equality checked separately.
All four saved sheets inspected; full Excel reread/export verified. Artifact Tool
returned exit 1 after saving, cause unresolved; independent saved-output checks pass.
Do not treat the authoring utility as a deployment-ready generator yet.
Independent read-only code review found no Critical/Important checkpoint issues;
the reviewer also reread all 547 source/draft rows and confirmed frozen hashes.
