# XML 기반 검토 v2 마이그레이션 명세

상태: 대화에서 승인한 방향을 문서화. 단계별 구현과 검증 상태는 루트 TODO.md에 기록한다.

## 1. 목적

태그 기반 PDF 추출 결과로 체크리스트 검토와 Excel 리포트를 실행하는 v2를 만든다. 기존 사용자의 업무 기준과 필요한 결과 양식을 보존한다. GridCell 추출과 fallback은 v2 실행 경로에 포함하지 않는다.

기준점과 복구 방법: [복구 기록](../../migration/2026-09-10-recovery_kr.md).

## 2. 합의한 역할

| 구성요소 | 책임 |
|---|---|
| XML 추출기 | PDF 구조·글자·순서·관찰 근거 추출, 기존 네 산출물 생성 |
| 파일명 및 profile mapping | source_token, 바이어, 예상 언어·문서 유형 확인 |
| XML adapter | Semantic XML의 구조와 근거를 ReviewDocument로 변환 |
| ReviewDocument | UI·DB·Excel에 종속되지 않는 공통 내부 데이터 |
| 검토용 분류기 | 필요할 때 검증된 규칙으로 review_role 부여 |
| 체크리스트 평가기 | 적용 기준 선택, 해당 언어와 문서 범위에서 문구/표 검증 |
| ReviewService | 위 절차와 비교·모델 검토·출력을 순서대로 실행 |
| Streamlit | 입력 수집, 실행 호출, 진행 상태와 결과 표시 |
| Excel 출력기 | 결과를 검토자에게 익숙한 시트·열·색상으로 표시 |

`ReviewService`는 일반 Python 코드이며 웹 서버나 LLM 에이전트가 아니다.

## 3. 데이터 흐름

```text
PDF + 파일명/profile mapping
  → 기존 XML 추출기
      → raw_structure.xml
      → semantic_document.xml → 기존 Markdown writer → semantic_document.md
      → extraction_report.json
  → bundle/품질/언어 검증
  → XML adapter → ReviewDocument
      → 체크리스트 평가 / 변경 비교 / 모델 검토
      → ReviewResult → Excel / Streamlit / 결과 JSON
```

기존 Markdown writer는 이미 검수된 Semantic XML 표현을 유지한다. 초기 통합에서 Markdown writer를 다시 만들 필요가 없다. Markdown과 ReviewDocument는 같은 Semantic XML을 읽는다. Markdown을 파싱하여 DB나 Excel을 만들지 않는다. 문장 분할·연결 규칙을 두 출력기에 중복 구현하지 않는다.

## 4. 공통 문서 구조

원본 구조와 업무상의 의미를 나눈다.

- `structure_type`: paragraph, heading, list, list_item, table, table_row, table_cell, figure 등 실제 구조.
- `review_roles`: specification, navigation_ui, regulatory_note 등 검토 목적. 없으면 빈 목록이며 추측하지 않는다. 각 역할은 적용 규칙과 근거를 갖는다.
- 원본 순서와 중첩을 보존한다. 표 셀 안의 여러 문단·목록·그림도 자식 노드로 유지한다.
- 텍스트와 인라인 그림/노드의 순서를 보존하기 위해 node의 content에 문자열과 child node를 순서대로 둔다.
- heading의 관찰 텍스트, source role, 승격/후보 상태와 근거를 보존한다. Markdown의 `###`만 보고 확정 heading으로 만들지 않는다.
- 언어를 알 수 없는 문서 공통 영역도 보존한다. 예상 언어를 알았다는 이유로 모든 노드에 자동 배정하지 않는다.
- `page_index`는 내부 0부터 시작하고 화면에서만 1을 더한다. MCID는 페이지·객체 문맥과 함께 저장한다.
- 한 문서 내 node_id는 유일하다. 서로 다른 PDF/추출 버전의 node_id를 업무 ID처럼 재사용하지 않는다.

첫 구현은 데이터 구조와 구조 보존 테스트만 포함한다. 이 객체를 생성할 수 있다는 사실은 추출 품질 통과나 검토 성공을 의미하지 않는다.

## 5. 다국어와 체크리스트

`common_id`는 언어에 독립적인 업무 요구사항이고 `check_id`는 적용 범위/언어의 승인 문구다. 한 행의 required_text는 여러 문장이어도 된다. 문장 수·줄 수·`<br>` 수로 DB 행을 나누지 않는다.

문구 매칭은 검증된 언어·heading·문서 범위에서 수행한다. 원문은 보존하고 비교용 정규화는 별도로 수행한다. Unicode를 보존하며 영어용 ASCII 토큰 비교를 모든 언어에 그대로 적용하지 않는다. 다른 목록 항목이나 표 행을 무제한 이어 붙여 필수 문구가 있다고 판정하지 않는다.

기존 데이터 조사값: JSON schema 1, 547행, approved 545 / review 1 / deprecated 1, common_id 125개. JSON은 현재 상태 조사용이며 실제 이관 원본은 사람이 관리하는 master Excel이다. Excel→JSON 동기화 검증 이후 이관한다.

기존 master는 수정하지 않고 새 v2 Excel을 만든다. 승인 상태와 적용 범위·문구·ID·원본 증거를 보존한다. 기존 `status`는 v2 `approval_status`로 의미를 유지한다. XML 호환 상태는 생성된 이관 감사 자료의 `migration_status`로 분리하고, 검증한 profile/언어/추출기 버전/DB 버전 및 증거를 함께 저장한다. 한 profile의 통과로 다른 profile까지 검증 완료로 올리지 않는다.

자동 이관 상태: pending / verified / needs_review / excluded. review/deprecated 행은 삭제하지 않고 제외 감사 기록으로 보존한다. 미해결 approved 행을 조용히 빼서 전체 Pass를 내지 않는다. 적용되는 미검증 규칙은 검토 미완료로 표시한다. 원본/이관 행 수와 모든 check_id 대응을 대조한다.

원본의 block_type·section_heading 제약을 제거하면 검출 범위가 넓어질 수 있으므로 필드별 대응표와 결과 차이 감사가 필요하다. 원래 승인된 문구를 새 PDF 텍스트로 자동 교체하거나 LLM이 approved를 부여하지 않는다. 외부 API 기반 의미 판정은 사용하지 않는다.

## 6. Excel 결과 양식

여기서 Excel은 두 종류다: 사람이 편집하는 checklist master와 프로그램이 생성하는 review report. 역할을 혼동하지 않는다.

출력 코드의 기준 후보:

- content_exporter.py: 추출 검수용 Summary, Heading Sections, Content Review 및 특수 구조 시트.
- review_report.py: 체크리스트·변경 비교·모델 사양 등의 최종 검토 결과 리포트.

이 두 종류의 파일을 동일한 Excel이라고 간주하지 않는다. 실제 승인된 출력 파일을 선정하여 시트명, 열명/순서, 셀 값 의미, 색상, 필터, 고정창, 너비 및 근거 링크를 추출한 양식 명세를 만든다. 현재 시트 목록은 유지 후보이며 최종 양식 검수 완료를 의미하지 않는다.

필수 유지 의미: 문서/언어/바이어, 기준 문구, 실제 근거, check_id, 결과/사유, 페이지, 수동 확인 표시. 제거 대상: GridCell 좌표 및 구 추출 전용 디버깅 값. 업무 구조별 시트는 사용성이 확인된 경우 유지하고 새 review_role에 연결한다. 표 헤더 근거와 국가별 행 근거는 분리한다. 일반 Content Review에 topic_id를 추가하지 않는다.

새 exporter는 ReviewDocument/ReviewResult를 입력받는다. 구 payload를 흉내 내기 위해 구방식의 특수 분리·복구 코드를 이식하지 않는다. Excel 테스트는 업무 값과 양식 유지 여부를 검사하며 파일 바이트 동일성을 요구하지 않는다.

## 7. 실패와 안전한 실행

- PDF 태그 누락, report 실패, 필요한 gate 누락/실패, 읽기 오류, 언어 구간 모호함은 자동 평가를 중단한다.
- unknown 노드를 body로 변환하거나 텍스트를 버리지 않는다. 구조를 보존하고 미지원 검토를 명시한다.
- quality report와 XML은 동일한 실행 묶음인지 확인한다. 새 run directory에 출력하고 완료된 산출물을 소비한다. XML·report·PDF hash, 추출기 버전과 mapping/DB 버전을 실행 기록에 남긴다.
- report의 `pass`만으로 모든 업무 역할이나 체크리스트 호환이 검증됐다고 판단하지 않는다.
- 결과 상태는 추출 실패/검토 미완료/문구 불일치를 구분한다. 추출 실패를 단순 문구 없음으로 표시하지 않는다.

## 8. 단계와 완료 조건

1. 복구 커밋/bundle와 독립 통합 worktree, 설계 및 데이터 모델: 복구 검증, 구조 보존 단위 테스트.
2. XML adapter와 품질 gate: 원본 네 산출물 유지, 혼합 텍스트/중첩 표/그림/heading/언어/근거 보존, fail-closed 테스트, ZC ENG와 C-FRA 실물 확인.
3. DB 이관과 평가: Excel/JSON 동기화, 547행 처리 감사, 승인 상태 보존, 역할 및 범위 대응표, 미해결 결과 노출.
4. Excel와 ReviewService, CLI: 선정된 기존 결과 양식 검증, 중단/성공/실패 경로 테스트.
5. Streamlit 연결과 profile 확대: ZC ENG 기준 이후 각 buyer ENG, 그 buyer의 localized 순서. ZG BOOK/RTL/표지/연락처 표와 모델 검토를 포함.
6. 최종 전환: 설명되지 않는 결과 차이 제거, 승인 데이터/특수 검토 누락 없음, 사용자의 결과 양식 검수 후 active GridCell 경로와 불필요 legacy 삭제.
7. PC 배포: 지원 Python 환경, 재현 가능한 의존성, setup/run 배치파일, DB 버전이 고정된 실행, 각 PC 로컬 결과 저장. 공유 DB는 검증된 버전으로 배포하고 사용 중인 파일을 덮어쓰지 않는다.

legacy 코드가 통합 Git checkout에 역사적으로 남아 있는 것과 v2 runtime이 legacy를 import하는 것은 다르다. 초기에는 전자를 허용하되 v2의 GridCell 호출은 금지한다. cutover에서 최종 삭제와 배포 포함 파일 검사를 한다.

## 9. 이번 1단계의 범위

`src/review_document.py`와 그 단위 테스트를 작성한다. 파일명 파서/DB/exporter를 바꾸지 않는다. XML reader, 업무 역할 자동 분류, 평가기, 화면 전환은 각각 다음 단계의 구현·검증 대상이다. 전체 DB 이관이나 배포 완료로 보고하지 않는다.
