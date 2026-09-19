# PY / SQ MI XML extraction review — 2026-09-19

추출 구조 검증 통과, 사용자 승인 대기. 기존 MENA / XL / XT / TK / ZW의 승인 상태는 변경하지 않았다. PY / SQ_MI를 포함한 승인 대기는 7개 바이어이다. 번역 품질 승인이나 DB 승인으로 해석하지 않는다.

## 작업 범위와 원본

- 작업장: `C:/Users/bella/image-extractor/.worktrees/xml-markdown-review`
- 브랜치: `feature/xml-markdown-review`
- 시작 HEAD: `bd4fca7264166040b25766a1dce1f67ee7e1415d`, 시작 시 미커밋 변경 없음.
- PY: `samples/SUG_RAW/TV_PY/BN68-26639A-00_SUG_Y26 TV ALL_PY_ENRU_260427.0.pdf`
  - `PY_ENRU`, A2, RUS → ENG, 2페이지, 북마크 없음.
  - SHA256 `973824f547bebb72fcd57e8c6ca50a455b2c8b83ea5392822fca2c461ddee1c1`
- SQ MI: `samples/SUG_RAW/TV_SQ_MI/BN68-24437H-00_SUG_Y26 TV ALL_SQ MI_HEAR_260220.0.pdf`
  - `SQ MI_HEAR`, A2, HEB → ARA, 2페이지, 북마크 없음. 영어 없음.
  - SHA256 `28831342b1433d01fbc93a8276bb4de1692dbc7cc7c5996d95204a468b9bcf18`
- 파일명과 canonical profile을 대조했고 실제 페이지와 일치함을 확인했다. 폴더 이름으로 언어를 추정하지 않았다.
- XML POC 경로만 수정했다. GridCell, root src, item_review, Excel/Streamlit, checklist DB, 다른 worktree를 수정하지 않았다. push/merge/rebase 없음.

## 수정 전 결함과 적용 범위

수정 전 출력은 `outputs/xml_review_py_sq_mi_20260919_before`에 보존했다. 자동 품질 검사만으로 잡히지 않는 결함은 PDF crop과 소스 문자 조각, object reference, MCID, 좌표를 대조해 확인했다. 실패 테스트를 확인한 후 수정했다.

PY는 표지 순서, 전원 설명의 연속문장 소속, 서비스 비용 (a)/(b) 하위 조건, 소수점·네트워크 주소 및 러시아어 복합 제목의 공백 경계를 수정했다. RUS/ENG에 각각 모델·소비전력 80쌍, 연락처 머리글 1행과 국가 12행이 보존된다. PY ENG를 ZC ENG와 먼저 대조한 뒤 PY RUS를 같은 파일 ENG 및 CE RUS와 비교했다. 러시아어의 포장재/규제 자료와 표지 코드 영역 때문에 전체 표·그림 수는 영어와 다르다.

SQ MI는 잘못된 언어 구간/표지 순서, 본문에 남은 제목 역할, HEB/ARA 읽기 순서, 문장 끝 문장부호, 결합부호, 소수·인치 따옴표·괄호·모델 별표 소속, 혼합 RTL/LTR 순서와 실제 공백 누락을 수정했다. HEB 번호 제목 01~05를 복원했고 음향 모델/수치를 16개 LTR 묶음으로 표시한다. 모델명·The Frame 등의 묶음을 합하면 44개 LTR isolate이다. HEB Wi-Fi와 5.925 사이의 실제 공백은 PDF의 원래 공백 문자와 좌표를 확인해 XML과 MD 양쪽에 보존했다.

SQ의 source font/ActualText 매핑 때문에 원시 괄호 수는 여는 괄호 72 / 닫는 괄호 66이었다. 원문 네 영역의 문자 위치와 글꼴 근거를 통해 69 / 69로 복원했다. 포괄적인 문자 수 검사 예외가 아니라 정확한 SHA, 원시 문자, MCID, 위치를 재검증하는 한정 규칙이다. 원시 XML은 보존하며 문자 이동·제어문자 제거의 이력을 기록한다.

새 규칙은 `source_token + A2 + language + source SHA`로 제한했다. 일반 언어 규칙으로 확장하지 않았다. 현지어 제목을 번역해 만들지 않았고 노드 ID를 고정 checklist 키로 사용하지 않았다. SQ에는 영어가 없으므로 검증된 MENA/TK ARA 구조를 참고하고 HEB/ARA 각각을 실제 원문과 대조했다.

## 최종 산출물과 수치

최종 폴더:
`C:/Users/bella/image-extractor/.worktrees/xml-markdown-review/samples/tagged_pdf_xml_poc/outputs/xml_review_py_sq_mi_20260919_verified`

- 시작 화면: `review.html`
- PDF / Markdown 비교: `source_checks.html`, 비교 화면 PNG 117개.
- 하위 `PY_ENRU`와 `SQ_MI_HEAR` 각각에 `raw_structure.xml`, `semantic_document.xml`, `semantic_document.md`, `semantic_document.preview.html`, `extraction_report.json`, `review_document.json`, `review_run.json`, `source_audit.json`, `html_validation.json`이 있다.
- 독립 원문 증거: `outputs/py_source_review_20260919`, `outputs/sq_mi_source_review_20260919`, `outputs/sq_mi_spec_review_20260919`.
- 원문 검토와 최종 산출물의 해시는 각 `source_audit.json`에 연결했다. PY의 raw/XML/MD는 독립 검토본과 바이트 동일하다. SQ의 최종 공백 수정은 실제 최종 XML/MD/HTML에서 다시 확인했으며, 나머지 15개 수정 영역은 이전 원문 검토와의 텍스트 동일성을 확인했다. 기존 20개 비교 이미지 검토 재사용 사실도 기록했다.

| 바이어 | 언어 | 표시 제목 | 검토 단위 | 문단 | 목록 / 항목 | 표 | 그림 노드 |
|---|---|---:|---:|---:|---:|---:|---:|
| PY | RUS | 24 | 109 | 256 | 38 / 115 | 21 | 50 |
| PY | ENG | 24 | 104 | 245 | 38 / 115 | 18 | 45 |
| SQ_MI | HEB | 24 | 103 | 142 | 37 / 113 | 19 | 47 |
| SQ_MI | ARA | 24 | 101 | 139 | 37 / 113 | 18 | 45 |

표시 제목 24는 표지 1 + 본문 23이며 본문에는 번호 제목 5개가 포함된다. 검토 단위는 문단·목록·표를 묶은 단위이므로 내부 문단/항목 수와 다르다. 그림은 XML figure 노드 수이며 고유 아이콘 수가 아니다. PY의 명시적 heading 노드는 5개이나 원문 스타일 기반 제목을 포함한 표시 제목은 24개이다. SQ는 제목 역할을 복원한 명시적 본문 heading이 23개이다.

SQ 각 언어의 본문 표는 17개이고, 목록 항목 113개와 번호 제목 5개가 대응한다. 음향 모델 18종, 마이크 모델 12종, 안전 표 9행/6심볼과 UI 4경로를 대조했다. 표지의 코드/그림 영역 차이 때문에 전체 표·그림 수를 강제로 맞추지 않았다. 표지 영역·연락처 머리글/데이터 행·안전 심볼·모델 사양표를 crop으로 확인했다.

## Gate와 남은 Warning

Hard gate 0. XML→MD의 전체 비공백 문자 순서, 417개 검토 단위, MD→HTML 텍스트/DOM 구조, 표 열 순서와 연락처 LTR, RTL 혼합 모델 표시, 원문 identity/path 추적을 확인했다. 문자 수 비교만으로 끝내지 않고 위험한 공백/괄호/모델 영역을 직접 대조했다.

남은 Warning은 추출 결함과 구분한다.

- PY 러시아어 `Датчик Датчик` 중복 및 어색한 제목은 실제 PDF 표현이다. 후속 번역·편집 검토 후보로 유지한다.
- SQ 아랍어 설치 방향 표현(`396 0 R`), `قك` 표기(`570 0 R`)는 원문 그대로이다.
- SQ `صندوق`와 `One Connect` 사이의 원문 붙임(`510 0 R`)도 실제 문자 위치를 확인해 유지했다.
- 바코드·QR·안전 심볼·UI 아이콘 및 문서코드 일부는 그림이다. PY/SQ 문서코드 앞부분은 윤곽선이고 tagged text에는 `-00`만 있다. 파일명에서 텍스트를 보충하거나 OCR 결과로 주장하지 않는다. PDF crop에서 확인한다.
- 추출 구조 검증은 현지어 번역/자연스러운 조판 품질 승인이나 사용자 승인과 다르다. 외부 API 의미 검토 없음.

## 테스트 및 회귀 근거

- 전체 XML 테스트: **2,456 passed, 1 skipped**, `outputs/py_sq_full_tests_20260919_final.xml`.
- skip은 Windows에서 symlink를 만들 수 없어 `test_preflight_rejects_non_regular_required_targets_before_staging[symlink]`를 건너뛴 것이다. 추출 언어 검사가 아니다.
- 전체 suite는 마지막 SQ 공백 writer 수정 전에 시작했다. 그 수정 후 관련 SQ/Markdown/XML writer **406 passed**, `outputs/py_sq_final_writer_tests_20260919.xml`. 전체 실행 시점 차이를 숨기거나 두 결과를 고유 테스트 개수로 합산하지 않는다.
- 이전 통합 집중 **64 passed**; PY **23 passed**, SQ spec **18 passed**; 모델 marker·소스 범위 검증 **8 passed**. 위 테스트와 중복되므로 합산하지 않는다.
- root public 호환: 시스템 Python의 `tests/test_content_poc.py` **43 passed**, 기존 public import 3개 callable 확인. POC venv는 root의 openpyxl 의존성이 없어 root 테스트는 시스템 Python으로 실행했다.
- 첫 전체 실행은 2,447 passed / 1 failed / 1 skipped였다. 실패는 일반 form detector에 대한 모델명 사전 금지 테스트가 source-bound 검증 모듈의 정확한 모델 문자열까지 금지한 문제였다. 일반 모듈 금지는 유지하고 SHA/MCID 검증용 SQ 모듈 3개만 분리했으며 후속 전체 suite가 통과했다.
- 기존 13프로필 AFRICA / CE / KR / LATIN / XU / ZC / ZG / ZW_TPE / TK_L02 / TK_ARA / MENA_L02 / XL_ENG / XT_L02를 재추출했다. raw XML / semantic XML / MD **39파일 바이트 동일**, `outputs/xml_review_py_sq_mi_20260919_regression_final/comparison.json`.
- 위 13개 재추출 후 마지막 SQ 전용 공백/writer 수정이 있었다. 해당 delta는 source-token/SHA/MCID에 한정되며 기존 TK source-space 경로를 추가 재추출해 **3파일 바이트 동일** 확인: `outputs/xml_review_py_sq_mi_20260919_writer_delta_regression`.
- 최종 POC `python -m compileall -q src tests scripts` 성공. root `python -m compileall -q src tests` 성공(root scripts/apps 없음). `git diff --check` 성공.

## 변경 파일

아래는 POC 기준이다. 별도로 root `TODO.md`, `docs/superpowers/plans/2026-09-19-py-sq-mi-xml-review.md`, 본 보고서를 변경했다.

- application: `extract_document.py`, `evaluate_quality.py`
- domain: `py_sheet.py`, `sq_mi_sheet.py`, `sq_mi_source_text.py`, `sq_mi_brackets.py`, `sq_mi_inline.py`, `sq_mi_spec_text.py`, `africa_inline_order.py`, `africa_rtl.py`, `numbered_heading_promotion.py`
- infrastructure: `py_source_evidence.py`, `sq_mi_source_evidence.py`, `pypdf_reader.py`, `xml_writer.py`, `markdown_writer.py`
- scripts: `review_py_sq_mi.py`, `finalize_py_sq_mi.py`, `verify_py_sq_regression.py`, `review_sheet_rollout.py`, `render_representative_review.cjs`, `render_tk_source_checks.cjs`
- tests: `test_py_sheet.py`, `test_sq_mi_sheet.py`, `test_sq_mi_spec_text.py`, `test_sq_mi_inline_validation.py`, `test_hebrew_preview_direction.py`, `test_layout_regression.py`

복구용 로컬 커밋 전체 SHA는 완료 응답과 최종 출력 `final_summary.json` / `review_run.json`의 `verified_commit`에 기록한다. 사용자 승인 상태는 false로 유지한다.
