# XML Adapter Implementation Plan

> **For agentic workers:** Execute inline with executing-plans. The user has authorized this next migration step. No delegation is required.

**Goal:** Run the existing XML extractor in a fresh directory and convert its verified bundle into ReviewDocument without changing its four outputs.

**Architecture:** `xml_review_run.py` owns fresh extraction and its receipt; `xml_review_gate.py` checks the receipt, required gates and language audit; `semantic_xml_reader.py` preserves XML nodes and source evidence. The accepted unversioned POC serialization is explicitly named `tagged-pdf-xml/8405120`; the receipt also records the actual extractor source digest. No checklist evaluation or business-role rules are added in this milestone.

**Tech Stack:** Python, existing tagged-pdf-xml-poc package, pytest. Tests load the worktree POC source; normal use installs that local package.

## Observed schema and decisions

- Semantic XML has a `document` wrapper, structural nodes and `text` fragments. Data characters are in `text`/`control`; whitespace outside those is XML formatting. `attributes/attribute` records source properties and is not body text.
- Raw XML supplies source-role values absent from most semantic nodes. Pair raw/semantic by structural child positions, excluding metadata, and verify fragment page/MCID/object identity and joined text.
- Retain paragraph/list/table hierarchy, all attributes, heading candidates, display hints and encoded characters. Keep heading candidates as paragraphs when the source semantic tag is paragraph. Do not split sentences or invent role names.
- The POC report has no durable bundle hash/version. A new v2 extraction receipt records PDF, mapping and all four artifact SHA256s after a fresh successful run. Loading an old directory without this receipt fails; simply hashing an old folder cannot prove which execution produced it.
- Read each artifact once; verify hashes and parse those same bytes. Reject unsupported contract, changed PDF/mapping, missing/false/non-boolean gates, report errors and conflicting language intervals.
- Multilingual canonical language comes from the audited path/page intervals (including end-node descendants). Ancestors spanning languages stay unassigned. Single-language nodes require an explicit recognized XML language tag; profile expectation alone does not label text. Preserve the original language attribute.
- A successful adapter is an extraction prerequisite, not a checklist Pass. Unknown structures and unassigned common nodes remain visible.

## Task 1 — Contract tests

- [x] Add `tests/xml_v2/conftest.py` to load this worktree's POC for tests.
- [x] Add writer-generated fixtures and tests in `tests/xml_v2/test_xml_adapter.py` for exact text, source roles, nested tables/lists/figures, controls and attributes, optional roles, language evidence and rejected mismatched bundles.
- [x] Run `python -m pytest tests/xml_v2 -q`; observed missing `src.semantic_xml_reader` before implementation.

API exercised by fixtures:

```python
document = read_review_bundle(bundle_dir, receipt, pdf_path=pdf, mapping_path=mapping)
assert document.context.source_token == "ZC_L02"
assert all(node.review_roles == () for node in document.iter_nodes())
```

## Task 2 — Implement the reader and gate

- [x] Create `src/xml_review_gate.py` with receipt validation, canonical context lookup, strict gate and audit validation.
- [x] Create `src/semantic_xml_reader.py` with raw/semantic pairing, data decoding, metadata preservation and language assignment.
- [x] Run focused tests and resolve failures against the observed writer schema. 30 tests passed; added failing regressions for extractor-version rejection and shared cover preservation before fixes.

## Task 3 — Fresh-run integration

- [x] Create `src/xml_review_run.py`: `extract_review_document(pdf_path, run_dir, mapping_path)` calls the existing ExtractDocument, captures immutable input/code hashes before/after, validates outputs and writes `review_run.json` plus `review_document.json` alongside the untouched four artifacts. Existing directories are rejected, including empty ones.
- [x] Add tests for occupied destinations and receipt/file changes; use the real ZC PDF for end-to-end validation.
- [x] Run ZC ENG/C-FRA, then XU ENG and ZG BOOK as adapter checks. Record text/node/table/language counts, exact source-fragment preservation and original four-output comparison. These checks do not approve semantic equivalence or checklist coverage.

## Task 4 — Verify and hand off

- [x] Run `python -m pytest tests -q` (138 passed / 6 subtests), focused POC writer/output/language/Markdown tests (511 passed / 1 symlink skip), `python -m compileall -q src tests`, and `git diff --check`.
- [x] Update README, architecture and TODO with actual results and usage. Preserve the previous uncommitted role-policy edits.
- [x] Leave DB, Excel generation and Streamlit as the next milestones. This implementation and the role-policy edits are checkpointed together; obtain the ID from `git log -1`.

Result details and exact commands: `docs/migration/2026-09-10-xml-adapter-validation_kr.md`.
