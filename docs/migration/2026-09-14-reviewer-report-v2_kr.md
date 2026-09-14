# 검토자용 통합 Excel 양식 v2

## 결과와 사용법

실제 ZC 영어 표본: `outputs/checklist_reviewer_zc_20260914_v2/review_report.xlsx`.
같은 폴더의 `review_report.json`은 상세 근거와 원장 제안을 보존한다.
기존 검증 실행 `checklist_20260914_130233_25dbc00a184e`의 내부 관찰 결과를 재사용했으며 PDF를 다시 추출하지 않았다.

| 시트 | 내용 |
|---|---|
| Summary | PDF 파일명, 프로필, 검토 언어, 현재 실행 기능과 건수. 헤더 포함 12행 |
| Checklist Results | 일반 체크리스트 59개. 기준 문구와 현재 근거, 설명, 페이지 |
| Item Results | CHK-002의 구성품 14개. 기준 문구, 실제 추출 원문, 설명, 페이지, 조건 안내 원문 후보 |
| Source Evidence | 일반 근거40행과 구성품 근거26행. 고정 체크/항목 키로 필터하고 노드·태그·페이지·XML 경로 추적 |

예: 기준 `Samsung Smart Remote`와 실제 `*Samsung Smart Remote`를 나란히 확인할 수 있다.
조건 안내 후보에는 `*: Some of the items specified above may not be included in the package, depending on the TV model.` 원문이 표시된다.
이 문구의 연결과 모델 적용은 아직 미확정이다. 조건이 검증되거나 해당 모델에 적용된다는 뜻이 아니다.
복수 후보는 빈 줄로 구분해 모두 표시한다. 근거가 없으면 현재 원문/페이지가 비어 있고 설명에서 미확인 사유를 확인한다.
PDF 페이지는 파일의 실제 페이지 순서(1부터)이다. 구성품 시트의 페이지는 항목 문구 위치이며 조건 안내의 개별 위치는 Source Evidence에서 확인한다.

원장 모델 조건 제안/제안 근거/원장 검토 메모와 상세 근거 JSON 열은 새 Excel에서 제외했다. 원본 데이터는 JSON에 보존한다.
검토 메모는 다운로드한 사본에 작성하며 DB 승인으로 반영되지 않는다.
일반59개 안에 CHK-002가 있으므로 구성품14개를 더해 73개라고 세지 않는다.

## 화면과 이전 파일

화면 실행 방법은 [PDF 입력 화면 사용법](2026-09-14-checklist-ui-run_kr.md)을 따른다.
완료 결과 폴더에 `C:\Users\bella\image-extractor\.worktrees\xml-review-v2\outputs\checklist_reviewer_zc_20260914_v2`를 입력하면 조회/다운로드할 수 있다. 새 PDF 실행도 새 양식을 사용한다.

새 표시 버전은 `combined-review-excel-view/2`이다. 이전 `/1` 파일은 당시 양식으로 대조 검증하고 그대로 다운로드한다.
화면도 검증된 저장 버전을 사용하므로 과거 Excel과 새 화면 열이 어긋나지 않는다. 업무 결과 JSON 형식은 바뀌지 않았다.

## 검증 기록

- 관련 Python/Node 경계 테스트: 54 passed, 작성 환경이 필요한 2개 skipped. 해당 2개를 실제 작성 환경으로 별도 실행해 2 passed. 리터럴 수식 형태 텍스트와 근거0행 XLSX 검증 포함.
- compileall src/tests/scripts 및 git diff --check 통과. apps 폴더는 이 작업장에 없음.
- 실제 ZC 구/신 완료 파일 모두 검증. review_report.json 바이트 완전 동일. 일반59/하위14/근거66, 제외488/원장547 유지.
- 저장 Excel 전 셀/필터/고정창/수식 주입 방지 검사 통과. 4시트7영역 렌더 확인.
- 실제 결과 AppTest: 59/14행, Excel/JSON 다운로드2개, 신규 구성품 원문 열 표시.
- 미지 버전 거부, 해시를 다시 계산한 표시 원문 변조 거부, 이전 버전 읽기 회귀 검사 포함.

전체 프로젝트/전체 XML POC 테스트를 이번에 다시 실행한 것은 아니다. PDF 누락, 다국어 의미 일치, 업무 합격/불합격, 회사 사양 검토와 PC 전체 배포 완료를 뜻하지 않는다.

## 사람 확인 시점과 다음 단계

실제 값으로 사용 편의성을 확인할 수 있는 양식 표본이다. 사용자는 편한 때 Item Results에서 기준/원문 비교, 조건 안내, 메모 배치가 편한지 의견을 줄 수 있다. 이 회신은 내부 후속 검증을 막는 선행 조건이 아니다.
자동 판정/evaluator와 ReviewDocument의 향후 agent용 구조 검증은 별도 작업으로 남아 있다. 원문 누락 판단이 필요해지면 바이어·언어·PDF·범위를 명시해 검증 대장에 기록하고 확인 요청한다.
