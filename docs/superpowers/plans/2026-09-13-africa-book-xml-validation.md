# AFRICA BOOK XML validation plan — 2026-09-13

Goal: Validate BN68-25031G-00 on feature/xml-markdown-review using the independent tagged-PDF POC. Starting HEAD: 840512002a80a12b19c712116530ab69b1459c3a; clean worktree.

Scope: samples/tagged_pdf_xml_poc runtime/tests, this plan, review findings, TODO. No GridCell, item_review, Excel, app, DB, other worktree, or remote changes.

Evidence: Initial bundle outputs/xml_review_africa_20260913_before fails. PDF bookmarks are English p2, Français p8, Español p14, Português p20, العربية p35. Arabic physical p30–35 is in reverse reading order. Raw ToUnicode maps rendered 04 to 14, while nested ActualText provides 0 and 4. ENG p7 includes Jordan-only subsection absent in FRA/SPA/POR (verify source before classifying parity differences).

Design: Keep Raw source order and MCID provenance. The exact AFRICA_L05 BOOK scope uses observed bookmarks, six-page LTR spans and contiguous Arabic-script/cover evidence. Semantic Arabic articles read backwards; source paths remain attached. An opt-in ActualText adapter uses PDF-authored replacement text, never translations or digit substitutions. A source glyph observer records MCID, raw operand hex, font and text/current matrices before pypdf flushes. Pure RTL glyph lines may be reconstructed with identical character bags, uniform glyph style, same baseline or NSM-only excursion and exact return, monotonic AL anchors, complete single-line MCIDs, and source whitespace at reordered boundaries. Mixed or uncertain evidence remains unmodified. No other profile or shared language rule changes.

- [x] Run unmodified extractor; preserve four-file bundle and Git state.
- [x] Reproduce numeric ActualText, scope, invalid-evidence, interval, Markdown-label, RTL glyph and unsafe-edge failures before fixes.
- [x] Implement scoped adapter, reader profile entry point, semantic interval/page/glyph order and compact chapter display.
- [x] Focused tests: 50 passed. New bundle: `xml_review_africa_20260913_final_v2`; earlier outputs preserved.
- [x] Render all 36 pages, inspect 29 crops plus supplemental cover/heading crops, compare ENG with confirmed ZC before local-language inspection.
- [x] Full real-sample POC: 1760 passed, 1 Windows symlink skip. Three legacy public imports and compileall pass.
- [x] Produce review_document.json, review_run.json, contact-row parity, provenance/character checks and detailed source-backed findings.
- [x] Follow-up from clean 8eb2dfbb6c0f9fca8d1a7fda2ef448a706cb0a3f: TDD fixes for mixed UI, source glyph advances, LTR islands, explicit RTL model separators, ActualText decimals and heading-count source exception.
- [x] Recheck scopes: 21 common heading child-type groups match all languages. Jordan adds one heading, seven P containers and a 2x1 CE/declaration table only to ENG/ARA. Covers/contact/blank pages are separate.
- [x] Exact fingerprinted source exception retains strict count=false and all three mismatches; changed SHA/profile/heading/level/table evidence fails closed.
- [x] Final bundle xml_review_africa_20260913_recheck_final_v2. Focused 101 passed; full 1811 passed, 1 Windows symlink skip. Compileall and three public imports pass. 18505 source glyph origins match independent geometry within 0.02 pt.
- [ ] Human native RTL presentation, meaning and image-only symbol review; no DB candidates.

Verified repairs are saved in a local commit; its full recovery number is recorded in the final review_run.json. Structural extraction acceptance is distinct from human semantic approval.
