# 대표 바이어 전원 연속문장 / 비용 하위 조건 수정 검증

이번에 승인받은 범위의 추출 검증을 완료했다. 확인된 구조 결함 8건을 수정했고,
기존 관계를 포함한 31곳 및 XML→Markdown 검토 단위 2,489개가 통과했다.
모든 바이어의 번역을 새로 승인했다는 뜻은 아니다. TK 신규 추출은 다음 단계다.

## 작업 상태와 범위

- 작업장: `C:/Users/bella/image-extractor/.worktrees/xml-markdown-review`
- 브랜치: `feature/xml-markdown-review`
- 시작 HEAD: `c3a497358124eaab6538d799c72c66986af72a8c`
- 시작 미커밋 변경: 없음.
- 집중: ZC/CE/AFRICA/ZG. XU: A3 비용 조건. KR/LATIN: 자동 회귀.
- XML POC 안에서만 추출 코드를 수정했다. GridCell, item_review, Excel/Streamlit,
  checklist DB 및 다른 작업장은 변경하지 않았다. 원격 push/merge/rebase 없음.

| 바이어 | source_token | 유형 | 실제 처리 언어 순서 | PDF 파일명 |
|---|---|---|---|---|
| ZC | ZC_L02 | A2 | ENG, C-FRA | BN68-25100B-00_SUG_Y26 TV ALL_ZC_L02_260122.0.pdf |
| CE | CE_L05 | BOOK | RUS, ENG, KAZ, MON, KYR | BN68-26318A-00_SUG_Y26 TV ALL_CE_L05_260422.0.pdf |
| AFRICA | AFRICA_L05 | BOOK | ENG, FRA, SPA, POR, ARA | BN68-25031G-00_SUG_Y26 TV ALL_AFRICA_L05_251230.0.pdf |
| ZG | ZG XN ZT_L05 | BOOK | ENG, DEU, FRA, ITA, DUT | BN68-25448A-00_SUG_Y26 TV ALL_ZG XN ZT_L05_260204.0.pdf |
| XU | XU_ENG | A3 | ENG | BN68-24437C-01_SUG_Y26 TV ALL_XU_ENG_260129.0.pdf |
| KR | KR_KOR | A3 | KOR | BN68-25108A-00_SUG_Y26 TV ALL_KR_KOR_251218.0.pdf |
| LATIN | LATIN_L02 | A2 | ENG, M-SPA | BN68-24972A-00_SUG_Y26 TV ALL_LATIN_L02_250105.0.pdf |

파일명 토큰과 profile mapping으로 확인했으며 BOOK 북마크 순서를 사용했다.
AFRICA ARA의 역방향 페이지 읽기, CE의 표지 포함 구간 및 러시아어 연락처 뒷표지 처리는 유지했다.
입력 PDF 절대 경로, SHA256 및 북마크 구간은 최종 `manifest.json`에 기록한다.
CE는 `xml-extractor-release/samples/SUG_RAW/TV_CE`의 PDF를 읽기 전용으로 사용했다.

## 수정 전 문제와 수정 범위

| 대상 | 수정 전 | 수정 후 |
|---|---|---|
| ZC C-FRA p2 | 전원 사양 참조 문장이 첫 불릿과 분리 | 같은 list_body 안에 source span으로 연결, 문장 줄바꿈 유지 |
| AFRICA ARA p35 | 동일한 전원 설명이 독립 문단 | 같은 불릿에 연결, RTL 및 원문 순서 유지 |
| ZG ENG/DEU/FRA/ITA/DUT p8/18/28/38/48 | 비용 도입문과 (a)/(b)가 독립 문단 3개 | section 안에서 도입문 + 두 항목의 list로 연결 |
| XU ENG p2 | 동일한 비용 조건 분리 | ZG와 같은 검토 구조로 연결 |

일반 위치 기반 continuation detector의 조건을 완화하지 않았다.
`verified_paragraph_source.py`는 위 PDF에서 추출하고 crop으로 확인한 문자열만 비교용으로 보관한다.
공백 접기 외의 번역·치환·문구 수정은 하지 않는다.
`verified_paragraph_ownership.py`는 source_token + doc_type + language,
프로필 언어 순서, 같은 페이지, 원본 태그, 형제 노드 순서와 정확한 문구를 모두 확인한다.

번호 제목이 일반 문단으로 태그된 PDF의 언어 구간은 임시 제목 판별 결과로 확인한다.
문장 재배치 뒤 최종 제목/표시 힌트를 다시 계산해 XML 경로가 다른 노드를 가리키지 않게 했다.
원본 source_structure_path와 raw_children, object-ref, MCID는 추적 근거로 보존하며
노드 ID를 고정 체크리스트 키로 사용하지 않는다.

CE의 기존 5언어 수정은 그대로 두고 회귀로 확인했다. 이미 연결되던 전원 설명 13곳도 보존했다.
독립 코드 검토에서 추가로 확인한 변형 태그의 순서 문제는, list_body가 항목의 마지막 자식일 때만
문장을 붙이는 조건으로 차단했다. 실패 테스트 2건 → 통과를 확인했다.

## 실제 검증 근거

- 수정 전 새 추출 결과에서 결함 재현: 예상한 소속 실패 8건, 원문 조각 검사 통과 4건.
- 수정 후 소속: 전원 20곳 + 비용 11곳 = 31곳 통과. CE는 각 5곳 포함.
- 7개 PDF의 raw_structure.xml: 수정 전후 바이트 단위 동일.
- 모든 semantic text 조각: 페이지/MCID/object-ref/공백 제외 문자 순서가 수정 전후 동일.
- 제목 순서, 표/그림 원문 서명, 기존 표시 힌트가 가리키는 원문 서명: 동일.
  수정한 전원 설명 안의 문장 줄바꿈 힌트 변경은 별도로 허용·확인했다.
- CE/KR/LATIN: semantic XML과 Markdown 파일도 수정 전후 바이트 단위 동일.
- 실제 Markdown을 Marked로 렌더링한 뒤 전체 원문 문자 순서와 개별 검토 단위를 대조:
  AFRICA 441, CE 514, KR 239, LATIN 191, XU 132, ZC 198, ZG 774개 — 합계 2,489개 모두 통과.
- Markdown 직접 렌더링과 저장된 HTML의 텍스트 및 제목/list/table/link/br 요소 서명 동일.
- native 불릿·숫자 목록 표식은 HTML 구조로 검사하며 문자 대조에서 분리한다.
  원문 의미 표식 `※` 및 `a)`~`g)`는 문자 대조에 포함해 보존을 확인했다.
- 수정한 8곳의 PDF/HTML 비교 이미지를 직접 확인했다. ARA crop은 p35 왼쪽 전원 영역으로
  보정했고, 긴 비용 조건의 마지막 줄도 확인할 수 있도록 주변 원문을 포함했다.

## 언어별 수치

아래 제목은 추출기의 **본문 제목 감사 수치**다. 표지나 표시용 소제목을 포함한 전체 HTML 제목 수와
정의가 다르므로 혼용하지 않는다. 단일 언어 XU/KR은 다국어 제목 감사가 없어 괄호 안에 추출 표시 제목 수를 적었다.
검토 단위는 목록·표를 하나의 단위로 보고 그 외 문단을 순회한 단위다.
표는 XML table 노드 수(중첩 포함), 아이콘은 inline-icon 표시 근거 수다.
페이지 구간 밖 표지/뒷표지는 전체 문서 2,489개 검증에 포함되며 아래 언어 합계와 다를 수 있다.

| 바이어 | 언어 | 제목 | 검토 단위 | 목록 | 목록 항목 | XML 표 | 인라인 아이콘 |
|---|---|---:|---:|---:|---:|---:|---:|
| ZC | ENG | 22 | 100 | 36 | 114 | 16 | 16 |
| ZC | C-FRA | 22 | 98 | 36 | 114 | 15 | 16 |
| CE | RUS | 23 | 103 | 39 | 111 | 18 | 14 |
| CE | ENG | 23 | 99 | 39 | 111 | 17 | 14 |
| CE | KAZ | 23 | 103 | 39 | 111 | 18 | 14 |
| CE | MON | 23 | 99 | 39 | 111 | 17 | 14 |
| CE | KYR | 23 | 102 | 39 | 111 | 17 | 14 |
| AFRICA | ENG | 22 | 85 | 33 | 100 | 14 | 14 |
| AFRICA | FRA | 21 | 83 | 33 | 100 | 13 | 14 |
| AFRICA | SPA | 21 | 83 | 33 | 100 | 13 | 14 |
| AFRICA | POR | 21 | 83 | 33 | 100 | 13 | 14 |
| AFRICA | ARA | 22 | 98 | 33 | 100 | 15 | 14 |
| ZG | ENG | 26 | 151 | 45 | 128 | 29 | 26 |
| ZG | DEU | 26 | 153 | 45 | 128 | 29 | 26 |
| ZG | FRA | 26 | 151 | 45 | 128 | 29 | 26 |
| ZG | ITA | 26 | 154 | 45 | 128 | 29 | 26 |
| ZG | DUT | 26 | 159 | 45 | 128 | 30 | 26 |
| XU | ENG | (26) | 132 | 43 | 136 | 24 | 14 |
| KR | KOR | (27) | 239 | 47 | 129 | 22 | 22 |
| LATIN | ENG | 21 | 95 | 34 | 101 | 16 | 14 |
| LATIN | M-SPA | 21 | 96 | 34 | 101 | 16 | 14 |

AFRICA는 이전에 확인한 Jordan 전용 제목이 ENG/ARA에만 있어 22/21/21/21/22이며
공통 부분은 21개다. 이번 변경으로 생긴 차이가 아니다. CE RUS/KAZ 원문 추가 구조,
언어 구간에 포함되는 연락처 뒷표지와 중첩 표도 총수 차이의 원인이므로 전체 숫자만 맞추지 않았다.
각 표의 행/셀/그림 수, 실제 XML 태그별 블록 수와 표시 역할별 수는 바이어별 review_document.json에 기록한다.

## 테스트와 판정

- 전체 XML POC: `python -m pytest -q` — **2,082 passed, 1 skipped**.
- 새 집중 테스트: 실제 PDF 12 + 적용 범위/문맥/반복 실행 90 = **102개**, 전체 테스트에 포함.
- 기존 CE: **65개**, AFRICA: **188개**, layout regression: **25개**, 모두 전체 테스트에서 통과.
- XML writer **102개**, Markdown writer **283개**, 모두 전체 테스트에서 통과.
- 기존 public import 3개 callable 확인:
  `src.content_poc.run_content_poc`, `write_content_poc_outputs`, `write_content_review_xlsx`.
- compileall: POC `src tests scripts` 통과. 루트 `src tests scripts` 통과(exit 0),
  루트 scripts 디렉터리가 없어 `Can't list 'scripts'` 안내가 있으며 apps도 없다.
- skip 1개: Windows 심볼릭 링크 생성 불가 시 제외되는 output bundle 보호 테스트.
  실제 PDF 샘플 누락으로 건너뛴 테스트는 없다.
- 독립 코드 재검토: 추가 조치 필요 사항 없음. 별도로 관련 **98개**를 재실행해 통과.

**이번 범위의 Hard gate 잔여 0. 추가 검토가 남은 새 추출 Warning 0.**
기존에 사용자가 원장 충실도 PASS 처리한 CE 원문 표현 6건은 향후 번역/편집 에이전트 사례로 유지한다.
이미지 전용 심볼·barcode 및 기존 원문 표현 검토 이력도 유지한다. 이번 작업은 그 의미를 재승인하거나
OCR 문자로 확정하는 작업이 아니다. 외부 의미 검토 API와 체크리스트 DB 작업은 사용하지 않았다.

## 최종 산출물과 복구

최종 폴더:
`C:/Users/bella/image-extractor/.worktrees/xml-markdown-review/samples/tagged_pdf_xml_poc/outputs/xml_review_common_20260915_verified`

- `ownership_findings.html`: PDF crop와 최종 Markdown의 31개 관계 비교, 바이어별 전체 HTML 링크.
- 각 `ZC/CE/AFRICA/ZG/XU/KR/LATIN/`:
  `raw_structure.xml`, `semantic_document.xml`, `semantic_document.md`,
  `semantic_document.preview.html`, `extraction_report.json`,
  `review_document.json`, `review_run.json`, `html_validation.json`.
- 폴더 루트: `manifest.json`, `review_summary.json`, `html_summary.json`, `review_run.json`.
- 수정 전 추출과 테스트 로그: 같은 outputs 아래 `xml_review_common_20260915_before`.
- 최종 커밋 전체 번호는 완료 답변과 최종 review_run.json의 recovery_commit에 기록한다.

변경 파일:

- `TODO.md`
- `docs/superpowers/plans/2026-09-15-representative-paragraph-ownership.md`
- `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/application/extract_document.py`
- `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/domain/verified_paragraph_source.py`
- `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/domain/verified_paragraph_ownership.py`
- `samples/tagged_pdf_xml_poc/tests/test_representative_paragraph_ownership.py`
- `samples/tagged_pdf_xml_poc/tests/test_verified_paragraph_ownership.py`
- `samples/tagged_pdf_xml_poc/scripts/review_representative_ownership.py`
- `samples/tagged_pdf_xml_poc/scripts/audit_representative_ownership.py`
- `samples/tagged_pdf_xml_poc/scripts/render_representative_review.cjs`
- 이 보고서 `samples/tagged_pdf_xml_poc/docs/reviews/2026-09-15-representative-paragraph-ownership.md`

이번 대표 유형의 두 문장 소속 개선은 추출 검증 완료다. 사용자는 최종 비교 HTML로 수정부를 확인할 수 있다.
다음 신규 바이어 단계는 TK_L02 ENG/TUR를 먼저 검증하고 TK_ARA A3를 이어서 검토하는 순서다.
