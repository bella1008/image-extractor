# ZW Taiwan XML extraction review

ZW_TPE / A3 / TPE(번체 중국어), 2페이지, 북마크 없음. 추출 구조 검증을 통과했으며 사용자 원문/표현 검토를 기다린다. 외부 의미 검토 API, 체크리스트 후보/DB 작업은 사용하지 않았다.

원본: `C:/Users/bella/image-extractor/samples/SUG_RAW/2_TV_ZW/BN68-24973D-00_SUG_Y26 TV ALL_ZW_TPE_260327.0.pdf`

SHA256: `37e8ef8c16b250463c4a57f5efc199a0f65bd8f9a1e10eacc5562b727f82e99f`.
파일명 파싱과 canonical profile mapping이 일치한다. 작업 브랜치는 `feature/xml-markdown-review`, 시작 HEAD는 `e06b998844e3b09887e612f4f22940abffeac2a4`, 시작 미커밋 변경은 없었다.

## 결과

최종 폴더: `C:/Users/bella/image-extractor/.worktrees/xml-markdown-review/samples/tagged_pdf_xml_poc/outputs/xml_review_zw_20260916_source_verified`

- [검토 시작 화면](../../outputs/xml_review_zw_20260916_source_verified/zw_review.html)
- [전체 HTML](../../outputs/xml_review_zw_20260916_source_verified/ZW_TPE/semantic_document.preview.html)
- [Semantic XML](../../outputs/xml_review_zw_20260916_source_verified/ZW_TPE/semantic_document.xml)
- [Markdown](../../outputs/xml_review_zw_20260916_source_verified/ZW_TPE/semantic_document.md)
- [PDF crop와 표지/표 비교 23영역](../../outputs/xml_review_zw_20260916_source_verified/source_checks.html)
- [검증 bundle](../../outputs/xml_review_zw_20260916_source_verified/ZW_TPE/review_document.json), [run 기록](../../outputs/xml_review_zw_20260916_source_verified/ZW_TPE/review_run.json)

`raw_structure.xml`, `extraction_report.json`도 같은 ZW_TPE 하위 폴더에 있다. 기존 폴더는 덮어쓰지 않았다. 초기 결과는 `xml_review_zw_20260916_before`, 중간 결과는 `structure`, `review`, `verified` 접미사 폴더에 남겼다. 검토는 위 **source_verified** 결과를 사용한다.

## 수정 전 결함과 해결

| 관찰된 결함 | 적용한 수정과 근거 |
|---|---|
| 굵은 제목/본문/UI 라벨과 번호 중복 | 같은 위치·글꼴·glyph·원문 바이트를 stroke/fill로 두 번 그린 75쌍을 확인하여 semantic 표시만 한 번 유지. Raw 원문과 제거된 MCID, 유지 MCID, PDF 연산 번호를 보존. 위치가 다른 반복 문구는 제거하지 않음. |
| 중국어 단어 내부의 인위적인 공백과 URL 분리 | 실제 PDF glyph 연산과 일치하는 326개 경계만 연결. 실제 원문 공백, Latin/모델 경계는 보존. 문단·표 셀·목록·그림 경계를 넘지 않음. |
| 표지가 본문 뒤에 위치 | 원문 표지 stories를 먼저 배치하고 원래 XML 경로 보존. |
| PDF 언어 metadata가 ko/en-GB | 등록 프로필의 TPE를 semantic에 적용. 원래 선언 언어는 진단에 별도 보존. |
| 첫 電源 불릿의 연속 설명 분리 | 원문 들여쓰기와 정확한 문장/태그 구조에 따라 같은 list body로 연결. |
| 소비전력 표의 다음 칼럼 내용을 별도 무제목 행으로 표시 | 37개 + 다음 칼럼 12개, 총 49개 모델/수치가 같은 소비전력 셀에 속하도록 연결. 원래 continuation 셀을 원문 경로가 있는 section으로 보존. |
| RoHS 병합 셀을 평면 목록으로 표시 | 원본 rowspan/colspan 구조를 보존하는 HTML table 표현 사용. MD에도 같은 table 구조 포함. |
| Form/OBJR 때문에 gate 실패 | Form29는 텍스트 없는 벡터 벽면 그림임을 전체 연산/리소스로 확인. OBJR31/32는 이미 추출된 www.samsung.com의 URI annotation. 원래 진단과 PDF 객체 근거를 audit에 보존하고 확인된 3건만 해소. |
| 중복 제거 후 특수문자 gate 오판 | 독립 baseline의 원래 기호 수가 raw와 같을 때만, 원본 연산에서 다시 계산한 중복 인쇄분을 반영. 실제 기호가 빠지면 여전히 실패하는 회귀 테스트 추가. |

모든 새 동작은 실제 XML 경로이며 ZW_TPE + A3 + TPE 및 승인된 원본 SHA에 한정된다. 다른 원본 revision은 재검토 오류로 차단한다. 구 GridCell 코드나 `content_poc` 추출 규칙은 수정하지 않았다.

## 수치와 원문 대조

| TPE 항목 | 결과 |
|---|---:|
| 표시 제목 | 24 (표지 1 포함) |
| 번호 장 제목 | 4 (01–04) |
| 검토 단위 | 122 |
| 원본 paragraph 노드 | 299 |
| list / list item | 35 / 107 |
| table / figure 노드 | 17 / 42 |
| 안전 표 | 9행, 심볼 셀 6개 |
| UI/navigation 경로 | 5 |
| 모델·소비전력 대응 | 49쌍, 독립 PDF 텍스트와 순서까지 일치 |
| RoHS | 6개 부품 × 6개 물질 = 36셀 |
| 원문 텍스트 조각 | 1,233, 원래 MCID 소유 관계 추적 |

paragraph/figure 수는 태그 노드 수이며 검토 단위 수와 합산하지 않는다. 제목 24개는 4개의 번호 장 제목과 source role/style로 확인한 나머지 제목을 포함한다.

PDF 두 페이지, 표지 영역, 안전 표, 조작/마이크 그림, 사양표 및 RoHS crop을 직접 대조했다. RoHS Pb는 회로기판/금속/패널/부속의 면제 표시 4개, 외장/스피커의 원 2개이며 나머지 30셀은 원이다. 모델/수치의 값뿐 아니라 소비전력 소속도 검사했다.

비교 기준은 XU A3 ENG(접힌 sheet), KR A3(CJK), 검증된 TK ENG 구조다. 이 PDF에는 ENG가 없으므로 같은 PDF의 ENG와 제목 수를 억지로 맞추지 않았다. 서비스 비용 조건은 실제로 없으며, 무선 네트워크/RoHS/대만 전파·시력 주의문구와 확장 소비전력표는 원본 차이로 보존했다. 표지 연락처는 대만 단일 연락처 블록이며 국가별 연락처 표가 아니다.

## Gate와 남은 검토 사항

Hard gate **0**. XML→MD 전체 문자 순서 및 122개 단위 일치, MD→HTML 텍스트/구조 일치. 원문 MCID별 텍스트는 증명된 중복 인쇄분 외 누락/중복이 없다. 제목/목록/표/소비전력 소속/읽기 순서 및 원문 위치 추적 검사를 통과했다. 최종 승인 기록 전에 원본·출력·HTML 검증 파일 hash를 검사하여 오래된 검증 결과를 재사용하지 않도록 했다.

Warning은 다음 네 범주로 기록했다. 앞의 두 건은 추후 편집/번역 에이전트 예시이며 추출 결함이 아니다.

1. 마이크 지원 모델의 `9*H`는 PDF도 동일하다. `R9*H`로 추정 수정하지 않았다.
2. 전원 설명의 `造成‵電擊`, `免受於受到`, `造成會電擊`는 PDF 원문 그대로다.
3. 표지 `BN68-24973D`는 벡터 윤곽선이다. PDF 텍스트는 `-00`만 있고, 전체 `BN68-24973D-00`은 crop을 직접 읽은 전사로 별도 표시했다. 자동 OCR/텍스트 추출 결과라고 주장하지 않는다.
4. 안전 심볼·barcode·조작 그림·UI 아이콘은 이미지 crop 근거를 사용한다. HTML/MD의 placeholder를 아이콘 인식 결과로 해석하지 않는다.

추출 검증은 완료했으나 대만 원문 표현에 대한 사용자 승인을 대신하지 않는다. HTML은 MD와 동일한 검토 내용이며 PDF의 조판을 그대로 복제한 화면은 아니다.

## 검증 실행 기록

- 최종 XML 전체 테스트: **2,311 passed, 1 skipped** (415.78초). Windows 환경에서 symlink를 만들 수 없어 관련 테스트 1개를 건너뜀. 새 보고서 무결성 테스트 6개는 이 전체 실행 후 별도 통과했다.
- ZW + XML/Markdown writer 집중: **432 passed**.
- 검증 기록 무결성 추가 테스트: **6 passed** (변경/누락된 MD·HTML·gate/검증 기록은 승인 거부).
- 루트 기존 테스트: **62 passed, 6 subtests passed**.
- public import: `run_content_poc`, `write_content_poc_outputs`, `write_content_review_xlsx` 3개 callable 확인.
- compileall: POC `src tests scripts`, 루트 `src tests` 성공. 이 worktree 루트에는 scripts/apps가 없고 POC에는 apps가 없다.
- ZC / ZG / AFRICA / CE / XU / KR / LATIN 및 TK_L02 / TK_ARA 재추출: 기존 XML·MD **27개 파일 바이트 동일**. [회귀 근거](../../outputs/xml_review_zw_20260916_regression/comparison.json).
- 독립 코드 검토에서 찾은 revision 범위와 검증 기록 무결성 문제도 회귀 테스트 후 수정했다.

## 변경 파일

작업 루트: `C:/Users/bella/image-extractor/.worktrees/xml-markdown-review`.

- `TODO.md`
- POC `application/extract_document.py`, `application/evaluate_quality.py`, `infrastructure/pypdf_reader.py`
- POC `domain/zw_sheet.py`, `domain/zw_source_text.py`, `domain/zw_line_join.py`
- POC `infrastructure/zw_source_evidence.py`, `infrastructure/zw_object_evidence.py`
- POC `tests/test_zw_sheet.py`, `test_zw_source_text.py`, `test_zw_line_join.py`, `test_zw_object_evidence.py`, `test_zw_review_finalization.py`
- POC `scripts/review_zw_xml.py`, `finalize_zw_review.py`, `render_representative_review.cjs`, `render_tk_source_checks.cjs`
- POC `docs/plans/2026-09-16-zw-extraction.md` 및 이 보고서

POC 코드 경로의 application/domain/infrastructure는 `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/` 아래다. 로컬 복구 커밋 전체 번호는 완료 메시지 및 최종 `review_run.json`에 기록한다.
