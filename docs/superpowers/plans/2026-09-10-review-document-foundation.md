# ReviewDocument Foundation Implementation Plan

> **For agentic workers:** Execute this bounded plan inline with the executing-plans workflow. User authorization to proceed is already recorded. Do not spawn subagents unless requested. Steps use checkbox syntax.

**Goal:** Preserve XML structure, ordered text, metadata and optional evidenced review roles in a dependency-free v2 model.

**Architecture:** Add one flat `src/review_document.py` module without importing the legacy extraction package. A recursive immutable node preserves mixed content; the document validates identity and exposes ordered traversal. XML parsing, gating, DB evaluation and rendering follow as separate milestones.

**Tech Stack:** Python standard-library dataclasses, pytest. No new dependency installation for this milestone.

## Task 1: Protect the baseline

- [x] Snapshot current tracked state and selected source/metadata directories using an alternate index; retain main HEAD/index/status.
- [x] Create `codex/pre-xml-review-v2-20260910` at `4b001ff9a1a4f8ef91bed75a8ab314f4189d9476`.
- [x] Create and verify the complete Git bundle in `.worktrees/migration-backups-20260910/pre-xml-review-v2.bundle`.
- [x] Create `.worktrees/xml-review-v2` on `codex/xml-review-v2` from `840512002a80a12b19c712116530ab69b1459c3a`.
- [x] Baseline `python -m pytest tests -q`: 62 passed, 6 subtests passed. This is the checkout's root suite; not the separate XML POC suite.

## Task 2: Model behavior tests

**Create:** `tests/test_review_document.py`.

- [x] Write tests for inline text/figure/tail order; nested table-cell paragraph/list preservation; two sentences remaining one node; one-to-many multilingual grouping; absent role preservation; role evidence; duplicate node IDs; invalid page/bbox; immutable collections; unknown structure preservation.
- [x] Run `python -m pytest tests/test_review_document.py -q`; observed missing `src.review_document` import before implementation.

Public API example:

```python
from src.review_document import DocumentContext, ReviewDocument, ReviewNode

context = DocumentContext("MANUAL", "ZC_L02", "ZC", ("ZC",), "A2", ("ENG", "C-FRA"))
node = ReviewNode("p1", "paragraph", ("Sentence one. Sentence two.",), language="ENG")
document = ReviewDocument(context, (node,))
assert document.roots[0].text_content == "Sentence one. Sentence two."
assert [item.node_id for item in document.iter_nodes()] == ["p1"]
```

## Task 3: Implement the model

**Create:** `src/review_document.py`.

- [x] Implement the five immutable dataclasses and exact invariants in `docs/architecture/xml-review-v2-architecture_kr.md`.
- [x] Use a stack for document traversal and duplicate-ID detection; preserve content order by pushing children in reverse. Do not infer language or business roles.
- [x] Keep text joining free of whitespace normalization and synthetic separators.
- [x] Run `python -m pytest tests/test_review_document.py -q`, then `python -m pytest tests -q`: 46 focused / 108 total passed, plus 6 root subtests.

## Task 4: Verify and record

**Modify:** `README.md`, `TODO.md`, `AGENTS.md` in the v2 worktree only.

- [x] Link spec, architecture and recovery record; clarify v2 policy takes precedence over legacy-only extraction notes for new v2 files.
- [x] Run `python -m compileall -q src tests`; passed. Scripts/apps do not exist in this first-milestone checkout.
- [x] Run `git diff --check`; inspect the actual changed files and verify no XML POC or legacy runtime file changed.
- [x] Verify source master Excel/JSON hashes remain as recorded; alternate snapshot index `git diff-files --exit-code` confirms scoped main working files match.

Commit this completed milestone on `codex/xml-review-v2` with only the listed files. Report the resulting ID with the recovery ID; do not mark full migration complete. The final commit ID is available from `git log -1` rather than embedded in its own file.

## Following milestone acceptance boundary

Before implementing `semantic_xml_reader.py`, inspect real XML/report serialization and define accepted versions and mandatory gates. Write fixtures using the actual writer, then test mixed text, nested tables, controls, source heading candidates, sentence/continuation hints, figure evidence and language intervals. A mismatched or failed bundle must stop evaluation. Preserve the current Markdown writer and four-file output bundle. This requires a separate implementation plan with the actual XML schema, not assumptions from this model-only milestone.
