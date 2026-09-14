# CE BOOK XML 추출 검증 — 2026-09-14

후속 사용자 판정: CE-SOURCE-01~06 모두 PDF 원장과 일치하므로 **추출 PASS**로 처리했다.
번역·편집 이슈는 향후 에이전트용 [사례집](../../../../docs/review_agent_cases/README.md)에 보존했다.
아래 Warning과 사람 검토 필요 문구는 최초 검증 당시 기록이며, 해당 6건의 최신 추출 판정은 PASS다.
전체 번역 정확성을 일괄 승인한 의미는 아니다. 추출 XML/MD는 변경하지 않았다.

AFRICA 5개 언어는 사용자의 최종 직접 검토 완료 의견으로 확정했다.
CE는 **추출 구조 검증 통과 / 현지어 원문 의미에 대한 사람 검토 필요** 상태다.
모든 현지어 문장의 번역 적합성을 승인한 결과가 아니다.

## 작업 대상과 시작 상태

- PDF: `BN68-26318A-00_SUG_Y26 TV ALL_CE_L05_260422.0.pdf`
- 원본: `C:/Users/bella/image-extractor/.worktrees/xml-extractor-release/samples/SUG_RAW/TV_CE/BN68-26318A-00_SUG_Y26 TV ALL_CE_L05_260422.0.pdf`
- SHA256: `0a0ff58debef3c386332b9708b13d38ffb12cb4b0cfacc3400ab4f93070a7640`
- 작업 worktree: `C:/Users/bella/image-extractor/.worktrees/xml-markdown-review`
- 브랜치: `feature/xml-markdown-review`
- 시작 HEAD: `4aa80dd9193b972ebff4aa2af194c0abd59e74fb`, 시작 미커밋 변경 없음.
- 파일명 파싱·canonical profile 일치: `CE_L05`, `BOOK`, `RUS/ENG/KAZ/MON/KYR`.
- 실제 북마크: Русский p2, English p10, Қазақ p18, Монгол p26, Кыргызча p34.
- PDF 44페이지, 각 약 466.535 × 642.283pt. 모든 언어 LTR.

AGENTS/README/TODO/SUG_RAW_ANALYSIS 및 XML POC 문서를 확인했다. CE 전용 XML 규칙·테스트는
기존에 없었다. 먼저 기존 추출기를 `outputs/xml_review_ce_20260914_before`에 실행한 뒤 결함을
재현했다. 초기 자동 gate 통과만으로 품질을 승인하지 않았다. 모델 제안 GPT-6 Astra/high는
복잡한 문서·코드 검토에 적합하다고 공식 모델 문서에서 확인했으며 설정을 변경했다고 주장하지 않는다.

## 확인한 결함과 최소 수정

1. **표지/언어 경계**: 북마크가 표지 다음 본문부터 시작하므로 기존 구간은 다음 언어 표지를
   이전 언어 구간에 포함하고 p44 러시아어 연락처를 KYR 구간에 포함했다.
   실제 `Cover_Title`의 5개 추출 문자열·페이지, 북마크 순서와 러시아어 연락처 제목을 확인해
   표지 포함 구간을 RUS p1–8, ENG p9–16, KAZ p17–24, MON p25–32, KYR p33–43으로 보정했다.
   p44는 별도 RUS 연락처다. p41–43의 실제 KYR 빈 페이지 안내는 유지한다.
2. **숫자 내부 공백**: 5개 언어 Wi-Fi 주파수의 `7 .125` / `7 ,125`는 PDF 텍스트 연산의
   실제 문자에는 없는 kerning 공백이었다. 같은 MCID의 단일 원본 연산이 정확히 증명하는 경우에만
   공백을 제거했다. ENG는 `7.125`, 나머지는 원본대로 `7,125`다. 숫자/단위/구두점은 바꾸지 않는다.
3. **문장 줄바꿈**: 5개 언어 Eco Sensor 문단의 inline icon 때문에 문장 분리가 제외되었다.
   검증된 아이콘 경로를 CE 프로필에서 허용하여 두 문장을 분리하고 UI 경로는 유지했다.
4. **원본 추가 소제목 표시**: RUS `Режим ожидания`, KAZ `Күту режимі`는 `Table-6_0` 역할이라
   일반 문단처럼 보였다. 실제 추출 문자열, 같은 언어의 뒤따르는 본문, 원본 글자 크기
   9pt/600 대 6.5pt/400 근거로 별도 `strong-label` 표시를 부여했다.
   공통 제목에 가짜 대응을 만들지 않고 원본에만 있는 소제목으로 집계한다.

적용 범위는 `CE_L05 + BOOK + (RUS, ENG, KAZ, MON, KYR)` 정확한 조합이다.
표지·북마크·연락처 근거가 바뀌면 임의 언어 배정 대신 검토 오류로 중단한다.
`domain/ce_book.py`와 `infrastructure/ce_source_evidence.py`에 규칙·근거 수집을 두고 실제 XML
use case/reader/readability 경로에 연결했다. 기존 glyph 관측기를 원본 텍스트 연산 관측에만 재사용한다.
GridCell, `src/content_poc.py`, item_review, Excel/Streamlit, checklist DB는 변경하지 않았다.

## 구조 집계와 원문 예외

본문의 source section 전체 하위 노드를 센 수치다. P/LI는 서로 다른 XML 태그 개수이며,
상위 wrapper나 span을 제외한 '문장 수'로 해석하지 않는다. 빈 셀도 셀 수에 포함한다.
공통 제목은 각 23개(원본 역할 후보 18 + 번호 장 제목 5), 표지 제목은 별도 각 1개다.

| 언어 | 본문 PDF | 공통 제목 | 추가 소제목 | P | LI | 표 | 행 | 셀 | 그림 | 대조 단위 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| RUS | 2–8 | 23 | 1 | 196 | 109 | 18 | 40 | 68 | 46 | 260 |
| ENG | 10–16 | 23 | 0 | 188 | 109 | 17 | 38 | 64 | 44 | 255 |
| KAZ | 18–24 | 23 | 1 | 196 | 109 | 18 | 40 | 68 | 46 | 260 |
| MON | 26–32 | 23 | 0 | 188 | 109 | 17 | 38 | 64 | 44 | 255 |
| KYR | 34–40 | 23 | 0 | 188 | 109 | 17 | 38 | 64 | 44 | 255 |

각 언어에 38개 list container, 114개 list_body(번호 장 제목 내부 포함)가 있다.
안전 심볼 표 각 1개(9행, 이미지 심볼 6개), 사양표 각 1개(6행, 65개 모델/소비전력 쌍 포함),
Wi-Fi 규제 안내 표 각 1개다. RUS/KAZ에는 포장재 심볼 표 1개(2행·그림 2개)가 추가된다.
Inline icon은 언어별 14개이며, 이 중 navigation route icon 8개가 4개 경로를 구성한다.
기타 작은 inline figure 6개와 전체 그림 수를 혼동하지 않는다.
모든 표의 원본 행/셀·ColSpan 및 그림 관계는 JSON trace와 Semantic XML에 남겼다.

RUS/KAZ에만 LED TV 설명, 대기 모드 소제목/본문, 포장재 005/2011 및 재활용 문구가 실제로 있다.
추가 5개 대조 단위를 제외하면 255개 대응 단위의 tag/source-role 순서는 5개 언어 모두 일치한다.
추출 누락을 숨기기 위해 개수를 맞춘 것이 아니라 p8/p24 crop으로 원문 예외를 확인했다.

CE ENG는 ZC ENG 기준을 먼저 확인한 뒤 가까운 ZG BOOK과 비교했다.
CE의 유선 One Connect/레이저 주의, 구성품·모델 목록·소비전력 추가와 ZC Internet security,
ZG Change PIN 및 지역별 규제 문구의 부재는 CE p13–16에 근거한 원문 차이다.
제목 하위가 큰 body로 합쳐지는 결함은 확인되지 않았다.
ENG 대비 네 현지어의 65개 모델→소비전력 값이 모두 일치하고, 화면 해상도·음향 출력·사용/보관
온습도·모델 조건의 수치도 대조했다. 숫자의 철자 표기, II/I→2/1, 모델 조건의 어순 차이는 별도 기록했다.

## PDF → XML → Markdown → HTML 근거

- 원본 44페이지와 표지 영역 crop 24개를 생성했다. 5개 표지 로고/제목/등록/모델·일련번호와
  연락처 header/12개 국가 행/이미지/copyright를 직접 확인했다. Header crop은 국가 행을 포함하지 않는다.
- p44 연락처는 source header 3셀과 국가 행 12개로 분리했다. KAZAKHSTAN GSM `7799`,
  TAJIKISTAN `7779` 등 서로 다른 숫자도 원본 그대로 보존한다.
- 수정 전/최종 Raw XML은 **바이트 동일**. 5,559개 source fragment의 page/MCID/object identity와
  비공백 문자 multiset이 Semantic XML에 그대로 보존된다.
- PyMuPDF와 Raw XML의 **44페이지 문자 counter 차이 전부**를 실제 footer/언어 side-tab 문자열과
  bbox로 설명했다. XML에만 추가된 잔여 문자는 없다. 이 counter 검사는 문장 순서 증명과 별개다.
- Semantic XML → 실제 Markdown DOM은 **96,990 비공백 문자 순서**, 34개 상위 단위와
  524개 writer 단위가 모두 일치한다. missing/added 0, 단위 순서 실패 0.
  목록 번호의 표시 변환과 행/열·이미지·빈 셀 안내는 생성 요소로 명시적으로 구분했다.
  `[빈 셀]` 10개는 실제 빈 XML table_cell 10개와 대응하며, 원문 글자로 세지 않는다.
- Markdown 직접 렌더링과 제공 HTML의 텍스트 및 **2,672개 요소 서명**이 동일하다.
  306개 원문 `*`도 유지된다. 원본 PDF와 HTML의 조판이 픽셀 단위로 같다는 의미는 아니다.
- XML 노드의 source-structure-path, object-ref, page-index, MCID를 통해 원문 위치를 추적한다.
  이번 실행의 경로/대조 번호는 체크리스트 고정 키로 사용하지 않는다.
- PDF metadata의 `ko`, 내부 Document의 `en-US`는 원본 metadata다. 실제 언어는 semantic 노드에
  canonical code로 부여했다. 여러 언어를 포함한 상위 노드에 단일 언어를 억지로 부여하지 않는다.

이미지-only 안전 심볼, 로고, QR/barcode는 crop 근거이며 OCR 결과가 아니다.
문서 코드의 이미지 부분 `BN68-26318A`와 태그에 있는 suffix `-00`을 구분한다.
검토 HTML은 텍스트 미리보기이며 실제 심볼 모양은 표지/원본 근거 화면에서 확인한다.

## 남은 Warning과 판정

추출 **Hard gate 0개**. 원문 표현 Warning 6건은 다음과 같다.

1. MON p28: ENG의 벽 고리 높이 조건 대신 나사 규격 안내가 적혀 있다.
2. MON p26: 접지/보호 접지 용어와 mains-lead 조건의 현지어 확인이 필요하다.
3. MON p28: 스탠드 설치 제목·본문에 벽걸이 표현이 있다.
4. RUS p4: 스탠드를 빼지 말라는 ENG 지시와 넘어뜨리지 말라는 원문 표현이 다르다.
5. MON p27: 원문에 `VESA` 대신 `VERSA`가 적혀 있다.
6. KYR p34/p39: UI 경로의 `Tips and User Guides`가 원본에서 영어로 남아 있다.

각 항목은 PDF 이미지와 실제 추출 문자열을 나란히 제공한다. 의미 판단 범위는 러시아어·몽골어
안전/설치와 일부 KAZ/KYR 조건·UI 등을 집중 검토한 것이며, 모든 문장의 의미를 전수 승인하지 않았다.
안전 문구 차이는 현지어를 확인할 수 있는 검토자에게 넘긴다. 추출기를 고쳐 원문을 번역/교정하지 않는다.
줄 끝 하이픈/URL의 원본 감김은 최종 MD에도 남을 수 있으나 비공백 문자 보존 검사를 통과했다.
추가 사람이 볼 항목을 남긴 추출 검증 완료 상태이며, CE 매뉴얼의 최종 의미 승인은 아니다.

## 테스트와 회귀

- CE 첫 재현: 16 failed / 1 passed. Wi-Fi 테스트의 wrapper 선택은 leaf로 바로잡아 5개 실제
  잘못된 주파수를 별도 재확인했다. Standby 추가 재현: 2 failed / 17 deselected.
- 최종 CE 집중: **33 passed** (`test_ce_book_rules.py`, `test_ce_book_integration.py`).
- 전체 XML POC: **1,948 passed / 1 skipped**, 237.39초. Skip은 Windows symlink 사용 불가.
  ZC/ZG/AFRICA 기존 실제 샘플, reader/use case, Semantic XML/Markdown writer 회귀가 포함된다.
- legacy public import 3개 별도 확인: run_content_poc/write_content_poc_outputs/write_content_review_xlsx.
- root `python -m compileall src tests scripts`, POC `python -m compileall src tests` 성공.
  root apps/scripts 폴더가 없어 scripts는 `Can't list scripts`, 실제 존재하는 폴더는 정상 컴파일했다.
- 독립 코드 리뷰에서 수정 요구 없음. 리뷰어가 CE 31개 및 추가 Standby 2개도 독립 실행했다.
- 새 검토 HTML 4개와 이미지 링크 42개(원문 확인 18 + 표지 crop 24)를 실제 Edge에서 확인했다.

## 결과 위치와 복구

최종 출력 절대 경로:
`C:/Users/bella/image-extractor/.worktrees/xml-markdown-review/samples/tagged_pdf_xml_poc/outputs/xml_review_ce_20260914_final`

그 안에 `raw_structure.xml`, `semantic_document.xml`, `semantic_document.md`, `extraction_report.json`,
`review_document.json`, `review_run.json`, `language_comparison.json`을 보존했다.

- [검토 시작 HTML](../../outputs/xml_review_ce_20260914_review/review_start.html)
- [같은 Markdown의 전체 HTML](../../outputs/xml_review_ce_20260914_review/semantic_document.preview.html)
- [원문 Warning 6건](../../outputs/xml_review_ce_20260914_review/source_findings.html)
- [5개 언어 255개 대응 단위](../../outputs/xml_review_ce_20260914_review/language_comparison.html)
- [표지·연락처 근거](../../outputs/xml_review_ce_20260914_review/cover_evidence.html)
- [최종 Semantic XML](../../outputs/xml_review_ce_20260914_final/semantic_document.xml)
- [최종 Markdown](../../outputs/xml_review_ce_20260914_final/semantic_document.md)

감사 원자료와 실행 로그는 `outputs/xml_review_ce_20260914_evidence`, HTML/DOM 검증 스크립트는
`outputs/xml_review_ce_20260914_review`에 있다. 출력은 Git ignored 로컬 산출물이며 기존 폴더를 보존했다.
복구용 로컬 commit 전체 번호와 파일 hash는 최종 `review_run.json`에 기록한다.

변경 파일: root TODO, CE 작업 계획, AFRICA 사용자 확정 기록, 이 보고서;
XML POC의 `application/extract_document.py`, `domain/readability_formatting.py`,
`infrastructure/pypdf_reader.py`, 신규 `domain/ce_book.py`, `infrastructure/ce_source_evidence.py`,
신규 `tests/test_ce_book_rules.py`, `tests/test_ce_book_integration.py`.
원격 push/merge/rebase, 다른 worktree 수정·정리, DB 후보·승인 작업은 수행하지 않았다.
