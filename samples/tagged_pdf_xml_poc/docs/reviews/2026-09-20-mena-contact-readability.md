# MENA contact and readability review — 2026-09-20

## Source and scope

- PDF: `BN68-25031L-00_SUG_Y26 TV ALL_MENA_L02_260114.0.pdf`
- profile: `MENA_L02 / A2 / ENG, ARA`
- branch: `feature/xml-markdown-review`
- starting HEAD: `1ef64066a3ddf90dd77495ad2400ffa779f6b508`
- final review bundle: `outputs/xml_review_mena_20260920_readability_review`
- consolidated pending-review index: `outputs/xml_review_pending_20260920_counts/review.html`

No checklist database, item-review path, legacy GridCell extractor, or other worktree was changed.

## Corrected defects

1. The cover contact title was plain in Markdown although the PDF uses SamsungOne-600 against a SamsungOne-400 explanation at the same 7-point size.
2. Separate source paragraphs in contact cells, including Syria phone and WhatsApp lines, were flattened into one line.
3. The Eco Sensor and following Brightness Optimisation sentences under `The screen dims.` were joined because validated navigation icons were only enabled for a buyer allowlist.
4. Model-only rows in the specification table were flattened although the PDF stores them on distinct baselines.

## Rule boundaries

Cover contact behavior requires one section with title, explanation, and one table; two or three header columns; a Samsung website; numeric contact data; and paragraph-only cells. The rule does not use translated headings or buyer/language strings. It adds line breaks only between distinct source paragraph nodes, not between visual wraps inside one paragraph.

Model rows require complete bbox evidence, at least two distinct baselines, and model-only tokens containing uppercase Latin letters and digits. Prose, units, dimensions, lowercase text, and incomplete geometry fail closed. The semantic XML stores reviewed child indexes; raw text and token order do not change.

Validated inline-icon geometry is now available to the existing sentence-boundary detector for every profile. URL, abbreviation, unknown-figure, and ambiguous-route rejection rules remain in place.

## Cross-buyer contact audit

| Profile | Semantic tables | Classified contact tables | Other tables changed |
| --- | ---: | ---: | ---: |
| MENA_L02 | 31 | 2 | 0 |
| ASIA_ENG | 18 | 1 | 0 |
| ZG XN ZT_L05 | 146 | 1 | 0 |
| XH_L16 | 466 | 1 | 0 |
| SQ MI_HEAR | 37 | 2 | 0 |

The five samples passed their extraction hard gates after re-extraction. MENA received four model-row annotations: ENG object refs `1336 0 R`, `1343 0 R`, and ARA refs `331 0 R`, `338 0 R`. ASIA, ZG, XH, and SQ MI received zero model-row annotations.

## MENA final structure counts

| Language | Displayed headings | Review units | Tables | Figures |
| --- | ---: | ---: | ---: | ---: |
| ENG | 22 | 93 | 16 | 40 |
| ARA | 22 | 92 | 15 | 38 |

The ENG-only QR, barcode, and document-code cover area explains the table and figure count difference already documented in the accepted source audit. The change did not alter heading, table, figure, text-node, or character counts.

## Source and rendering evidence

- The rerun uses the same PDF SHA-256 as the accepted 2026-09-17 MENA source audit.
- Semantic source signature and table row/cell/span relationships are identical to that accepted bundle.
- XML to Markdown full character sequence passed for all 185 review units.
- Markdown and preview HTML text/DOM structure match.
- The final review bundle contains raw XML, semantic XML, Markdown, extraction report, review document, review run, preview HTML, and a targeted source audit.

Hard gate failures: 0. Remaining warnings are the existing non-text icon, safety-symbol, QR, barcode, and editorial/translation review items. These are source-review concerns and were not converted to OCR claims or automatic corrections. User final approval remains pending.

## Verification

- focused affected tests: `741 passed`
- complete POC suite: `2514 passed, 1 skipped` (`symlinks unavailable` on Windows)
- root public-import compatibility: `43 passed`
- POC compileall: `src tests scripts`
- root compileall: `src tests` (root `scripts` and `apps` directories do not exist)
