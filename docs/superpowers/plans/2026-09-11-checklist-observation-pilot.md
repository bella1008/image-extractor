# Checklist observation pilot implementation plan

> **For agentic workers:** Use executing-plans inline, TDD and independent requesting-code-review before checkpoint.

**Goal:** Connect the frozen checklist draft to bounded ZC ENG XML evidence without issuing business Pass/Fail or changing migration approval.

**Architecture:** A pure observation module builds heading anchors from existing reader evidence and compares one bounded text unit at a time. The CLI validates the original draft Excel/JSON pairing and XML receipt, emits all 547 rules with explicit applicability/unsupported states, and refuses stale or overwritten outputs.

**Tech Stack:** Python stdlib, existing ReviewDocument/text units/migration reader, pytest.

## Decisions within the approved migration design

Whole-document text search would discard legacy heading constraints. Automatically mapping every legacy role to paragraph would broaden review scope. Instead, implement a **provisional observation pilot**, ZC_L02 + A2 + ENG only. This is the next location/matching verification step authorized by the user, not a general runtime activation.

- Preserve every source rule, ID, approval and source_reference_token. Applicability uses the existing scope/exclusion/language/doc_type semantics, never provenance.
- Rules not approved remain excluded; out-of-scope rules remain not_applicable. Applicable rules ALWAYS remain needs_review and migration_status=pending.
- For heading/body/bullet, retain the legacy constraint in the report and label the proposed v2 selector provisional. Other structural types or methods have explicit unsupported reasons and are not searched.
- Normalize whitespace only for comparison. Do not lowercase, remove hyphens/punctuation, discard non-ASCII, translate, split required_text, or join separate units.
- Heading anchors use reader `review:heading-evidence`, exact observed text and XML path/source role. Preserve source_role_candidate versus confirmed/promoted classification; never promote candidates.
- A duplicate, unsafe, missing or language-ambiguous heading cannot yield a positive observation.
- Heading scope ends at the next observed heading (even a deeper heading), enclosing section end or first incompatible text-language occurrence. This pilot deliberately does not claim descendant-section coverage.
- Select heading itself, non-table paragraph, or non-table list_body beneath list_item. Table units are not searched by body/bullet rules. Unknown/visual/unsafe units remain visible in rejected evidence.
- Store raw expected/observed text, normalization policy, source unit IDs, heading/boundary evidence, page/XML/MCID evidence and reasons. A literal match is evidence_found, not Pass; no selected literal match is not_found_in_selected_units, not Fail.
- The producer loads the committed draft Excel and its derived JSON and checks equality/hashes; it never rewrites either. All entry input hashes are rechecked before writing.

## Tasks

- [x] Create `tests/test_checklist_observation.py`: scope duplicate/missing/boundary and source-candidate tests, metadata/provenance invariance, no cross-unit/table/language search, unsupported-rule retention, no approval change, strict punctuation/Unicode preservation.

```python
report = observe_checklist(document, [rule])
assert report['rows'][0]['status'] == 'needs_review'
assert report['rows'][0]['observation'] == 'evidence_found'
assert report['decision_status'] == 'not_evaluated'
```

- [x] Confirm tests fail for missing API, then implement `src/checklist_observation.py` using `build_text_unit_index`, reader heading evidence and existing audit applicability semantics.
- [x] Add checked-bundle integration tests for producer, draft JSON/Excel drift, input changes and existing output refusal. Missing-receipt refusal is covered by the checked-bundle inventory integration test using the same reader boundary. Implement `scripts/run_checklist_observation.py` after expected failures. Keep source DB unchanged.
- [x] Run ZC real completed bundle. Independently verify every row's applicability against frozen legacy metadata_matches, every reported match against its original XML node/heading/paragraph, and all547 IDs/state preservation.
- [x] Run focused and root tests, compileall src/tests/scripts, diff check. Have independent reviewer check false-positive paths.
- [x] Record Korean result examples, exact limitations and next steps; retain v2 worktree and commit checkpoint without merge.

Verification: root230 passed +6subtests; focused69. Actual ZC ENG59applicable:
28literal observations,9not found in selected units,21unsupported structures,1missing
heading scope. All547source rows retained; frozen old metadata_matches agrees on
every rule. Candidate headings remain candidates. Independent review identified
cross-unit heading anchoring; reproduced with nested paragraph and empty unsupported
descendants, fixed atomic whole-heading coverage, and rereview cleared important findings.
Regenerated report is byte-identical to independently checked initial report.
