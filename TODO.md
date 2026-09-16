# TODO

## Current Goal

- 2026-09-17 MENA_L02(A2 ENG/ARA) / XL_ENG(A3 ENG) / XT_L02(A2 ENG/THA) XML 추출 검증 완료.
  최신 검토 시작: `samples/tagged_pdf_xml_poc/outputs/xml_review_mena_xl_xt_20260917_ready/review.html`.
  각 바이어 폴더에 semantic XML/MD/전체 HTML, raw XML, report/review_run/source_audit가 있다.
  Hard gate 0; 전체 2,391 passed / 1 Windows symlink skip, 비교 화면/제목 추가 9 passed.
  기존 10개 프로필의 XML/MD 30파일 바이트 동일. XL은 공식 프로필 부재로 검토용 overlay만 사용했다.
  MENA 원문 ActualText/RTL·표지·연락처, XL 사양 소수·문장 소속, XT 내장 글꼴의 태국어 매핑을 검증했다.
  TK 비교 화면 RTL 방향만 새 폴더 `outputs/xml_review_tk_20260917_direction_review`에 갱신했으며 추출/전체 HTML 10파일은 동일.
  사용자 컨펌은 MENA/XL/XT/TK/ZW 모두 대기 상태; 원문 표현·비텍스트 Warning은 후속 사람 검토 대상으로 유지.
  상세: `samples/tagged_pdf_xml_poc/docs/reviews/2026-09-17-mena-xl-xt-xml-review.md`.

- 2026-09-16 TK ARA 제목 대응표의 `0 1`~`0 5` 표시 오류 수정.
  전체 MD는 원래 `01`~`05` 정상이며, 대응표가 raw 숫자 조각을 별도로 합치던 결함이었다.
  본문 writer와 동일한 원문 번호 검증을 사용하고 ARA 표 번호는 LTR isolate 처리.
  최신 TK 검토: `samples/tagged_pdf_xml_poc/outputs/xml_review_tk_20260916_heading_review/tk_review.html`.
  3언어 제목 72개 본문 대조 및 숫자 5개의 브라우저 위치/간격 PASS, 집중 294 passed, compileall 성공.
  기존 추출 XML·MD·보고서·전체 HTML 10개는 바이트 동일. 이전 출력은 보존.

- 2026-09-16 TK 사용자 검토와 별도로 ZW_TPE / A3 / TPE 추출 검증 완료, 사용자 검토 대기.
  원본 `samples/SUG_RAW/2_TV_ZW/BN68-24973D-00_SUG_Y26 TV ALL_ZW_TPE_260327.0.pdf`.
  시작 HEAD `e06b998844e3b09887e612f4f22940abffeac2a4`, clean 상태.
  XML 경로에서 겹쳐 그린 글자, 표지 순서, 전원 문장 소속, CJK 줄 연결 및 RoHS 병합 셀 검증.
  최종: `samples/tagged_pdf_xml_poc/outputs/xml_review_zw_20260916_source_verified/zw_review.html`.
  Hard gate 0; 제목 24, 검토 단위 122, 표 17, 모델·소비전력 49쌍, RoHS 36셀.
  전체 XML 2,311 passed / 1 Windows symlink skip, 집중 432 passed, 추가 무결성 6 passed.
  기존 7개 바이어 + TK 2종의 XML·MD 27파일 바이트 동일. 원문 표현/비텍스트 Warning 4범주.
  보고서: `samples/tagged_pdf_xml_poc/docs/reviews/2026-09-16-zw-xml-review.md`.
  계획: `samples/tagged_pdf_xml_poc/docs/plans/2026-09-16-zw-extraction.md`.

- 2026-09-15 사용자가 대표 바이어 결과의 추가 검토가 필요 없음을 확인하고 TK 추출을 승인했다.
  TK_L02 A2 ENG/TUR 및 TK_ARA A3의 XML 추출·원문 구조 검증 완료.
  최종: `samples/tagged_pdf_xml_poc/outputs/xml_review_tk_20260915_source_verified/tk_review.html`.
  Hard gate 0, XML→MD 360개 단위 PASS, 공백 경계 8곳 및 RTL 모델 별표 검증.
  원문 편집 후보 7건은 별도 보존. 전체 XML 2,264 passed / 1 symlink skip, TK 집중 148 passed.
  기존 7개 바이어의 XML·MD 21파일 바이트 동일. 현재 XML 라인 커버리지 95.81%, 분기 91.30%.
  계획: `docs/superpowers/plans/2026-09-15-tk-xml-review.md`.

- 2026-09-15 대표 바이어 문장 소속의 잔여 8건을 수정·검증했다.
  ZC C-FRA / AFRICA ARA 전원 연속문장, ZG 5언어 / XU ENG 비용 하위 조건.
  ZC/CE/AFRICA/ZG 집중, XU A3 해당 구조, KR/LATIN 자동 회귀를 수행했다.
  최종: `samples/tagged_pdf_xml_poc/outputs/xml_review_common_20260915_verified/ownership_findings.html`.
  31개 소속 관계 및 XML→MD 2,489개 검토 단위 PASS, 이번 범위 Hard gate 0.
  전체 2,082 passed / 1 Windows symlink skip. CE/KR/LATIN XML·MD 바이트 동일.
  보고서: `samples/tagged_pdf_xml_poc/docs/reviews/2026-09-15-representative-paragraph-ownership.md`.
  이후 TK_L02 ENG/TUR → TK_ARA A3는 위 최신 항목에서 추출 검증을 완료했다.

- 2026-09-14 CE 문장 소속 수정 후 기존 바이어 5개/15언어를 재추출하여 같은 두 관계를 감사했다.
  새 미해결 구조 문제: ZC C-FRA 및 AFRICA ARA의 전원 연속문장 2곳,
  ZG ENG/DEU/FRA/ITA/DUT 및 XU ENG 비용 하위 조건 6곳. 당시 8개는 수정 전이었으며 위 2026-09-15 작업에서 해소했다.
  기존 회귀 PASS가 해당 관계 전체의 검토 완료를 의미하지 않음을 확인했다.
  감사: `samples/tagged_pdf_xml_poc/outputs/xml_review_cross_buyer_20260914_ownership_audit/ownership_findings.html`.
  보고서: `samples/tagged_pdf_xml_poc/docs/reviews/2026-09-14-cross-buyer-paragraph-ownership-audit.md`.
  CE 5언어의 직전 수정 결과는 유지되며, 이 감사로 다른 바이어를 재승인하지 않는다.

- 2026-09-14 CE 5언어 전원 불릿의 연속문장 및 서비스 비용 하위 조건 소속을 수정 검증했다.
  최신 출력: `samples/tagged_pdf_xml_poc/outputs/xml_review_ce_20260914_paragraph_final`.
  최신 HTML: `samples/tagged_pdf_xml_poc/outputs/xml_review_ce_20260914_paragraph_review/semantic_document.preview.html`.
  수정부 PDF/HTML 비교: 같은 폴더의 `paragraph_findings.html`.
  전체 1,980 passed / 1 symlink skip, CE 관련 65개 포함. Hard gate 잔여 0.
  원문 표현 6건 사용자 PASS 및 향후 편집 에이전트 사례는 승계한다.
  보고서: `samples/tagged_pdf_xml_poc/docs/reviews/2026-09-14-ce-paragraph-ownership.md`.

- 2026-09-14 AFRICA 전 언어 사용자 검토 완료를 확정했다. CE_L05 BOOK의 실제 북마크 순서
  RUS → ENG → KAZ → MON → KYR로 추출 구조 검증을 진행했고 Hard gate는 해소했다.
  최종 출력: `samples/tagged_pdf_xml_poc/outputs/xml_review_ce_20260914_final`.
  검토 시작: `samples/tagged_pdf_xml_poc/outputs/xml_review_ce_20260914_review/review_start.html`.
  사용자가 CE 원문 표현 6건 모두 원장 충실도 PASS로 처리했다. 향후 번역/편집 에이전트 평가 사례는
  `docs/review_agent_cases/ce_l05_translation_editorial_cases.json`에 보존했다.
  에이전트 제작 시 6건 탐지, 숫자 표기 오탐 방지, TRAMS 승인 KYR 용어 조회를 평가에 반영한다.
  현재 에이전트 구현이나 DB 작업을 시작한 것은 아니다.
  보고서: `samples/tagged_pdf_xml_poc/docs/reviews/2026-09-14-ce-book-xml-review.md`.

- 2026-09-14 ARA p35 안전 표의 한 줄 경고 문구에서 강제 문장 줄바꿈을 제거했다.
  현재 출력은 `samples/tagged_pdf_xml_poc/outputs/xml_review_africa_20260914_ara_safety_label_final`,
  HTML은 `samples/tagged_pdf_xml_poc/outputs/xml_review_africa_20260914_ara_safety_label_review/semantic_document.preview.html`.
  원문/표 구조는 동일하며 기존 전체 의미 검토를 승계한다. 사용자 ARA 직접 검토 의견도 기록했다.
  보고서: `samples/tagged_pdf_xml_poc/docs/reviews/2026-09-14-africa-safety-label-line.md`.

- 2026-09-13 AFRICA ENG–ARA 전체 의미/구조 재검토: 당시 결과는
  `samples/tagged_pdf_xml_poc/outputs/xml_review_africa_20260913_eng_ara_final`.
  Eco Sensor 문장 줄바꿈(5개 언어), ARA 안전 문단의 glyph 조각 순서 10곳을 수정했다.
  196개 ENG–ARA 본문 대응을 읽었으며 원문 의미 차이 9건과 이미지 검토를 남겼다.
  특히 ARA p31 LS03H의 가로/세로 조건은 ENG와 반대인 원문 표현이다.
  현재 보고서는 `samples/tagged_pdf_xml_poc/docs/reviews/2026-09-13-africa-eng-ara-full-review.md`,
  HTML은 `samples/tagged_pdf_xml_poc/outputs/xml_review_africa_20260913_eng_ara_full_review/semantic_document.preview.html`.
  이전 누락 감사 결과/폴더는 그대로 보존했다.

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

- [x] AFRICA_L05 BOOK scoped RTL repair (2026-09-13), branch
  `feature/xml-markdown-review`, starting clean at
  `840512002a80a12b19c712116530ab69b1459c3a`. Actual bookmark order is
  ENG/FRA/SPA/POR/ARA (physical pages 2/8/14/20/35). Semantic Arabic reads
  36 down to 27; Raw retains source order. ActualText restores chapter digits;
  pure RTL glyph reconstruction retains glyph owners and combining marks.
  Focused: `50 passed`; full real-sample POC: `1760 passed, 1 skipped`.
  Public imports and compileall pass. No legacy GridCell or DB changes.
- [x] AFRICA follow-up structural acceptance (2026-09-13), starting clean at
  `8eb2dfbb6c0f9fca8d1a7fda2ef448a706cb0a3f`: common 21 heading child-type groups
  match all five languages. Covers/contact/blank pages are counted separately.
  Observed totals 22/21/21/21/22 remain visible; only the fingerprinted Jordan-only
  source difference is accepted. RTL UI, LTR islands, model/range associations and
  ActualText decimals have source-backed fixes. All engine hard gates pass.
  Final: `samples/tagged_pdf_xml_poc/outputs/xml_review_africa_20260913_recheck_final_v2`.
  Focused: `101 passed`; full real-sample POC: `1811 passed, 1 skipped`.
  Raw/Semantic 4499 fragment identities and text survive. 18505 glyph origins
  match independent PyMuPDF geometry within 0.02 pt.
- [x] ZG ENG/FRA same-language review and Arabic rendered-output follow-up (2026-09-13).
  Common 21 headings match each; actual One Connect/password/declaration/source wording differences documented.
  Fixed four LTR decimal spaces, three Arabic inch-condition paragraphs and Wi-Fi bracket boundaries.
  Raw XML byte-identical; 4499 source identities retained. Marked/Edge rendering verifies four RTL spans.
  Current: `samples/tagged_pdf_xml_poc/outputs/xml_review_africa_20260913_followup_final_v3`.
  Focused 141 passed; full 1851 passed, 1 Windows symlink skip; compileall/public imports pass.
  Review: `samples/tagged_pdf_xml_poc/docs/reviews/2026-09-13-africa-zg-same-language-and-rtl-review.md`.
- [ ] User overall review with source crops for image-only symbols/barcode. Generic native/meaning warnings
  closed for extraction scope; actual EC/1999/5 preserved. No DB candidates.
- [x] Audit sug-manual-review skill against current XML workflow; proposal recorded in POC docs/reviews.
  Global skill was not changed.

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
