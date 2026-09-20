# XL / XT readability follow-up — 2026-09-20

## Scope

- XL: `BN68-25031J-00_SUG_Y26 TV ALL_XL_ENG_260306.0.pdf`, `XL_ENG / A3 / ENG`
- XT: `BN68-25031M-00_SUG_Y26 TV ALL_XT_L02_260113.0.pdf`, `XT_L02 / A2 / ENG, THA`
- branch: `feature/xml-markdown-review`
- final bundle: `outputs/xml_review_xl_xt_20260920_readability_final`
- remaining eight-buyer index: `outputs/xml_review_pending_20260920_counts_v3/review.html`

MENA ENG/ARA was removed from the pending index after the user confirmed that review was complete. XL and XT remain pending human approval. No checklist database, item-review path, legacy GridCell extractor, or other worktree was changed.

## User findings and results

### XL

The 2026-09-17 HTML predated the shared contact/readability rules. The current rerun now renders `Contact Samsung world wide` as a strong label, preserves separate source paragraphs in the Malaysia and Philippines service-centre cells, and places a line break after the first Eco Sensor sentence under `The screen dims.`.

The XL specification is an 18-row by 4-column grid. Its first cell in each row contains source-bold labels while values occupy the remaining cells. The common rule now recognizes this repeated row-label/value topology and renders all 33 source-bold item paragraphs as strong labels. It does not use an English label dictionary. XL is an India-market manual; the two source `For India only` sections remain unchanged.

### XT

The ENG contact section contains the expected title, explanation, and table plus one empty tagged paragraph. The previous strict three-child topology rejected the section, so its title remained plain and its two source paragraphs (`Hotline no : 1282` and `1800-29-3232...`) were flattened. The rule now ignores only an empty paragraph with no children. A non-empty extra section child still fails closed.

The specification labels now render as strong labels in both languages: ENG 7 and THA 7. Thai recovery retains the exact PDF-derived text. Where the embedded Thai font name does not expose a normal weight, the rule requires the verified source role pair `Description-L-B` / `Description-L`, a source-bold label style, repeated numeric value groups, and the same table topology.

## Common rule boundaries

Two specification layouts are supported:

1. repeated bold-label / weaker-value paragraph pairs within one cell;
2. repeated source-bold paragraphs in the first cell of a multi-column row, with numeric value paragraphs in the remaining cells.

Both require at least two distinct numeric value groups and complete label typography evidence. Multi-column detection rejects URL-bearing tables, preventing service-centre contact tables from being classified as specification labels. Text-only forms and troubleshooting Q&A remain excluded. Existing form and contact display hints take precedence when paths overlap.

## Source fidelity and structure

The final XL and XT semantic XML was compared against the accepted 2026-09-17 source-reviewed XML. Exact text-node content, source paths, object references, page/language/MCID identity, element order, and table row/cell/span relationships are unchanged. Only reviewed display metadata and Markdown presentation changed.

| Buyer / language | Displayed headings | Review units | Tables | Figures | Spec strong labels |
| --- | ---: | ---: | ---: | ---: | ---: |
| XL ENG | 24 | 101 | 21 | 45 | 33 |
| XT ENG | 23 | 95 | 17 | 45 | 7 |
| XT THA | 23 | 94 | 16 | 44 | 7 |

XML-to-Markdown character sequence and Markdown-to-preview DOM/text structure passed for all 290 review units, with zero unit failures. Extraction Hard gate failures are 0. Remaining warnings are the existing source wording and non-text icon/barcode/safety-symbol review items; the extractor did not add OCR claims or edit source wording.

## Verification

- focused XL/XT/contact/spec tests: `113 passed`
- full POC suite: `2524 passed, 1 skipped`
- skipped test: Windows symlink unavailable
- root public-import compatibility: `43 passed`
- POC compileall: `src tests scripts`
- root compileall: `src tests`

The final review state is `extraction_review_pass_pending_human_review` for XL and XT. MENA ENG/ARA is user-approved; XL/XT/TK/ZW/PY/SQ_MI/UA/XD remain pending.
