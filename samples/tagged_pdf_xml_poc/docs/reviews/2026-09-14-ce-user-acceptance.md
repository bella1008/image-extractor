# CE 후속 설명과 사용자 판정 — 2026-09-14

시작 worktree `C:/Users/bella/image-extractor/.worktrees/xml-markdown-review`,
브랜치 `feature/xml-markdown-review`, HEAD `41be8e0d2ed4611674b9e578a199963488364be9`, 미커밋 변경 없음.
이번에는 추출 코드를 바꾸거나 재추출하지 않았다. 사용자 판정·설명·향후 평가 사례를 기록했다.

## 테스트 용어의 정확한 의미

- 전체 1,948 passed / 1 skipped는 앞선 추출 코드 검증 실행 결과다. 이번 문서 변경 뒤 재실행했다고
  주장하지 않는다. Skip은 `test_preflight_rejects_non_regular_required_targets_before_staging[symlink]`다.
  출력 대상 `raw_structure.xml`이 다른 파일을 가리키는 symbolic link일 때 저장을 거부하고 기존
  파일을 보존하는 테스트다. 이 환경에서 테스트 준비용 링크를 생성하지 못해 건너뛰었다.
  일반 디렉터리 거부 경우 등 다른 저장 검사는 실행됐다. PDF 문장이나 언어 검토를 건너뛴 것이 아니다.
- CE 집중 33은 CE 변경에 대한 자동 테스트 경우 33개다. 작은 재현 데이터 14개와 실제 CE PDF
  추출 결과 검사 19개로 구성된다. 언어 5개를 각각 검사하는 항목은 각기 한 테스트로 센다.
  대표 항목은 표지/본문 언어, 연락처 언어, 주파수, 문장 줄바꿈, 추가 소제목, 문자/ID 보존,
  다른 프로필에 적용되지 않는지와 불충분한 원본 근거를 거부하는지다. 33개 문장을 의미 검토했다는 뜻이 아니다.
- 회귀 검사는 공용 reader/writer/use case 수정이 기존 동작을 깨뜨리지 않았는지 보는 것이다.
  실제 ZC/ZG/AFRICA 샘플을 추출하는 자동 테스트와 고정 기대 결과 검사를 실행했다.
  예: ZG 모든 페이지/장 제목/선언서/소제목/표시 규칙, ZC 태그 구조와 모델 문자,
  AFRICA RTL 읽기 순서와 기존 숫자·문장·안전 라벨 수정. 모든 바이어의 모든 문장을 사람이
  처음부터 번역 재검토했다는 뜻은 아니다. `test_layout_regression.py`의 실제 ZG fixture도 확인했다.
- public import 3항목은 기존 프로그램이 부르는 함수 이름/경로가 그대로 사용 가능한지 확인한 것이다.
  `src.content_poc.run_content_poc`, `write_content_poc_outputs`, `write_content_review_xlsx`를
  import하고 callable인지 확인했다. 이는 함수 호출 입구의 호환 검사이며 각 함수의 전체 동작,
  Excel 결과, 문장 의미를 검증한 것은 아니다. XML 추출의 핵심 검증은 별도의 실제 추출/회귀 검사다.

## 제목 비교

CE ENG 23개는 CE 내부 현지어 비교의 공통 제목 집계이며 ZG ENG 전체 제목 수와 같다는 뜻이 아니다.
동일 기준에서 ZG ENG는 26개이고 CE의 23개가 같은 문구·순서로 포함된다.

| ZG에만 있는 제목 | PDF 페이지 | 실제 의미 |
|---|---:|---|
| Changing the TV’s password | 7 | 비밀번호 변경 |
| Declaration of Conformity | 9 | Smart Control VG-TM2660 선언서 |
| Declaration of Conformity | 10 | Smart Control VG-TM2280 선언서 |

두 선언서는 제목만 같고 모델이 다른 실제 문서다. 중복 추출이 아니다. CE 원장에는 해당 블록이 없으므로
추출 누락으로 간주하지 않는다. CE RUS/KAZ의 대기 모드 소제목처럼 공통 제목 외 항목은 따로 센다.
전체 문자열/페이지 비교는 [사례 JSON](../../../../docs/review_agent_cases/ce_l05_translation_editorial_cases.json)에 있다.

## 사용자 처리와 미래 에이전트용 사례

CE-SOURCE-01~06을 모두 **원장과 동일한 추출이므로 PASS**로 기록했다.
01은 번역사가 제공한 의미가 그대로 반영됐다는 사용자 의견을 추가했다.
02의 접지 문구, 03/04의 설치 행동 차이, 05의 규격 명칭, 06의 UI 용어는 미래 검토 예시다.
06의 TRAMS KYR 용어 존재는 사용자 제보로 보존했고, 정확한 용어/버전/제품 범위는 아직 조회하지 않았다.

[사례집](../../../../docs/review_agent_cases/README.md)에는 기대 보고 내용과 원문 18개를 Git 파일로 저장했다.
원문 문장 18개 모두 최종 Semantic XML과 정확히 일치함을 확인했다. 숫자 표기만으로 오류를 만들지
않아야 하는 음성 대조군도 추가했다. 향후 제작 시 회귀 평가에 사용하며, 지금 에이전트를 구현한 것은 아니다.
추출 PASS를 번역 정확성 승인으로 해석하지 않고, 원문을 자동 교정하지 않도록 요구사항을 남겼다.

몽골 공식 맞춤법 자료 §64에는 로마 숫자의 순서 표시 사용 규칙이 있다. 몽골에서 로마 숫자를
사용하지 않거나 이해하지 못해서 1/2로 바꿨다고 추정할 수 없다. 이번 번역자의 표기 선택 이유는 미확인이다.
[공식 맞춤법](https://toli.gov.mn/r)

Samsung 몽골어 공식 제품 페이지는 `VESA бэхэлгээ`를 쓴다. 같은 CE PDF MON 인접 문장도 VESA다.
이 문맥의 VERSA는 몽골식 표기가 아닌 오타로 판단한다. 추출문은 PDF대로 유지한다.
[Samsung 몽골어 제품 사양](https://www.samsung.com/mn/business/smart-signage/video-wall/vmt-lh46vmtubgbxci/)

## 산출물과 검증

기존 출력은 보존했다. 새 판정 화면/JSON:
`C:/Users/bella/image-extractor/.worktrees/xml-markdown-review/samples/tagged_pdf_xml_poc/outputs/xml_review_ce_20260914_user_acceptance`.

[사용자 PASS와 미래 사례 화면](../../outputs/xml_review_ce_20260914_user_acceptance/source_findings.html).
이 화면은 원래 추출 HTML로 연결되며, 6건의 최신 추출 PASS와 미래 편집 검토 기대를 함께 보여준다.
원래 extraction bundle의 6개 파일 hash를 재검증했다. Semantic XML/Markdown은 동일하다.
이번 검증은 사례 JSON/원문 일치, 상태 분리, 링크/이미지, Git diff 검사이며 추출 코드 테스트 재실행은 불필요하다.
체크리스트 DB, runtime heading mapping, 다른 worktree를 변경하지 않았다.
