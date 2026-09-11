# 항목별 초안과 출처가 있는 결과 표시

## 이번 변경

사용자가 확인한 항목별 검토/출처 표시 명세를 구현했다. 일반 결과는 `검토 판정`과 `설명` 두 열로 표시하고, 세부 observation/reason은 JSON 진단으로 남긴다. 원문 DB, XML 추출기, Markdown writer 및 기존 검토 완료 파일은 변경하지 않는다.

`Summary`에 원본 PDF 파일명, 추출 결과 폴더, XML 위치, PDF/XML 해시, 추출 완료 기록을 한 번 표시한다. 일반 결과에는 근거를 소유하는 문단/목록/그림 ID를, 상세 근거에는 실제 텍스트 노드와 태그, XML 경로, 있는 경우 MCID/object-ref를 보존한다. 보고서 근거 행 ID와 원문 노드 ID는 별개다.

`scripts.prepare_review_report`는 보관된 완료 관찰 결과와 해시가 맞는 XML/추출 기록을 읽는다. 표시만 할 때 원본 PDF가 없어도 된다. 반면 새 항목 근거를 찾는 `scripts.prepare_item_proposal`은 원본 PDF와 동결 DB까지 다시 검증한다. 둘의 검증 범위가 다르다.

## CHK-002-ZC-ENG의 실제 분리 결과

기존 14줄을 명시적인 14개 하위 항목 키로 대응시켰다. 원문을 자동으로 문장별 분리한 것이 아니다. 기존 부모 규칙의 전체 17필드와 줄바꿈을 포함한 문구를 별도 보존하고, 각 하위 항목은 그 문구의 정확한 문자 구간을 참조한다. 항목 키는 XML 경로나 출력 행 번호가 아니다.

실제 ZC ENG XML에서 14개 모두 각각의 list_body 원문과 연결됐다. `Power Box`와 `Power Box Cable x 2`, `Remote Control`과 `Standard Remote Control`을 부분 문자열로 혼동하지 않도록 전체 항목을 비교한다. 비교는 공백 차이와 별도로 기록한 선두 `*`만 허용하며 실제 원문은 변경하지 않는다.

- `Simple User Guide`: 별표 없음.
- `Warranty Card / Regulatory Guide (Not available in some locations)`: 괄호 조건을 그대로 보존.
- 나머지 12항목: PDF 원문에 선두 `*` 존재. 해당 제목 범위의 `*: Some of the items specified above may not be included in the package, depending on the TV model.` 안내를 조건 후보로 연결.
- `Wall Mount Adapter x 2`, `Power Box Cable x 2`: 수량 표현 보존.

모든 항목은 `proposal_state=pending`, `condition_state=unverified`, 판정은 `needs_review`다. 별표 안내가 있다는 사실은 확인했지만 어떤 모델에 무엇이 필수인지 승인한 것은 아니다. 기존 approved는 역사적 부모 DB 상태이며 신규 조건 승인이 아니다.

## 전체 DB 분류

동결 DB 547행을 빠짐없이 구조 기준으로 분류했다:

| 분류 | 행 수 | 해석 |
|---|---:|---|
| item_split_candidate | 10 | 기존 item_list, 항목별 분리 정의 대상 |
| table_relation_review | 126 | 표 구조 또는 table_row/table_header 검사 방식 |
| retain_or_define | 411 | 유지 가능 여부 및 별도 정의 검토 대상 |

기계적 조사이며 `retain_or_define` 411행이 이미 XML 호환 검증을 통과했다는 뜻은 아니다. 조건은 자연어 추측으로 분류하지 않고 not_inferred로 남겼다. 이번에 실제 item별 대응한 대상은 ZC ENG CHK-002 한 행이다.

## 결과 파일과 사용 방법

작업장: `C:\Users\bella\image-extractor\.worktrees\xml-review-v2`.

출력 폴더: `outputs/review_item_layout_20260911/`.

- `review_report_prototype.xlsx`: 결과 개정본. Item Proposals에서 14개 원문/조건/근거를 확인한다.
- `item_proposal.json`: DB 활성화용 JSON이 아닌 원본 대조 및 근거 연결 감사 파일.
- `report_view_verified.json`: 노드 소속 관계까지 재검증한 최종 표시용 변환. 앞선 report_view 파일은 중간 점검 자료다.

워크북 시트: Summary, Checklist Results, Item Proposals, Source Evidence, Excluded Rules, Migration Inventory. 일반 결과 59행과 구성품 초안 14행을 합산하지 않는다. 부모 규칙은 원본 감사용으로 남아 있으며 기존 결과 집계는 547/59/488, 근거 40행 그대로다.

```powershell
Set-Location C:\Users\bella\image-extractor\.worktrees\xml-review-v2
$env:PYTHONPATH = (Resolve-Path samples/tagged_pdf_xml_poc/src).Path
.venv\Scripts\python.exe -m scripts.prepare_item_proposal outputs/review_service_zc_20260911_r2 "samples/SUG_RAW/TV_ZC/BN68-25100B-00_SUG_Y26 TV ALL_ZC_L02_260122.0.pdf" --output outputs/new_item_review/item_proposal.json
.venv\Scripts\python.exe -m scripts.prepare_review_report outputs/review_service_zc_20260911_r2 --output outputs/new_item_review/report_view.json
```

기존 출력 이름은 거부하므로 새 폴더를 사용한다. Excel 생성기는 아직 개발 환경의 Artifact Tool을 사용하는 초안 생성기이며 동료 PC용 배포 명령이 아니다.

## 검증과 남은 범위

항목 테스트는 원문 복원, 수량/조건, 겹치는 구간/누락/키 중복, 임의 승인 변경, 언어/제목 경계, 전체 항목 비교, 실제 14항목/12별표, 실행 전/도중 동결 DB 변경 거부를 다룬다. 일반 표시 테스트는 판정 불변, 설명 구분, 출처 해시, 노드/근거 불일치 및 저장 중 변경을 다룬다.

전용 v2 환경에서 전체 `python -m pytest tests -q` 333개 통과, 항목 집중 테스트 17개 통과, compileall 통과. 독립 검토에서 발견한 존재하지만 무관한 owner ID 연결 문제는 실패 테스트 7개로 재현하고 실제 부모/그룹/조상/표 컨테이너/그림 관계 검증으로 수정했다. 수정 중 실행했던 전체 테스트는 해당 7개 실패를 포함했으므로 최종 검증으로 사용하지 않았고, 수정 완료 후 333개를 새로 실행했다.

Excel은 6개 시트를 렌더링해 확인했으며 일반59/근거40/제외488/항목14/조사547행의 전체 열 값을 입력과 대조했다. 출처 패널, 집계 수식 캐시59, 항목수14, 필터/고정창과 조건부 서식을 확인했다. Excel 데스크톱에서의 클릭/편집 동작 검수는 수행하지 않았다. 기존 메인 DB Excel/JSON SHA256는 이전 복구 기준과 동일하다.

신규 항목 초안을 DB로 활성화하거나 기존 부모 행을 삭제하지 않았다. 다음 DB 단계에서는 확정된 하위 항목/조건 구조를 별도 Excel 원장에 관리하고 JSON으로 내보내야 한다. 현재 감사 JSON을 runtime DB로 복사하면 안 된다. 다른 언어/바이어의 item 분리, 모델별 적용 조건, 표/표지 전용 판정, 배포용 Excel writer와 Streamlit은 별도 검증이 남아 있다.
