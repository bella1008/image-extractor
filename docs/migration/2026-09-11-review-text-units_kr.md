# XML 검토 단위 연결과 source_token 설명

## 두 source token의 차이

PDF 파일명이 아래와 같다고 하자.

```text
BN68-25100B-00_SUG_Y26 TV ALL_ZC_L02_260122.0.pdf
```

프로그램은 파일명에서 바이어/지역 부분 `ZC`와 언어 구성 토큰 `L02`를 읽고
`source_token=ZC_L02`를 만든다. 본문이나 XML에서 새로 추출하는 문구가 아니다.
`metadata/pdf_profile_mapping/pdf_profile_mapping.json`에서 이 키를 찾으면
대표 지역 ZC, 문서 형식 A2, 기대 언어 ENG/C-FRA를 알 수 있다.
`L02`만으로 프랑스어라고 단정하는 것이 아니라, **전체 키로 확인한 매핑**을 사용한다.
실제 텍스트의 언어 배정은 별도로 검증한 XML 구조/언어 구간을 따른다.

- 문서의 `source_token`: **지금 검사하는 PDF는 어떤 프로필인가?**
- DB의 `source_reference_token`: **이 기준 문구의 후보를 어디서 가져왔는가?**

예를 들어 ZC 자료에서 가져온 영어 문구가 다른 바이어에도 적용될 수 있다.
이때 DB 출처가 ZC라고 해서 다른 바이어를 검사 대상에서 빼지 않는다.
적용 범위는 scope/exclude_scope·언어·문서 형식으로 판단한다. 직접 작성한 기준은 출처가 비어 있어도 된다.

`source_token`은 고유 PDF ID가 아니다. 연도나 개정판이 달라도 ZC_L02일 수 있다.
파일 식별에는 매뉴얼 코드, 파일명 날짜/버전과 실제 파일 hash를 함께 사용한다.

## 이번에 연결한 부분

```text
검증된 PDF→XML 실행 결과
    → 기존 gate + XML adapter
    → ReviewDocument
    → 새 검토 단위 목록(JSON, 아직 판정하지 않음)
```

이번 작업은 DB 규칙에 맞는 문단을 고르기 위한 **구조적 준비**다.
어떤 문단이 어느 체크리스트 요구사항에 해당하는지 확정한 단계는 아니다.
원본 XML/MD, ReviewDocument, DB 승인/이관 상태를 바꾸지 않았다.

`paragraph` 태그 안에 표나 하위 구역이 있는 실제 사례가 있으므로 태그 한 개를 통째로 검색하지 않는다.
앞 문장 → 표의 첫 셀 → 둘째 셀 → 뒤 문장은 각각 다른 검사 단위로 남긴다.
한 문단의 정상적인 인라인 글자 조각은 원래 순서로 이어서 보존하되, 다른 문단·목록 본문·셀을 넘어가지 않는다.

각 단위는 다음 정보를 담는다.

- 원래 노드 ID와 상위 구조 ID들: 어느 문단·목록·표 행·셀에서 나왔는지 추적.
- 각 원문 조각의 노드 ID와 위치, 정확한 글자, 언어, 페이지/XML 근거.
- 동일 노드에서 표 앞/뒤가 나뉘는 경우 구분할 segment_index.
- 아이콘, 미배정/혼합 언어, 지원하지 않는 구조, 근거 누락 등의 확인 필요 사유.

`ready_for_text_match=true`는 **텍스트를 비교할 구조적 사전 조건을 갖췄다**는 뜻이다.
업무 역할·제목 범위·DB 규칙과의 대응이 맞다는 뜻이나 최종 합격이 아니다.
모든 출력은 `decision_status=not_evaluated`로 기록한다.

## 실제 검증 결과

기존 완료 기록이 있는 ZC, XU, ZG XML bundle을 다시 검증하여 연결했다. PDF 재추출은 하지 않았다.

| 자료 | 검사 단위 | 보존한 원문 조각 | 텍스트 사전 조건 충족 | 별도 확인 |
|---|---:|---:|---:|---:|
| ZC ENG/C-FRA | 724 | 1,938 | 428 | 296 |
| XU ENG | 476 | 1,168 | 296 | 180 |
| ZG BOOK 5언어 | 2,449 | 6,696 | 1,583 | 866 |

별도 확인 숫자는 불합격 수나 추출 오류 수가 아니다. 목록 번호·기호만 있는 조각도 분리해서 남기고,
아이콘이 포함된 구간은 텍스트 검사만으로 판단하지 않으므로 여기에 포함된다.
무시하거나 삭제한 조각은 없다. 표/목록 구조 자체는 ReviewDocument에 그대로 남아 있다.

독립 검증에서 각 원문 조각의 ID·위치·글자·언어·근거와 전체 순서를 모두 대조했다.
세 자료 모두 누락/중복/변경이 없었고, 한 단위에 여러 표 행이나 셀이 섞이지 않았다.
ZC 예시 heading은 원문 공백까지 포함한 ` 01 Package Content`이며 번역·정규화하지 않았다.
숫자 제목 아닌 후보 heading은 임의로 승격하지 않았고, 기존 reader의 근거 속성에 남아 있다.

테스트: 신규 26개 포함 루트 **195 passed, 6 subtests passed**.
인라인/중첩 구조, 미배정·혼합 언어, 아이콘, 알 수 없는 구조, 텍스트 근거 누락,
1,100단계 중첩, 완료 기록 없음, XML 변경, 연결 도중 입력 변경을 확인했다.
`compileall src tests scripts` 및 diff 검사를 통과했다. 별도 POC 전체 suite나 PDF 시각 검수를 다시 수행한 것은 아니다.

## 실행 방법

결과: 이 worktree의 `outputs/review_text_units_20260911_r2/zc.json`, `xu.json`, `zg.json`.
이 폴더는 생성 산출물이므로 Git에 포함하지 않는다. 코드는 재실행 가능하게 보존한다.

PowerShell에서 다음처럼 실행한다. 출력 파일은 기존 파일과 다른 이름을 쓴다.

```powershell
Set-Location C:\Users\bella\image-extractor\.worktrees\xml-review-v2
$env:PYTHONPATH = (Resolve-Path samples/tagged_pdf_xml_poc/src).Path
python -m scripts.audit_review_text_units --bundle outputs/xml_review_v2_zc_20260910 --pdf "samples/SUG_RAW/TV_ZC/BN68-25100B-00_SUG_Y26 TV ALL_ZC_L02_260122.0.pdf" --output outputs/review_text_units_NEW/zc.json
```

`review_run.json` 완료 기록이 없거나 PDF/매핑/XML 산출물 hash가 다르면 중단하며 출력하지 않는다.
순수 `build_text_unit_index()` 함수 자체는 gate가 아니다. 앱에서 사용할 때에는 검증된 bundle reader를 앞에 두어야 한다.

## 다음 단계

ZC ENG의 제한된 규칙부터 제목/언어/문서 범위를 근거로 선택하고, 필수 문구와의 정확 비교·정규화 정책을 시험한다.
현재 `legacy_section_heading`과 `legacy_block_type`을 무시한 광역 검색은 하지 않는다.
미지원 제약은 검토 미완료로 표시하며, 검증이 끝나기 전에는 approved 545행의 migration_status를 변경하지 않는다.
표 헤더/연락처 행, 모델 조건, 다국어 문단 묶음은 각각 근거를 확인한 별도 선택 규칙이 필요하다.

이번 작업 전 복구 기준은 `51049e56fd5216fdd97f5c14a80e535e714ea5c6`이다.
현재 작업을 hard reset하지 말고 필요하면 해당 커밋의 별도 worktree를 만든다.

별도 리뷰에서 제목 내부의 중첩 list_body를 인라인으로 오인하는 문제를 발견했다.
list_body/span/label 세 경로의 실패 테스트로 재현한 뒤, 제목의 직접 자식에만 예외를 허용하도록 수정했다.
검토자는 수정 후 관련 테스트 56개 통과를 재확인했고, 미해결 Critical/Important 지적은 없다.
수정 후 세 실물 산출물을 재생성했으며, 독립 대조한 최초 산출물과 바이트까지 동일하다.
메인 DB의 원본 Excel/JSON hash도 다시 확인했고 변경되지 않았다.
