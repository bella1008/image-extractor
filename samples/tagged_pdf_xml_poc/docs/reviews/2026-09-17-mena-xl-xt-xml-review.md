# MENA / XL / XT XML 추출 검증

작업 위치: `C:/Users/bella/image-extractor/.worktrees/xml-markdown-review`.
브랜치: `feature/xml-markdown-review`.
시작 HEAD: `54861b3842cc06113d9fe7077011e35dc8513b78`; 시작 시 미커밋 변경 없음.
사용자 요청은 3개 신규 PDF의 연속 추출·검증이며, TK/ZW를 포함한 사용자 컨펌은 별도이다.

## 원본과 프로필

| source_token | PDF | 형식 | 원문 언어 순서 |
|---|---|---|---|
| MENA_L02 | BN68-25031L-00_SUG_Y26 TV ALL_MENA_L02_260114.0.pdf | A2 | ENG, ARA |
| XL_ENG | BN68-25031J-00_SUG_Y26 TV ALL_XL_ENG_260306.0.pdf | A3 | ENG |
| XT_L02 | BN68-25031M-00_SUG_Y26 TV ALL_XT_L02_260113.0.pdf | A2 | ENG, THA |

원본은 main checkout의 `samples/SUG_RAW/2_TV_MENA`, `2_TV_XL`, `2_TV_XT`에서 읽기만 했다.
모두 2페이지이며 BOOK 북마크가 없는 sheet PDF다. 언어는 파일명 토큰·등록 프로필·실제 PDF 표시를 대조했다.
XL은 canonical profile에 없으므로 실제 PDF로 확인한 `XL_ENG/A3/ENG/1`만 검토용 overlay로 사용했다.
대표 region/buyer_codes는 연락처 국가나 폴더명으로 추정하지 않았다. canonical metadata는 수정하지 않았다.
재현 명령은 `scripts/review_sheet_rollout.py <새 출력 폴더>`이며, overlay를 canonical 사본에 합쳐 해당 실행에만 사용한다.

## 수정 전 결함과 적용 범위

- MENA: 표지가 본문 뒤에 위치하고 언어 구간 게이트 실패. ARA 장 번호가 분리되어 제목 승격 누락.
  Arabic 원문 ActualText와 glyph 위치에 근거해 읽기 순서·소수·모델 기호·괄호를 복원했다.
  `LS03H*` 별표의 실제 소속을 감사 기록에 남기고, Markdown의 안전한 bdi로 RTL 화면 위치도 검증했다.
  전원 연속문장을 원래 bullet 아래로 연결하고, 5개 국가가 공유하는 연락처 Website 셀을 RowSpan=5로 표시한다.
- XL: 표지 순서, 전원 문장 소속, Cambodia/Laos 공유 연락처 셀을 보정했다.
  PDF 한 text operation에 존재하는 숫자 근거로 `7 .125`와 `7. 3`의 추출 중 삽입된 공백을 제거했다.
- XT: PDF ToUnicode/ActualText의 잘못된 태국어 매핑 때문에 자음·모음·성조가 중복되거나 U+FFFD가 나타났다.
  내장 Tahoma subset의 glyph outline/cmap 대응을 확인한 코드표로 복원한다. 번역·추측한 단어를 runtime에 넣지 않았다.
  glyph 증거와 두 내장 글꼴 SHA를 기록하며 runtime에서 외부 글꼴이나 API에 의존하지 않는다.
  실제 유효 font size, 원본 fragment 식별자·경로를 유지하고 양언어 전원 문장과 표지 순서·연락처를 정리했다.
  양언어 parental-rating appendix는 본문 뒤의 원문 위치를 유지한다.

규칙은 POC의 전용 MENA/XL/XT 모듈에서 source_token + doc_type + languages + 정확한 PDF SHA로 제한한다.
다른 revision은 재검토 없이 적용하지 않는다. 공용 수정은 reader/application 연결, MENA 장 번호 및 검증된 bdi 표시 분기에 한정한다.
raw_structure는 원래 노드를 유지하고, semantic 변경은 원본 MCID·object-ref·source-structure-path와 근거를 기록한다.
MENA 별표 한 글자의 MCID 소속 이동은 명시적 원래/변경 소유자 감사로 검증한다. 추출 노드 ID를 고정 DB 키로 사용하지 않는다.

## 언어별 구조

| 바이어·언어 | 표시 제목 | 검토 단위 | paragraph 노드 | list / list_item | 표 | figure 노드 |
|---|---:|---:|---:|---:|---:|---:|
| MENA ENG | 22 | 93 | 219 | 33 / 100 | 16 | 40 |
| MENA ARA | 22 | 92 | 215 | 33 / 100 | 15 | 38 |
| XL ENG | 24 | 101 | 305 | 34 / 103 | 21 | 45 |
| XT ENG | 23 | 95 | 189 | 33 / 101 | 17 | 45 |
| XT THA | 23 | 94 | 192 | 33 / 101 | 16 | 44 |

표시 제목은 표지 포함이다. XML heading 태그 4개는 각 언어의 01–04 장 번호이고, 나머지 실제 표시 제목은 원문 역할/표시 계층으로 확인한다.
paragraph/figure 노드 수는 독립 검토 블록 수 또는 고유 그림 파일 수와 다르다.

- MENA 양언어 본문은 paragraph 157, list_item 100, 표 14, figure 37로 정확히 일치한다.
  전체 차이는 ENG에만 있는 QR/barcode/document-code 영역의 paragraph 4개·표 1개·figure 2개로 설명된다.
  모델 136개(일반 67 + Saudi-only 69), 연락처 국가 13행, 안전 심볼 표 9행·그림 6개씩 확인했다.
- XL은 사양표 18행×4열, 모델 열 묶음 9개, 사양값 54셀을 원문과 확인했다. 연락처 14개 데이터 행이며 source header는 별도이다.
- XT는 모델 84개씩, parental-rating 표 8행×3열씩, 연락처 2행×2열씩, 사양표 4행씩 확인했다.
  본문 paragraph는 143개씩이다. ENG barcode 영역 +3, THA appendix의 원문 paragraph 세분화 +6으로 전체 THA +3 차이를 설명한다.
  source_audit에 해당 셀과 원본 노드 근거를 남긴다.

각 ENG를 검증된 ZC ENG와 먼저 비교한 후 같은 PDF의 현지어와 비교했다.
이 PDF들에는 ZC의 Internet security가 없고 01 제목은 What's in the Box?다. 원문 차이를 누락으로 오인하지 않았다.
XL의 India RoHS/BEE 제목 2개, XT의 태국 parental-rating appendix도 원문 추가 구조로 유지했다.

## 남은 사람 검토 항목

- MENA ENG `DC v-oltage` 및 실제 Arabic 중복 표현은 원문 그대로이다.
- XT ENG `broadcated`, THA 전원 문장의 `ตู้เย็น`, 스위치 표현 `ชัตเตอร์สวิตช์`는 원문 표현 검토 예시로 남긴다.
- XL `All voice`, `Star Labeling` 등 원문 표현은 임의 편집하지 않는다.
- BN68 문서코드·barcode·안전 심볼·조작 그림·UI 아이콘의 비텍스트 부분은 PDF crop 근거다. `-00` 외 그래픽 문서코드를 OCR 텍스트로 주장하지 않는다.
- XL canonical profile 등록은 별도 metadata 업무다. 이번 추출 검증에서는 검토용 overlay만 사용했다.

위 항목은 추출 누락과 분리한 원문/이미지 검토 사항이다. 사용자 컨펌 전 승인 상태로 변경하지 않는다.
외부 의미 검토 API, checklist 후보/DB 변경, 구 GridCell 규칙, root extraction, item_review, Excel/Streamlit 변경은 없다.

## 최종 검증 기록

최종 출력 절대 경로:
`C:/Users/bella/image-extractor/.worktrees/xml-markdown-review/samples/tagged_pdf_xml_poc/outputs/xml_review_mena_xl_xt_20260917_ready`.
시작 화면은 `review.html`, 원문 비교는 `source_checks.html`이다.
`MENA_L02`, `XL_ENG`, `XT_L02` 각 하위 폴더에 다음 파일이 있다:
`raw_structure.xml`, `semantic_document.xml`, `semantic_document.md`, `semantic_document.preview.html`,
`extraction_report.json`, `review_document.json`, `review_run.json`, `source_audit.json`, `html_validation.json`.

- 각 바이어 Hard gate 0. XML→MD 전체 문자 순서, 모든 검토 단위 475개(185+101+189), MD→HTML 문자·DOM 구조 일치.
- 원문 비교 128개를 생성했다. 표지·표·모델·숫자·전원 문장 근거는 각 source_audit와 crop에 연결된다.
- 실제 브라우저에서 ARA LS03H*의 별표가 H 오른쪽에 있는지 검사했다. 번호 01–04는 원문 두 숫자의 검증된 결합이다.
- 비교 HTML에서 RTL을 컨테이너 전체에 적용하던 결함을 발견하여, 실제 Arabic 문장/셀에만 방향을 적용한다.
  원본 열 순서와 영문 전화번호 표시를 브라우저 좌표/방향 테스트로 확인했다. 전체 본문 HTML에는 해당 결함이 없었다.
- TK도 비교 화면만 새 `outputs/xml_review_tk_20260917_direction_review`에 갱신했다.
  두 PDF의 raw/semantic XML, MD, extraction_report 및 전체 HTML 10파일은 기존 결과와 동일하다. 이전 폴더는 보존했다.
- 최종 XML 전체 테스트: **2,391 passed, 1 skipped** (628.23초).
  Windows symlink 생성 불가로 `test_output_bundle.py`의 관련 테스트 1개만 건너뛰었다.
- 전체 실행에는 신규 바이어 집중 테스트 **66개**, XML/Markdown writer 테스트 **385개**가 포함되어 모두 통과했다.
- 이후 비교 화면 실제 브라우저 + 기존 TK 제목 테스트: **9 passed**. 새 비교 방향 테스트 1개와 기존 제목 테스트 8개이다.
- root 호환성: `tests/test_content_poc.py` **43 passed**;
  `run_content_poc`, `write_content_poc_outputs`, `write_content_review_xlsx` **3개 callable import** 성공.
- compileall: POC `src tests scripts`, 루트 `src tests` 성공. 루트 scripts/apps와 POC apps는 없다.
- 최종 코드로 ZC/ZG/AFRICA/CE/XU/KR/LATIN/ZW_TPE/TK_L02/TK_ARA **10프로필 재추출**, XML·MD **30파일 바이트 동일**.
  근거: `outputs/xml_review_mena_xl_xt_20260917_final_regression/comparison.json`.
- 실패를 재현한 회귀 테스트 후 보정했고, 중간 실패/후보 출력은 최종 승인 자료로 사용하지 않았다.

## 변경 파일

아래 POC 경로는 `samples/tagged_pdf_xml_poc/` 기준이다.

- 루트 `TODO.md`.
- `config/review_profile_overrides.json`.
- `docs/plans/2026-09-16-mena-xl-xt.md`, 이 검토 기록.
- `scripts/review_sheet_rollout.py`, `scripts/finalize_sheet_rollout.py`, `scripts/render_tk_source_checks.cjs`.
- `src/tagged_pdf_extractor/application/extract_document.py`.
- `src/tagged_pdf_extractor/domain/numbered_heading_promotion.py`, `mena_sheet.py`, `mena_source_text.py`, `xl_sheet.py`, `xt_sheet.py`.
- `src/tagged_pdf_extractor/infrastructure/pypdf_reader.py`, `markdown_writer.py`, `xl_source_evidence.py`, `xt_source_evidence.py`.
- `tests/test_mena_sheet.py`, `test_mena_source_text.py`, `test_mena_arabic_bidi.py`, `test_xl_sheet.py`, `test_xt_sheet.py`,
  `test_sheet_rollout_integration.py`, `test_source_comparison_direction.py`.

추출 검증 완료이며 원문 표현·이미지에 대한 사람 검토와 사용자 컨펌은 대기 상태다.
로컬 복구 커밋 전체 번호는 완료 응답 및 각 review_run의 recovery_commit에 기록한다. 원격 push는 하지 않는다.
