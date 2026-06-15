# Agent Working Notes

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
