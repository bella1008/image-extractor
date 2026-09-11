# Structured evidence follow-through implementation plan

> **For agentic workers:** Use executing-plans for inline implementation and requesting-code-review at the verification checkpoint. The user requested uninterrupted continuation of the approved migration; do not insert routine approval pauses.

**Goal:** Explain the nine structural mismatches with source-preserving evidence candidates, then connect the checked workflow to a readable local report without changing DB approvals.

**Architecture:** Preserve the existing strict observation as a baseline. Add separately named, provisional evidence windows: atomic text, contiguous sibling paragraphs, same-item label/body, and uninterrupted text runs beside figures. Never flatten table rows, cross headings/languages, or infer cover regions. Candidate evidence is not an accepted selector or Pass. Keep modules flat and the XML producer/Markdown unchanged.

**Tech Stack:** Python dataclasses, pytest, existing checked XML bundle and frozen Excel/JSON loader; standard-library HTML rendering for a local review handoff.

## 1. Evidence windows

- [x] Add `tests/test_review_evidence_windows.py`: assert sibling paragraphs retain separate parts and an explicit display separator; label/body only within the same item; figures interrupt text; empty unknown nodes interrupt composition; nested rows and foreign languages never join.
- [x] Run `python -m pytest tests/test_review_evidence_windows.py -q` and observe the missing implementation fail.
- [x] Add `src/review_evidence_windows.py`, immutable windows with exact source parts, structure paths, boundaries, composition method and review caveats. Bound consecutive paragraph windows to four; report the limit, not universal coverage.
- [x] Run the focused tests and the existing text-unit tests; the existing partition remains unchanged.

## 2. Supplemental candidates

- [x] Add observation tests showing strict `matches` unchanged while `candidate_matches` explains label/paragraph/visual-context differences; duplicate/missing/unsafe headings and non-applicable rows have no candidates.
- [x] Run failing focused tests, then wire windows into `src/checklist_observation.py` under the same checked heading/section/language boundary. Preserve unsupported-selector reasons and every draft field.
- [x] Regenerate a fresh ZC result with the existing checked runner. Compare all 547 source rules and strict status/match counts with the checkpoint; inspect every additional candidate against original XML parts.

## 3. Readable execution handoff

- [x] Add report tests for HTML escaping, expected versus observed text, pending/unsupported states, page display and exact source references. No external resources or active source-text markup.
- [x] Add a small `src/review_observation_report.py` formatter and expose it through a separate service/CLI that calls the existing checked observation runner. Use a new output directory and preserve failures visibly; do not activate the DB or change the existing app.
- [x] Run integration tests for successful output, changed inputs, existing output refusal and report failure. Generate the real local report.

## 4. Verification and next gate

- [x] Independent code review of the bounded windows and publication path; fix important findings with failing regression tests first.
- [x] `python -m pytest tests -q`; `python -m compileall -q src tests scripts`; `git diff --check`.
- [x] Recheck original main Excel/JSON digests, update TODO and Korean guide, save a recovery commit only in `codex/xml-review-v2`.
- [x] Continue safe unresolved diagnostics. Stop only if accepting a business role/scope, changing approved wording, or approving the user-facing layout requires the user's judgment; provide the concrete evidence together instead of asking technical questions.

## Continued safe work and actual user gate

- [x] Added separate DB-line fragment diagnostics for SAFETY-008; all three located without claiming whole-rule/order/table correctness.
- [x] Fresh PDF end-to-end execution in isolated pypdf6.16.2 environment; all 547 strict baseline rows identical, XML/MD byte-identical.
- [x] Inspected actual legacy extraction and result XLSX contracts. Added a pure report-view mapper and completed-snapshot reader with red/green tests.
- [x] Generated one development-only Excel layout prototype; full 59/40/488 row-value equality, four sheet previews, filters/panes/conditional formatting and formula caches verified.
- [x] Full root 285 tests + 6 subtests; dedicated venv 285 tests; compileall. Original main DB digests unchanged.
- [ ] User-facing column layout confirmation requested asynchronously. This is a real display contract choice before implementing the deployed Excel writer, not a routine progress checkpoint. No DB approval or business Pass is requested.
