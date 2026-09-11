# 구성품 결과 Excel과 로컬 사용 화면

## 이번에 연결한 것

이미 검증된 항목별 결과를 **Excel 파일과 Streamlit 화면에서 같은 내용으로 확인**할 수 있다. 새 PDF를 검사하거나 업무 판정을 바꾸는 기능이 아니라, 완료된 결과를 표시하는 연결이다.

```text
PDF → XML → ReviewDocument → 항목별 관찰 결과 + 완료 기록
                                  ↓ 검증해서 읽기
                           결과 Excel + Excel 완료 기록
                                  ↓
                    로컬 화면에서 확인 / JSON·HTML·Excel 내려받기
```

CHK-002-ZC-ENG 구성품 14개만 지원한다. 부모 항목을 더해서 15개로 세지 않으며, 기존 547행 결과와 합치지 않는다. 14개 모두 검토 필요이고 모델 적용은 미확정이다.

## Excel 읽는 방법

실물 결과: `outputs/item_excel_zc_20260911_r2/item_review.xlsx`.

| 시트 | 내용 |
|---|---|
| Summary | 항목 수, 발견 상태별 수, 이번 PDF와 원장 작성 당시 PDF의 출처를 구분해 표시 |
| Item Results | 고정 항목 키, 기준 문구, 검토 판정, 설명, 항목/조건 근거 ID, 검토 메모 |
| Source Evidence | 근거 ID별 현재 원문, 현재 XML 노드 ID·태그·페이지·경로, 전체 상세 근거 JSON |

실제 ZC 결과는 항목 14행, 근거 26행이다. 항목 근거 14개와 별표 조건 안내 연결 후보 12개를 구분한다. 조건 안내를 찾았다는 이유로 모델별 필수 여부를 승인하지 않는다.

`Item Results`의 노란 `검토 메모`는 내려받은 사본에 의견을 적는 칸이다. 오른쪽의 `원장 모델 조건 제안 / 원장 제안 근거 / 원장 검토 메모`는 원장에서 가져온 제안 이력이다. 서로 섞지 않으며, 어느 쪽도 자동 승인 입력으로 실행하지 않는다.

**검증된 보관 파일 자체는 수정하지 않는다.** 메모를 쓰려면 다른 이름으로 저장한 사본을 사용한다. 원본 Excel을 수정하면 완료 기록의 해시와 달라져 프로그램에서 다시 내려받을 수 없다. 이번에는 메모 사본을 DB로 다시 가져오는 기능을 구현하지 않았다.

## 사용 화면 실행

이 작업장의 전용 환경에는 필요한 UI 패키지를 설치하고 검증했다. PowerShell에서 실행한다.

```powershell
Set-Location 'C:\Users\bella\image-extractor\.worktrees\xml-review-v2'
.venv/Scripts/python.exe -m scripts.start_item_review_ui
```

브라우저에서 `http://127.0.0.1:8501`을 연다. 창에는 두 입력칸이 있다.

1. 완료된 관찰 결과 폴더: `outputs/item_review_zc_20260911_fresh`
2. 완료된 Excel 내보내기 폴더: `outputs/item_excel_zc_20260911_r2`

`불러오기`를 누르면 현재 출처, 14개 항목, 상세 근거와 다운로드 버튼이 나온다. Excel 폴더를 비우면 JSON/HTML만 내려받는다. 지정한 Excel이 잘못됐으면 오류를 표시하고 현재 결과·다운로드를 모두 숨긴다. Excel 없이 보려면 두 번째 칸을 비우고 다시 불러온다.

폴더 입력값을 바꾸면 다시 불러와야 한다. 화면 재실행과 다운로드 클릭 시 파일을 다시 검증하므로, 파일이 변경됐거나 실패 기록이 생긴 경우 이전 정상 결과를 그대로 제공하지 않는다.

종료는 실행한 PowerShell에서 `Ctrl+C`. 기본 포트가 사용 중이면 다음처럼 다른 로컬 포트를 지정할 수 있다.

```powershell
.venv/Scripts/python.exe -m scripts.start_item_review_ui --port 8502
```

`127.0.0.1`에만 연결하므로 사내 서버 포트를 여는 작업은 필요 없다. 다만 개인 PC의 보안 정책이 로컬 실행을 막는 경우에는 별도 확인이 필요하다. 다른 PC에서 접속하는 공동 서버로 공개하지 않으며, 실행기는 사용 통계 전송을 끈다.

## Excel 새로 생성

관찰 결과 폴더는 기존 [항목 검토 실행 명령](2026-09-11-item-observation-service_kr.md)으로 먼저 만든다. Excel 생성은 별도 명령이며, 기존 결과 폴더를 수정하지 않는다. `--output`에는 아직 없는 새 폴더 이름을 쓴다.

이 PC의 현재 작성 환경을 사용하는 예:

```powershell
Set-Location 'C:\Users\bella\image-extractor\.worktrees\xml-review-v2'
$env:ITEM_REVIEW_NODE = 'C:/Users/bella/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe'
$env:ITEM_REVIEW_NODE_MODULES = 'C:/Users/bella/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules'
.venv/Scripts/python.exe -m scripts.export_item_review_excel outputs/item_review_zc_20260911_fresh --output outputs/my_item_excel_001
```

경로는 이 PC의 설치 위치다. 프로그램 코드에 Bella의 경로를 고정하지 않았으며, 다른 환경에서는 해당 경로를 명시해야 한다. 작성 도구를 자동 설치하거나 내려받지 않는다.

정상 출력에는 `item_review.xlsx`, `item_excel_view.json`, `item_excel_complete.json`이 있다. 완료 기록에는 어떤 관찰 결과로 만들었는지와 파일 해시가 담긴다. 저장 중 입력·출력이 바뀌거나 셀 값/필터/고정창이 계약과 다르면 완료 처리하지 않는다. 실패 폴더는 진단용으로 남으며 다른 새 폴더로 재시도한다.

## 의존성과 배포 경계

- 화면에서 완료된 결과와 Excel을 **읽고 내려받는 일**: Python + `requirements-review-ui.txt`. Node가 없어도 된다.
- 새 Excel을 **생성하는 일**: 현재는 별도 Node + Artifact Tool 작성 환경이 필요하다. 이 환경은 Codex에 번들된 작성 도구이며 일반 Python 설치만으로 제공되지 않는다.
- 새 담당자 환경 구성 시 `python -m pip install -r requirements-review-ui.txt`가 필요하다. 이는 기존 Python 외에 필요한 라이브러리 설치이지, 배포 패키지 완성을 뜻하지 않는다.
- 따라서 **담당자 PC용 Python-only 전체 배포는 아직 완료가 아니다.** 이 도구를 재배포 가능한지와 작성 방식 단순화를 배포 단계에서 검토한다. 검토/표시 데이터 계약은 출력 도구와 분리되어 있으므로 그때 매칭 로직을 다시 만들 필요는 없다.
- 이 화면에는 PDF 업로드/실행 버튼, 모델 적용 승인, DB 편집, 메모 되가져오기, 다른 바이어 지원을 아직 넣지 않았다. 이전 Streamlit이나 기존 exporter를 import하지 않는다.

## 검증 기록

- 최종 루트 테스트 **492개 통과**(104.92초). 이번 Excel 32개·화면 25개 테스트와 실제 작성 도구 통합 테스트 2개를 포함한다. `compileall`과 `pip check`도 통과했다. 독립 명세·품질 검토에서 발견한 문제는 회귀 테스트를 추가해 수정하고 재검토를 통과했다.
- 실제 완료된 ZC 관찰 결과와 새 Excel을 함께 읽어 14행과 다운로드 3개가 나오는 것을 확인했다. 화면 동작은 [Streamlit 공식 AppTest](https://docs.streamlit.io/develop/api-reference/app-testing/st.testing.v1.apptest)로 검사했다. 패키지는 [Streamlit 1.63.0](https://pypi.org/project/streamlit/1.63.0/)으로 고정했다.
- Excel 세 시트 전체 셀 값을 표시 계약과 대조하고, 숫자형 집계·필터·고정창·수식/외부 링크 없음·현재 근거 26행을 확인했다. 세 시트의 출력 이미지를 열어 원문과 설명·출처·상세 JSON의 잘림 여부도 검사했다.
- 첫 생성은 기본 표 설정에서 필터가 저장되지 않아 검증에 실패했다. 표 필터 표시를 명시해 `r2`에서 해결했다. 처음 폴더는 실패 기록과 함께 보존했다.
- 실제 작성 도구 통합 테스트는 수식처럼 보이는 문자열과 원래 작은따옴표로 시작하는 메모, 근거가 없는 경우까지 검사했다. 작은따옴표 중복 결함을 발견해 수정했고 문자 그대로 왕복되는 것을 확인했다.
- 독립 검토에서 완료 기록이 `[]` 또는 `null`인 경우의 오류 처리 누락을 찾아 수정했다. 잘못된 완료 기록/결과 구조도 검증 오류로 처리하고 이전 화면·다운로드를 지우는 회귀 테스트를 추가했다.
- 원본 DB, 별도 동결 547행 초안, 항목 원장은 바뀌지 않았다. XML 추출기와 Markdown writer도 수정하지 않았다.
- 브라우저 도구의 기존 로컬 파일 정책 제한을 우회하지 않았다. AppTest는 화면 동작 검사이며 실제 브라우저의 육안 검수나 최종 사용자 양식 승인을 대신하지 않는다. 서버는 상시 실행해 두지 않았다.

## 코드 복구 기준점

이번 연결 작업 직전 커밋은 `c4b455ebbfc1a3c2f249de94aca36c04b8cd857c`다. 이번 구현을 저장한 커밋 번호는 이 문서와 함께 저장되므로 작업장 터미널에서 다음 읽기 전용 명령으로 확인할 수 있다.

```powershell
git log -1 --format=%H -- docs/migration/2026-09-11-item-excel-ui_kr.md
```

Git 커밋은 코드·테스트·문서를 보존한다. `outputs/` 결과물과 `.venv` 설치 환경은 포함하지 않으므로 별도 보관하거나 안내된 명령으로 재생성한다. 복구 시 현재 미커밋 작업을 먼저 보존하고 별도 작업장에서 해당 커밋을 확인한다. 메인/다른 작업장을 강제로 되돌리거나 덮어쓰지 않는다.
