# 실제 체크리스트 연결 시험 — ZC 영어

## 이번 단계의 의미

새 XML 데이터와 기존 기준 문구를 실제로 연결해 **어디에서 무엇을 찾았는지** 기록했다.
파일은 `outputs/checklist_observation_zc_20260911_r2/observation.json`이다.
이 결과는 사람의 검토를 위한 시험 관찰이며, 운영 합격/불합격 결과가 아니다.
기존 DB와 v2 초안의 값·승인·이관 상태는 수정하지 않았다.

대상 PDF: `BN68-25100B-00_SUG_Y26 TV ALL_ZC_L02_260122.0.pdf`.
문서 프로필 ZC_L02/A2, 이번 관찰 언어 ENG. C-FRA나 다른 바이어로 자동 확대하지 않는다.
검증 완료된 기존 XML bundle을 다시 읽었으며 재추출하거나 Markdown을 입력으로 사용하지 않았다.

## 결과 숫자를 읽는 방법

547개 DB 규칙을 모두 결과에 남겼다. 기존 규칙과 같은 적용 범위 판단을 사용했다.

| 구분 | 개수 | 의미 |
|---|---:|---|
| 이번 ZC 영어 적용 대상 | 59 | 전부 `needs_review`, 이관 상태 `pending` 유지 |
| 이번 문서/언어 적용 대상 아님 | 486 | 언어·scope/exclude_scope·doc_type 기준 |
| 기존 review/deprecated | 2 | 보존하되 실행 제외 |

59개를 더 나누면 다음과 같다.

| 관찰 | 개수 | 주의 |
|---|---:|---|
| 선택한 위치에서 문구 근거 발견 | 28 | 자동 합격 아님 |
| 선택한 단위에서 문구 전체 일치 없음 | 9 | PDF에 문구가 없다는 판정 아님 |
| 아직 지원하지 않는 구조 | 21 | 표·표지·법규·모델 등 별도 선택 규칙 필요 |
| 제목 범위를 못 찾음 | 1 | COVER-002의 `cover`는 실제 제목 문자열이 아니라 기존 업무 영역명 |

`decision_status=not_evaluated`는 최종 업무 판정을 하지 않았다는 뜻이다.
`evidence_found`와 `not_found_in_selected_units`는 시험 관찰값이고 Pass/Fail이 아니다.

## 실제 연결 예시

`SAFETY-007-ZC-ENG`의 기준 문구는 다음과 같다.

> Do not mount the TV at more than a 15 degree tilt.

관찰 결과는 PDF 1쪽의 `Mounting the TV on a wall` 제목 범위 아래,
`xml:0/0/1/16/6/1` 목록 본문에서 같은 문구를 찾았다.
결과에는 원문 공백을 유지한 실제 문구, 제목 근거, 페이지, XML 위치, MCID와 좌표 근거가 함께 남는다.
이 제목은 XML reader가 `source_role_candidate`로 기록한 항목이다.
후보라는 사실을 유지하며 확정 제목이나 승인된 업무 역할로 승격하지 않았다.

`CHK-001-ZC-ENG`는 ` 01 Package Content`라는 실제 제목 자체를 찾았고,
`ISEC-006-ZC-ENG`는 `Internet security` 범위의 목록 본문 `xml:0/0/1/45/0/2/0/1`에서
무선 공유기 관리 암호 관련 기준 문구를 찾았다. 각 규칙마다 범위와 근거를 별도로 남긴다.

## 미일치 9개에서 확인한 연결 차이

다음은 저장된 XML/ReviewDocument와 선택·제외 단위를 대조한 결과다.
원본 PDF의 시각 검수나 의미 동등성 승인을 새로 수행했다는 의미는 아니다.

| 규칙 | 현재 구조에서 확인한 차이 | 다음 연결 작업 |
|---|---|---|
| ISEC-002 | DB 한 행이 XML의 연속 문단 43·44로 나뉨 | 근거 있는 연속 문단 묶음 선택 |
| ISEC-003/004/005 | 관련 문구가 `xml:0/0/1/45/0/1` 목록 본문에 있고 경로/아이콘도 포함 | 아이콘 근거와 문구 검사 구간을 분리해 검증 |
| SAFETY-008 | DB 문구 일부가 표 내부 `xml:0/0/1/17/0/0/1/0`에 있음 | 표를 무시하지 않는 전용 선택과 복수 근거 검증 |
| SAFETY-010/023/025 | `– `가 같은 목록 항목의 별도 label에 보존되어 있음 | 같은 항목의 label+본문을 명시적으로 연결; 기호를 삭제하지 않음 |
| SAFETY-020 | DB는 bullet, XML에서는 `xml:0/0/1/27` 일반 문단 | 현 구조/검토 목적에 맞는 업무 역할 대응 검증 |

즉, 이 결과를 보고 DB 문구를 새 XML 문자열로 덮어쓰거나, 원래 승인된 기준을 삭제하면 안 된다.
구방식의 block_type을 새 XML의 필수 역할로 강요하지도 않는다.
구조 대응은 아직 잠정적이고, 위 차이들이 그 대응을 구체화하는 근거다.

## 현재 검색 범위와 안전 조건

- 지원하는 잠정 선택: 제목 자체, 표 밖의 일반 문단, 목록 항목 아래의 목록 본문.
- 제목은 기존 reader의 `review:heading-evidence`와 원문/XML 경로/source role을 대조해 선택한다.
- 제목 전체가 한 안전한 단위여야 한다. 중첩 문단·표·미지 구조가 있으면 제목 범위로 사용하지 않는다.
- 제목이 중복되거나 불확실하면 전체 문서 검색으로 우회하지 않는다.
- 범위는 다음 관찰 제목, 현재 section 끝, 언어 경계 중 가장 먼저 오는 위치에서 끝난다.
  하위 제목의 내용까지 모두 검사했다는 뜻이 아니며 이번 시험에서는 보수적으로 제한했다.
- 단위끼리 이어 붙이지 않는다. 그림/아이콘, 언어·근거 불확실성은 제외 사유와 원문을 함께 기록한다.
- 비교용으로 공백만 정리한다. 대소문자·구두점·하이픈·비ASCII 문자를 제거하거나 번역하지 않는다.
- `source_reference_token`은 출처 기록일 뿐 검사 대상 제한으로 쓰지 않는다.

원본 승인 상태와 새 구조의 검증 상태는 별개다. 이 시험에서 발견한 근거만으로 `verified`나 `approved`로 변경하지 않는다.

## 실행 방법

```powershell
Set-Location C:\Users\bella\image-extractor\.worktrees\xml-review-v2
$env:PYTHONPATH = (Resolve-Path samples/tagged_pdf_xml_poc/src).Path
python -m scripts.run_checklist_observation --bundle outputs/xml_review_v2_zc_20260910 --pdf "samples/SUG_RAW/TV_ZC/BN68-25100B-00_SUG_Y26 TV ALL_ZC_L02_260122.0.pdf" --output outputs/checklist_observation_NEW/observation.json
```

기본 DB 입력은 `metadata/checklist_v2/drafts/20260911/`의 동결 초안이다.
JSON hash, 연결된 Excel hash와 547행의 실제 Excel 값을 비교한 뒤 읽는다.
이 파일을 편집해 바로 시험에 넣는 것은 허용하지 않는다. 새 기준본이 필요하면 별도 이관/검증 절차를 따른다.
XML 완료 기록이 없거나 입력 hash가 변하면 중단한다. 기존 결과 파일은 덮어쓰지 않는다.

## 검증과 복구

- 루트 230 passed, 6 subtests passed. 신규 35개 포함. 집중 검증 69개 통과.
- compileall src/tests/scripts 통과. 별도 XML POC 전체 suite를 재실행한 것은 아니다.
- 547개 원본 규칙의 값·ID·순서·승인 상태가 결과에 그대로 남는지 독립 대조했다.
- 동결된 구 `metadata_matches`와 547개 적용 대상 판단이 전부 같았다.
- 발견한 28개 근거의 원문·언어·페이지/XML 근거를 저장된 ReviewDocument의 원문 조각과 직접 대조했다.
- 별도 리뷰가 찾은 중첩 제목 범위 문제를 실패 테스트로 재현하고 수정했다. 빈 미지 구조/표/문단도 거절한다.
  재검토에서 미해결 중요 지적은 없었다. 수정 후 실물 결과를 재생성했고 독립 대조한 결과와 바이트 동일했다.

작업 전 기준 커밋: `8fe734fd36815276c1e1b6954a46513cb144f96e`.
작업은 별도 `codex/xml-review-v2`에만 보존하며 메인/기존 DB/기존 추출기에는 합치지 않는다.

다음 단계는 위 9개 연결 차이를 다루는 좁은 규칙부터 테스트하는 것이다.
표/표지/모델/다국어 지원과 최종 사용자 결과 Excel은 그 다음 검증 단계다.
