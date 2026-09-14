# TODO

## Active XML review v2 migration — 2026-09-10

이 절이 새 v2 작업의 현재 상태다. 아래 GridCell/MVP 기록은 과거 구현 이력이다.

- [x] 2026-09-14 검토자용 통합 Excel 표시 v2: 구성품 기준/현재 원문/페이지/조건 안내 후보 나란히 표시. 원장 제안과 상세 JSON은 내부 보존, Summary12행/4시트 유지. 저장 버전별 구/신 검증 및 화면 일치. 실제 표본 `outputs/checklist_reviewer_zc_20260914_v2/`, JSON 기존 실행과 바이트 동일. 관련54개 및 실제 작성2개 통과, 전 셀·4시트 렌더·실제 AppTest 확인. 설명 `docs/migration/2026-09-14-reviewer-report-v2_kr.md`. 사용성 회신은 가능할 때 받으며 내부 검증을 막지 않음.

- [x] 2026-09-13 사용자 요구: 원본 PDF 누락/구조 확인이 필요하면 반드시 명시적으로 요청. [바이어·언어 검증 대장](docs/migration/buyer-language-validation-ledger_kr.md)에 매핑23프로필/73언어조합 등록, 기존3 PDF/8조합의 adapter 근거 연결. 나머지는 다른 작업장 포함 미조사이며 미추출로 단정하지 않음.
- [ ] HR-20260913-001: ZC_L02 ENG/C-FRA 원본 전체 확인 범위 확정 요청. 기존 확인 기록이 있으면 동일 PDF/추출본·범위로 연결. 무응답/진행 허가는 검수 승인이 아님.
- [ ] 다른 작업장의 바이어별 추출 및 사람 확인 기록을 대장에 합산. 신규 RTL(ARA/HEB), 비라틴 문자, BOOK/복합 표/표지 사례를 ReviewDocument 설계 회귀 표본으로 확보. 전체 조합 완료 전에 기본 설계/개발은 진행하되 미확인 조합을 운영 지원으로 선언하지 않음.

- [x] 복구 커밋 `4b001ff9a1a4f8ef91bed75a8ab314f4189d9476`, XML 기준 `840512002a80a12b19c712116530ab69b1459c3a` 보존.
- [x] 두 기준점의 complete Git bundle 검증 및 `codex/xml-review-v2` worktree 생성.
- [x] 마이그레이션 명세, 복구 안내, ReviewDocument 설계 및 1단계 구현 계획 작성.
- [x] `src/review_document.py`: 구조/텍스트 순서/근거/선택적 review_role 보존 모델. 새 테스트 46개 통과.
- [x] 실제 XML writer/report schema 기반 adapter와 fail-closed gate 구현. 새 실행마다 PDF/mapping/추출기/네 산출물 hash를 기록하고, receipt 없는 과거 폴더는 자동 검토 입력으로 사용하지 않음.
- [x] ZC ENG/C-FRA, XU ENG, ZG BOOK 5언어 실물 변환. 기존 Semantic XML/MD 바이트 동일, raw/report는 원본 경로 제외 동일. ZG 공통 표지 텍스트 조각 9개는 언어 미배정으로 보존.
- [ ] v2 review_role은 실제 검토 규칙에 필요한 시점에 XML 구조/현재 검토 목적 기준으로 정의. legacy role명은 감사 참고만 하며 현재 adapter의 review_roles는 빈 tuple 유지.
- [x] Master Excel/JSON 547행 일치 확인, 17필드 가역 이관, 별도 v2 초안 Excel→JSON 및 이관 감사 생성. 출처 열은 source_reference_token으로 보존(빈 값 허용), 적용 제한에 사용하지 않음.
- [x] ReviewDocument→원문 검토 단위 목록 연결. 중첩 표/문단/목록 경계 분리, 언어·근거·그림 불확실성 표시. ZC/XU/ZG 원문 조각 1,938/1,168/6,696개와 근거/순서 전부 보존. DB 판정 아님.
- [x] ZC ENG 동결 DB 관찰 파일럿: 547행 보존, 적용59/미적용486/기존비승인2. 근거발견28/선택단위미일치9/미지원구조21/제목범위미발견1. 후보 제목·잠정 역할은 검토 필요로 유지하며 Pass/Fail 없음.
- [x] 관찰 파일럿 미일치9개 근거 대응: 8개 전체 문구 구조 후보, SAFETY-008은 목록+표의 3개 분산 근거. 별도 SAFETY-003 표 경고 후보도 추가. 엄격 관찰28/미일치9/미지원21/제목없음1 유지, 후보와 승인 분리.
- [x] ReviewService/CLI: 새 PDF 또는 검증 bundle → 동결 DB → 관찰 JSON/오프라인 HTML. 입력 변경/저장 중 변경/완료 기록 중단 방어, 완료 snapshot 소비자 검증. 전체 신규 ZC 실행 XML/MD는 기존과 바이트 동일.
- [x] Windows Python3.12 전용 `.venv`와 `requirements-review-v2.txt` 검증. pypdf6.16.2 사전 확인, 공용6.10.0 환경의 새 PDF 추출 실패를 진단하고 다른 작업장 변경 없이 해결.
- [x] 기존 추출 Excel/최종 리포트 실물 양식 조사와 `review_report_view.py` 표시용 변환, 테스트 구현. 새 Excel 양식 초안 59규칙/40근거/488제외 행 전체 값·4시트 렌더·수식·필터·A2 고정창 확인.
- [x] 후속 사용자 피드백 기록: observation/reason 중복을 줄이는 판정+설명 두 열 권고안, 원본 PDF/추출본 출처 패널과 노드ID+태그+페이지 추적, item별 DB 단위 설계 진행 승인. `docs/superpowers/specs/2026-09-11-item-review-and-evidence-display-design_kr.md` 참고. 기존 코드/Excel 초안은 아직 이전 구성.
- [x] DB 구조 조사 547행 보존: item 분리 후보10/표 관계126/유지 또는 정의411. CHK-002-ZC-ENG 14개 명시적 하위 항목 초안과 원문 구간 보존, 실제 XML 목록 항목14개 대응 및 별표12개의 모델 조건 안내 후보 연결. 조건 적용/업무 승인 없음.
- [x] result+한국어 설명 두 열의 표시 변환과 출처 패널, 노드/태그/페이지 상세 추적 구현. 원문/기존 엄격 관찰 결과 변경 없음. `docs/migration/2026-09-11-item-proposal-and-display_kr.md` 참고.
- [x] CHK-002 부모1/하위14 별도 v2 작성용 Excel 원장→JSON exporter 구현. 출처/원문과 담당자 제안 세 열 분리, 모델 적용 unknown/조건 unverified 유지. 26개 근거와 별표12개 조건 참조 보존. 동결547행 DB나 ReviewService에는 미연결. `docs/migration/2026-09-11-item-master_kr.md` 참고.
- [x] 별도 ItemReviewService/CLI: 원장 Excel/JSON/고정 seed 대조 → 현재 XML에서 하위14개 다시 조사 → JSON/오프라인 HTML/완료 기록. 원장 과거 근거와 검토 대상 근거 분리, 복수 근거/미발견/범위 미확정 구분. 실물 PDF 새 추출·검증 묶음 재사용 모두 14개 발견/12개 조건 안내 후보, 전부 needs_review. 기존547행 경로 미변경. `docs/migration/2026-09-11-item-observation-service_kr.md` 참고.
- [x] 항목별 결과 Excel writer/검증 완료 기록과 읽기 전용 Streamlit 화면 연결. Summary/Item Results/Source Evidence 3시트, 항목14/현재 근거26, 판정+설명/출처 분리. 새 출력 폴더로 생성, 완료된 관찰 결과와 연결된 Excel만 다운로드. 실물 `outputs/item_excel_zc_20260911_r2/`, 사용법 `docs/migration/2026-09-11-item-excel-ui_kr.md`.
- [x] 2026-09-13 사용자 개정: 항목 결과 JSON과 Excel을 동일 실행 폴더에 저장. 새 HTML 생성/다운로드 중단, Summary 12행, 임시 근거 ID 제거, 고정 항목 키 연결, 화면 폴더 입력 하나. observation 완료 기록 v2/Excel view v2 사용. 기존 v1 관찰 결과는 HTML 해시까지 검증하는 읽기 호환 유지.
- [ ] 전체 PC 배포 의존성 정리: 현재 새 Excel 생성은 Node/Artifact Tool 작성 환경 필요. 화면 읽기/다운로드는 Python으로 가능. 번들 작성 도구 재배포 가능 여부 및 Python-only 대체 writer 검토 후 결정; 현재 구현을 담당자 전체 배포 완료로 간주하지 않음.
- [x] 통합 레포트 설계 승인 및 CLI 구현: 같은 PDF/XML/추출 완료 기록/context의 완료 관찰 두 개 → 자체 보관 통합 JSON → 4시트 Excel 하나. 상위59건/그중 구성품상세14건 분리 집계, 근거40+26행/내부제외488행/원본547행 보존. 기존 DB/부모 판정/관찰 원문 변경 없음. 실제 결과 `outputs/combined_review_zc_20260913_r2/`, 사용법 `docs/migration/2026-09-13-combined-review-report_kr.md`.
- [x] 통합 결과의 단일 폴더 Streamlit 조회/다운로드 및 공통 실행 명령 연결. PDF 추출 1회/동일 bundle 공유, `_internal`에 중간 자료 보관, 최상위 통합 Excel/JSON. 일반 관찰 v2 JSON-only/구 v1 HTML 검증 호환, 전체 실행 lock/실패 차단, 다운로드 때 재검증. 실제 `outputs/combined_review_zc_20260913_shared_r2/`. 사용법 `docs/migration/2026-09-13-combined-run-ui_kr.md`.
- [x] 비개발자용 전체 구조·ReviewDocument/adapter/검토 기능 책임·사람 검토 시점 설명 문서 작성: `docs/architecture/review-document-explained_kr.md`. 기술적 보존 검사와 PDF 원문/업무 승인을 구분.
- [x] 2026-09-14 화면 PDF 경로 입력/검토 실행 연결. 실행마다 새 폴더, 완료 결과 자동 조회/다운로드, 실패 시 이전 결과 비움, launcher XML 패키지 경로 자동 설정. 현재 ZC ENG 체크리스트 관찰 전용. 사용법 `docs/migration/2026-09-14-checklist-ui-run_kr.md`. 실제 결과 `outputs/checklist_20260914_130233_25dbc00a184e/`; XML/MD/ReviewDocument 기존 검증본과 바이트 동일. 모델 적용 승인/DB 편집은 별도 단계.
- [x] 항목별 HTML 실물 렌더 검수 후속은 사용자 요청으로 종료. 새 결과의 HTML 생성/노출을 중단하고 과거 파일은 보관한다.
- [ ] 모델 적용 자료/사람 승인 절차와 실제 항목 evaluator 연결. 현재 원장의 제안문은 실행하지 않음. 다른 9개 item_list 행은 아직 분리 정의 전.
- [ ] 사용자 Excel 개정 실물 검수 및 배포용 writer 연결. 최초 양식을 최종 승인본으로 간주하지 않음.
- [ ] XML 위치 선택·문구 매칭을 검증한 뒤 evaluator 구현. 모든 approved 545행의 XML 호환 상태는 아직 pending이며 자동 판정 미연결.
- [ ] 추출 검수 Excel와 최종 검토 Excel의 실제 표본 선정·양식 명세·새 exporter 구현.
- [ ] ReviewService/CLI, Streamlit 연결 및 프로필별 결과 검증.
- [ ] 사용자 양식 검수, 설명되지 않는 차이 해소, GridCell active 코드 정리 및 PC 배포.

검증(2026-09-11): 루트 `python -m pytest tests -q` 285 passed / 6 subtests passed; 전용 `.venv`에서도 285 passed. `python -m compileall -q src tests scripts` 통과. 이번 연속 구현 신규55개. 독립 리뷰의 구역 경계·출력 변경·완료 기록 부분 저장 지적을 회귀 테스트로 수정.
후속 항목/표시 구현 검증: 전용 `.venv` 전체333 passed, 항목 집중17 passed, compileall 통과. 6시트 개정본의 59/40/488/14/547행 전체 열 값 대조와 렌더 완료. 기존 원본 DB 해시 유지. 노드 소속 관계 오류7개 회귀 테스트 포함.
항목 원장 후속 검증: 전체362 passed, 신규 원장 집중29 passed(기존 항목과 합쳐46), compileall 통과. CHK-002 원장5시트 전체 값 대조·렌더, Excel→draft JSON 통과. 독립 명세/품질 검토 통과. 보관본 `metadata/checklist_v2/item_master_drafts/20260911/`, 편집본 `outputs/item_master_20260911/checklist_item_master.xlsx`. 기존 DB 변경/운영 활성화 없음.
현재 PDF 항목 연결 후속 검증: 전체435 passed, 신규 집중73 passed, compileall 통과. 독립 명세/코드 품질 검토 통과, 두 실행의 XML로 항목 근거를 전부 재계산해 일치 확인. 실물 결과 `outputs/item_review_zc_20260911_fresh/`, 검증 묶음 재사용 `outputs/item_review_zc_20260911_reuse_r2/`. 원본 DB/동결 DB/항목 원장 해시 유지. HTML 실물 렌더 검수는 위 제한 참고.
XML POC 관련 writer/output-bundle/language-interval/Markdown 테스트 511 passed, 1 skipped (Windows symlink). POC 전체 suite 재실행은 아님.
항목 결과 Excel/화면 연결 후속 검증: 전체492 passed(실제 Artifact Tool 통합2개 포함), 신규 Excel32/UI25, compileall 및 pip check 통과. 독립 명세·품질 재검토 통과. 실물 Excel 전체 셀 대조 및 3시트 6영역 렌더 검수, 실제 결과 AppTest 14행/다운로드3개 확인. 원본 DB/동결 DB/항목 원장 유지. 전체 PC 배포나 브라우저 육안 검수 완료를 뜻하지 않음.
동일 폴더/간소화 개정 검증(2026-09-13): 전체503 passed(실제 Artifact Tool 통합2개 포함), compileall·pip check·diff check 통과. 실물 새 PDF 실행 `outputs/item_review_zc_20260913_unified/`에서 JSON+Excel 동시 보관, HTML 없음. Summary12행/항목14개/근거26개 유지 열 전부 기존 r2 Excel과 동일, 기존 파일 해시 유지. 3시트5영역 렌더 및 실제 결과 AppTest 입력1개/다운로드2개 확인. 독립 코드 검토 통과. 기존 DB/추출 규칙 변경 없음.
일반/항목 통합 후속 검증(2026-09-13): 전체558 passed(실제 Artifact Tool 통합4개 포함), compileall(src/tests/scripts)·pip check·diff check 통과. 독립 명세/코드 품질 검토 통과. 실물 통합 Excel 전 셀·4시트10영역 렌더(최장 근거 포함), Item Results 기존8열 동일성, 원본 관찰/추출 보관 바이트 불변 확인. 새 HTML 없음. 첫 `combined_review_zc_20260913`은 표시 한도 초과로 실패 기록만 보존하고 `_r2`를 정상 결과로 사용한다. 노드 필수 필드/소속/개별 및 합친 원문/페이지·경로/제안 상태 우회 회귀 테스트 포함. XML POC 전체 suite는 이번에 재실행하지 않음. `apps/` 폴더는 이 작업장에 없으며 별도 앱 모듈은 src/scripts/tests 검증 범위에 포함된다.
사용 방법·산출물·지원 범위: `docs/migration/2026-09-10-xml-adapter-validation_kr.md`.
공통 실행/통합 UI 후속 검증(2026-09-13): 신규15/루트 전체573 passed, compileall(src/tests/scripts)·pip check 통과. 실제 ZC 공통 실행 XML/MD/ReviewDocument 바이트 불변, 일반/항목 관찰 행·Excel 표시값 전체 동일. AppTest 59/14행·다운로드2개, 4시트 대표 렌더 확인. 독립 코드 검토에서 중대한 결함 없음. `_shared`는 XML 패키지 PYTHONPATH 누락 실패 기록, `_shared_r2`가 정상 결과. 사람의 PDF 원문/업무 승인 및 전체 PC 배포는 아직이며, 이번에 별도 XML POC 전체 suite는 재실행하지 않음.
DB 초안·사용 방법: `docs/migration/2026-09-11-checklist-draft-validation_kr.md`.
검토 단위·source_token 설명: `docs/migration/2026-09-11-review-text-units_kr.md`.
실제 DB 연결 결과·미일치 원인·사용 방법: `docs/migration/2026-09-11-checklist-observation-pilot_kr.md`.
현재 관찰 결과: `outputs/checklist_observation_zc_20260911_r2/observation.json` (ZC ENG만, 운영 판정 아님).
최신 전체 실행: `outputs/review_service_zc_20260911_r2/` (JSON/HTML/새 XML 추출 묶음).
최신 표시 구분: 엄격 근거28 / 구조 후보9 / 분산 근거1 / 미연결21. 적용59개는 모두 needs_review/pending 유지.
Excel 양식 초안: `outputs/review_excel_prototype_20260911/review_report_prototype.xlsx`.
최신 항목/출처 개정본: `outputs/review_item_layout_20260911/review_report_prototype.xlsx` (runtime DB 활성화/배포본 아님).
자세한 사용법: `docs/migration/2026-09-11-structured-evidence-and-service_kr.md`.
초안 보존 위치: `metadata/checklist_v2/drafts/20260911/`. 메인의 기존 master와 교체하지 않음.
개발용 Artifact Tool 작성 프로세스의 저장 후 exit 1 원인은 반복 생성 도구 배포 전에 조사한다. 저장물 자체의 전체 값 대조/수식 캐시/Excel→JSON 검증은 통과했다.
메인의 기존 DB와 기존 추출기는 변경하지 않았다. 자세한 복구 범위는 `docs/migration/2026-09-10-recovery_kr.md`를 읽는다.

## Current Goal

2026-09-14 화면 실행 연결 검증: 관련58 passed, compileall(src/tests/scripts) 및 diff check 통과.
실제 AppTest PDF→Excel/JSON→자동 표시 59/14행·다운로드2개 확인. 전체 suite 재실행은 아님.

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
