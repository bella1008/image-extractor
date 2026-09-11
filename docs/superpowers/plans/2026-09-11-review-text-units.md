# Review text unit boundary implementation plan

> **For agentic workers:** Use executing-plans inline for this continuation of the approved XML v2 design; use requesting-code-review at the checkpoint.

**Goal:** Produce a traceable, non-decision inventory of bounded XML text units before implementing checklist matching.

**Architecture:** Keep ReviewDocument unchanged. A pure flat module partitions source string occurrences into ordered units; a development CLI loads a checked XML bundle and writes a fresh JSON inventory. No DB, Markdown reader, normalization, heading translation or business classification is introduced.

**Tech Stack:** Python dataclasses, existing bundle adapter, pytest.

## Approved boundary and alternatives

The user approved continuing the documented XML-location/matching verification stage.
Whole-document search would cross languages; whole-paragraph search would cross nested tables observed in ZC.
Use contiguous text segments separated by structural children instead. This is source-structure preparation, not proof that a rule's heading or semantic role has been selected correctly.

- String identity is `(node_id, content_index)`, including empty strings; preserve exact text and source order once only.
- Each unit records owner ID/type, ancestors, segment index, text parts and original evidence.
- Inline text/span/label descendants may contribute to one segment. Heading label/list_body may compose one heading only when their descendants are inline.
- Paragraph, list_body, heading, leaf table_cell are supported owners. Other owners' direct text is retained with a blocking issue.
- Nested blocks, paragraphs, lists, table rows and cells always separate segments. Do not concatenate across them.
- Figures retain all source text but mark the segment for visual review, including figures with no text.
- Missing/mixed/unexpected language and missing part evidence mark a unit unavailable for text matching. Do not inherit a guessed language.
- An index is not a quality gate or business Pass. Its readiness flag means structural text preconditions only.
- Do not modify source XML, master DB, ReviewDocument, source roles or review_roles.

## Tasks

- [x] Add `tests/test_review_text_units.py` with ordered mixed-text, nested table/list, inline figure, unknown wrapper, empty/Unicode, mixed/unassigned language, and evidence-loss cases. Example assertion:

```python
index = build_text_unit_index(document)
assert [unit.text for unit in index.units] == ["before", "cell one", "cell two", "after"]
assert len({(part.node_id, part.content_index) for unit in index.units for part in unit.parts}) == 4
```

- [x] Run `python -m pytest tests/test_review_text_units.py -q`; confirm new API missing before implementation.
- [x] Implement `src/review_text_units.py` with frozen TextPart, ReviewTextUnit, TextUnitIndex and `build_text_unit_index(document)`. Use a stack traversal and flush before every structural child; never join units to locate a phrase. Validate exact partition before returning.
- [x] Run focused tests. Add real checked-bundle integration verification using existing ZC, XU and ZG receipts without re-extraction.
- [x] Implement `scripts/audit_review_text_units.py` CLI accepting `--bundle`, `--pdf`, `--mapping`, `--output`. Load receipt then `read_review_bundle`; refuse existing output. Write `schema_version=review-text-units/1`, `decision_status=not_evaluated`, input receipt/hash, context, units and summary. Invalid gates produce no output.
- [x] Test CLI refusal on missing receipt/changed artifacts and fresh-output round trip. Run full root tests and compileall src/tests/scripts.
- [x] Read counts and inspect representative units of checked ZC/XU/ZG. This verifies structural partition, not PDF visual acceptance or checklist compatibility. Keep unsupported units visible.
- [x] Update TODO and Korean usage guide, request independent code review, commit checkpoint without merging main.

Validation: 195 root tests + 6 subtests; 56 focused tests. Reviewer identified nested
list_body flattening under a heading; reproduced 3 failures and fixed the direct-child
exception. Rereview passed. Regenerated ZC/XU/ZG inventories are byte-identical to the
independently checked original inventories (1,938/1,168/6,696 ordered text parts).

## Source-token explanation to retain

For `BN68-25100B-00_SUG_Y26 TV ALL_ZC_L02_260122.0.pdf`, filename parser constructs
`source_token=ZC_L02`; profile mapping gives region ZC, doc_type A2, expected ENG/C-FRA.
It is a profile key, not a globally unique PDF ID. Manual code, version/date and content hash distinguish PDFs.
DB `source_reference_token=ZC_L02` means where candidate wording came from and never limits rule applicability.
