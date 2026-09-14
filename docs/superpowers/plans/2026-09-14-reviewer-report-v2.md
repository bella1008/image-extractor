# 검토자용 통합 Excel v2 계획

사용자가 승인한 후속 작업: 실제 값이 있는 검토용 Excel 정리와 화면 일치 검증.

목표: 체크리스트 관찰 결과를 읽기 쉽게 표시한다. PDF/XML 추출, DB, 판정은 변경하지 않는다.

설계: 기존 4시트와 12행 이내 Summary 유지. 구성품에는 현재 원문과 페이지 및 조건 안내 후보를 표시하고 원장 작성용 제안은 JSON에 유지한다. Source Evidence의 상세 JSON 열은 제거하되 노드/태그/페이지/XML 경로를 유지한다. 새 표시 버전은 /2, 기존 /1은 검증하며 읽는다. 화면은 저장된 버전으로 생성한 검증 view를 사용한다.

- [x] 실제 fixture 기반 새 표시 테스트 작성 및 실패 확인. 현재 후보 원문, 페이지, 조건 원문을 정확히 대조하고 report 불변을 확인한다.
- [x] `src/combined_review_view.py`: /1 호환과 /2 기본 출력 구현. `src/combined_review_service.py`: 저장 view 버전별 검증 및 view 반환. `scripts/combined_review_app.py`: 반환 view 사용.
- [x] `scripts/build_combined_review_excel.mjs`: /2 열 계약과 렌더 범위 갱신.
- [x] 기존 /1 결과 읽기 및 변경된 /2 view 거부 회귀 테스트. 관련 pytest와 compileall 실행.
- [x] 검증된 실제 ZC 실행의 내부 관찰 결과를 재사용해 새 폴더에 결과 생성. 이전 결과와 JSON 원문 불변, 59/14/66행 및 전 셀 검증. 4시트 렌더 확인.
- [x] 사용법과 TODO에 결과·한계를 기록. 사람의 의미 검수나 자동 Pass/Fail 완료로 표현하지 않는다.
