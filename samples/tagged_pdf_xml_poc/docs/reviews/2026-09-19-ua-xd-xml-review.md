# UA / XD XML extraction review — 2026-09-19

UA_ENG와 XD_INS의 원문 기반 추출 구조 검증을 완료했다. 사용자 승인은 대기이다. 기존 MENA / XL / XT / TK / ZW / PY / SQ_MI 7개 바이어의 승인 상태는 변경하지 않았고, UA / XD를 포함한 승인 대기는 총 9개이다.

## 범위 및 원본

- 작업장: `C:/Users/bella/image-extractor/.worktrees/xml-markdown-review`
- 브랜치: `feature/xml-markdown-review`
- 시작 HEAD: `d05b4a852c69bd70042d2a65c8c867f6d0d2f573`, 시작 시 미커밋 변경 없음.
- UA: `samples/SUG_RAW/TV_UA/BN68-26754A-00_SUG_Y26 TV ALL_UA_ENG_260520.0.pdf`
  - `UA_ENG`, A3, ENG, 2페이지, 북마크 없음.
  - SHA256 `38b9bdb357c6b9fd0ccfa0fc3fd3e3a0a0c9ce787fe56fb3fc16c4db1c1ee80a`
- XD: `samples/SUG_RAW/TV_XD/BN68-25031D-00_SUG_Y26 TV ALL_XD_INS_260113.0.pdf`
  - `XD_INS`, A3, INS(인도네시아어), 2페이지, 북마크 없음.
  - SHA256 `f332cca0f65ea88a6b00489d076173a6a5eaf859bc4a1773c05a3153c97dad56`
- 파일명 token, canonical profile, 실제 PDF 페이지를 대조했다. 폴더명으로 프로필을 추정하지 않았다.
- 현재 XML POC 경로만 수정했다. 다른 worktree, root 추출 코드, GridCell, Excel/Streamlit, checklist DB 및 profile metadata는 수정하지 않았다. 원격 push/merge/rebase 없음.

## 수정 전과 수정 범위

기존 추출기 실행 결과는 `outputs/xml_review_ua_xd_20260919_before`에 보존했다. 두 파일 모두 자동 report는 pass였지만 실제 PDF 대조에서 다음 결함을 확인했다. 먼저 재현 테스트 실패를 확인한 뒤 source-bound 전용 모듈로 수정했다.

UA:

- 원문 표지가 본문 뒤에 나오던 순서를 수정했다.
- 전원 설명의 연속문장을 해당 글머리표의 하위 구조로 이동했다. 이전 MD의 들여쓰기만으로 XML 소속까지 맞다고 판단하지 않았다.
- 서비스 비용 안내의 (a)/(b)를 안내 문단과 묶인 하위 목록으로 복원했다.
- Wi-Fi `7 .125`의 추출 공백을 단일 원문 PDF 연산 근거로 `7.125`로 복원했다.

XD:

- 표지를 본문 앞으로 배치하고 보증서·보증 조건·서비스 주소 부록은 독립 구조로 유지했다.
- 표지 모델 80개가 개별 문단으로 흩어져 있던 것을 원문 좌표로 확인한 16행×5열 표로 복원했다. 모델 문자열을 생성하지 않고 원래 문자 조각을 이동했다. 독립 PyMuPDF 좌표 검사에서도 80개 모두 같은 행·열 순서이다.
- 전원 연속문장 `1506 0 R`을 원문 글머리표 `1986 0 R`의 본문에 연결했다.
- 서비스 주소표의 Jakarta 병합 셀 및 보증 기간 표의 병합 셀을 MD/HTML에서 보존했다.
- 원문 연산으로 확인한 `https:/ /`와 `7 ,125`의 불필요한 공백을 제거했다. 원문에서 섞어 쓴 5,925 / 7,125 / 6.425의 쉼표·점은 바꾸지 않았다.
- 주소와 회사명의 `Jl.`, `PT.`, `no.` 등에서 생기던 잘못된 문장 줄바꿈은 검증된 XD 원본 경로에서만 억제했다. 다른 INS 문서나 일반 문단에는 적용되지 않는다.

규칙은 source_token + A3 + language + 정확한 원본 SHA로 제한했다. 알 수 없는 개정본, 누락/변조된 연산 근거, 다른 프로필은 거절하거나 원래 경로를 유지한다. 원시 XML, fragment ID·MCID·객체 참조·원래 source path를 보존한다. 번역 제목을 runtime에 추가하지 않았다.

## 최종 출력 및 확인 수치

최종 폴더:
`C:/Users/bella/image-extractor/.worktrees/xml-markdown-review/samples/tagged_pdf_xml_poc/outputs/xml_review_ua_xd_20260919_ready`

- 시작 화면: `review.html` — 기존 7개 바이어 검토 링크 포함.
- PDF / Markdown 비교: `source_checks.html`, 비교 이미지 86개.
- `UA_ENG` / `XD_INS` 하위 폴더 각각에 `raw_structure.xml`, `semantic_document.xml`, `semantic_document.md`, `semantic_document.preview.html`, `extraction_report.json`, `review_document.json`, `review_run.json`, `source_audit.json`, `html_validation.json`.
- 독립 원문 근거: `outputs/ua_source_review_20260919/ua_source_audit.json` 및 `outputs/xd_source_review_20260919/audit.json`.
- 최종 XD 시각 확인: `XD_INS/final_source_review.json`. 표지 모델 확대 crop, 보증표, Jakarta 병합 행을 최종 HTML과 대조했다.
- 두 파일의 raw XML은 수정 전 기준본과 바이트 동일하다. 최종 semantic XML/MD는 독립 원문 검토본과 바이트 동일하며 audit에 해시를 연결했다.

| 바이어 | 언어 | 표시 제목 | 검토 단위 | 문단 | 목록 / 항목 | 표 | 그림 노드 |
|---|---|---:|---:|---:|---:|---:|---:|
| UA | ENG | 24 | 109 | 249 | 38 / 109 | 19 | 51 |
| XD | INS | 30 | 138 | 665 | 37 / 118 | 43 | 42 |

표시 제목은 원문 표지·보증서 등의 제목을 포함한다. 명시적 번호 heading은 UA 5개, XD 4개이다. 그림은 XML figure 노드 수로 고유 아이콘 개수가 아니다. 검토 단위와 내부 문단·목록 항목 수는 집계 단위가 다르다.

- UA: 본문 제목 23 + 표지 1. 안전 표 9행·6심볼, UI 경로 6개·아이콘 12개, 연락처 머리글과 11개 국가 행, 모델/소비전력 75쌍 확인. 실제 확인한 원문 crop 25개.
- XD: 표지 모델 80개, 안전 표 9행·6심볼, UI 경로 5개, 연락처 표 2행(머리글+데이터), 전화번호 3개. 서비스 주소표 45행 = 머리글 1 + 주소 44, 도시 이름 43개(Jakarta 2개 주소). 보증 기간 표 15행, 보증서 양식 표 23개, 사양표 3행(해상도 조건 2, 음향 조건 8, 환경 조건 4). 전체 양면을 나눈 원문 crop 16개 모두 확인.
- XD 연락처 근거는 `803 0 R`의 `Pusat Servis Samsung / Situ Web`, `512 0 R`의 `Kota / Alamat` 머리글을 데이터 행과 분리했다. 모델표 첫 행이나 보증표를 연락처 머리글로 잘못 분류하지 않는다.

## 기준 비교와 원문 차이

UA ENG는 ZC ENG와 먼저 비교한 뒤 가까운 XL/XU A3 구조와 대조했다. 모델 종류·수량, 지역 연락처 및 원문 문구 차이를 추출 결함과 구분했다.

XD에는 영어 구간이 없다. XL/XU A3의 구조를 참고하되 INS 실제 PDF와 직접 비교했다. XD는 XL처럼 번호 장이 4개이고 XU의 별도 One Connect 장이 없다. 이를 누락으로 간주하거나 영어 제목을 번역해 추가하지 않았다. 보증 양식·조건·주소표, 긴급 방송 우편번호 UI 경로는 XD의 실제 추가 내용이므로 UA와 제목/표 수를 강제로 맞추지 않았다.

## Gate 및 Warning

Hard gate 0. XML→MD 전체 비공백 문자 순서, MD→HTML 텍스트/구조, 247개 검토 단위, 원문 identity/문자 소속/source path, 표 열 순서, 연락처 LTR을 확인했다. 원문 전체·고위험 crop을 직접 대조하고 잘못된 공백·문장 소속·병합 셀은 별도 검사했다. 파일 생성이나 자동 pass만으로 완료 처리하지 않았다.

Warning:

- UA의 `Always educate about the dangers of climbing`, `out of the reach.`, `All voice`, `Guide came with this product`는 실제 원문 표현이다. 생략된 주어 등을 다른 바이어에서 보충하지 않았다.
- XD의 `Situ Web`, Samarinda 주소 `15,,`, TanjungPinang의 `Deangan`, Tegal의 `N0.` 및 INS 본문 안의 영어 LS03HW 문장을 보존했다. 후속 번역·편집 검토 후보이다.
- 문서코드 앞부분 BN68-26754A / BN68-25031D는 윤곽선/그래픽이고 tagged text에는 `-00`만 있다. 파일명에서 보충하지 않았다. 로고·바코드·QR·전화 그림·안전 심볼·UI 아이콘은 crop 근거이며 OCR 텍스트로 주장하지 않는다.
- 추출 구조 검증은 현지어 표현/법률적 정확성 또는 사용자 승인과 다르다. 외부 API 의미 검토나 DB 후보 생성/승인 없음.

## 검증

- UA 집중: 27 passed. XD 집중: 16 passed. 새 dispatch, 실제 PDF 결함, raw/원문 경로 보존, 잘못된 프로필/SHA/연산 근거 거절, XML/MD 결과를 검사했다.
- 전체 XML suite: **2,499 passed, 1 skipped** (814.08초), `outputs/ua_xd_full_tests_20260919.xml`. 최종 runtime에서 실행했으며 writer/프로필/기존 회귀 테스트를 포함한다. 집중 테스트와 중복되므로 합산하지 않는다.
- skip은 Windows symlink 생성이 불가능해 `test_preflight_rejects_non_regular_required_targets_before_staging[symlink]`를 건너뛴 것이다. PDF/언어 검사가 아니다.
- Root public 호환: `python -m pytest tests/test_content_poc.py -q` **43 passed**. 기존 public import 경로를 유지한다.
- 기존 15프로필 AFRICA / CE / KR / LATIN / XU / ZC / ZG / ZW_TPE / TK_L02 / TK_ARA / MENA_L02 / XL_ENG / XT_L02 / PY_ENRU / SQ_MI_HEAR 재추출: raw XML / semantic XML / MD **45파일 바이트 동일**. `outputs/xml_review_ua_xd_20260919_regression/comparison.json`과 runtime 해시 참조.
- POC `python -m compileall -q src tests scripts`, root `python -m compileall -q src tests` 성공(root scripts/apps 없음). `git diff --check` 통과.
- 원문 수정 동작은 실패 테스트를 먼저 확인했다. 이후 잘못된 근거를 거절하는 검사에서 pypdf 정수 subclass를 너무 엄격히 거절한 중간 실패를 수정했다. 초기 통합 집중 결과 8 failed / 30 passed / 3 errors는 최종 결과로 사용하지 않는다. 최종 UA 27개 재실행은 통과했고 전체 suite에도 포함된다.
- 독립 코드 리뷰: UA/XD 근거 변조 거절, XD 80개 모델의 독립 좌표 대조, 다른 프로필/문단에서 문장 줄바꿈 유지 확인. 남은 차단 결함 없음.

## 변경 파일

POC 기준:

- `src/tagged_pdf_extractor/domain/ua_sheet.py`, `xd_sheet.py`: 원문에 한정한 구조/텍스트 규칙.
- `src/tagged_pdf_extractor/infrastructure/ua_source_evidence.py`, `xd_source_evidence.py`: 원래 PDF 연산과 좌표 근거.
- `application/extract_document.py`, `infrastructure/pypdf_reader.py`: 명시적 프로필 연결.
- `domain/readability_formatting.py`: XD의 검증된 주소/회사명 경로에서만 문장 줄바꿈 보존.
- `tests/test_ua_sheet.py`, `tests/test_xd_sheet.py`: 재현·dispatch·범위/무결성 테스트.
- `scripts/review_ua_xd.py`, `finalize_ua_xd.py`, `verify_ua_xd_regression.py`, `review_sheet_rollout.py`: 신규 bundle, 검토 화면, 회귀 및 정확한 표지 crop/연락처 근거.
- 본 보고서, root `TODO.md`, `docs/superpowers/plans/2026-09-19-ua-xd-xml-review.md`.

검증된 로컬 커밋 전체 SHA는 완료 응답과 최종 폴더 `final_summary.json` / `review_run.json`의 `verified_commit`에 기록한다. 사용자 승인 상태는 false로 유지한다.
