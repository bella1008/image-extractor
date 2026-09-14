# CE BOOK 문장 소속 수정 검증

대상 PDF: `BN68-26318A-00_SUG_Y26 TV ALL_CE_L05_260422.0.pdf`
source_token: CE_L05 / BOOK / 실제 북마크 순서 RUS → ENG → KAZ → MON → KYR.

시작 브랜치: feature/xml-markdown-review. 시작 HEAD: `7344b67e7f8496cf2a3cef093bc856d8d0cc9d84`.
시작 시 미커밋 변경 없음. 이 worktree 외의 코드, checklist DB, item_review, Excel/Streamlit 코드는 변경하지 않았다.

## 확인된 결함과 수정

1. PDF 2p RUS Электропитание 첫 불릿의 `Сведения о напряжении…`가 독립 문단으로 떨어졌다. 해당 문장은 첫 불릿의 연속 설명이다. ENG/KAZ/MON/KYR의 PDF 10/18/26/34p에서도 같은 관계를 확인했다. 원래 문단의 source path와 fragment를 보존하면서 앞 list_body의 span으로 이동했다. Markdown은 같은 불릿 내 문장 줄바꿈으로 표시한다.
2. PDF 8p RUS 서비스 비용 안내의 `(а)/(б)`는 도입문의 두 하위 조건이다. ENG/KAZ/MON/KYR의 PDF 16/24/32/40p도 같은 구조다. 도입문과 두 항목을 한 semantic section으로 묶고 list/list_item으로 표현했다. 원문 문단과 기호는 보존했다. KAZ `(a)/(ә)`, MON `(а)/(b)`, KYR `(a)/(б)`를 임의로 통일하지 않았다.

PDF 태그가 해당 부분을 UnorderList_1-Bullet 일반 문단으로 저장했으며, 필요한 text bbox가 없어 보수적인 공통 연결 탐지기가 연결하지 못했다. CE_L05 + BOOK + 검증된 5개 언어 조합에서만 실제 추출 문구, 앞뒤 태그, 페이지와 언어를 확인하여 수정한다. 일반 writer나 다른 바이어 규칙은 바꾸지 않았다.

재배치 후 RUS/KAZ Standby 부제목 표시 힌트는 현재 트리 경로로 다시 계산했다. source_structure_path는 계속 원본의 위치를 가리킨다. 원문 노드 경로를 체크리스트 키로 사용하지 않는다.

## 원문과 표시 근거

- 수정 전 실제 PDF 재현 테스트: 두 결함 × 5언어 = 10개 실패 확인.
- 해당 PDF crop 10개와 최종 HTML 캡처 10개를 각각 검토했다.
- 원본 구조 경로 5,025개 전부 유지. 원문 노드 중 소속/역할 변경은 의도한 20개뿐이다: 전원 연속문장 5개, 비용 도입문 5개, 비용 조건 10개.
- raw_structure.xml은 기존 추출과 동일하다. source fragment 식별자와 비공백 글자 수 보존 검사 통과.
- XML → Markdown 실제 렌더링: 비공백 문자 96,990개 순서 일치, 누락 0, 추가 0.
- 원문 상위 단위 34개, writer 단위 514개 모두 문자 순서 일치. Markdown과 HTML DOM 2,708개 요소의 내용/구조 서명 일치.
- 다섯 언어 DOM에서 전원 설명은 단일 list item 안의 줄바꿈, 비용 조건은 도입문 다음 2개 list item으로 확인했다.
- 기존 본문/표/모델/경고/표지 원문 감사는 source paths와 원문 유지 근거로 승계했다. 외부 의미 검토 API는 사용하지 않았다.

## 언어별 수치 (본문)

| 언어 | 공통 제목 | 추가 원문 부제목 | paragraph | list/list_item | table | 행/셀 | figure |
|---|---:|---:|---:|---:|---:|---:|---:|
| RUS | 23 | 1 | 195 | 39 / 111 | 18 | 40 / 68 | 46 |
| ENG | 23 | 0 | 187 | 39 / 111 | 17 | 38 / 64 | 44 |
| KAZ | 23 | 1 | 195 | 39 / 111 | 18 | 40 / 68 | 46 |
| MON | 23 | 0 | 187 | 39 / 111 | 17 | 38 / 64 | 44 |
| KYR | 23 | 0 | 187 | 39 / 111 | 17 | 38 / 64 | 44 |

수치는 중첩 구조 노드를 포함하므로 합계가 독립 문단 수를 뜻하지 않는다. 공통 제목 23개에는 원래 heading 5개와 검증된 제목 후보 18개가 포함된다. RUS/KAZ에는 원문에 실제 LED TV 표기, Standby 부제목/본문, 포장 심볼 표가 더 있다. 모든 언어에 안전 심볼 표 1개, 사양표 1개, Wi-Fi 규제 안내 1개, 모델/사운드 출력 수치 쌍 65개, navigation 경로 4개, inline icon 14개를 유지했다. 별도 러시아어 연락처 표 p44의 source header와 12개 국가 행도 유지했다.

## Gate와 검토 범위

Hard gate 잔여 0. 이번 두 구조 문제는 5언어 모두 수정 검증 완료.
사용자가 승인한 CE-SOURCE-01~06은 원문 충실도 PASS를 승계하며 향후 번역/편집 에이전트 사례로 보존했다. 새 추출 결함 Warning은 없다. 해당 원문 표현의 번역/편집 판단 및 TRAMS KYR 승인 용어 조회는 향후 검토 범위이며 전체 번역 품질을 승인한 뜻은 아니다.

러시아어 검증만으로 다른 언어 검증을 생략해서는 안 된다. 이번에도 5개 언어 각각 원문 crop, 문장 소속, 목록 기호, XML/MD/HTML을 확인했다. 특히 RUS/KAZ 원문 추가 구조와 MON/KYR 표현/용어 차이가 이미 있어 동일 레이아웃만으로 의미까지 보장할 수 없다. 사용자는 수정 부위를 아래 비교 화면으로 확인할 수 있다.

## 실제 검증 결과

- 전체 XML POC pytest: **1,980 passed, 1 skipped**, 252.21초.
- 전체 실행에 포함된 CE 관련 테스트: **65개** (기존 규칙 14, 실제 PDF 통합 29, 소속 보호 테스트 22).
- 이번에 새로 추가한 테스트: 결함 재현 10 + scope/변경 원문/페이지/언어/원문 보존 보호 22 = 32개.
- 1개 skip은 `test_output_bundle.py::test_preflight_rejects_non_regular_required_targets_before_staging[symlink]`의 Windows symlinks unavailable. PDF/언어 테스트 skip 없음.
- ZC/ZG/AFRICA 실제 샘플 회귀, semantic XML/Markdown writer 테스트가 전체 suite에서 통과했다. 사람의 번역 재검토를 뜻하지 않는다.
- legacy public import 3개 callable 확인. XML public import 테스트도 포함.
- compileall: root src/tests, POC src/tests 통과. root scripts/apps 폴더가 없어 scripts에는 Can't list 안내가 출력됨.
- 독립 코드 검토: actionable finding 없음.

## 산출물

최종 추출 폴더 (아래 XML/MD/JSON 모두 이 폴더):
`C:/Users/bella/image-extractor/.worktrees/xml-markdown-review/samples/tagged_pdf_xml_poc/outputs/xml_review_ce_20260914_paragraph_final`

- semantic_document.xml
- semantic_document.md
- raw_structure.xml
- extraction_report.json
- review_document.json
- review_run.json

검토 폴더:
`C:/Users/bella/image-extractor/.worktrees/xml-markdown-review/samples/tagged_pdf_xml_poc/outputs/xml_review_ce_20260914_paragraph_review`

- semantic_document.preview.html: 전체 MD 표시
- paragraph_findings.html: 5언어 원문 crop와 수정 HTML 비교
- character_audit.json, ownership_delta.json, relationships_dom.json: 문자/소속 근거
- red_tests.log, full_tests.log, ce_test_inventory.txt, root_compileall.log, poc_compileall.log

기존 추출과 사용자 승인 산출물은 덮어쓰지 않았다. 향후 에이전트 사례 라이브러리도 수정하지 않았다.

## 변경 파일

- samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/domain/ce_book.py
- samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/domain/ce_paragraph_ownership.py
- samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/domain/ce_paragraph_source.py
- samples/tagged_pdf_xml_poc/tests/test_ce_book_integration.py
- samples/tagged_pdf_xml_poc/tests/test_ce_paragraph_ownership.py
- docs/superpowers/plans/2026-09-14-ce-paragraph-ownership.md
- samples/tagged_pdf_xml_poc/docs/reviews/2026-09-14-ce-paragraph-ownership.md
- TODO.md

로컬 복구 커밋은 이 문서를 추가한 Git 커밋이며 최종 번호는 review_run.json에도 기록한다.
