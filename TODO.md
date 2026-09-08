# TODO

## Current Goal

Build a local Python-based PDF manual review engine for SUG manuals.

The current focus is still extraction quality, not final pass/fail review. The engine must reliably extract document structure, language sections, headings, blocks, tables, model conditions, navigation paths, and review evidence before checklist DB rules are finalized.

## Current Status

### Completed Foundation

- Created canonical PDF profile metadata in `metadata/pdf_profile_mapping/`.
  - `pdf_profile_mapping.json` is the application source.
  - `pdf_profile_mapping.xlsx` and `.csv` are review/diff helpers.
- Implemented filename parsing and `source_token` lookup.
- Implemented profile loading from `pdf_profile_mapping.json`.
- Implemented PDF structure analysis for current sample types.
- Verified current sample PDF structure against profile metadata.
- Implemented GridCell extraction and reading order.
  - A2 landscape: `2 x 8`
  - A3 portrait: `2 x 4`
  - BOOK A5 portrait: `1 x 2`
- Implemented RTL/LTR GridCell reading order.
  - LTR: left to right within each row.
  - RTL: right to left within each row.
- Implemented BOOK language section extraction from PDF bookmarks.
- Implemented BOOK RTL page reading order correction for Arabic.
- Added review-oriented JSON export and Excel review export.

### Completed ZC English Extraction POC

ZC English extraction is now stabilized against current available ZC ENG samples:

```text
BN68-20834D-00_SUG_Y25 TV ALL_ZC_L02_250710.0.pdf
BN68-25100A-00_SUG_Y26 TV ALL_ZC_L02_251222.0.pdf
BN68-25100B-00_SUG_Y26 TV ALL_ZC_L02_260122.0.pdf
```

Latest verified output:

```text
outputs/content_poc_review_zc_eng_final_v3/
```

Verification summary:

- Full tests: `58` tests passing.
- `python -m compileall src tests` passing.
- `26Y A` block sequence matches user-verified `26Y B`.
- `25Y` has a different format, but current checks show no remaining orphan fragments such as `>`, `Auto`, `Frame.`, `.`, or `1. 2. 3.`.
- Current suspicious pattern check found no body blocks containing known bullet-only fragments.

ZC ENG block handling now includes:

- `safety_symbol_table`
- `navigation_ui`
- `item_list`
- `item_list_note`
- `condition_label`
- `procedure_note`
- `numbered_step`
- `figure_notice`
- `figure_legend`
- `figure_action_labels`
- `figure_variant_labels`
- `figure_callout_label`
- `model_condition`
- `spec_table`
- `regulatory_note`

## Current Code Modules

```text
src/
  models.py                shared dataclasses
  filename_parser.py       parse manual PDF filenames and source tokens
  profile_repository.py    load pdf_profile_mapping.json
  profile_lookup.py        combine filename parsing and profile lookup
  pdf_analyzer.py          analyze page size, orientation, language, GridCells, BOOK sections
  structure_validator.py   compare profile metadata with actual PDF structure
  text_extractor.py        extract review text as items, blocks, and normalized sentences
  excel_exporter.py        legacy XLSX exporter for extracted review text
  content_poc.py           current section/block content extraction POC and review export
  cli.py                   temporary developer CLI
```

## Current Extraction Decisions

### Review Unit

GridCell is an intermediate extraction unit only.

The future review unit is:

```text
language
  section / heading
    block
      lines
      sentences
      structured rows when table/spec/list
```

GridCell/page/cell coordinates should remain as provenance fields, not final review grouping.

### Lines and Sentences

Keep both `lines` and `sentences` internally, but review Excel should prioritize `lines_text`.

Reason:

- Block/line level is more stable for multilingual DB management.
- A single English sentence may become 2-3 sentences in another language.
- Sentence level is still useful for phrase checks and diffs.

### Topic IDs

Use `topic_id` only where a stable DB/checklist key is necessary.

Current rule:

- Keep `topic_id` in JSON.
- Show `topic_id` in `Regulatory Notes`.
- Do not show `topic_id` in the general `Content Review` sheet.

### Navigation and Icons

If navigation text is recoverable, keep it as `navigation_ui`.

Do not introduce `icon_token` unless navigation text cannot be recovered or an icon-only instruction becomes a required checklist item.

For navigation paths that start with a button-only vector icon, keep the block as `navigation_ui` and evaluate inline `btn_*` tokens only when the icon is needed to preserve the path meaning. Current candidate:

- home button at the start of navigation paths => `{btn_home}`

### English Variants

Do not store English text as only `ENG`.

Always preserve profile context:

```text
language=ENG
source_token=ZC_L02
region=ZC
buyer_codes=ZC
doc_type=A2
language_variant=null
```

Future checklist DB should allow:

```text
ENG / GLOBAL
ENG / US
ENG / UK
ENG / CA
ENG / source-token-specific exception
```

## Heading-Based Extraction Rules

Heading-specific behavior is required for multilingual stability.

English canonical headings should become stable rule keys. Localized headings must be mapped and checked before broad multilingual extraction.

Current ZC ENG canonical rule examples:

```text
Warning! Important Safety Instructions
- safety symbol content => safety_symbol_table
- include split table rows even when final row moves to adjacent cell

Safety Precaution
- warning intro => body
- precaution items => bullet
- remove numeric layout artifacts such as "1. 2. 3."

Preventing the TV from falling
- "Wall-anchor (not supplied)" => procedure_note
- procedure text => numbered_step
- do not rely only on extracted step numbers

Internet security / Troubleshooting / Eco Sensor and screen brightness
- navigation paths => navigation_ui
- merge split UI/navigation fragments

01 Package Content
- package items => item_list
- "*:" and "**:" notes => item_list_note

Using the TV Controller
- figure legend labels => figure_legend

02 Connecting the TV to the One Connect Box
- model scoped text => condition_label
- Bending/Twisting/Pulling/Pressing on/Electric shock => figure_action_labels

How to turn on and off the Microphone
- Type A/B/C/D => figure_variant_labels
- On/Off Switch => figure_callout_label
- model applicability text => model_condition with parsed model list

Specifications
- Display Resolution and Sound (Output) => spec_table
- inline model/value attached to heading must be included in spec_table
- Operating/Storage Temperature/Humidity => common_required_spec table

Notes
- regulatory note topics => regulatory_note with topic_id
```

## Next Work

### Tagged PDF XML/Markdown Review Follow-ups

- Implement the approved cross-profile readability and multilingual-heading
  parity design. Capture optional MCID text BBoxes, protect spaced
  abbreviations, split eligible leaf-body sentences, recover only fully
  evidenced list-continuation paragraphs, support single-paragraph table
  subtitles, and apply heading parity to every canonical profile with
  `language_count >= 2`.
  - Design: `docs/superpowers/specs/2026-09-08-cross-profile-readability-and-heading-parity-design.md`
  - Korean review copy: `docs/superpowers/specs/2026-09-08-cross-profile-readability-and-heading-parity-design_kr.md`
- [x] Preserve complex table structure in `samples/tagged_pdf_xml_poc` Markdown output instead of flattening nested paragraphs and lists into a single `- 행 N:` line.
- [x] Add typography-backed subtitle display hints. Do not hardcode `Correct Disposal...` wording; use verified structure plus relative PDF font weight and keep uncertain cases as separate plain paragraphs.
- Add a conservative verified-icon catalog for recurring icon-only figures. Name only verified matches, retain evidence, and leave unknown icons for human review.
- [x] Preserve source-authored comma-following RF line breaks for the verified `ZG XN ZT_L05 + BOOK` profile, with ZC/ZA/XY/KR negative regression controls.
- [x] Implement the detailed hierarchy under `Declaration of Conformity` using a complete structure-and-relative-typography cluster: title as a level-2 heading, verified labels in bold, and detail paragraphs kept separate. Runtime detection contains no title or translation dictionary.
- Later, install and integrate local Tesseract OCR for targeted risky regions rather than whole-page OCR. First target: extract the PDF-visible manual code such as `BN68-25100B-00`, retain crop/confidence evidence, and compare it with the filename manual code and version. A filename-derived value must never be reported as PDF-observed OCR text.

Design references:

- `docs/superpowers/specs/2026-09-05-semantic-markdown-icon-review-design.md`
- `docs/superpowers/specs/2026-09-05-zg-rf-doc-markdown-formatting-design.md`

### 1. Build Localized Heading Rule Mapping

Before broad multilingual extraction, create a canonical heading rule table:

- map English canonical headings to localized heading text
- verify localized heading order against the PDF
- apply expected block sequence per canonical heading
- flag unmatched or ambiguous translated headings for manual review
- check whether localized headings are literal translations or region-specific variants

Suggested output shape:

```text
canonical_heading_id
english_heading
localized_heading
language
source_token
heading_match_method
expected_block_sequence
status
manual_review_note
```

### 2. Start C-FRA Validation for ZC_L02

Use ZC C-FRA as the first multilingual validation target because ZC PDFs include `ENG` and `C-FRA`.

Goal:

- Compare C-FRA heading order with ENG canonical heading order.
- Confirm localized heading detection.
- Apply heading-based expected block rules.
- Identify where non-English extraction still collapses into large body blocks.
- Check whether navigation paths with leading home-button vectors fragment in C-FRA; if they do, decide whether to normalize them with `{btn_home}` inside `navigation_ui`.

Important current limitation:

- Non-ENG extraction is still coarse compared with ENG and needs improvement before C-FRA can be considered stable.

### 3. Generalize Current ENG Rules Without Overfitting

After C-FRA heading mapping starts, verify the same extraction shape against:

```text
ZX_L02 English
one A3 English sample
one BOOK English section
```

Goal:

- avoid overfitting to `ZC_L02`
- validate A2/A3/BOOK heading and block rules
- check English variant differences
- prepare for checklist DB and multilingual alignment

### 4. Add Crop Evidence for Risky Blocks

Create image crops for:

- cover cells
- section front/back cover pages
- safety symbol table
- navigation/UI blocks
- figure/action label blocks
- table-like regions

Store crop paths in JSON and include them in review reports.

### 5. Add OCR Decision Flow

Do not OCR every page by default.

Recommended flow:

```text
1. Try PyMuPDF text extraction.
2. Check char count, empty cells, suspicious UI/table/cover blocks.
3. Apply OCR only to risky regions or failed regions.
4. Compare OCR text with PyMuPDF text.
5. Mark manual_review_required when disagreement is high.
```

## Next Start Prompt

Use this prompt when starting the next session:

```text
C:\Users\bella\image-extractor 프로젝트를 이어서 진행할거야.

먼저 AGENTS.md, TODO.md, SUG_RAW_ANALYSIS.md를 읽고 현재 상태를 파악해줘.

현재까지 ZC_L02 ENG content extraction POC는 아래 샘플 기준으로 안정화했어.

- BN68-20834D-00_SUG_Y25 TV ALL_ZC_L02_250710.0.pdf
- BN68-25100A-00_SUG_Y26 TV ALL_ZC_L02_251222.0.pdf
- BN68-25100B-00_SUG_Y26 TV ALL_ZC_L02_260122.0.pdf

최신 산출물은 outputs/content_poc_review_zc_eng_final_v3/ 에 있어.
26Y B는 사람이 확인한 기준 파일이고, 26Y A는 B와 block sequence가 동일한 것으로 확인했어.
25Y는 포맷 차이가 있지만 현재 의심 패턴 검사까지 통과했어.

다음 작업은 다국어 확장 전 단계로, ZC C-FRA를 대상으로 localized heading mapping을 시작하는 거야.

진행 순서:

1. TODO.md와 SUG_RAW_ANALYSIS.md의 Heading-Based Block Rules 확인
2. ZC_L02 ENG canonical heading 목록 추출
3. 같은 PDF의 C-FRA heading 후보 추출
4. ENG canonical heading과 C-FRA localized heading을 매핑
5. heading order와 expected block sequence를 비교
6. C-FRA에서 large body로 뭉치는 구간을 찾아 원인 분석
7. 바로 고치기보다 먼저 heading mapping/schema를 안정화

주의:

- C-FRA는 아직 ENG처럼 세밀하게 추출되지 않을 수 있어.
- 다국어에서는 heading 번역어가 영문과 같은 의미인지 체크가 필요해.
- 같은 canonical heading이면 같은 block rule이 적용되어야 해.
- navigation이 텍스트로 정상 추출되면 icon_token은 만들지 않아.
- 섣불리 DB schema를 확정하지 말고 extraction 안정화를 우선해줘.
```

## Deferred

- Checklist DB final schema
- Required phrase authoring
- Full multilingual alignment
- Model/spec validation against model system data
- Image/icon similarity review
- Previous-version diff
- Streamlit/FastAPI UI
- Report format finalization
