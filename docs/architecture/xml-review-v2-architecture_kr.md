# ReviewDocument 구조와 구현 경계

관련 명세: [XML v2 마이그레이션](../superpowers/specs/2026-09-10-xml-review-v2-design_kr.md).

## 첫 단계의 자료형

기존 `src/models.py`에는 GridCell도 함께 정의되어 있다. v2 모델은 독립 파일 `src/review_document.py`에 두고 Python 표준 라이브러리만 사용한다. 기존 flat `src/` 방침을 유지한다.

| 자료형 | 필드와 의미 |
|---|---|
| DocumentContext | manual_code, source_token, region, buyer_codes, doc_type, expected_languages, language_variant |
| SourceEvidence | semantic XML 위치 xml_path, page_index(0-based), mcid, object_ref, bbox |
| ReviewRole | name, rule_id, evidence_paths. v2 검토 목적 분류의 근거이며 PDF source role과 구분 |
| ReviewNode | node_id, structure_type, content, language, source_role, attributes, evidence, review_roles |
| ReviewDocument | context, roots, schema_version=`review-document/1` |

모든 dataclass는 frozen이고 컬렉션은 tuple로 받는다. `content`는 `str | ReviewNode`의 tuple이다. 문자열과 child의 순서를 보존하므로 XML의 text-child-tail, 인라인 아이콘, 중첩 목록/표를 표현할 수 있다. `attributes`는 `(이름, 값)` tuple들로 구성해 source heading 후보·행/열 병합·display hint 등을 소실 없이 전달할 수 있게 한다. 실제 XML 속성 해석은 다음 adapter 단계에서 검증한다.

`ReviewNode.text_content`는 content의 문자열을 원래 순서대로 재귀 연결한 편의 보기다. 이 함수는 공백을 삽입하거나 제거하지 않는다. 표 전체의 text_content를 곧바로 체크리스트 검색 범위로 사용해서는 안 된다. 실제 비교는 검증된 문단/목록/표 행 범위를 선택한다.

`ReviewDocument.iter_nodes()`는 root 순서와 자식 순서에 따른 preorder 순회다. 문서 내 중복 node_id는 생성 시 거부한다. `expected_languages`는 기대값이므로 실제 검출 언어라고 표시하지 않는다. 첫 모델은 문서 품질 pass 값을 제공하지 않는다.

## 불변 조건

- 빈 필수 ID, 지원하지 않는 doc_type, 잘못된 canonical 언어 코드와 중복 expected language를 거부한다.
- 소문자 언어·임의 번역을 canonical 언어로 조용히 바꾸지 않는다. `C-FRA`, `M-SPA`, `B-POR`를 그대로 허용한다.
- 원문 텍스트를 정규화하거나 문장별로 자르지 않는다. 여러 문장도 하나의 문단에 들어간다.
- page_index/MCID는 None 또는 음수가 아닌 정수다. bool은 정수로 취급하지 않는다.
- bbox는 None 또는 유한한 네 수이며 좌우/상하 순서가 맞아야 한다. 근거가 없으면 None을 유지한다.
- 미인식 structure_type도 이름 그대로 보존한다. adapter/quality 단계에서 지원 여부를 판단한다.
- review_role은 rule_id와 evidence_paths를 함께 받아야 한다. 자동 추측은 하지 않는다.
- legacy role명(`navigation_ui`, `spec_table`, `regulatory_note`, `model_condition`, `safety_warning` 등)은 v2의 필수 출력명이 아니다. v2 role은 XML 구조와 현재 검토 목적을 기준으로 새로 정의하고, legacy 대응은 감사용 매핑으로만 둔다.
- 문서 공통/미배정 노드의 language=None을 허용한다. 다국어 정합성 gate는 reader 단계에서 수행한다.
- 원본 XML 계층과 heading 논리 계층이 항상 동일하다고 가정하지 않는다. heading 기반 grouping은 XML reader 후의 별도 검토 보기로 구현한다.

## 다음 단계의 파일 경계

| 예정 파일 | 책임 및 소비자 |
|---|---|
| `src/semantic_xml_reader.py` | 검증된 XML bundle → ReviewDocument |
| `src/xml_review_gate.py` | 보고서/버전/언어/구조 조건 검사, 실패 사유 |
| `src/review_roles.py` | v2 업무 분류 규칙, legacy 대응 감사, role 적용 근거 |
| `src/checklist_review_v2.py` | 문서/언어 범위를 지키는 deterministic 평가 |
| `scripts/migrate_checklist_v2.py` | Excel 기반 반복 가능한 이관 및 감사 출력 |
| `src/review_excel_v2.py` | 결과 데이터 → 승인된 Excel 양식 |
| `src/review_service.py` | 요청 → 추출/검토/결과 파일 생성 |
| `apps/streamlit_review_v2.py` | UI 입력과 ReviewService 호출 |

`semantic_xml_reader.py`와 `xml_review_gate.py`는 2단계에서 구현했다. 나머지는 다음 단계의 예정 경로다. 기존 content_exporter와 review_report는 서로 다른 결과를 생성하므로 양식 inventory 단계에서 별도 표본을 선정한다.

## XML adapter 실행 경계 — 2026-09-10

`xml_review_run.py`의 `extract_review_document`가 새 실행 폴더를 예약하고 기존 XML 추출기를 호출한다. 검증한 추출기 코드 hash를 고정하며 PDF·mapping·추출기 변경 여부를 실행 전후 확인한다. 기존 네 파일은 그대로 두고 `review_document.json`, `review_run.json`을 추가한다. 완료 기록이 없는 폴더는 검토용 완료 산출물이 아니다.

gate는 네 파일의 hash를 확인한 동일 바이트를 파싱한다. reader는 raw XML과 semantic XML을 구조 위치별로 대조하여 source role·속성·본문·fragment 좌표를 보존한다. `text`도 독립 노드이므로 문단 내 여러 text/figure를 원래 순서대로 유지한다. XML `attributes/attribute`는 `source:` 접두 속성으로 보존하고 본문으로 합치지 않는다. 보고서의 heading 근거는 `review:heading-evidence`에 저장하며 paragraph 후보를 확정 heading으로 바꾸지 않는다.

다국어는 검증된 경로/페이지 구간을 사용한다. 북마크 밖 공통 표지 텍스트는 `language=None`, `review:language-evidence=outside_audited_pages`로 보존한다. 반면 언어 페이지 안에서 경로가 맞지 않으면 변환을 중단한다. 단일 언어는 현재 확인된 XML `en`, `en-US`, `en-GB`, `ko`, `ko-KR` 또는 명시적 canonical code만 사용한다. 기대 언어를 근거로 언어를 채우지 않는다. report의 전역 language는 실제 페이지 언어로 간주하지 않는다.

현재 CLI는 추출 및 공통 데이터 생성까지만 수행한다. ReviewService·체크리스트 평가·사용자 화면은 후속 단계이며, 생성 성공을 checklist Pass라고 표시하지 않는다.

## DB와 연결 시 주의

ReviewDocument의 node_id/XML 위치는 실행 결과의 추적용이다. common_id/check_id에 합치지 않는다. checklist의 evidence_file은 과거 승인 근거이므로 감사에 보존하고, 새 PDF의 검출 근거는 실행 결과에서 별도로 관리한다.

한 common_id에서 영어 문단 하나와 프랑스어 문단 두 개가 대응할 수 있다. 이 관계는 검토용 alignment 자료에 `left_node_ids`, `right_node_ids` 배열로 표현하며 node나 DB 행을 강제로 동일 개수로 만들지 않는다. 원문 의미 동등성은 자동 번역으로 승인하지 않는다.
