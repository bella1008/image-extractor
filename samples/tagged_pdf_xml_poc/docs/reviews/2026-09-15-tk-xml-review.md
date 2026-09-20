# TK XML extraction review

Worktree: `C:/Users/bella/image-extractor/.worktrees/xml-markdown-review`

Branch: `feature/xml-markdown-review`

Initial HEAD: `de941f020de6208713e45100c2d0f5f282866077`; initial working tree clean.

The user accepted the representative ownership review and authorized TK rollout.
No other worktree, checklist DB, item-review, Excel/Streamlit, or GridCell implementation was changed.

## Sources and sequence

Source directory (read only): `C:/Users/bella/image-extractor/.worktrees/xml-extractor-release/samples/SUG_RAW/TV_TK`.

| PDF | Profile | Languages | Source layout |
|---|---|---|---|
| BN68-26343A-00_SUG_Y26 TV ALL_TK_L02_260327.0.pdf | TK_L02 / A2 | ENG, TUR | Two pages, no bookmarks; p1 ENG, p2 TUR |
| BN68-26344A-00_SUG_Y26 TV ALL_TK_ARA_260327.0.pdf | TK_ARA / A3 | ARA | Two pages, no bookmarks; p1 then p2, RTL inside content |

Filename parsing and canonical profile mapping agree. Page sizes and SHA-256 are recorded in `outputs/xml_review_tk_20260915_evidence/initial_state.json`.
TK A3 page order must not inherit the reversed physical page order of AFRICA Arabic BOOK.

ENG was reviewed first against ZC ENG, with XU/ZG ENG as closer layout/source references. Its 23 body headings follow XU ENG. ZC Internet security and ZG password headings are not in this source; One Connect and regional/model differences were verified rather than inserted from a baseline.
TUR was compared against its own ENG, then TK ARA against TK ENG and the verified AFRICA Arabic mechanisms.

## Defects and repairs

- A2 cover stories followed the complete body for both languages. Move the observed cover stories before the body, preserving raw order and original source paths.
- Restore TUR Power continuation and both ENG/TUR service-fee child conditions. ARA has the analogous Power and fee repairs.
- Remove only source-operation-proven synthetic spaces in Wi-Fi decimals, URLs, `network-based`, and `IEC 62087.`. Token boundaries carry semantic evidence into the Markdown writer.
- Preserve TUR manufacturer RowSpan=2 and laboratory RowSpan=4/4 using HTML tables embedded in Markdown. Table selection uses the verified TK/TUR span shape, not a heading dictionary.
- Recover Arabic numbered headings, diacritic order, VESA/One Connect/model tokens, RF model separators and inch/output conditions using PDF glyph positions and PDF-authored ActualText.
- Keep the source Arabic comma in output conditions. It is accepted by validation without replacing source punctuation.
- MCID 771 contains both a slash and the adjacent model's wildcard. Its disjoint source slices keep the same MCID and distinct XML paths; the source union is exact. This is not a duplicated source token.
- An exhaustive standalone-whitespace inventory classified 492 semantic fragments (ARA 186; ENG/TUR 306). Eight ARA source separators were dropped: seven numeric boundaries and one navigation boundary. Exact source-hash/path/MCID wrappers retain the original fragments and preserve those spaces. The navigation source newline plus space is retained before normal XML whitespace normalization. One slash/RLM spacing relocation remains intentional formatting, with the explicit model delimiter intact.
- The final visual check additionally required LTR isolation of the complete `LS03H*` token within its Arabic list, so the wildcard remains on the same side as in the PDF. Isolation is emitted in Markdown itself and checked in rendered HTML.

New behavior is in dedicated TK modules and explicit profile dispatch within the XML POC. Object-addressed Arabic repairs also require the exact verified source SHA-256. An unknown revision cannot silently reuse those object IDs. Incomplete glyph evidence, changed text/roles, different pages, and different list shapes leave the source unchanged.

## Structure and fidelity

Each language has 23 body headings plus one cover title. Five numbered chapters are promoted to semantic heading nodes; other review headings retain their observed PDF roles/display evidence. Counts below include all native nested table/list nodes, not only business-level tables.

| Language | Review headings | Review units | Paragraphs | Lists | Items | Tables | Figures |
|---|---:|---:|---:|---:|---:|---:|---:|
| ENG | 24 | 124 | 207 | 43 | 125 | 26 | 50 |
| TUR | 24 | 128 | 278 | 43 | 125 | 30 | 50 |
| ARA | 24 | 108 | 184 | 39 | 118 | 21 | 47 |

Differences are source-supported:

- TUR adds 85 model codes, importer/CE/ecodesign/lifetime statements and manufacturer/laboratory tables. All 85 model codes match the PDF. Manufacturer and LVD/EMC merged-cell relationships remain visible.
- ARA puts RF information in the p2 bottom columns and a source table with five model groups, instead of the ENG cover layout. It lacks the ENG non-authorised repair/energy-label/WEEE/battery disposal material and TUR-specific additions.
- Contact headers are kept separately from data rows. ENG/TUR have service-centre/website headers; ARA reverses physical column placement. Each contains `444 77 11` and the Turkish support URL. No country column was invented.
- Cover title, support/registration/model/serial/contact/copyright regions, source contact headers, safety symbols, image-only document code and TUR importer badge have PDF crop evidence. `İthalatçı Firma` is image-only; it is not claimed as OCR text.
- Four Arabic navigation paths, three falling-prevention steps, safety table, model conditions and numerical values were checked. Images remain explicit image evidence.

Raw→semantic verification checks fragment identity with explicitly documented disjoint splits, complete per-MCID non-whitespace character ownership and global character preservation. XML→MD verifies all 360 review units and the entire rendered character sequence. MD→HTML verifies text and DOM, including table spans and model isolation. Geometric rendering verifies the wildcard position, not just character counts.

## Source wording warnings

Seven source-preserving examples are recorded in `2026-09-15-tk-source-cases.json` for a future translation/editorial agent:

- TUR existing-TV condition and protective-film condition (2).
- ENG `icncorporated` spelling (1).
- ARA installation orientation, RF unit wording, `قك`, and repeated `دليل` (4).

These match the original PDF and are not extraction failures. They require language/editorial judgment before changing the manual. No checklist candidates were made and no runtime heading translations were added.

## Validation and recovery

Initial tests reproduced 12 A2 failures, three ARA failures and two merged-cell display failures before fixes. Independent review found and reproduced three unsafe fallback/ownership conditions; all were fixed with negative tests. The later visual wildcard defect was treated separately from logical text preservation.

Seven representative PDFs were re-extracted: ZC, CE, AFRICA, ZG, XU, KR, LATIN. Their raw XML, semantic XML and Markdown are byte-identical to the accepted `xml_review_common_20260915_verified` baseline. Evidence: `outputs/xml_review_tk_20260915_source_regression/comparison.json`.

Final test counts, compileall results, code hashes, artifact hashes and local recovery commit are recorded in the final bundle's `validation_evidence.json` and `review_run.json`. The only expected skip is the Windows symlink test in `test_output_bundle.py`, not a PDF or language skip. Public compatibility imports remain callable.

## Final source review bundle

Absolute output: `C:/Users/bella/image-extractor/.worktrees/xml-markdown-review/samples/tagged_pdf_xml_poc/outputs/xml_review_tk_20260915_source_verified`.

- Entry: `tk_review.html`; source comparisons: `source_checks.html` (19 comparisons).
- ENG/TUR: `TK_L02/semantic_document.xml`, `TK_L02/semantic_document.md`, `TK_L02/semantic_document.preview.html`.
- ARA: `TK_ARA/semantic_document.xml`, `TK_ARA/semantic_document.md`, `TK_ARA/semantic_document.preview.html`.
- Each buyer folder also includes raw XML, extraction report, review document, HTML validation and review run.
- `whitespace_audit.json`: all 492 whitespace-only fragments classified; all eight repaired boundaries verified in final Markdown and HTML.

Additional special structures: each language has four navigation paths with eight navigation icons, 14 total inline icons, and one service-fee group with two child conditions. TUR has two explicitly preserved merged-cell tables; ARA has one isolated Latin model token and eight source-separator wrappers. These semantic markers preserve source content and are not checklist keys.

The source review has zero remaining hard-gate failures. All 360 XML/Markdown review units and full rendered text pass; table spans, source ownership, bidi geometry and eight whitespace boundaries pass. Seven source wording cases remain editorial review candidates. Image-only content is available as PDF/crop evidence, not OCR text. This completes extraction-quality review; it does not approve translations or editorial changes.

Final validation: **2,264 XML tests passed / 1 Windows symlink skip**, **148 TK focused tests passed**, **62 root tests passed**, and **3 public compatibility imports remained callable**. Both source trees compiled; the XML POC scripts compiled. Root scripts/apps directories are absent. Independent final review ran 92 related tests without findings. All seven regression PDFs produced byte-identical raw XML, semantic XML and Markdown (21 files).

XML source line coverage: **95.81%**; branch coverage: **91.30%**. The complete coverage measurement is documented in `2026-09-15-test-coverage.md`. The full local recovery commit is recorded in the final bundle’s `review_run.json` and `validation_evidence.json`.

## Changed files

- `TODO.md`
- `samples/tagged_pdf_xml_poc/scripts/render_representative_review.cjs`
- `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/application/extract_document.py`
- `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/domain/africa_rtl_conditions.py`
- `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/domain/africa_safety_label_readability.py`
- `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/domain/models.py`
- `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/domain/numbered_heading_promotion.py`
- `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/domain/readability_formatting.py`
- `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/domain/verified_paragraph_ownership.py`
- `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/domain/verified_paragraph_source.py`
- `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/infrastructure/markdown_writer.py`
- `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/infrastructure/pypdf_reader.py`
- `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/infrastructure/xml_writer.py`
- `samples/tagged_pdf_xml_poc/tests/test_verified_paragraph_ownership.py`
- `docs/superpowers/plans/2026-09-15-tk-xml-review.md`
- `samples/tagged_pdf_xml_poc/docs/reviews/2026-09-15-test-coverage.md`
- `samples/tagged_pdf_xml_poc/docs/reviews/2026-09-15-tk-source-cases.json`
- `samples/tagged_pdf_xml_poc/docs/reviews/2026-09-15-tk-xml-review.md`
- `samples/tagged_pdf_xml_poc/scripts/render_tk_review.cjs`
- `samples/tagged_pdf_xml_poc/scripts/render_tk_source_checks.cjs`
- `samples/tagged_pdf_xml_poc/scripts/review_tk_xml.py`
- `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/domain/tk_arabic.py`
- `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/domain/tk_arabic_source.py`
- `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/domain/tk_sheet.py`
- `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/domain/tk_source_text.py`
- `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/infrastructure/tk_source_evidence.py`
- `samples/tagged_pdf_xml_poc/tests/test_tk_arabic.py`
- `samples/tagged_pdf_xml_poc/tests/test_tk_arabic_bidi.py`
- `samples/tagged_pdf_xml_poc/tests/test_tk_arabic_guards.py`
- `samples/tagged_pdf_xml_poc/tests/test_tk_sheet.py`
- `samples/tagged_pdf_xml_poc/tests/test_tk_source_whitespace.py`
- `samples/tagged_pdf_xml_poc/tests/test_tk_writer_evidence.py`
