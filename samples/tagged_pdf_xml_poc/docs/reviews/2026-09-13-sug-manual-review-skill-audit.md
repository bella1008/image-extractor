# sug-manual-review 스킬 검토 — 2026-09-13

검토 대상: `C:/Users/bella/.codex/skills/sug-manual-review/SKILL.md`와
`references/zc-mvp-review-rules.md`. 이 파일은 수정 제안이며 전역 스킬을 설치·변경하지 않았다.
현재 작업은 `samples/tagged_pdf_xml_poc`의 PDF → Raw XML → Semantic XML/Markdown 품질 검증이다.

## 수정이 필요한 항목

| 현재 지침 | 현재 작업에서의 문제 | 권장 변경 |
| --- | --- | --- |
| 설명과 Workflow가 ZC MVP, XLSX/JSON, `section_heading`, `lines_text` 중심 | 현재 XML 역할·경로와 Markdown 검증이 누락됨 | 시작 시 실제 추출 엔진과 검토 산출물을 확인하고 XML/legacy 절차를 분기 |
| `safety_symbol_table`, `navigation_ui`, `condition_label` 등의 이름을 필수로 열거 | 의미 관계를 보존한 현재 `table`/`figure`/list 구조도 잘못된 이름으로 판정할 수 있음 | 의미 보존 기준을 우선하고 현재 XML 역할에 대응. legacy 키는 해당 엔진에서만 사용 |
| ZC ENG/C-FRA workbook을 항상 첫 기준으로 제시 | FRA≠C-FRA, SPA≠M-SPA, POR≠B-POR. 언어·영어 변종·문서 범위 차이가 제목 차이로 나타남 | AGENTS/사용자가 정한 ZC 선행 gate를 준수한 뒤 가장 가까운 검증 완료 동일 언어 기준을 선택. 이번 추가 비교는 ZG ENG/FRA |
| 제목 수·블록 순서 비교만 명시 | 승격 장 제목 수, 전체 제목, 표지·본문 집계가 혼합될 수 있음 | 본문/표지/연락처/공통 제목별 하위 구조를 분리. 원본에 입증된 지역 전용 항목을 명시적 예외로 기록 |
| RTL 및 BOOK 페이지 역순 지침 없음 | 페이지 순서, 줄 내 읽기 순서, Unicode bidi 표시 문제를 혼동할 수 있음 | PDF 북마크와 RTL 페이지 순서를 확인하고 저장 문자열·논리 순서·최종 표시 화면을 각각 검사 |
| `manual review required`의 종료 조건 없음 | 원문과 같은 `EC/1999/5`도 막연한 의미/현지어 Warning으로 남을 수 있음 | 문제 위치, 근거, 확인 방법, 종료 조건을 기록. 원문 일치가 입증되면 추출 Warning 종료; 번역 품질 평가는 요청된 경우 별도 수행 |
| Auxiliary Sheets와 Excel `lines_text` 검사를 일반 절차로 연결 | 이번 작업에서 금지된 Excel/legacy 코드 수정을 유도할 수 있음 | XLSX를 요청하고 legacy exporter를 사용하는 경우에만 참조 문서 적용 |
| navigation의 `{btn_*}`와 과거 모델 예시 중심 | 현재 아이콘은 실제 XML Figure/Markdown placeholder이며 OCR 문자가 아님 | 실제 Figure·표 셀·UI 경로와 crop을 추적. placeholder만으로 이미지 형상 확인 완료를 주장하지 않음 |

## 유지할 규칙

- PDF/profile에서 source_token·doc_type·정확한 언어 코드 확인. 샘플 폴더명으로 추정하지 않는다.
- runtime 현지어 제목은 실제 추출 별칭만 사용. 번역·추측·후보/거절 별칭을 넣지 않는다.
- 제목 뒤 목록·표·모델 조건·안전 구조가 큰 body로 합쳐졌는지 검사한다.
- 원문 차이와 추출 결함을 분리하고 UI·안전 심볼·그림 범례를 우선 확인한다.
- 다른 바이어에 검증 없이 규칙을 확대하지 않는다.

## 권장 XML workflow 문안

1. 허용된 worktree, branch, HEAD, 미커밋 변경을 기록한다. AGENTS와 프로젝트 문서를 읽는다.
2. PDF 파일명/profile 및 실제 북마크에서 언어·문서 유형·BOOK 읽기 순서를 확인한다.
3. 현재 추출기를 수정 전에 새 결과 폴더로 실행한다. Raw XML, Semantic XML/MD,
   extraction_report와 현재 review bundle/review_run을 확인한다.
4. 프로젝트가 요구하는 ENG 선행 기준을 통과한 뒤 같은 바이어 현지어를 ENG에 대응시킨다.
   추가 바이어 비교는 동일 언어 코드를 사용한다. 사용자 확인 영어 변종은 비교 맥락으로 기록한다.
   같은 언어가 없는 기준 PDF는 대체하지 말고 미비교 범위를 밝힌다.
5. 원 PDF와 XML source path/page/MCID를 연결하여 읽기 순서, 제목별 구조,
   표의 행·열·그림 셀, 모델 조건, UI, 표지·연락처의 source_header/국가 행을 검토한다.
6. XML/MD 문자 보존과 순서를 확인한다. 문자 multiset은 누락·중복 보조 검사이며
   순서/표시 검사의 대체물이 아니다. 수치 소수점·단위·괄호·인치 표시도 확인한다.
7. RTL은 물리 페이지와 논리 읽기 순서를 분리한다. 최종 표시를 시험하지 않고
   문자/MCID 일치만으로 시각적 일치를 승인하지 않는다. 재조판 줄바꿈의 픽셀 일치는 요구하지 않는다.
8. Hard gate는 실제 구조·누락·순서 결함에 적용한다. Warning에는 정확한 위치와
   확인 기준을 넣는다. 원문에 있는 표현 차이는 추출 결함으로 계속 남기지 않는다.
9. 결함은 실제 XML 경로에서 실패 테스트 → 최소 범위 수정 → 새 폴더 재추출 → 재검증한다.
   legacy GridCell/import 구조를 XML 수정 위치로 강제하지 않는다. 필요한 호환 검사는 유지한다.
10. 테스트·회귀·compileall 결과, 남은 제한, 근거 경로와 로컬 복구 commit을 기록한다.
    추출 검증에서 체크리스트 후보/DB 승인/외부 의미 API 작업을 자동으로 시작하지 않는다.

## 스킬 적용 전 점검 사례

- AFRICA BOOK ENG/FRA/SPA/POR/ARA: ZG에는 ENG/FRA만 대응, ARA는 p36→27.
- LATIN/ZX M-SPA: AFRICA SPA의 동일 언어 기준으로 자동 사용하지 않는다.
- ZC C-FRA legacy XLSX 검토: 기존 `lines_text`/보조 시트 지침이 여전히 유효하다.
- XML 안전 심볼 표: `table` + `figure` 셀 근거가 있으면 기존 block_type 이름을 강요하지 않는다.
- ENG 22 / FRA 21: 원본 Jordan-only와 공통 21개 제목별 구조를 확인하며 수를 억지로 맞추지 않는다.
- Arabic `EC/1999/5`: 실제 glyph/PDF 일치로 추출 표기 Warning을 종료한다.
- Arabic 괄호·인치: 원문 crop과 실제 렌더링을 보고 판단하며, 단순히 “아랍어를 모름”으로 보류하지 않는다.

이 제안은 문서 검토 결과다. 스킬 변경/배포 테스트를 수행했다는 뜻은 아니다.

## 사용자 누락 지적에서 추가할 검증 규칙

- XML과 MD 파일의 존재, 알파벳 multiset 또는 일부 RTL span 검사만으로 완료 처리하지 않는다.
  실제 Markdown renderer의 전체 DOM 텍스트를 숫자·별표·문장부호까지 포함해 source 순서와 비교한다.
  목록의 source marker, 생성한 표 행/열 표식, 이미지 placeholder는 변환 정책을 명시한다.
- PDF crop에 포함된 검토 대상 행과 Markdown의 선택 범위를 맞춘다. 그림의 오른쪽에 원문을
  직접 입력하지 않는다. 실제 MD DOM에서 source XML 전체 문단과 일치하는 요소를 가져오고
  source path/MCID와 선택 범위를 기록한다. 다른 문단을 부분적으로 잘라 오해를 만드는 crop을 피한다.
- RTL 문장의 영문 끝말·규제 코드 뒤 마침표, 분리 RLM과 슬래시, 모델 wildcard를 확인한다.
  단독 마침표 규칙이 분리 소수점에 적용되지 않는지, 슬래시 규칙이 URL을 손상하지 않는지도 시험한다.
- 원문 `EC/1999/5`가 같더라도 문장부호 위치와 최종 renderer의 문단 방향을 별도로 확인한다.
  비교 그림에서 설정한 RTL 방향과 일반 MD 뷰어의 기본 방향을 구별해 안내한다.
- 독립 PDF 숫자/기호 감사에서는 페이지 쪽번호 등 제외한 artifact의 위치와 이유를 기록한다.
  ASCII 기호 검사만으로 모든 아랍어 문자나 의미까지 검증했다고 주장하지 않는다.

## 전체 ENG–ARA 검토에서 추가할 규칙

- 제목/표/목록 개수가 같고 문자 multiset이 같아도 단어 조각의 순서가 틀릴 수 있다.
  같은 MCID가 미세한 baseline reset으로 분리된 줄, ActualText 결합 부호의 별도 run을 확인한다.
  복원은 같은 줄의 연속 좌표와 결합 부호의 자음 anchor까지 증명해야 한다. 문자 Counter만으로
  부호의 소속을 승인하지 않는다. 광범위한 RTL/언어 공통 규칙으로 확장하지 않는다.
- 의미 전체 검토를 요청받으면 겹치지 않는 원문 단위를 대응시키고 각 판정과 원본 위치를 남긴다.
  구조 수치 일치를 의미 동등성으로 바꾸어 보고하지 않는다. 부정/조건/방향/위치/수치 소속을 읽는다.
- 원문 의미 차이는 추출 Hard gate와 분리하되 삭제하지 않는다. AFRICA의 ENG vertically 대
  ARA أفقيًا(가로로)처럼 원문 작성자에게 판단을 요청할 구체적 차이를 한국어 설명·crop으로 남긴다.
- HTML 글꼴/굵기 문제는 PDF의 실제 font name·size와 DOM computed font-weight를 각각 측정한다.
  MD–HTML 문자/구조 동일성은 원본 PDF의 추출 정확성이나 모든 글꼴 강조의 재현을 보증하지 않는다.
- 아이콘 포함 문단의 문장 줄바꿈도 확인한다. 검증된 inline icon 앞뒤의 텍스트 구간만 검사하고,
  알 수 없는 그림을 가로질러 문장을 추측하지 않는다. XML offset과 MD `<br>`을 함께 검증한다.
