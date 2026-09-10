# TODO

## Active XML review v2 migration — 2026-09-10

이 절이 새 v2 작업의 현재 상태다. 아래 GridCell/MVP 기록은 과거 구현 이력이다.

- [x] 복구 커밋 `4b001ff9a1a4f8ef91bed75a8ab314f4189d9476`, XML 기준 `840512002a80a12b19c712116530ab69b1459c3a` 보존.
- [x] 두 기준점의 complete Git bundle 검증 및 `codex/xml-review-v2` worktree 생성.
- [x] 마이그레이션 명세, 복구 안내, ReviewDocument 설계 및 1단계 구현 계획 작성.
- [x] `src/review_document.py`: 구조/텍스트 순서/근거/선택적 review_role 보존 모델. 새 테스트 46개 통과.
- [ ] 실제 XML writer/report schema 기반 adapter와 fail-closed gate 설계·구현. 기존 XML POC의 네 산출물과 Markdown 표현 유지.
- [ ] Master Excel/JSON 일치 확인, v2 이관표/이관 감사 및 체크리스트 evaluator 구현.
- [ ] 추출 검수 Excel와 최종 검토 Excel의 실제 표본 선정·양식 명세·새 exporter 구현.
- [ ] ReviewService/CLI, Streamlit 연결 및 프로필별 결과 검증.
- [ ] 사용자 양식 검수, 설명되지 않는 차이 해소, GridCell active 코드 정리 및 PC 배포.

검증: 루트 `python -m pytest tests -q` 108 passed / 6 subtests passed; `python -m compileall -q src tests` 통과. 변경 범위 검사 통과.
이번 기준 테스트 범위는 루트 suite다. XML POC 전체 suite를 이번 모델 변경의 결과로 다시 통과했다고 보고하지 않는다.
메인의 기존 DB와 기존 추출기는 변경하지 않았다. 자세한 복구 범위는 `docs/migration/2026-09-10-recovery_kr.md`를 읽는다.

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

- [x] Task 8: gate cross-profile readability and multilingual-heading parity
  against the exact ZG, ZC, LATIN, KR, and XU real PDFs. Shared evidence policy:
  BBoxes and detector reasons remain optional XML/report audit evidence; Raw XML
  text and Markdown stay free of detector attributes; sentence, continuation,
  subtitle, and heading-parity decisions fail closed unless every required
  generic structure/geometry/typography condition is present. This policy adds
  no buyer, phrase, language-combination, translation, or localized-heading mapping.
  - Design: `docs/superpowers/specs/2026-09-08-cross-profile-readability-and-heading-parity-design.md`
  - Korean review copy: `docs/superpowers/specs/2026-09-08-cross-profile-readability-and-heading-parity-design_kr.md`
  - Real-PDF gate: `37 passed`; full POC gate after independent review fixes:
    `1709 passed, 1 skipped` (Windows symlink capability only). All five reports
    are `status=pass`, with ZG/ZC/LATIN
    multilingual audits `passed` and KR/XU `not_applicable`; no failed hard gate,
    text-quality page, or quality diagnostic remains.
  - Outputs: `samples/tagged_pdf_xml_poc/outputs/cross_profile_readability_zg_260908`,
    `..._zc_260908`, `..._latin_260908`, `..._kr_260908`, and `..._xu_260908`.
  - ZG manual review confirmed protected `z. B.`, reviewed DEU/FRA sentence
    boundaries, one FRA target continuation, the evidenced ITA inline disposal
    subtitle, navigation paths, icon parity, and clean localized text.
  - XU manual review confirmed that `Warranty Card` and `WARRANTY CONDITIONS`
    remain PDF `Heading2` source-role candidates rendered as Markdown `###`, and
    that RF maximum-transmitter-power plus `[QN990H]` remain in one table. No
    translated heading mapping was added. Current blocker: none.
  - Independent review fixes: flush geometry before position changes, model
    character spacing while failing closed for unsupported word-spacing/text-rise
    geometry, derive named language combinations from canonical JSON rows, and
    keep sentence detection out of the Markdown writer. XU non-empty `(0,0)`
    text BBoxes after regeneration: 0.
- [x] Preserve complex table structure in `samples/tagged_pdf_xml_poc` Markdown output instead of flattening nested paragraphs and lists into a single `- 행 N:` line.
- [x] Add typography-backed subtitle display hints. Do not hardcode `Correct Disposal...` wording; use verified structure plus relative PDF font weight and keep uncertain cases as separate plain paragraphs.
- Add a conservative verified-icon catalog for recurring icon-only figures. Name only verified matches, retain evidence, and leave unknown icons for human review.
- [x] Preserve source-authored comma-following RF line breaks across profiles when
  the tagged PDF provides the same explicit newline inside a table cell. ZG
  retains 90 preserved boundaries and XU adds 18; ordinary commas and unsupported
  newline shapes remain unchanged. Declaration-of-Conformity typography formatting
  remains independently scoped to `ZG XN ZT_L05 + BOOK`.
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
