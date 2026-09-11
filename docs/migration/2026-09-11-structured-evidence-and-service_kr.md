# 구조 근거 연결과 로컬 실행 안내

## 이번에 연결한 범위

PDF → 고정된 XML 추출기 → 품질/언어/파일 검증 → ReviewDocument → 동결 체크리스트 → 관찰 JSON → 로컬 HTML까지 하나의 `ReviewService`로 실행한다. 서버나 외부 LLM API는 사용하지 않는다. 기존 Markdown writer와 원본 DB는 변경하지 않았다.

`ReviewService`는 실행 순서와 실패 처리를 담당하는 Python 코드다. 화면을 그리거나 업무 승인을 하는 에이전트가 아니다. 기존 JSON 전용 CLI도 같은 서비스 함수를 호출하도록 연결했다.

## 실제 ZC 영어 결과

547행 전부 보존. 이번 대상 59, 다른 적용 범위 486, 기존 비승인 2.

| 적용 59개 구분 | 개수 | 의미 |
|---|---:|---|
| 단일 검토 단위에서 문구 근거 | 28 | 이전 엄격 관찰 결과 유지 |
| 새 구조의 전체 문구 후보 | 9 | 자동 합격/역할 승인 아님 |
| 분산 문구 근거 | 1 | 목록·표에 나뉜 문구를 각각 연결. 전체 일치 아님 |
| 연결 미완료 | 21 | 표/표지/법규/구성품 등의 별도 범위/검사 필요 |

기존 미일치 9개 중 8개가 구조 후보로 연결됐다. 별도로 미지원이던 SAFETY-003의 경고 문구가 표 내부에서 발견되어 구조 후보가 총 9개다. 기존 미일치의 나머지 SAFETY-008은 기준의 첫 문장이 목록 본문, 나머지 두 문장이 경고 표에 있어 분산 근거로 표시했다.

새 구조 후보:

- ISEC-002: 연속된 XML 문단 43/44. 각 원문과 출처를 남기고 보기용 줄바꿈만 추가한다.
- ISEC-003/004/005: 아이콘 옆의 끊기지 않은 텍스트 구간. 아이콘을 건너뛰어 문구를 연결하지 않는다.
- SAFETY-010/023/025: 같은 목록 항목의 `– ` label과 본문. 기호를 삭제하지 않는다.
- SAFETY-020: 기존 bullet 규칙에 해당하는 문구가 XML paragraph에 있음. 역할 동등성은 별도 확인 대상이다.
- SAFETY-003: 표 안의 경고 문구. 표/아이콘 관계를 확인해야 한다는 주의도 남긴다.

모든 적용 행은 `needs_review`, 이관은 `pending`이다. 원본의 역사적 `approved`와 새 문서에서의 검증은 별개다. `candidate_matches`는 검색 범위를 넓혀 합격시키는 fallback이 아니다. 기존 `matches`와 분리된 이관 감사 후보다.

## 경계와 근거 보존

- 연속 문단은 같은 부모의 바로 이웃 문단만, 최대 4개까지 후보로 묶는다. 이를 넘어선 묶음까지 검사했다고 표시하지 않는다.
- 목록 항목/표 행/표 셀을 가로질러 텍스트를 평탄화하지 않는다.
- 그림은 텍스트 구간을 끊는다. 그림의 대체 텍스트를 실제 문구로 사용하지 않는다.
- 중간의 다른 제목, 새 section/article/document, 미배정/다른 언어 노드는 후보 범위를 종료한다. 빈 노드도 검사한다.
- 미지 구조, 근거 부족, 복합 언어는 조용히 일반 본문으로 취급하지 않는다.
- 원문 문자열, XML 위치, 페이지/MCID 근거를 보존한다. 후보 연결의 방법과 주의사항도 별도 기록한다.
- DB 줄별 분산 진단은 위치 찾기일 뿐, 순서/횟수/문맥/표 관계가 맞다는 판정이 아니다.

## 현재 결과 파일

- 전체 신규 추출 실행: `outputs/review_service_zc_20260911_r2/`
  - `extraction/`: 기존 네 추출 산출물 + ReviewDocument/추출 완료 기록.
  - `observation.json`: 규칙 547행, 선택/제외 단위, 전체 후보/분산 근거, 원본 입력 해시.
  - `review.html`: 기준과 근거를 나란히 보는 로컬 보고서.
  - `review_complete.json`: JSON/HTML 검증 완료 기록. 업무 Pass는 아니다.
- Excel 양식 초안: `outputs/review_excel_prototype_20260911/review_report_prototype.xlsx`.
  - 59개 적용 규칙, 40개 근거 행, 488개 제외 기록.
  - `review_report_view.py`가 만든 표를 개발용 작성 도구로 그렸다. Node/Artifact Tool은 동료 PC의 실행 필수 조건으로 넣지 않는다.
  - Python 배포용 Excel writer와 Streamlit 연결은 아직이며, 양식 확정 후 연결한다.

## 실행 환경과 사용 방법

Python 3.12 / Windows에서 확인했다. 공용 Python/다른 터미널 환경을 변경하지 말고 이 worktree의 전용 환경을 사용한다.

```powershell
Set-Location C:\Users\bella\image-extractor\.worktrees\xml-review-v2
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-review-v2.txt
$env:PYTHONPATH = (Resolve-Path samples/tagged_pdf_xml_poc/src).Path
```

환경이 이미 있다면 다시 만들 필요 없다. 현재 XML 추출기가 요구하는 `pypdf==6.16.2`를 실행 전에 검사한다. 이번 검증 중 공용 런타임의 6.10.0은 새 PDF 추출에서 실패했다. 기존 XML bundle 읽기와 새 PDF 추출의 환경 조건을 혼동하지 않는다.

새 PDF에서 처음부터 실행:

```powershell
.venv\Scripts\python.exe -m scripts.run_review_v2 "samples/SUG_RAW/TV_ZC/BN68-25100B-00_SUG_Y26 TV ALL_ZC_L02_260122.0.pdf" --output outputs/my_new_review
```

이미 검증된 추출 폴더를 재사용:

```powershell
.venv\Scripts\python.exe -m scripts.run_review_v2 "samples/SUG_RAW/TV_ZC/BN68-25100B-00_SUG_Y26 TV ALL_ZC_L02_260122.0.pdf" --bundle outputs/xml_review_v2_zc_20260910 --output outputs/my_new_review_from_bundle
```

출력 폴더는 매번 새 이름을 쓴다. 기존 결과를 덮어쓰지 않는다. `review_complete.json`이 없거나 `review_failed.json`이 있으면 완료 결과가 아니다. 프로그램은 `read_completed_observation()`으로 완료 상태와 두 파일의 해시를 검증한 후 다른 양식으로 변환한다.

실패 자료는 원인 확인을 위해 남긴다. 최초 환경 불일치 실행 `outputs/review_service_zc_20260911/`에는 `review_failed.json`만 있으며 완료 기록은 없다. 성공 결과로 사용하면 안 된다.

## 저장 안정성과 검증

보고서 생성 전후 입력을 검증한다. 저장 후 JSON/HTML이 예상 바이트와 같은지 확인하고, 완료 기록은 임시 이름에 모두 쓴 뒤 같은 파일시스템에서 원자적으로 공개한다. 저장 중 중단되거나 파일이 바뀌면 완료로 취급하지 않는다. 해시는 변경 탐지용이며 암호학적 업무 승인 서명이 아니다.

독립 코드 리뷰에서 발견한 새 구역 경계 및 저장 중 변경/완료 기록 중단 문제를 실패 테스트로 재현하고 수정했다. 실제 신규 추출 XML·MD는 이전 검증본과 바이트 동일했고 547개 원본 규칙·적용 여부·엄격 관찰 결과도 같았다. 메인의 DB Excel/JSON 해시도 유지됐다.

HTML은 실제 Edge 렌더링으로 59개 카드와 가로 넘침 없음을 확인했다. Excel은 모든 상세 셀을 표시용 원본과 대조했고, 네 시트 렌더링·필터·A2 고정창·검토 필요 조건부 서식·집계 수식 캐시를 확인했다. Excel 데스크톱에서의 사용자 양식 검수는 아직이다.

작업 전 복구 커밋: `b65eef09b5ec94f9856e96861f359b388bdb73d3`. 이번 결과도 별도 `codex/xml-review-v2`에만 저장한다. 메인으로 병합하거나 다른 담당자에게 배포한 상태는 아니다.
