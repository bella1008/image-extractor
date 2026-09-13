# 일반 체크리스트·구성품 통합 결과 사용 안내

## 이번에 연결한 범위

검증된 일반 검토 결과와 구성품 상세 결과를 읽어 **한 폴더, Excel 한 파일**로 제공한다. 기존 Excel을 복사하거나 Markdown을 다시 분석하는 방식이 아니다.

`완료된 두 관찰 결과 → 동일 PDF/XML 확인 → 통합 JSON → 표시 데이터 → Excel → 전체 셀 검증 → 완료 기록`

기존 DB, 원장, 원본 관찰 결과, XML 추출 규칙은 변경하지 않는다. 전 항목은 계속 **검토 필요**이며, 문구를 찾았다는 사실을 합격이나 모델 적용 승인으로 바꾸지 않는다.

## 담당자가 열 파일

작업장: `C:/Users/bella/image-extractor/.worktrees/xml-review-v2`

현재 결과: `outputs/combined_review_zc_20260913_r2/review_report.xlsx`

| 시트 | 무엇을 보는가 |
|---|---|
| Summary | 대상 PDF와 검토 상태, 상위 체크 59건 / 그중 구성품 상세 14건. 머리글 포함 12행 |
| Checklist Results | 기존 상위 체크 59행의 기준 문구·현재 원문·판정·설명·페이지·메모 |
| Item Results | CHK-002-ZC-ENG를 구성하는 14개 항목. 기존 8열 구성과 값 유지 |
| Source Evidence | 일반 40행 + 구성품 26행. 체크 ID/고정 항목 키/근거 종류로 필터링 |

59건과 14건을 합해 73건이라고 세지 않는다. 구성품 부모 행은 남기고 `Item Results 참조` 안내만 표시한다. 부모 행의 현재 원문이 비어 있는 것은 기존 부모 검사 방식이 미지원이기 때문이며, 구성품 원문이 없다는 뜻은 아니다. 하위 근거를 찾았다고 부모 검사가 완료된 것도 아니다.

Excel은 **사본으로 저장한 뒤 메모**한다. 검증된 원본을 직접 수정하면 해시/셀 검증에서 변경으로 판정한다. 결과 사본의 메모는 DB 승인 입력이 아니다.

일반 근거는 항목 키가 비어 있고, 구성품 근거는 부모 체크 ID와 항목 키가 함께 있다. 조건 안내가 여러 구성품과 연결될 수 있으므로 같은 원문이 반복되어도 임의로 제거하지 않는다. XML 노드 ID는 해당 추출본의 위치 정보다. 다른 실행에서도 영구히 같은 ID라고 가정하지 않는다.

## 같은 폴더의 내부 파일

- `review_report.json`: 두 원본 관찰, 원본 완료 기록, 검증된 XML/추출 기록, 내부 제외 488행 및 원본 규칙 547행을 보존.
- `review_report_view.json`: Excel에 넣는 정확한 행·열·값.
- `review_report_complete.json`: 위 JSON 두 개와 Excel의 해시 및 완료 상태. 모든 검증이 끝난 뒤 생성.
- `authoring.log`, PNG, inspect 파일: 개발용 작성/화면 검증 자료. 담당자에게는 Excel만 전달해도 열람할 수 있다. 검증된 시스템 조회를 위해서는 결과 폴더 전체를 보관한다.

새 HTML 파일은 만들지 않는다. 과거 v1 입력 결과의 HTML은 원래 완료 기록을 검증하기 위해 내부 JSON에만 보존한다. 새로운 웹/HTML 기능을 추가한 것이 아니다.

일반 상세 근거 JSON 셀은 옆 열에 이미 있는 정보를 반복하지 않고, 전체 노드별 근거와 나머지 문맥을 보존한다. 경로 목록은 `; `로 구분한다. 긴 문구나 근거는 자르지 않는다. 전체 원본은 통합 JSON에 그대로 있다.

## 다시 생성하는 개발용 명령

PowerShell에서 이 작업장으로 이동한다. 현재 PC의 검증된 작성 환경을 지정한 예다. Node/Artifact Tool을 다른 담당자 PC에 자동 설치하거나 복제하는 명령은 아니다.

```powershell
Set-Location C:/Users/bella/image-extractor/.worktrees/xml-review-v2
$env:ITEM_REVIEW_NODE = 'C:/Users/bella/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe'
$env:ITEM_REVIEW_NODE_MODULES = 'C:/Users/bella/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules'
.venv/Scripts/python.exe -m scripts.export_combined_review outputs/review_service_zc_20260911_r2 outputs/item_review_zc_20260913_unified --output outputs/combined_review_zc_new
```

`--output`에는 **아직 없는 폴더명**을 쓴다. 같은 폴더를 다시 쓰면 덮어쓰지 않고 중단한다. `--node`, `--node-modules`로 환경변수 대신 경로를 전달할 수도 있다. 이 통합 명령은 PDF 재추출을 하지 않으므로 POC의 `PYTHONPATH` 설정이 필요하지 않다.

생성할 때에는 입력 두 폴더와 그 결과가 참조하는 XML/추출 완료 자료가 있어야 한다. 파일명뿐 아니라 PDF 해시·XML 해시·추출 완료 기록·문서 프로필이 같아야 한다. 다른 추출본을 임의로 합치지 않는다.

이미 완료된 통합 폴더를 검증하는 내부 Python 함수는 다음과 같다.

```python
from src.combined_review_service import read_completed_combined_review
result = read_completed_combined_review('outputs/combined_review_zc_20260913_r2')
print(result['report']['summary'])
```

재조회는 통합 폴더 자체의 보관 자료를 사용하므로 과거 PDF/DB/입력 폴더가 없어도 가능하다. 실행 중이거나 실패한 결과, 파일이 바뀐 결과, 완료 기록이 없는 결과는 거절한다. 해시는 변경/혼용 검사용이며 전자서명이나 업무 승인 증명은 아니다.

## 실패한 폴더와 복구

처음 시도한 `outputs/combined_review_zc_20260913/`는 상세 근거 표시가 Excel 행 높이 한도를 넘어서 실패했다. 실패 폴더는 진단용으로 남겼고, 원문을 줄이지 않은 표시 조정 뒤 새 `_r2` 폴더에 생성했다. 담당자는 `_r2/review_report.xlsx`를 사용한다.

이번 변경 직전 코드 기준은 `cd803f12d69bb1874765072e6d6f381fe9bcd95e`다. 작업 중인 파일을 지우는 reset 대신, 필요하면 이 기준으로 **별도 복구 worktree**를 만들어 비교한다. 결과 파일은 Git에 포함되지 않으므로 결과 폴더는 별도 보관한다.

## 아직 하지 않은 일

- 통합 결과를 읽는 Streamlit 화면 연결. 기존 항목별 화면은 계속 기존 item 결과용이다.
- PDF 한 번 실행으로 일반 관찰·항목 관찰·통합 결과를 함께 생성하는 공통 실행 명령.
- 담당자 PC 전체의 Excel 작성기/설치·실행 환경 배포.
- 다른 바이어·언어, 나머지 항목 분리, 모델 조건 승인, 자동 업무 판정.

다음 구현은 통합 결과의 단일 폴더 조회/다운로드와 공통 실행 연결이다. 현재 산출물을 전체 운영 전환이나 DB 승인 완료로 보지 않는다.

## 검증 기록

2026-09-13 검증:

- 루트 전체 테스트 **558 passed**. 실제 작성 도구를 사용하는 통합 테스트 4개 포함. 이번 신규 테스트 55개.
- `compileall -q src tests scripts`, `pip check`, `git diff --check` 통과. 이 작업장에는 `apps/` 폴더가 없다. XML POC 전체 테스트는 이번에 다시 실행하지 않았다.
- 독립 명세 검토와 코드 품질 검토 통과. 이는 업무 내용 승인이나 운영 배포 승인과 다르다.
- 실물 ZC 결과의 4시트 11/59/14/66 데이터 행과 저장된 **모든 셀 값**을 다시 읽어 대조. Item Results는 기존 8열·14행과 동일.
- 4시트 10개 화면 영역 렌더 확인. 가장 긴 근거 행도 추가 확인했고 원문 축약 없이 표시됨.
- 원본 두 관찰 및 원본 추출 보관 파일 바이트가 그대로임을 대조. DB/metadata/추출 코드 변경 없음.
- 잘못된 출처 혼용, 부모/항목 키 오류, 노드 소속·필수 필드 누락, XML 개별/합친 문구 차이, 페이지·경로 근거 차이, 임의 승인, 저장 도중 변경을 거절하는 회귀 검사.

현재 Excel SHA-256: `73f8177fb316097b459ac72626e5a8580fd9e76fa28dd54e018eca51aba41d6c`.
표시 JSON SHA-256: `2eca9c97a42fe33575df817b7324df4d3c737f8ee11620d5c7574457f2a8b3fd`.
