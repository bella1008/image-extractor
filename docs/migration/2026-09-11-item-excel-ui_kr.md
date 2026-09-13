# 구성품 결과 Excel과 로컬 사용 화면

## 현재 사용 방식 — 2026-09-13

검토 결과 폴더 하나에서 JSON과 Excel을 함께 관리한다. 사용자는 `item_review.xlsx`를 열거나 Streamlit 화면에서 결과를 확인한다. 새 실행에서는 HTML을 만들거나 내려받지 않는다.

```text
PDF → XML → ReviewDocument → 항목별 결과 JSON → 같은 폴더의 결과 Excel
```

현재 지원은 ZC ENG의 CHK-002 구성품 14개다. 모든 항목은 검토 필요이고 모델 적용은 미확정이다. 일반 체크리스트 결과와 통합하는 작업은 후속 단계이며, 아직 전체 검토의 최종 레포트는 아니다.

실제 결과 폴더: `outputs/item_review_zc_20260913_unified/`.

```text
item_review_zc_20260913_unified/
├─ item_review.xlsx              담당자 확인용
├─ item_observation.json         원문·항목·출처 정보
├─ item_review_complete.json     관찰 결과 완료 기록
├─ item_excel_view.json          Excel 표시 데이터
├─ item_excel_complete.json      Excel 완료 기록
└─ extraction/                  XML·MD·ReviewDocument·추출 기록
```

작성 로그와 화면 검증 PNG도 이 폴더에 남을 수 있다. 사용자가 확인할 결과 파일은 Excel 하나다. 새 PDF 추출 시 `extraction/`을 만들고, 검증 묶음 재사용 시에는 JSON에 기존 묶음의 위치를 기록한다.

## Excel 읽는 방법

| 시트 | 내용 |
|---|---|
| Summary | 검토 상태·집계·대상 PDF 파일명. 머리글 포함 12행 |
| Item Results | 고정 항목 키·기준 문구·검토 판정·설명·검토 메모·원장 제안 이력 |
| Source Evidence | 고정 항목 키·근거 종류·현재 원문·XML 노드 ID·태그·페이지·XML 경로·상세 근거 |

실제 ZC 결과는 항목 14행, 근거 26행이다. 항목 문구 근거 14개와 조건 안내 연결 후보 12개를 구분한다. 문구 발견은 합격 판정이 아니다.

Summary의 기존 13행부터 있던 PDF/XML 해시, 내부 경로, 완료 기록과 원장 작성 당시 출처는 Excel에서 제외했다. `item_observation.json`의 `target_source`, `master_source`, `inputs`와 완료 기록에 보존한다.

`E0001` 같은 번호는 이전 Excel 안에서 순서대로 붙인 임시 참조번호였다. 이제 두 상세 시트는 **고정 항목 키**로 연결한다. 예를 들어 `samsung_smart_remote`를 Source Evidence에서 필터링하면 해당 항목의 문구와 조건 안내 후보를 함께 찾을 수 있다. 한 항목에 근거가 여러 개면 여러 행으로 유지한다. JSON에는 항목별 `candidates`와 `condition_candidates` 관계가 그대로 남는다.

노란 `검토 메모`는 내려받은 사본에 의견을 적는 칸이다. 오른쪽의 원장 제안 이력은 원장에서 가져온 자료이며, 결과 사본의 메모와 별개다. 메모를 쓰려면 다른 이름으로 저장한다. 보관 원본 Excel을 수정하면 완료 기록과 달라져 프로그램에서 정상 결과로 읽지 않는다. 메모를 DB로 다시 가져오는 기능은 아직 없다.

## 화면 실행

PowerShell에서 다음 명령을 실행한다.

```powershell
Set-Location 'C:\Users\bella\image-extractor\.worktrees\xml-review-v2'
.venv/Scripts/python.exe -m scripts.start_item_review_ui
```

브라우저에서 `http://127.0.0.1:8501`을 연다. 결과 폴더 입력칸 하나에 `outputs/item_review_zc_20260913_unified`를 입력하고 `불러오기`를 누른다. 같은 폴더의 검증된 Excel을 자동으로 찾아 JSON/Excel 다운로드를 제공한다.

Excel 생성 전에는 JSON 결과만 표시하고 `Excel이 아직 생성되지 않았습니다.`를 알린다. 생성 도중이거나 일부 Excel 파일만 있거나 파일이 변경됐으면 검증 오류를 표시하고 이전 결과·다운로드를 숨긴다. 다운로드를 누르는 시점에도 다시 검증한다.

종료는 실행한 PowerShell에서 `Ctrl+C`. 포트가 사용 중이면 `.venv/Scripts/python.exe -m scripts.start_item_review_ui --port 8502`로 실행한다. 실행기는 `127.0.0.1`에만 연결하고 사용 통계를 끈다. 다른 PC에 공개하는 공동 서버는 아니다.

## 새 결과 생성

먼저 [항목별 검토 명령](2026-09-11-item-observation-service_kr.md)으로 새 폴더에 관찰 결과를 만든다. 다음은 이 PC의 실제 경로를 사용하는 예다. 재실행할 때 `my_item_review_001`을 아직 없는 이름으로 바꾼다.

```powershell
Set-Location 'C:\Users\bella\image-extractor\.worktrees\xml-review-v2'
$env:PYTHONPATH = (Resolve-Path 'samples/tagged_pdf_xml_poc/src').Path
$env:PYTHONIOENCODING = 'utf-8'
.venv/Scripts/python.exe -m scripts.run_item_review_v2 'samples/SUG_RAW/TV_ZC/BN68-25100B-00_SUG_Y26 TV ALL_ZC_L02_260122.0.pdf' --output outputs/my_item_review_001

$env:ITEM_REVIEW_NODE = 'C:/Users/bella/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe'
$env:ITEM_REVIEW_NODE_MODULES = 'C:/Users/bella/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules'
.venv/Scripts/python.exe -m scripts.export_item_review_excel outputs/my_item_review_001
```

두 번째 명령은 첫 번째 명령의 **같은 폴더**에 Excel을 추가한다. 별도 `--output` 옵션은 없다. 이미 Excel 관련 파일이 있으면 덮어쓰지 않고 거부한다. 기존 완료 결과에서 두 번째 명령을 다시 실행해도 그 결과는 유지된다.

관찰 결과와 Excel은 각각 완료 기록을 가지므로 Excel 생성이 실패해도 원래 관찰 JSON은 보존된다. 실패한 Excel 파일은 완료 결과로 제공하지 않는다. 실패 폴더는 진단용으로 보관하고, 입력/작성 환경을 확인한 뒤 새 결과 폴더에서 재실행한다. `item_excel.lock`은 생성 중인 표시이며 정상 종료 시 자동 해제된다.

## 과거 결과와 배포 범위

- 2026-09-11 결과 폴더와 HTML/Excel은 그대로 보관한다. 이전 JSON+HTML 완료 기록(v1)은 읽을 때 두 파일을 모두 검증한다. 새 완료 기록(v2)은 JSON만 필수다. 과거 HTML을 삭제하면 그 과거 결과의 검증은 실패한다.
- 예전의 별도 Excel 폴더는 탐색기에서 직접 열 수 있다. 새 화면은 같은 폴더의 새 형식 Excel(view v2)을 사용하므로, 예전 Excel을 단순 복사해서 연결하지 않는다. 필요한 경우 과거 관찰 폴더에서 새 Excel 생성 명령을 실행한다. 이미 Excel 관련 파일이 있는 폴더는 덮어쓰지 않는다.
- 화면의 읽기·다운로드는 Python과 `requirements-review-ui.txt` 설치로 가능하다. 새 Excel 생성은 현재 Node/Artifact Tool 작성 환경이 추가로 필요하다. 자동 설치하지 않는다.
- 담당자용 Python-only 전체 배포는 후속 과제다. PDF 업로드/실행 버튼, DB 편집, 모델 적용 승인, 다른 바이어 지원도 아직 포함하지 않는다.

## 검증·복구 기록

2026-09-13 검증: 전체 테스트 **503개 통과**(실제 Artifact Tool 통합 2개 포함), compileall·pip check·Git 공백 검사 통과. 실제 PDF를 새로 추출한 폴더에서 Excel 3시트의 5개 영역을 렌더해 확인했다. Summary 12행과 두 상세 시트의 유지 열 전체 값은 이전 r2 Excel과 동일하며, 항목 14개·근거 26개를 보존했다. 기존 r2 Excel 파일 해시도 변경되지 않았다.

실제 결과를 사용한 Streamlit AppTest에서 입력칸 1개, 항목 14행, JSON/Excel 다운로드 2개를 확인했다. 독립 코드 검토에서 수정 필요 사항은 없었다. 실제 브라우저 육안 검수와 사용자의 최종 양식 승인은 이 자동 화면 테스트와 별개다.

새 Excel SHA-256: `467c2a9a0b3b880f923ee4b00b293755124c6f13278df2bcc6ce3059bfa099ee`.

이번 개정 직전 코드·계획 기준점은 `fc3e74f`다. 구현 커밋 번호는 `git log -1 --format=%H -- src/item_review_excel.py`로 확인한다. Git에는 코드·테스트·문서가 저장되며 `outputs/` 결과물과 `.venv`는 별도 보관 또는 재생성 대상이다.
