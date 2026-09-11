# Agent Working Notes

## XML review v2 integration policy

- This worktree follows the user-approved `docs/superpowers/specs/2026-09-10-xml-review-v2-design_kr.md` for new v2 code. The older GridCell rules below remain legacy context, not instructions to port GridCell extraction into v2.
- Keep v2 modules flat under `src/`. `src/review_document.py` is dependency-free and must not import legacy extraction, Streamlit or checklist modules.
- Preserve XML structure separately from optional evidenced business `review_roles`. Do not require old block_type names or force source paragraphs into legacy special blocks.
- Do not guess localized headings or translate source text. Preserve unclassified structures and flag unsupported review operations.
- Preserve the existing XML POC and its Markdown writer; Markdown is never parsed as Excel/DB input. A constructed ReviewDocument is not a quality-gate pass.
- New v2 execution must fail closed on failed/missing extraction gates and ambiguous language evidence; no GridCell fallback.
- The v1 checklist master remains a frozen source. v2 migration starts from Excel, exports JSON and keeps a profile/version-specific migration audit. No automatic business approval.
- User clarified on 2026-09-11: checklist source_token is source provenance, not an applicability constraint. Rename it source_reference_token in v2 and preserve empty values for manually authored rules. DocumentContext.source_token remains document metadata used by scope/exclude_scope.
- Keep existing public legacy imports while legacy callers still exist. New v2 imports must not depend on them. Their removal belongs to the validated cutover milestone already approved by the user.
- Update only this worktree during migration; original main and XML worktrees may be used by other terminals. Recovery IDs are in `docs/migration/2026-09-10-recovery_kr.md`.
- After v2 changes, run focused tests, the relevant root suite and compileall for existing src/tests/scripts/apps directories. Record exact scope rather than claiming the separate POC suite ran.

## Project Context

- This project builds an internal PDF manual review system.
- Read `README.md`, `TODO.md`, and `SUG_RAW_ANALYSIS.md` before changing review logic or metadata.
- `SUG_RAW_ANALYSIS.md` is a domain analysis document, not an agent instruction file.

## Current Metadata

- The canonical PDF profile metadata is stored in `metadata/pdf_profile_mapping/`.
- `pdf_profile_mapping.json` is the machine-readable source for application logic.
- `pdf_profile_mapping.xlsx` and `pdf_profile_mapping.csv` are maintained for human review and Git diff convenience.

## Sample Data

- Sample SUG PDFs live under `samples/SUG_RAW/`.
- Do not infer operational metadata from sample folder names. Use filename tokens and `pdf_profile_mapping`.

## Mapping Rules

- `source_token` is parsed from the PDF filename as `<buyer_region_token>_<language_token>`.
- `region` means the representative region code, not the broad REGION category from the reference spreadsheet.
- `C-FRA`, `M-SPA`, and `B-POR` are distinct language codes.
- For BOOK PDFs, language order must follow the actual PDF bookmark order.
- `AFRICA MENA_L05` is normalized as `region=AFRICA`, `doc_type=BOOK`.

## Current Code

- Source code is intentionally kept as a flat `src/` package for now.
- Do not split into `domain/application/infrastructure/interfaces` folders until the codebase is large enough to justify it.
- Current modules:
  - `src/models.py`: shared dataclasses.
  - `src/filename_parser.py`: parse manual PDF filenames and source tokens.
  - `src/profile_repository.py`: load `pdf_profile_mapping.json`.
  - `src/profile_lookup.py`: combine filename parsing and profile lookup.
  - `src/pdf_analyzer.py`: analyze PDF page size, orientation, language labels, GridCells, reading order, and BOOK bookmark sections.
  - `src/structure_validator.py`: compare metadata profile with actual PDF structure.
  - `src/text_extractor.py`: extract review text as review items and normalized sentences.
  - `src/excel_exporter.py`: export extracted review text to XLSX for human review.
  - `src/content_poc.py`: current section/block content extraction POC and review XLSX export.
  - `src/cli.py`: temporary developer CLI.

## Implemented Layout Rules

- A2 landscape currently uses `2 x 8` GridCells.
- For A2 landscape, `row=1`, `column=1~2` is treated as cover.
- A3 portrait currently uses `2 x 4` GridCells.
- For A3 portrait, page 1 `row=1`, `column=1~2` is treated as cover; page 2 is content only.
- BOOK A5 portrait currently uses `1 x 2` GridCells.
- BOOK language sections are extracted from PDF bookmarks.
- For BOOK sections, use bookmark language order as the source of truth.
- For BOOK RTL sections, use section reading order instead of physical page order.
- LTR language labels are detected from the top-left corner.
- RTL language labels are detected from the top-right corner.
- LTR GridCell reading order is left-to-right within each row.
- RTL GridCell reading order is right-to-left within each row.
- Single-language A3 PDFs may omit page labels on page 2. Use the profile language as fallback.
- `ZW_TPE` may omit visible language labels entirely. Use profile metadata as fallback.
- Do not infer physical BOOK front/back cover from page number alone.
- BOOK page roles are `section_front_cover`, `content`, `section_back_cover`, and `book_unassigned`.
- `book_unassigned` means outside bookmark-defined language sections, not automatically cover.
- Cover and back-cover areas are review targets; do not lower their priority or exclude them.

## Text Extraction Rules

- GridCell is an intermediate extraction unit, not the final review unit.
- Current content extraction POC groups review text as `language -> section/heading -> block -> lines/sentences`.
- Review Excel should prioritize `lines_text`; sentence arrays may remain in JSON for phrase checks and diffs.
- Bullet/list/table/spec blocks should not be collapsed into generic body text.
- Store profile context with extracted text, especially for English:
  - `language`
  - `source_token`
  - `region`
  - `buyer_codes`
  - `doc_type`
  - `language_variant`
- Current English variants are not yet encoded in metadata. Keep `language_variant=null` until explicit rules exist.
- Navigation/UI text is high risk. Treat navigation and UI labels as candidates for crop/OCR/manual review.
- If navigation text is recoverable, keep it as `navigation_ui`; do not introduce `icon_token` unless text cannot be recovered.
- Safety symbol tables should be extracted as table blocks, with image crops planned for symbol cells.
- Heading-specific rules are required for multilingual stability. English canonical headings should be mapped to localized headings before broad multilingual extraction.
- Use `topic_id` only where stable DB/checklist keys are needed. Keep it in JSON and specialized sheets such as `Regulatory Notes`, but do not show it in the general `Content Review` sheet.

## Verified Samples

- A2: `ZC_L02`, `LATIN_L02`, `MENA_L02`, `TK_L02`, `XT_L02`, `ZX_L02`, `PY_ENRU`, `SQ MI_HEAR`.
- A3: `ZA_ENG`, `ASIA_ENG`, `KR_KOR`, `TK_ARA`, `XD_INS`, `ZW_TPE`.
- BOOK: `AFRICA MENA_L05`, `AFRICA_L05`, `CE_L05`, `XC_L12`, `XH_L16`, `ZG XN ZT_L05`.
- Additional ZC case verified: `BN68-20834D-00_SUG_Y25 TV ALL_ZC_L02_250710.0.pdf`.
- Full structure validation has passed for all current 25 sample PDFs.
- ZC English content extraction POC is stabilized across current available ZC ENG samples:
  - `BN68-20834D-00_SUG_Y25 TV ALL_ZC_L02_250710.0.pdf`
  - `BN68-25100A-00_SUG_Y26 TV ALL_ZC_L02_251222.0.pdf`
  - `BN68-25100B-00_SUG_Y26 TV ALL_ZC_L02_260122.0.pdf`
- Latest verified ZC ENG review output: `outputs/content_poc_review_zc_eng_final_v3/`.
- Current verification: `58` tests passing and `python -m compileall src tests` passing.

## Next Work

- Build localized heading rule mapping, starting with ZC `C-FRA`.
- Compare localized heading order with ENG canonical heading order and expected block sequences.
- Identify non-English regions that still collapse into large body blocks before adding checklist DB rules.
- After C-FRA mapping starts, verify current ENG extraction shape against `ZX_L02`, one A3 English sample, and one BOOK English section.
- Add crop evidence for cover/back-cover, safety symbol tables, navigation/UI blocks, and table-like regions.
- Add OCR decision flow for risky or failed regions.
