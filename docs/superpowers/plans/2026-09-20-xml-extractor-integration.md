# XML extractor integration and regression plan

**Goal:** Integrate the verified XML extractor into v2 without losing source evidence, weakening gates, or changing checklist business approval.

**Execution:** Work inline in the existing v2 worktree. User authorized integration and verification. Do not modify the source XML worktree, delete legacy code/worktrees, change the master DB, or push remotely in this task.

**Baseline:** v2 `e5076d5e3163266f535cae829042400adfef8bc3`; incoming extractor `813489261096f87cf6a613e5cb1feeb0fd2914a6`; common ancestor `840512002a80a12b19c712116530ab69b1459c3a`. Source worktree clean at inspection. Later source commits require a separate integration.

## Checks and implementation sequence

- [x] Preserve a named pre-integration Git reference. Record baseline root and incoming extractor test results, including skips and existing failures.
- [x] Compare changes from the common ancestor. Merge the pinned incoming commit with no automatic commit; retain both branches' TODO history and v2 policies. Check Git conflicts and extractor source identity independently.
- [x] Reproduce portability defects in tests before repairs: build a release from a copied checkout, preserve original frozen metadata, remove historic developer paths only from release snapshots, verify Excel/JSON digests remain aligned.
- [x] Run the merged XML suite using this checkout's package. Resolve repository-relative sample paths rather than depending on old PC folders. Keep source extraction semantics unchanged.
- [x] Add integration regression tests for current extractor identity and new semantic source-path/provenance representation. Adapt `src/semantic_xml_reader.py` and `src/xml_review_gate.py` only where validated evidence proves a legitimate XML transformation. Reject altered/missing/duplicate evidence and wrong languages. Do not bypass failed extraction gates.
- [x] Re-extract representative PDFs covering ZC, XU, ZG, AFRICA, CE, TK ARA, MENA, SQ MI, XT, ZW, and XL. Record technical adapter pass/block status per language. Compare raw/semantic/MD to the same incoming extractor; compare changed ZC checklist results to pre-integration output. Preserve existing human approval boundaries. 14 PDF/32 combinations pass; XL blocked on absent canonical metadata (not inferred).
- [x] Validate ZC checklist 59 parent / 14 child scope, observations, JSON/Excel consistency, and no automatic business decisions. Do not rewrite DB wording to make tests pass.
- [x] Run root suite and XML suite separately, `compileall src tests scripts` (and apps if present), and dependency checks. Rebuild pilot ZIP and run extracted ZIP self-check and ZC CLI in a different folder. Root616/4skip; XML2524/1skip; candidate pilot133files passed.
- [ ] Record exact checks, changed outputs, limitations and any required human review in a dated migration report, validation ledger, README and TODO. Save scoped integration commit after review; preserve prior results and branches.

## Relevant implementation files

- `samples/tagged_pdf_xml_poc/`: incoming extractor, tests and source review records.
- `src/xml_review_run.py`: producer identity and completion receipts.
- `src/xml_review_gate.py`: pinned contract, extraction gates and audited language evidence.
- `src/semantic_xml_reader.py`: source-to-semantic identity and evidence-preserving conversion.
- `tests/xml_v2/test_xml_adapter.py`: synthetic malformed-bundle rejection.
- `tests/xml_v2/test_integrated_extractor.py`: actual current-source integration regressions.
- `scripts/build_review_pilot.py`, `tests/test_review_pilot_delivery.py`: portable release and unchanged master integrity.
- `docs/migration/2026-09-20-xml-integration_kr.md`: baseline, result matrix and handoff.

## Completion rule

Git merge alone is not completion. Report test execution separately from collection, automatic preservation separately from source-PDF human review, and XML/adapter support separately from ZC-only checklist support. Do not infer that all buyers/languages are approved from representative tests.
