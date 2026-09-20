# CE BOOK paragraph ownership repair

Initial branch: feature/xml-markdown-review. HEAD: 7344b67e7f8496cf2a3cef093bc856d8d0cc9d84. No pre-existing uncommitted changes.

User identified the Power continuation and administration-fee conditions as incorrectly independent paragraphs. All five language PDF crops confirm the same indentation and ownership. Tagged source stores these as UnorderList_1-Bullet paragraphs; text geometry is absent on relevant fragments, so conservative generic continuation detection cannot prove ownership.

Use only CE_L05 BOOK with verified bookmark languages RUS/ENG/KAZ/MON/KYR. Exact PDF-extracted text, adjacency, page, language, and original role guard the repair. Reparent the Power continuation into the preceding list body as an inline span, preserving the original source path and fragments. The sentence writer supplies a break without a second bullet. Group the original fee introduction and a two-item semantic list; keep literal Cyrillic/Latin labels and original source paragraphs. No translated aliases or global writer changes.

1. Real-PDF tests reproduce the two defects in each language before runtime changes.
2. Implement scoped semantic grouping; preserve raw XML, source identities, text order and source paths. Recompute standby display paths after grouping.
3. Add fail-closed and other-profile negative tests.
4. Extract to a fresh folder, regenerate HTML and compare exact character order, whole-document structure deltas and all ten source crops. Carry forward source wording acceptance and editorial cases.
5. Run focused/full XML regressions, legacy public import compatibility, compileall, review the patch and commit locally.

Other UnorderList_1-Bullet source paragraphs were enumerated: the five * Shielded Twisted Pair notes are separate explanatory footnotes, not service-fee conditions. Preserve these annotations for this repair.
