# 통합 PDF 실행과 결과 화면 사용법

## 이번에 연결한 것

PDF 한 개를 입력하면 XML 추출을 한 번 수행하고, 같은 추출본으로 일반 체크와 구성품 상세를 조사한 뒤 결과 폴더 하나에 Excel과 JSON을 만듭니다. 화면은 그 폴더 하나를 받아 검증된 결과를 보여 줍니다.

지원 범위는 기존 ZC_L02 / A2 / ENG 파일럿입니다. 일반 체크 59건과 그중 구성품 상세 14건이며, 전부 검토 필요 상태입니다. 다른 바이어/언어 지원, 모델 적용 승인, 자동 합격·불합격은 추가하지 않았습니다.

## 지금 확인할 수 있는 결과

정상 결과: `outputs/combined_review_zc_20260913_shared_r2/`

```text
combined_review_zc_20260913_shared_r2/
  review_report.xlsx               ← 검토자가 사용하는 통합 Excel
  review_report.json               ← 내부 원본 결과와 출처 보관
  review_report_view.json          ← 표시용 값
  review_report_complete.json      ← 프로그램의 완료 확인 기록
  _internal/
    extraction/                   ← XML / 사람이 보는 MD / ReviewDocument
    checklist/                    ← 일반 체크 관찰 JSON과 완료 기록
    items/                        ← 구성품 상세 관찰 JSON과 완료 기록
```

사용자는 결과 폴더나 Excel 하나만 선택하면 됩니다. `_internal`은 재현·진단 자료로, 결과를 서로 다른 작업 폴더에서 찾아 합칠 필요가 없습니다. 작성 로그와 렌더 확인 PNG도 같은 실행 폴더에 남습니다.

`--bundle`을 사용하면 추출은 생략하고 지정한 기존 추출본을 검증하여 사용합니다. 이 경우 `_internal/extraction` 복사본은 만들지 않습니다. 통합 JSON에는 결과 읽기에 필요한 원문 XML과 출처를 별도로 보관하므로, 나중에 과거 입력 폴더가 없어져도 완료된 Excel/JSON 조회는 가능합니다. 기존 MD의 위치는 사용자가 지정한 추출 폴더입니다.

## 새 PDF에서 실행하기

이 작업장의 기존 Python 환경을 사용합니다. 처음 환경을 구성할 때에는 `requirements-review-ui.txt`를 설치하며, 이 파일이 XML 검토 의존성도 포함합니다. 이미 설치된 환경을 다시 만들 필요는 없습니다.

현재 Excel 작성은 Node/Artifact Tool 환경도 필요합니다. 아래는 Bella PC에서 확인한 경로입니다. 전체 PC 배포용 작성 도구 구성이 확정됐다는 의미는 아닙니다.

```powershell
Set-Location C:\Users\bella\image-extractor\.worktrees\xml-review-v2
$env:PYTHONPATH = (Resolve-Path samples/tagged_pdf_xml_poc/src).Path
$env:ITEM_REVIEW_NODE = 'C:/Users/bella/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe'
$env:ITEM_REVIEW_NODE_MODULES = 'C:/Users/bella/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules'

.venv\Scripts\python.exe -m scripts.run_combined_review_v2 'samples/SUG_RAW/TV_ZC/BN68-25100B-00_SUG_Y26 TV ALL_ZC_L02_260122.0.pdf' --output outputs/my_combined_review
```

`my_combined_review`는 실행할 때마다 새 폴더 이름으로 바꿉니다. 이미 있는 결과 폴더는 덮어쓰지 않습니다.

기존 추출본을 재사용하려면 같은 명령에 다음 옵션을 추가합니다.

```powershell
--bundle outputs/combined_review_zc_20260913_shared_r2/_internal/extraction
```

파일명과 PDF 내용, 프로필 매핑, 추출 완료 기록 및 파일 내용이 맞아야 재사용됩니다. 완료 기록이 없는 옛 XML 폴더는 자동 검토 입력으로 사용하지 않습니다.

## 결과 화면 열기

```powershell
Set-Location C:\Users\bella\image-extractor\.worktrees\xml-review-v2
.venv\Scripts\python.exe -m scripts.start_item_review_ui --combined
```

브라우저에서 `http://127.0.0.1:8501`을 엽니다. 이 주소는 자기 PC 안에서만 접속합니다. 다른 프로그램이 해당 포트를 사용한다면 `--port 8502`를 붙이고 표시된 주소를 엽니다.

1. “완료된 통합 결과 폴더”에 아래 경로를 입력합니다.
2. “불러오기”를 누릅니다.
3. 일반 체크와 구성품 상세를 확인하고 “통합 Excel 다운로드”를 누릅니다.

```text
C:\Users\bella\image-extractor\.worktrees\xml-review-v2\outputs\combined_review_zc_20260913_shared_r2
```

내부 JSON 다운로드는 “내부 확인용 데이터”를 펼쳤을 때 제공됩니다. 상세 근거는 Excel의 `Source Evidence` 시트를 사용합니다. 검토 메모는 다운로드한 사본에 작성하며, 원본 결과 파일을 직접 수정하면 다음 조회에서 변경된 결과로 판단하여 차단합니다.

화면은 현재 조회·다운로드 전용입니다. PDF 실행은 위 명령으로 합니다. 화면 PDF 업로드·실행 버튼 연결은 다음 단계입니다. 기존 `start_item_review_ui` 명령에서 `--combined`를 생략하면 이전 구성품 전용 화면을 엽니다.

## 실패한 실행과 완료 기록

전체 실행 중에는 `review_workflow.lock`이 있고, 실패하면 `review_report_failed.json`을 남깁니다. 이런 폴더는 화면에서 결과나 다운로드를 제공하지 않습니다. 실패 폴더에서 표시 파일을 삭제해 억지로 여는 대신, 실패 원인을 해결하고 새 이름의 폴더로 다시 실행합니다.

이번 첫 실행 `outputs/combined_review_zc_20260913_shared/`은 `PYTHONPATH` 설정 누락으로 실패했습니다. 이 폴더는 실패 기록으로 보존하며, 정상 결과는 `_shared_r2`입니다. 패키지/추출 코드를 바꾼 것이 아니라 기존 안내에 있던 XML 소스 경로 설정을 적용해 해결했습니다.

공통 실행은 일반 관찰 완료 기록 v2(JSON 전용)를 사용하므로 HTML을 생성하지 않습니다. 기존 일반 관찰 v1과 항목 관찰 v1은 과거 HTML까지 검증하는 읽기 호환을 유지합니다. 이전 일반 검토 명령은 기존 HTML 포함 동작을 유지합니다.

## 실물 확인 결과

- 신규 연결/UI 테스트 15개 통과. 루트 전체 `python -m pytest tests -q` 573 passed. 기존 `src/tests/scripts` compileall, pip check 통과. 별도 XML POC 전체 테스트는 재실행하지 않음.
- 새 명령으로 실제 ZC PDF 실행 완료. 일반 59 / 구성품 상세 14 / 일반 근거 40 / 항목 근거 26 / 내부 제외 488 / 원본 규칙 547.
- 두 검토의 추출 완료 기록 해시 동일. 새 HTML 파일 0개.
- 기존 `review_service_zc_20260911_r2/extraction`과 Semantic XML, MD, ReviewDocument JSON 바이트 동일.
- 이전 통합 `_r2`와 일반 체크 행·구성품 상세 행·Excel 표시 데이터 전체 동일. 출처 경로와 새 JSON-only 완료 기록은 현재 실행 기준으로 기록.
- 실제 결과를 Streamlit AppTest로 읽어 59/14행과 다운로드 2개 확인. Excel 저장값 검증 및 네 시트 대표 영역 렌더 확인. 이번 화면은 AppTest 검증이며 브라우저 육안 사용성 승인은 아님.
- 별도 코드 검토에서 중대한 결함 없음. README의 오래된 미구현 안내를 갱신.

자동 검증은 중간 데이터와 출력 연결을 확인합니다. 원본 PDF와 결과를 사람이 업무 관점에서 최종 승인했다는 의미는 아닙니다. [사람이 확인하는 시점과 ReviewDocument의 책임](../architecture/review-document-explained_kr.md)을 함께 참고하세요.
