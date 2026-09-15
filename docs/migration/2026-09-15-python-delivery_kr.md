# 검토용 Excel 이후: Python PC 배포 파일럿

## 이번에 연결한 부분

검토용 4시트 Excel을 담당자 PC의 Python으로 생성한다.
`ReviewDocument → 체크리스트 근거 조사 → 표시용 데이터 → Python Excel 작성기` 흐름이다.
기본 화면/CLI는 Node 환경 변수를 요구하지 않는다. 명시적으로 두 Node 인수를 전달한 개발 호출은 호환된다.

새 표본은 `outputs/checklist_reviewer_zc_20260915_python/review_report.xlsx`다.
2026-09-14의 같은 관찰 결과를 재사용해 작성기 변경만 검증했다.
기존 report/view JSON은 바이트 동일하고 Excel 1,232개 셀 및 행 높이·열 너비·고정창·표 스타일이 동일하다.
저장 파일의 Summary/Checklist Results/Item Results/Source Evidence 전체 4시트 7영역을 렌더링해 확인했다.

## 담당자에게 전달하는 구조

최종 전달 ZIP: `outputs/review_pilot_20260915/review-pilot.zip`.

```text
review-pilot.zip 압축 해제 폴더/
  setup.cmd / setup_review.py    처음 한 번 설치
  start.cmd / start_review.py    매번 화면 시작
  review_cli.py                 터미널 실행
  사용안내.md
  pilot_support.py / release_manifest.json
  requirements-review-*.txt
  src/ / scripts/               실행에 필요한 코드
  samples/tagged_pdf_xml_poc/src/  고정 XML 추출기
  metadata/                     프로필과 동결 체크리스트 초안
```

Git·기존 GridCell 실행기·가상환경·개발용 Node·원본 PDF·기존 결과는 ZIP에 포함하지 않는다.
ZIP 생성 시 필요한 Python import를 추적하고 데이터 파일은 명시한 목록만 포함한다.
원본 코드의 내용과 해시를 기록하며, 생성 도중 변경되거나 기존 ZIP이 있으면 덮어쓰지 않는다.
수정된 개발 작업장에서 만든 경우 manifest의 `working_tree_changed`로 표시한다.
해시 검사는 손상/변경 감지이며 배포 서명이나 DB 업무 승인이 아니다.

## 설치와 실행

Windows/Python 3.12 기준이다. 최초 설치에는 Python 패키지 다운로드가 필요하다.
ZIP을 새 폴더에 풀고 `setup.cmd`를 실행하면 그 폴더의 `.venv`에 설치한다.
이후 `start.cmd`를 실행하면 `127.0.0.1:8501`의 개인 PC용 화면이 열린다.
포트 중복 시 `start.cmd --port 8502`를 쓴다. 사내 서버의 외부 포트 개방은 필요하지 않다.

자세한 안내: [배포본에 포함하는 사용안내](../../deployment/review-pilot/사용안내.md).
내부 배포 경로이며 외부 서비스에 게시/전송하지 않았다.

## 개발자 생성 명령

이 작업장 루트에서 실행한다. 매번 새 ZIP 경로를 사용한다.

```powershell
.venv\Scripts\python.exe -m scripts.build_review_pilot --output outputs/새배포폴더/review-pilot.zip
```

실행 코드를 변경했다면 테스트 후 다시 생성한다. 설치한 폴더를 직접 수정하거나 결과를 덮어쓰지 않는다.
원본 기준점 `ad2c317`과 마이그레이션 이전 복구 기준은 그대로 보존한다.

## 검증 근거와 범위

- 관련 집중 테스트 97 passed / 2 skipped. skipped는 변경하지 않은 개발용 Artifact Tool 작성 테스트다. Python 실물 작성·서비스·UI·패키지 테스트는 통과했다.
- 기존/새 Excel 전 셀·구조 대조, report/view JSON 동일성, 기존 완료 파일 읽기 확인.
- 수식 모양 텍스트/오류 모양 텍스트/다국어/빈 근거/표시 한계/덮어쓰기/입력 변경/실패 차단 검사.
- ZIP 85개 파일과 manifest 검증, 한글·공백 경로로 재배치 후 runtime 점검과 CLI import 확인.
- 작성기와 배포 코드에 대한 독립 검토에서 수정 필요 결함 없음.
- compileall src/tests/scripts/deployment 및 pip check 통과. apps 폴더는 이 작업장에 없다.

## 별도 설치 환경 실물 검증

시험 ZIP을 `outputs/review_pilot_20260915_smoke/다른 PC 검토 프로그램/`에 풀고,
`setup_review.py`로 **새 가상환경**에 패키지를 실제 설치했다. 설치 후 pip check와 runtime 점검 통과.
최초 시도는 작업 도구의 제한된 네트워크 환경에서 다운로드 대기가 발생해 종료했고,
같은 시험 환경에서 다운로드 가능한 실행으로 재시도해 완료했다. 실제 담당자 PC의 네트워크 정책 검증은 별도다.

새 PDF: `BN68-25100B-00_SUG_Y26 TV ALL_ZC_L02_260122.0.pdf`.
실제 결과: `outputs/review_pilot_20260915_smoke/다른 PC 검토 프로그램/outputs/zc_fresh/`.

- 새 설치본 CLI로 PDF → XML/MD/ReviewDocument → 일반/항목 조사 → Python Excel까지 완료.
- 상위59/하위14/일반근거40/항목근거26/내부제외488/원장547 유지.
- 새 XML/MD/ReviewDocument가 `checklist_20260914_130233_25dbc00a184e`와 바이트 동일.
- 새 설치본 Streamlit AppTest에서 59/14행과 다운로드2개 확인. 실제 로드 모듈도 재배치 폴더 소속임을 확인.
- 고정 DB 초안 Excel/JSON과 항목 원장 Excel/JSON은 작업 시작 HEAD와 바이트 동일.
- 원문 확인 대장에 `RUN-20260915-PILOT-ZC`로 ENG/C-FRA 보존 근거를 연결.

브라우저의 실제 더블클릭 실행이나 담당자의 별도 물리 PC에서 설치한 것으로 확대하지 않는다.
의존성의 상위 패키지는 고정되어 있으나 간접 의존성 전체를 잠근 offline 배포본은 아니다.

## 남은 작업

이 배포본은 **ZC_L02 ENG 근거 조사 파일럿**이다. 자동 Pass/Fail이나 전체 바이어 지원이 아니다.
이번 단계에서 추출 규칙/DB 원문을 바꾸지 않았으며, 다국어 의미 검증이나 사람 검수 범위를 확대하지 않았다.
표지 연락처 제목의 MD bold 후속 HR-20260914-002와 자동 evaluator는 남아 있다.
