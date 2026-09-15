# PDF 입력부터 체크리스트 결과까지 화면에서 실행

## 현재 생성하는 결과의 의미

이번 기능은 네 agent 중 **체크리스트 DB 대조** 경로에 해당한다.
현재는 ZC ENG 파일럿으로, 문구 발견/구조 근거/미지원 사유를 조사하며 자동 업무 Pass/Fail은 하지 않는다.
“통합”은 일반 체크리스트와 그 하위 구성품 상세를 한 Excel에 모았다는 뜻이다.
Before/After PDF 비교, 회사 시스템 사양 검토, 다국어 참고 의견은 향후 별도 구현한다.

| 파일 | 의미 | 용도 |
|---|---|---|
| `_internal/extraction/review_document.json` | 추출한 PDF 원문과 구조를 담은 공통 입력 데이터 | 네 agent가 공유할 입력 |
| `_internal/extraction/semantic_document.md` | PDF 추출 내용을 사람이 읽기 편하게 표시한 자료 | 원문 추출 검수 |
| `review_report.json` | 현재 체크리스트의 일반/구성품 관찰 결과와 재현 근거 | 시스템/문제 조사 |
| `review_report.xlsx` | 위 체크리스트 결과를 사람이 확인하는 보고서 | 담당자 검토 |
| `review_report_view.json` | Excel 행·열 표시용 데이터 | 보고서 생성 |
| `review_report_complete.json` | 산출물 무결성을 확인하기 위한 완료 기록 | 시스템 |

향후 권장 운영은 실행한 agent별 결과를 구분하고, 사용자가 받는 Excel 하나에 기능별 시트를 모으는 것이다.
실행하지 않은 agent를 검토 완료로 표시하지 않는다. 다국어 검토는 반드시 “참고 의견”으로 표시한다.
향후 통합 포맷은 각 agent 구현 시 확정하며 이번 변경은 현재 보고서 형식을 바꾸지 않는다.

## 실행 방법

2026-09-15부터 통합 Excel은 Python 작성기를 기본으로 사용한다.
개발 작업장에서는 아래 명령을 실행한다. 담당자 PC용 ZIP은 [배포 안내](2026-09-15-python-delivery_kr.md)를 따른다.

```powershell
Set-Location C:\Users\bella\image-extractor\.worktrees\xml-review-v2
.venv\Scripts\python.exe -m scripts.start_item_review_ui --combined --open-browser
```

1. 브라우저에서 `http://127.0.0.1:8501`을 연다. 포트가 사용 중이면 명령 끝에 `--port 8502`를 붙인다.
2. “PDF로 새 체크리스트 검토 실행”에서 PDF 경로를 붙여 넣는다. 원래 PDF 파일명은 유지한다.
3. 결과 저장 위치를 확인하고 “체크리스트 검토 실행”을 누른다.
4. 실행마다 `checklist_날짜_시간_고유번호` 폴더를 만들고, 완료 후 해당 폴더 결과를 자동 표시한다.
5. Excel을 다운로드한다. JSON은 “내부 확인용 데이터”에서 필요할 때 받는다.

기존 결과는 “완료된 통합 결과 폴더”에 경로를 입력하고 “불러오기”로 확인한다.
실행 중에는 화면 추가 조작을 피한다. 실패하면 오류와 생성된 폴더 위치를 표시하고 이전 다운로드를 비운다.
실패 폴더는 문제 조사용으로 남긴다. 재실행은 새 폴더에 저장하므로 이전 산출물을 덮어쓰지 않는다.
입력/환경 오류처럼 실행 전에 발견한 문제는 결과 폴더를 만들지 않는다.

XML 패키지 경로는 launcher가 자동 설정한다. 개인 PC의 localhost 실행용이다.

## 실물 확인

연결/완료 검증/기존 화면 회귀 테스트 58개 통과. src/tests/scripts 컴파일 검사 통과.
`apps/`는 이 작업장에 없다. 이번에는 전체 테스트와 XML POC 전체 suite를 다시 실행하지 않았다.

2026-09-14 Streamlit AppTest에서 실제 ZC PDF 입력과 실행 버튼으로 생성:
`outputs/checklist_20260914_130233_25dbc00a184e/`.
일반 체크59/구성품상세14, 다운로드2개, HTML없음.
`combined_review_zc_20260913_shared_r2`의 XML/MD/ReviewDocument와 바이트 단위 동일.
자동 검증은 실행 연결과 추출 내용 보존의 증거이며, 원본 PDF의 모든 시각 요소에 대한 사람 승인이나 업무 승인과 같지 않다.
바이어·언어별 원문 검수 상태는 기존 검증 대장을 계속 따른다.
