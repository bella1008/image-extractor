# SUG_RAW Sample Analysis

This is a domain analysis document, not an agent instruction file.

This file is the original working analysis document for the SUG_RAW sample set.
It now combines the current sample findings with the direction from
`C:\Users\bella\Documents\명세서.md`.

## Product Direction

The project is a local Python-based PoC for automatic review of multilingual PDF
manuals.

Primary goal:

- Parse layout-based PDF structure.
- Extract multilingual manual text in a stable review unit.
- Build a future multilingual master DB.
- Compare extracted text and specification values against master/checklist/spec DBs.
- Detect missing, incorrect, or suspicious content automatically.
- Provide review evidence for manual confirmation where full automation is risky.

Operating assumption:

- Local PC environment.
- Network and external cloud usage may be restricted.
- The first target is a reliable local review engine, not a full enterprise system.

Success criteria for the early phase:

- Do not aim for 100% automatic pass/fail immediately.
- Produce reliable extracted evidence.
- Mark risky regions for manual review.
- Reduce repeated manual checking and missing-item risk.

## Recommended Technical Direction

Current PoC stack:

- Python 3.10+
- PyMuPDF for PDF parsing
- JSON and XLSX outputs for review

Recommended future stack:

- SQLite for local PoC DB
- PostgreSQL or internal RDBMS later if the tool becomes operational
- Streamlit for quick internal MVP UI, or FastAPI + React for a longer-term app
- OCR only for risky or failed extraction regions, not every page by default
- Local embedding model or approved internal AI API for semantic similarity checks

## Target Review Workflow

```text
User input
  |
  |-- new PDF
  |-- previous PDF
  |-- model code
  |-- buyer / country
  |-- review options
  v

PDF analysis
  |
  |-- document type detection
  |-- page structure analysis
  |-- language section splitting
  |-- text extraction
  |-- table / image / icon extraction candidates
  |-- OCR/manual-review candidates
  v

Review execution
  |
  |-- checklist phrase review
  |-- model specification validation
  |-- buyer/country image and icon review
  |-- previous-version comparison
  v

Result report
  |
  |-- pass/fail candidates
  |-- manual review required items
  |-- changed sections
  |-- evidence crops / extracted text
  |-- execution logs
```

## Future Agent Responsibilities

The extraction engine being built now is the foundation for these later agents.

### PDF Extraction Agent

Extract source evidence from PDFs:

- filename/profile lookup
- page size and document type
- A2, A3, and BOOK layout structure
- language section splitting
- GridCell reading order
- section/block text extraction
- table candidates
- image/icon candidates
- OCR decision flags

This is the current active development area.

### Checklist Review Agent

Use checklist/master DB rules to check:

- required phrases by buyer/country
- required phrases by language
- product/model conditional phrases
- missing phrases
- similar but incorrect phrases
- prohibited phrases

### Spec Validation Agent

Use model code and spec DB values to check:

- voltage
- frequency
- dimensions
- weight
- capacity
- other model-specific values

Formatting variants such as `220V`, `AC 220 V`, and `220-240V~` will need
normalization rules before comparison.

### Image/Icon Review Agent

Review visual requirements:

- required icon existence
- image/icon similarity against reference assets
- location within language or buyer-specific region
- evidence crop for manual confirmation

Initial approach should be automatic detection plus manual confirmation, not
fully automatic judgment.

### Diff Review Agent

Compare new PDF against previous PDF:

- extracted text differences
- section-level changes
- language-level changes
- intended checklist changes vs unexpected changes
- review-focused change summary

### Report Generation Agent

Create human-readable review outputs:

- overall status summary
- failed items
- manual review items
- previous-version differences
- page/language/section evidence
- HTML, Excel, and later PDF reports

## Future DB Direction

Use a tag-based single DB concept for multilingual and country-specific review
rules.

The DB should not store only sentence-by-sentence text. The safer unit is a
logical block with sentence details below it.

Target review unit:

```text
language
  section / heading
    block
      sentence
```

Recommended master block fields:

```text
Block_ID
Heading_Anchor
Base_EN_Text
Tags
Translations
```

Translation handling should allow one English block to become multiple child
translation blocks:

```json
{
  "Block_ID": "SEC-001",
  "Heading_Anchor": "Operation",
  "Base_EN_Text": "Press the desired button to confirm the setting.",
  "Tags": ["Common", "Operation"],
  "Translations": [
    {
      "Lang": "FR",
      "Child_ID": "SEC-001.a",
      "Text": "Appuyez sur le bouton souhaite."
    },
    {
      "Lang": "FR",
      "Child_ID": "SEC-001.b",
      "Text": "Cela confirmera le reglage."
    }
  ]
}
```

Reason:

- English one sentence may become two or three sentences in another language.
- Bullet-level or block-level review is more stable for multilingual DB use.
- Sentence arrays are still useful for phrase checks, diffs, and semantic review.

## Sample Set

Current sample PDFs live under:

```text
samples/SUG_RAW/
```

The current sample set contains 25 PDFs.

Do not infer operational metadata from folder names such as `TV_ZC` or
`TV_AFRICA`. Folder names are only for sample organization. Application logic
must use filename tokens and:

```text
metadata/pdf_profile_mapping/pdf_profile_mapping.json
```

## Metadata Rules

Canonical profile fields:

```text
source_token
region
buyer_codes
languages
doc_type
language_count
```

Important rules:

- `source_token` is parsed from the PDF filename as `<buyer_region_token>_<language_token>`.
- `region` is the representative region code, not a broad spreadsheet category.
- `C-FRA`, `M-SPA`, and `B-POR` are distinct language codes.
- BOOK language order follows actual PDF bookmark order.
- `AFRICA MENA_L05` is normalized as `region=AFRICA`, `doc_type=BOOK`.

## Page Sizes

Observed SUG sample page sizes:

| Name | PDF size |
|---|---|
| A5 | `466.5 x 642.3` |
| A3 | `888.9 x 1237.6` |
| A2 | `1730.8 x 1237.6` |

## Document Types

### A2

Rules:

- A2 landscape.
- `2 x 8` GridCells.
- `row=1`, `column=1~2` is cover.
- Remaining cells are content.
- LTR language labels are detected from the top-left corner.
- RTL language labels are detected from the top-right corner.
- LTR cell reading order is left-to-right within each row.
- RTL cell reading order is right-to-left within each row.

Verified tokens:

```text
ZC_L02
LATIN_L02
MENA_L02
TK_L02
XT_L02
ZX_L02
PY_ENRU
SQ MI_HEAR
```

Notes:

- `MENA_L02` page 2 is Arabic and uses RTL reading order.
- `SQ MI_HEAR` contains Hebrew and Arabic; both use RTL reading order.
- `PY_ENRU` language order is `RUS`, `ENG` per profile and detected labels.

### A3

Rules:

- A3 portrait.
- `2 x 4` GridCells.
- Page 1 `row=1`, `column=1~2` is cover.
- Page 2 is content only.
- Single-language A3 PDFs may omit page labels on page 2. Use profile language
  as fallback.
- LTR/RTL GridCell reading order follows the detected or fallback language
  direction.

Verified tokens:

```text
ZA_ENG
ASIA_ENG
KR_KOR
TK_ARA
XD_INS
ZW_TPE
UA_ENG
XU_ENG
XY_ENG
```

Notes:

- `ZW_TPE` may omit visible language labels entirely. Use profile metadata as
  fallback.
- Avoid treating body headings such as `Operation` as language labels. Only
  language-code patterns are labels.

### BOOK

Rules:

- A5 portrait.
- `1 x 2` GridCells.
- PDF bookmarks are the primary language section source.
- Bookmark language order is the source of truth.
- Language sections provide page ranges and reading order.
- For RTL sections, use section reading order instead of physical page order.
- Physical first/last page is not automatically front/back cover.

BOOK page roles:

```text
section_front_cover
content
section_back_cover
book_unassigned
```

`book_unassigned` means the page is outside bookmark-defined language sections.
It is not automatically a cover.

Verified tokens:

```text
AFRICA MENA_L05
AFRICA_L05
CE_L05
XC_L12
XH_L16
ZG XN ZT_L05
```

BOOK bookmark language codes:

```text
AFRICA MENA_L05: ENG, FRA, SPA, POR, ARA
AFRICA_L05:      ENG, FRA, SPA, POR, ARA
CE_L05:          RUS, ENG, KAZ, MON, KYR
XC_L12:          ENG, FRA, SPA, POR, DEU, SWE, DAN, NOR, FIN, CAT, GLG, EUS
XH_L16:          ENG, HUN, POL, GRE, BUL, CRO, CZE, SLK, ROM, SER, ALB, MKD, SLV, LAT, LTU, EST
ZG XN ZT_L05:    ENG, DEU, FRA, ITA, DUT
```

## Structure Validation Status

Current full-sample structure validation:

```text
25 samples
0 failures
```

Verified dimensions:

- profile `doc_type` vs detected document type
- profile `language_count` vs detected language count
- profile `languages` vs detected language order
- GridCell reading order sanity
- BOOK bookmark section extraction

## Current Text Extraction Findings

First-pass English extraction was tested with:

```text
ZC_L02
BN68-25100B-00_SUG_Y26 TV ALL_ZC_L02_260122.0.pdf
```

Generated artifacts:

```text
outputs/text_extraction/ZC_L02_ENG.json
outputs/text_extraction/ZC_L02_ENG_review_cover_schema.xlsx
outputs/text_extraction/ZC_L02_ENG_cover_audit.json
```

Extraction status:

```text
method: pymupdf_text
language: ENG
ocr_applied: false
```

Current extracted item/block kinds:

```text
heading
body
bullet
warning
navigation
navigation_ui
list_item
ui_label
safety_symbol_table
contact_table
```

Important conclusion:

GridCell is useful for extraction order, but it should not be the final review
unit. Final review should be section/block based. GridCell data remains as
provenance.

## Special Extraction Risks

### Cover and Back Cover

Cover and back-cover areas are review targets and must not be excluded or
treated as lower priority.

They often contain:

- contact information
- model/serial fields
- websites
- irregular tables
- icons
- document code and copyright

Required handling:

```text
text extraction
schema-based region classification
table extraction where applicable
image crop
OCR/manual review flag
```

Current ZC English cover schema:

```text
schema_id = ZC_A2_ENG
required_regions:
  language_label
  title
  model_serial_fields
  support_note
  disclaimer
  contact_heading
  contact_table
  copyright
  document_code
optional_regions:
  contact_note
  address
```

ZC cover observations:

- Contact note should follow the contact heading.
- `Samsung Service Center` and `Website` are one visual contact table.
- Older ZC samples may also include an `Address` column in the same table.
- Copyright and document code should be ordered as final footer regions.
- Product registration URL in the cover body is not the same as contact-table
  support URLs.

### Safety Symbol Table

`ZC_L02` English GridCell reading order 3 contains the safety symbol explanation
table.

It should be extracted as a table block, not plain body text:

```text
block_type = safety_symbol_table
rows:
  symbol_image_crop
  label
  description
```

This area is expected to need image extraction because symbol images are part of
the table.

### Navigation and UI

Navigation and UI text is high risk because icons and text are mixed.

Required handling:

```text
raw_text
normalized_text
image_crop
ocr_text
manual_review_required
```

Navigation text should generally be treated as UI text, not ordinary body text.

### Heading Detection

Heading detection should use text content and style.

Useful signals:

- bold
- underline
- font size
- short title-like text
- no terminal period
- followed by explanatory body text

Example that should be treated as a heading:

```text
Mounting the TV on a wall
```

### Heading-Based Block Rules

For multilingual extraction, section handling should be driven by a stable
heading rule table instead of only row/column position. The English heading is
the first canonical key, and each target language must be checked against the
translated heading text before using the same rule.

Recommended rule fields:

```text
canonical_heading_id
english_heading
localized_heading
heading_match_method
expected_block_sequence
special_split_rule
required_block_types
model_condition_rule
navigation_rule
table_rule
manual_review_required
```

Current ZC English heading rules:

```text
Warning! Important Safety Instructions
- Keep safety symbol content as safety_symbol_table.
- Include split table rows even when the final row moves to an adjacent cell.

Safety Precaution
- Keep warning intro as body.
- Split each precaution item into bullet blocks.
- Remove stray numeric layout artifacts such as "1. 2. 3.".

Preventing the TV from falling
- Keep "Wall-anchor (not supplied)" as procedure_note.
- Split the following procedure into numbered_step blocks.
- Do not rely only on visible extracted numbers; use step start phrases/layout
  fragments as fallback because numbers can be lost during extraction.

Internet security / Troubleshooting / Eco Sensor and screen brightness
- Keep navigation paths as navigation_ui.
- Merge UI/navigation fragments across adjacent items when the path is split.
- Do not introduce icon_token unless navigation text cannot be recovered.

01 Package Content
- Keep package items in item_list.
- Keep "*:" and "**:" notes outside item_list as item_list_note.

Using the TV Controller
- Keep figure legend labels as figure_legend.

02 Connecting the TV to the One Connect Box
- Keep model-scoped labels such as "(One Connect Box Supported Model only)" as
  condition_label.
- Keep figure action words such as Bending/Twisting/Pulling/Pressing on/Electric
  shock as figure_action_labels.

How to turn on and off the Microphone
- Keep Type A/B/C/D as figure_variant_labels.
- Keep On/Off Switch as figure_callout_label.
- Merge split model applicability text into one model_condition block and parse
  model names separately.

Specifications
- Keep Display Resolution and Sound (Output) as spec_table.
- If the first model/value is attached to the heading, split the heading and
  include the inline value in the spec_table.
- Keep Operating/Storage Temperature/Humidity as common_required_spec tables.

Notes
- Keep regulatory topics as regulatory_note with topic_id in JSON and the
  Regulatory Notes sheet.
```

For each new language, verify:

- localized heading text matches the intended canonical heading
- translated heading order follows the source PDF order
- expected block_type sequence matches the canonical rule
- model conditions remain separate from body text
- navigation is recovered as navigation_ui or marked for crop/manual review
- table/list/note blocks are not collapsed into body text

## Checklist DB Direction

The checklist DB should be review-rule data, not only a phrase list.

Recommended fields:

```text
check_id
buyer / country
language
product family
model condition
required phrase
allowed similar phrase
required keyword
prohibited phrase
required image or icon
effective_start_date
effective_end_date
source standard or internal document
severity
review_method
exception condition
```

Severity examples:

- `Critical`: regulation, safety, certification
- `Major`: specification, model information, core user guidance
- `Minor`: expression, format, recommended wording

Review method examples:

- exact match
- contains
- semantic similarity
- regular expression
- manual confirmation

## MVP Scope

Recommended first MVP:

- one new PDF
- one previous PDF
- model code input
- two or three priority languages
- 20 to 50 checklist rules
- required phrase existence review
- previous-version text diff
- execution log
- Excel or HTML report

Do not finalize the full DB schema before extraction quality is stable.

## Current ZC English Content POC Status

`ZC_L02` English content extraction has been stabilized against the currently
available ZC ENG samples:

```text
BN68-20834D-00_SUG_Y25 TV ALL_ZC_L02_250710.0.pdf
BN68-25100A-00_SUG_Y26 TV ALL_ZC_L02_251222.0.pdf
BN68-25100B-00_SUG_Y26 TV ALL_ZC_L02_260122.0.pdf
```

Latest verified output:

```text
outputs/content_poc_review_zc_eng_final_v3/
```

Current verification:

- `58` tests passing
- `python -m compileall src tests` passing
- `26Y A` block sequence matches the user-reviewed `26Y B`
- `25Y` has a different format, but no remaining known orphan-fragment or
  bullet/body collapse patterns were found in the latest check

## Next Analysis Targets

After `ZC_L02` English stabilization, start localized heading validation:

```text
ZC_L02 C-FRA
ZX_L02 English
one A3 English sample
one BOOK English section
```

Purpose:

- map English canonical headings to localized headings
- verify localized heading order and expected block sequences
- find non-English regions that still collapse into large body blocks
- avoid overfitting extraction rules to one ZC sample/type
- verify heading/block extraction across layout types
- check English variant differences for future DB management
- prepare data shape for the future master/checklist DB
