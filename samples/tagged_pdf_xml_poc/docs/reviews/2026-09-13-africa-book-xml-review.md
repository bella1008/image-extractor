# AFRICA_L05 BOOK XML 재검토 — 2026-09-13

> 현재 결과와 Warning 종료 상태는 [후속 검토](2026-09-13-africa-zg-same-language-and-rtl-review.md)를 참조한다. 아래는 28723bb 단계의 검토 이력을 보존한 것이다.

**구조 검수 통과. Hard gate 0개. 사람의 의미·표현 검토는 필요하다.**
기존 보고는 표지·연락처를 포함한 전체 합계를 본문 제목 수와 함께 제시해 차이가 크게 보였다.
이번에는 같은 본문 범위와 공통 제목 21개 각각의 하위 블록 종류·개수를 비교했고 모두 일치했다.

## 대상과 시작 상태

- PDF: `BN68-25031G-00_SUG_Y26 TV ALL_AFRICA_L05_251230.0.pdf`
- 입력: `C:\Users\bella\image-extractor\.worktrees\xml-extractor-release\samples\SUG_RAW\TV_AFRICA\BN68-25031G-00_SUG_Y26 TV ALL_AFRICA_L05_251230.0.pdf`
- SHA-256: `cdc2123f2e1dde2f46314a9ef31bda0bdfb4b4455ff26436838004d65e05c848`
- 작업장: `C:\Users\bella\image-extractor\.worktrees\xml-markdown-review`
- 브랜치: `feature/xml-markdown-review`
- 최초 HEAD: `840512002a80a12b19c712116530ab69b1459c3a`.
- 이번 재검토 시작 HEAD: `8eb2dfbb6c0f9fca8d1a7fda2ef448a706cb0a3f`, 미커밋 변경 없음.
- 파일명 parser와 canonical mapping 확인: `AFRICA_L05`, `BOOK`, ENG/FRA/SPA/POR/ARA.
- 실제 북마크: English p2, Français p8, Español p14, Português p20, العربية p35.
- 본문: ENG p2–7, FRA p8–13, SPA p14–19, POR p20–25, ARA p35→30.
  표지를 포함한 ARA 전체 읽기 순서는 p36→27. Raw 물리 순서는 보존했다.

AGENTS/README/TODO/SUG_RAW_ANALYSIS를 확인했다. 실제 XML POC 경로만 수정했다.
GridCell, item_review, Excel/Streamlit, checklist DB, xml-review-v2는 수정하지 않았다.
매 추출마다 새 폴더를 사용했다. 외부 의미 API/OCR/원격 push/merge/rebase는 사용하지 않았다.

## 제목·블록 수 재검토

다음은 **본문만** 집계한 Semantic 구조다. paragraph는 중첩 wrapper를 포함하는 XML 컨테이너 수이며
문장 수가 아니다. 제목은 source-role 후보와 승격 장 제목을 포함한다.

| 언어 | 제목 | paragraph | list_item | table | row | cell | figure |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| ENG | 22 | 128 | 100 | 14 | 29 | 46 | 38 |
| FRA | 21 | 121 | 100 | 13 | 27 | 44 | 37 |
| SPA | 21 | 121 | 100 | 13 | 27 | 44 | 37 |
| POR | 21 | 121 | 100 | 13 | 27 | 44 | 37 |
| ARA | 22 | 128 | 100 | 14 | 29 | 46 | 38 |

ENG p7와 ARA p30에는 원본에 Jordan-only 항목이 있다. FRA p13, SPA p19, POR p25에는 없다.
독립 PDF StructTree와 이미지 검토로 확인했다. 제목은 `Recommendation - Jordan Only`,
`توصيات - الأردن فقط`이며 source path는 `0/2/0/14`, `0/12/0/14`다.
뒤의 표 경로는 각각 `.../15/0`, object-ref는 `4182 0 R`, `1256 0 R`이다.
이 표는 **2행×1열 레이아웃 표**로 첫 행 CE 그림, 다음 행 선언문이다.

이 부분을 별도로 계산하면 다섯 언어 모두 **제목 21, paragraph 121, list_item 100,
table 13, row 27, cell 44, figure 37**이다. Jordan 증가량은 제목 1, paragraph 7
(제목 1+wrapper 1+내부 5), table 1, row 2, cell 2, figure 1이다.
`review_document.json/common_heading_child_type_parity`에는 21개 제목별 비교를 남겼다.
각 제목 아래의 위 여섯 구조 종류 개수까지 모두 일치하므로 총합만 맞춘 결과가 아니다.

원본 Raw `LI`는 언어마다 104개이며 4개가 장 제목 01–04로 승격되어 Semantic은
`list_item=100`, `heading=4`다. engine `heading_count=20`은 다섯 언어 승격 장 제목 합계다.
`heading_hierarchy=109`는 본문 107개와 표지 제목 2개다. 서로 다른 집계 범위를 혼용하지 않는다.

본문 밖 영역은 다음과 같이 분리했다.

| 영역 | paragraph | table | row | cell | figure |
| --- | ---: | ---: | ---: | ---: | ---: |
| ENG 앞표지 p1 | 4 | 0 | 0 | 0 | 1 |
| ENG 연락처 p26 | 68 | 1 | 20 | 54 | 0 |
| ARA 앞표지 p36 | 5 | 0 | 0 | 0 | 3 |
| ARA 연락처 p27 | 69 | 1 | 20 | 55 | 0 |
| ARA 빈 페이지 라벨 p28–29 | 2 | 0 | 0 | 0 | 0 |

연락처 cell 54/55 차이도 원본 구조다. ENG의 ALGERIA/TUNISIA Website는 RowSpan=2
한 셀을 공유하고 ARA는 동일 URL 두 셀을 가진다. 확장 후 국가 19행의 국가명/전화/URL은
모두 일치한다. `source_header`에는 머리글만, 국가 데이터는 `country_rows`에 있다.

언어마다 안전 심볼 표 1개(9행, 그림 6개), 사양표 1개(3행), 구성품 표 1개,
Controller 그림 표 1개, Microphone Type A–D 범례 표 1개, inline icon 14개가 있다.
그림 셀·표·목록을 일반 본문 하나로 합치지 않았다.

## 결함과 수정 범위

이전 커밋은 POR/ARA 구간, Arabic 역순 페이지, ActualText 장 번호, 일부 순수 RTL glyph와
Markdown 장 번호를 수정했다. 이번 시작 추출에서는 UI 순서와 heading-count gate가 실패했다.
새 동작은 정확한 `AFRICA_L05 + BOOK + ENG/FRA/SPA/POR/ARA` XML 경로로 제한했다.

- 원 glyph 폭, Tc/Tw/Tz, TJ kerning, 원 byte 0x20, 글꼴 encoding을 반영한 좌표로
  paragraph/span/inline list_body를 줄별로 읽는다. 표·목록·셀 경계를 넘지 않는다.
- ARA UI 경로 4개, Controller 제목, Eco 문장, 온도·습도, LAN 조건의 순서를 복원했다.
- 영문 URL/해상도와 연속 숫자는 LTR로 유지하며 RLM 및 조건·범위 구분자는 경계로 유지한다.
  RTL 모델 목록의 줄 끝 slash와 다음 줄 모델·출력값 연결도 재현 테스트로 확인했다.
- 혼합 줄의 완전한 Arabic MCID는 glyph 단위로 복원한다. `لى` ligature와 shadda/모음
  glyph 내부 codepoint를 뒤집지 않는다. 문구를 번역하거나 추정하지 않는다.
- ActualText 소수는 원 glyph/ActualText/한 baseline/연속 좌표/완전한 숫자 문자열이
  모두 일치할 때만 합쳐 `5.925`, `7.125`, `6.425`로 유지한다.
- 제목 수 22/21/21/21/22, strict count=false와 FRA/SPA/POR mismatch 3개는 report/XML에
  남긴다. 정확한 PDF SHA·실제 제목/경로/페이지·2×1 표·공통 21개 서명이 모두 맞는
  Jordan source exception만 count gate에 반영한다. 다른 hard gate는 이 예외로 통과하지 않는다.

최종 glyph 복원은 340 fragment(공백 정리 포함), inline 순서 수정은 83 container,
ActualText 소수는 3개다. 대상 container의 미해결 geometry skip은 0개다.
독립 PyMuPDF texttrace와 glyph 원점 18,505개를 대조해 0.02 pt 초과 불일치 0개였다.

## 검증 근거와 남은 Warning

검증된 ZC ENG(`cross_profile_readability_zc_260908`)를 먼저 비교했고 가까운 BOOK 회귀
기준은 ZG(`cross_profile_readability_zg_260908`)다. 최초 검토에서 확인한 ENG 구조를
유지하면서 이번에는 현지어와 각 제목별 하위 구조를 다시 비교했다.

Raw/Semantic 4,499 fragment의 `(page-index, mcid, object-ref)` multiset과 공백 제외 전체
문자 multiset이 일치했다. Markdown은 writer의 행/열/아이콘 표시를 제외한 알파벳 문자
multiset이 Semantic과 일치한다. 장 번호 20개, inline icon 70개 대응, XML round-trip 통과,
미해결 참조/알려진 손실/금지 제어문자 0개다. 집계만으로 순서를 승인하지 않고
UI/모델·수치 회귀, source path와 crop 비교를 함께 사용했다.

**Hard gate 0개.** 남은 Warning은 사람 검토 3종이다.

1. Arabic bidi 제어문자·인치 따옴표·괄호·원본 줄바꿈의 최종 표시 품질.
   모델/수치 소속과 순서는 확인했지만 자연스러운 현지어 조판을 보증하지 않는다.
2. 언어별 의미와 실제 원문 표현 차이. ARA `EC/1999/5`는 실제 glyph/PDF 표기이므로
   ENG `1999/5/EC`로 임의 수정하지 않았다.
3. 이미지인 아이콘·안전 심볼·barcode. crop을 직접 확인했으며 OCR 텍스트로 주장하지 않는다.

전 36쪽 렌더 및 앞선 `xml_review_africa_20260913_evidence/crops_v2` 29개 crop,
표지 p1/26/27/36, 보충 p36 등록문구와 p33 제목 crop을 근거로 보존했다.
이번 제목별 집계와 좌표 감사는 `xml_review_africa_20260913_recheck_evidence`에 있다.
Global LCS는 물리 baseline과 RTL Semantic 순서를 비교하므로 승인 지표로 사용하지 않는다.
체크리스트 후보 생성이나 DB 승인 작업은 하지 않았다.

## 최종 산출물과 테스트

절대 폴더:
`C:\Users\bella\image-extractor\.worktrees\xml-markdown-review\samples\tagged_pdf_xml_poc\outputs\xml_review_africa_20260913_recheck_final_v2`

- `raw_structure.xml`
- `semantic_document.xml`
- `semantic_document.md`
- `extraction_report.json`
- `review_document.json`: 동일 범위 본문/표지 집계, 21개 제목별 비교, 표/연락처 및 Warning.
- `review_run.json`: 입력/bundle SHA, 시작 상태, 테스트 로그와 최종 복구 commit.

POC `.venv\Scripts\python -m tagged_pdf_extractor.cli <입력 PDF> --output <새 폴더>` exit=0.
집중 6개 AFRICA 테스트 파일 **101 passed**. `TAGGED_PDF_REQUIRE_SAMPLES=1` 전체 POC
suite **1811 passed, 1 skipped**(Windows symlink 기능). 기존 ZC/ZG/LATIN/KR/XU와 ZA/XY
실물, public reader/import, XML profile 경로, Semantic XML/Markdown writer 회귀를 포함한다.
처음 전체 run은 마지막 모델 목록 경계 수정 때문에 중단했고 최종 코드로 전체를 재실행했다.

`python -m compileall src tests scripts` 및 POC `src/tests` compileall exit=0.
루트 apps/scripts는 실제로 없으므로 검사할 파일이 없었다.
기존 `src.content_poc` 공개 함수 3개는 프로젝트 기본 Python에서 import 통과했다.
POC 전용 venv에는 legacy openpyxl이 없어 그 venv의 legacy import 시도는 실패했지만
프로젝트 기본 Python에서 재검증했다. 의존성이나 legacy 코드를 변경하지 않았다.

## 변경 파일과 복구

- `TODO.md`, `docs/superpowers/plans/2026-09-13-africa-book-xml-validation.md`.
- POC `README.md`, 이 검토 기록.
- POC application: `evaluate_quality.py`.
- POC domain: `africa_book.py`, `africa_rtl.py`, `africa_inline_order.py`,
  `africa_numeric_text.py`, `africa_heading_evidence.py`, `models.py`, `multilingual_heading_validation.py`.
- POC infrastructure: `africa_glyphs.py`, `pypdf_reader.py`, `xml_writer.py`.
- POC tests: `test_africa_book_integration.py`, `test_africa_rtl.py`,
  `test_africa_inline_order.py`, `test_africa_numeric_text.py`.

완료 commit의 전체 SHA는 `review_run.json/final_commit`과 최종 응답에 기록한다.
검증된 변경만 현재 브랜치에 로컬 커밋한다. 구조 추출 검증 완료와 사람의 의미 승인은 구분한다.
