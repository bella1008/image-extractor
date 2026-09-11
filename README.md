# PDF Manual Auto Review System

전자 제품 매뉴얼 PDF를 자동으로 검토하기 위한 내부 도구 기획 문서입니다.  
이 문서는 개발자뿐 아니라 실제 검토 업무를 수행하는 비개발자도 전체 흐름을 이해할 수 있도록 작성되었습니다.

## XML review v2 작업 안내 — 2026-09-10

현재 브랜치 `codex/xml-review-v2`는 XML 추출기 `8405120`에서 시작한 통합 작업장이다.
아래의 오래된 MVP 설명은 이력이며, 새 v2의 설계와 진행 상태는 다음 문서를 따른다.

- [복구 커밋과 백업 사용 방법](docs/migration/2026-09-10-recovery_kr.md)
- [승인된 마이그레이션 방향](docs/superpowers/specs/2026-09-10-xml-review-v2-design_kr.md)
- [ReviewDocument 구조](docs/architecture/xml-review-v2-architecture_kr.md)
- [첫 단계 구현 계획](docs/superpowers/plans/2026-09-10-review-document-foundation.md)
- [현재 진행 상태](TODO.md)

공통 데이터 모델과 XML adapter·품질 gate·새 추출 실행 경로를 구현했다. 아직 DB v2·Excel·Streamlit 전환은 제공하지 않는다.
기존 Markdown은 XML POC의 writer로 계속 생성한다. 새 실행 경로는 기존 네 파일에 `review_document.json`과 완료 기록 `review_run.json`을 추가한다.
실행 방법과 실물 검증 결과: [XML adapter 사용 안내](docs/migration/2026-09-10-xml-adapter-validation_kr.md).

2026-09-11: 기존 checklist 547행을 대조하고, 원본과 별개인 **자동 검토 미연결 DB 초안**을 만들었다.
출처 열은 `source_reference_token`으로 보존하며 적용 제한으로 사용하지 않는다.
[DB 이관 초안·검증 결과·다음 단계](docs/migration/2026-09-11-checklist-draft-validation_kr.md)를 읽는다.

이어 ReviewDocument의 원문을 문단/표/목록 경계별 검토 단위로 연결했다. 아직 체크리스트 판정은 하지 않는다.
[source_token 설명과 검토 단위 실행 안내](docs/migration/2026-09-11-review-text-units_kr.md).

ZC ENG의 동결 DB를 연결한 [체크리스트 관찰 파일럿](docs/migration/2026-09-11-checklist-observation-pilot_kr.md)도 제공한다.
근거를 찾거나 미지원 사유를 기록할 뿐, 운영 합격/불합격이나 이관 승인을 부여하지 않는다.

문단·목록·아이콘 주변의 구조 근거 연결과 `ReviewService`의 **PDF→관찰 JSON→로컬 HTML** 실행도 제공한다.
[실행 환경·결과·사용 방법](docs/migration/2026-09-11-structured-evidence-and-service_kr.md),
[기존 Excel 조사와 새 양식 계약 초안](docs/migration/2026-09-11-excel-contract-inventory_kr.md).
Excel은 양식 검수용 초안이며, 배포용 Excel writer/Streamlit 및 자동 업무 판정은 아직 전환하지 않았다.

CHK-002 구성품을 14개 하위 항목으로 관리하는 별도 작성용 원장과 Excel→JSON 내보내기를 제공한다.
[항목별 원장과 편집 범위](docs/migration/2026-09-11-item-master_kr.md)를 참고한다.
전체 547행 DB를 교체하거나 모델별 적용 조건을 자동 승인하는 작업은 아니다.

이 원장을 **현재 검토 대상 XML에서 다시 검색하는 항목별 실행 경로**도 연결했다.
14개 구성품별 JSON/로컬 HTML을 만들고, 원장 작성 당시 출처와 현재 문서의 근거를 분리한다.
[항목별 실행 명령·결과 읽는 방법·지원 범위](docs/migration/2026-09-11-item-observation-service_kr.md).
문구 발견은 합격 판정이 아니며, 모델 적용은 계속 미확정이다.

## 1. 프로젝트 목적

이 시스템의 목적은 신규 매뉴얼 PDF가 기존 기준과 이전 버전에 비해 올바르게 작성되었는지 자동으로 검토하고, 검토자가 확인할 수 있는 결과 리포트를 제공하는 것입니다.

주요 검토 대상은 다음과 같습니다.

- 안전 주의사항 문구
- 언어별 필수 문구
- 바이어/국가별 필수 문구
- 모델코드별 사양값
- 규격 관련 이미지 또는 아이콘
- 이전 PDF 대비 변경사항

최종 목표는 사람이 반복적으로 확인하던 검토 업무를 줄이고, 누락 가능성을 낮추며, 검토 근거를 리포트로 남기는 것입니다.

## 2. 기본 입력값

사용자는 검토를 시작할 때 다음 정보를 입력합니다.

- 검토할 신규 PDF
- 이전 버전 PDF
- 제품 모델코드
- 바이어 또는 판매 국가
- 검토 옵션

검토 옵션은 체크박스로 선택할 수 있도록 설계합니다.

- 필수 문구 검토
- 모델 사양값 검토
- 이미지/아이콘 검토
- 이전 버전과 비교
- 전체 검토

## 3. 전체 워크플로우

```text
사용자 입력
  |
  |-- 신규 PDF 업로드
  |-- 이전 버전 PDF 업로드
  |-- 모델코드 입력
  |-- 바이어/국가 선택
  |-- 검토 옵션 선택
  v

PDF 분석
  |
  |-- 페이지 구조 분석
  |-- 텍스트 추출
  |-- 언어 영역 분리
  |-- 이미지/아이콘 추출
  v

검토 실행
  |
  |-- 체크리스트 DB 기준 필수 문구 검토
  |-- 모델코드 기준 사양값 검토
  |-- 국가/바이어별 이미지 및 아이콘 검토
  |-- 신규 PDF와 이전 PDF 비교
  v

결과 정리
  |
  |-- Pass/Fail 판단
  |-- 수동 확인 필요 항목 분류
  |-- 변경사항 요약
  |-- 실행 로그 저장
  v

결과 리포트 제공
```

## 4. 권장 시스템 하이어라키

```text
PDF Manual Auto Review System
  |
  |-- User Interface
  |     |-- PDF 업로드 화면
  |     |-- 모델코드 입력 화면
  |     |-- 검토 옵션 선택 화면
  |     |-- 진행 로그 화면
  |     |-- 결과 리포트 화면
  |
  |-- Review Orchestrator
  |     |-- 전체 검토 흐름 제어
  |     |-- 선택된 검토 옵션에 따라 에이전트 실행
  |     |-- 결과 취합
  |
  |-- Agents
  |     |-- PDF Extraction Agent
  |     |-- Checklist Review Agent
  |     |-- Spec Validation Agent
  |     |-- Image/Icon Review Agent
  |     |-- Diff Review Agent
  |     |-- Report Generation Agent
  |
  |-- Domain Logic
  |     |-- 문서 구조 모델
  |     |-- 체크리스트 규칙
  |     |-- 검토 결과 모델
  |     |-- 사양값 비교 규칙
  |
  |-- Data Layer
  |     |-- 체크리스트 DB
  |     |-- 모델 사양값 조회 연동
  |     |-- 검토 이력 DB
  |     |-- 로그 저장소
  |
  |-- Report Output
        |-- HTML 리포트
        |-- Excel 리포트
        |-- PDF 리포트
```

## 5. 에이전트 역할

### 5.1 PDF Extraction Agent

PDF에서 검토에 필요한 원본 데이터를 추출합니다.

역할:

- PDF 페이지별 텍스트 추출
- A2, A3, book type 등 편집 타입 분석
- 언어 영역 분리
- 표, 스펙 영역, 주의사항 영역 추정
- 이미지와 아이콘 추출
- OCR 필요 여부 판단

가장 중요한 에이전트입니다. PDF에서 텍스트가 불안정하게 추출되면 이후 검토 결과도 신뢰하기 어렵습니다.

### 5.2 Checklist Review Agent

체크리스트 DB를 기준으로 필수 문구가 PDF에 적용되었는지 확인합니다.

역할:

- 바이어/국가별 필수 문구 확인
- 언어별 필수 문구 확인
- 제품군 또는 모델 조건별 문구 확인
- 누락 문구 탐지
- 유사하지만 다른 문구 탐지
- 금지 문구 탐지

### 5.3 Spec Validation Agent

모델코드를 기준으로 제품 사양값을 조회하고 PDF에 올바르게 반영되었는지 확인합니다.

역할:

- 모델코드로 사양값 조회
- 전압, 주파수, 크기, 무게, 용량 등 PDF 내 표기 확인
- 단위 변환 또는 표기 차이 처리
- 기준값과 PDF 값 비교

예를 들어 `220V`, `AC 220 V`, `220-240V~` 같은 표현을 같은 의미로 볼 수 있는지 규칙이 필요합니다.

### 5.4 Image/Icon Review Agent

국가, 바이어, 언어, 규격에 따라 필요한 이미지나 아이콘이 PDF에 포함되었는지 확인합니다.

역할:

- 필수 아이콘 존재 여부 확인
- 기준 이미지와 유사도 비교
- 특정 페이지 또는 언어 영역에 이미지가 있는지 확인
- 사람이 확인할 수 있도록 리포트에 이미지 캡처 제공

이미지 검토는 난이도가 높기 때문에 초기에는 완전 자동 판정보다 `자동 탐지 + 수동 확인` 방식이 현실적입니다.

### 5.5 Diff Review Agent

신규 PDF와 이전 버전 PDF를 비교합니다.

역할:

- 두 PDF의 추출 텍스트 비교
- 체크리스트에 포함된 의도된 변경사항 제외
- 나머지 변경사항 요약
- 페이지별, 언어별, 섹션별 변경점 정리

이 기능은 단순히 다른 글자를 찾는 것이 아니라, 검토자가 확인해야 할 의미 있는 변경사항을 줄여서 보여주는 것이 중요합니다.

### 5.6 Report Generation Agent

검토 결과를 사람이 읽기 쉬운 리포트로 정리합니다.

역할:

- 전체 Pass/Fail 요약
- 실패 항목 정리
- 수동 확인 필요 항목 정리
- 이전 버전 대비 변경사항 정리
- 페이지 번호, 언어, 검토 근거 표시
- HTML, Excel, PDF 리포트 생성

결과 리포트 제작용 에이전트는 추가하는 것이 좋습니다.  
검토 로직과 리포트 작성 로직을 분리해야 나중에 리포트 양식이 바뀌어도 검토 엔진을 수정하지 않아도 됩니다.

## 6. 체크리스트 DB에 들어가야 할 정보

체크리스트는 단순한 문구 목록이 아니라 검토 기준 데이터입니다.

권장 항목:

- 체크 ID
- 바이어/국가
- 언어
- 제품군
- 모델 조건
- 필수 문구
- 허용 가능한 유사 문구
- 반드시 포함되어야 하는 키워드
- 금지 문구
- 필수 이미지 또는 아이콘
- 적용 시작일
- 적용 종료일
- 근거 규격 또는 내부 문서 번호
- 중요도
- 검토 방식
- 예외 조건

중요도 예시:

- Critical: 법규, 안전, 인증 관련 필수 항목
- Major: 제품 사양, 모델 정보, 핵심 안내 문구
- Minor: 표현, 형식, 권장 문구

검토 방식 예시:

- 정확히 일치
- 일부 포함
- 유사도 비교
- 정규식 비교
- 수동 확인
## 7. 비개발자와 함께 사용하는 방향에 대한 의견

이 시스템은 비개발자와 함께 사용하는 프로그램으로 만드는 방향이 맞습니다.  
다만 중요한 전제는 있습니다.

비개발자가 직접 코드나 DB를 수정하는 구조는 피해야 합니다.

권장 운영 방식:

- 사용자는 웹 화면에서 PDF와 모델코드를 입력합니다.
- 체크리스트 담당자는 Excel 또는 관리 화면으로 검토 기준을 관리합니다.
- 시스템은 체크리스트를 DB로 변환하여 검토에 사용합니다.
- 검토자는 결과 리포트에서 실패 항목과 근거만 확인합니다.
- 개발자는 PDF 추출 규칙, 외부 시스템 연동, 검토 엔진을 관리합니다.

즉, 비개발자는 `검토 기준 입력`과 `결과 확인`에 집중하고, 개발자는 `자동화 로직`과 `시스템 안정성`을 책임지는 구조가 좋습니다.

## 8. 개발 시 주의해야 할 점

### 8.1 PDF 텍스트 추출이 가장 큰 위험 요소

PDF는 사람이 보는 순서와 실제 내부 텍스트 순서가 다를 수 있습니다.  
특히 다음 경우에는 추출 품질이 떨어질 수 있습니다.

- 다단 편집
- 여러 언어가 한 페이지에 섞인 PDF
- A2, A3 대형 문서
- book type 문서
- 표와 아이콘이 많은 문서
- 이미지로만 들어간 텍스트

따라서 개발 초기에 다양한 PDF 샘플을 모아 추출 품질을 먼저 검증해야 합니다.

### 8.2 처음부터 완전 자동화를 목표로 하면 위험함

초기 목표는 완전 자동 판정이 아니라 `자동 검토 + 사람이 확인할 근거 제공`이 되어야 합니다.

자동 판정이 어려운 항목은 `수동 확인 필요`로 분류하고, 리포트에 해당 페이지와 근거를 보여주는 방식이 현실적입니다.

### 8.3 체크리스트 DB를 너무 빨리 확정하면 안 됨

텍스트 추출 규칙이 안정되기 전에 DB 구조를 확정하면 나중에 수정 비용이 커집니다.  
초기에는 샘플 데이터를 기반으로 체크리스트 구조를 검증한 뒤 점진적으로 확장하는 것이 좋습니다.

## 9. 권장 MVP 범위

처음 버전은 작게 시작하는 것이 좋습니다.

MVP 권장 범위:

- 신규 PDF 1개 업로드
- 이전 버전 PDF 1개 업로드
- 모델코드 입력
- 언어 2~3개 우선 지원
- 체크리스트 20~50개 항목 우선 등록
- 필수 문구 존재 여부 검토
- 이전 버전과 텍스트 비교
- 실행 로그 표시
- HTML 또는 Excel 리포트 생성

MVP에서 안정성을 확인한 뒤 다음 기능을 추가합니다.

- 지원 언어 확대
- 바이어/국가 확대
- 모델 사양값 시스템 연동
- 이미지/아이콘 검토
- 리포트 양식 고도화
- 검토 이력 관리

## 10. 추천 기술 방향

운영 인원이 8명이라면 개인용 스크립트보다 웹 기반 내부 도구가 적합합니다.

권장 구조:

- Backend: Python FastAPI
- Frontend: React 또는 초기 MVP용 Streamlit
- PDF 처리: PyMuPDF, pdfplumber
- OCR: Tesseract 또는 사내/클라우드 OCR
- DB: PostgreSQL, 초기 MVP는 SQLite 가능
- 비동기 작업: FastAPI Background Tasks, RQ, Celery
- 리포트: HTML, Excel
- 배포: 사내 서버 또는 Docker

초기 검증이 목적이면 Streamlit이 빠릅니다.  
부서에서 계속 사용할 운영 시스템으로 키울 계획이면 FastAPI + React 구조가 더 적합합니다.

## 11. 로그 설계

로그는 사용자용 진행 로그와 개발자용 상세 로그를 분리합니다.

사용자용 진행 로그 예시:

```text
PDF 업로드 완료
신규 PDF 텍스트 추출 중
이전 PDF 텍스트 추출 중
언어 영역 분석 중
체크리스트 검토 중
모델 사양값 검토 중
이전 버전 비교 중
리포트 생성 중
검토 완료
```

개발자용 상세 로그 예시:

```text
page=12 language=fr extraction_method=pymupdf confidence=0.82
check_id=EU_SAFETY_014 expected=required_safety_phrase status=missing
model_code=ABC123 spec=voltage expected=220-240V actual=230V
diff_section=safety_notice page=4 status=changed
```

사용자에게는 이해하기 쉬운 진행 상태를 보여주고, 문제 분석을 위해 내부 로그는 상세하게 남깁니다.

## 12. 향후 회의에서 논의할 질문

부서원들과 먼저 정해야 할 질문은 다음과 같습니다.

- 가장 자주 검토하는 PDF 타입은 무엇인가?
- 우선 지원해야 할 언어와 바이어는 무엇인가?
- 안전 문구와 사양값 중 어느 쪽이 더 중요도가 높은가?
- 현재 검토 기준은 Excel, 문서, 시스템 중 어디에 관리되고 있는가?
- 모델코드별 사양값을 가져올 시스템은 API가 있는가?
- 결과 리포트는 HTML, Excel, PDF 중 어떤 형식이 가장 편한가?
- 자동 판정이 어려운 항목은 누가 최종 확인할 것인가?
- 검토 이력을 얼마나 오래 보관해야 하는가?

## 13. 결론

이 프로젝트는 단순 PDF 비교 도구가 아니라 `PDF 분석`, `체크리스트 검토`, `모델 사양값 검증`, `이미지 검토`, `이전 버전 비교`, `리포트 생성`이 결합된 업무 자동화 시스템입니다.

가장 먼저 해야 할 일은 전체 기능을 한 번에 만드는 것이 아니라, 샘플 PDF를 이용해 텍스트 추출 품질과 검토 기준 구조를 검증하는 것입니다.

성공 기준은 완전 자동화가 아닙니다.  
검토자가 믿을 수 있는 근거를 제공하고, 반복 확인 업무를 줄이며, 누락 가능성을 낮추는 것이 이 시스템의 핵심 목표입니다.

## 14. 현재 MVP 구현 상태

현재 로컬 Python 엔진은 다음 단계까지 구현되어 있습니다.

- PDF 파일명 파싱
- `pdf_profile_mapping.json` 기반 프로필 조회
- A2/A3/BOOK 구조 분석
- GridCell 및 LTR/RTL 읽기 순서 분석
- BOOK bookmark 기반 언어 구간 분석
- 구조 검증
- ZC 영어 샘플 기준 section/block 텍스트 추출 POC 안정화
- 추출 결과 검토용 JSON/XLSX 생성

현재 전체 샘플 구조 검증 결과:

```text
25 samples
0 failures
```

현재 추출 설계의 핵심은 다음과 같습니다.

```text
GridCell = PDF 읽기 순서를 안정화하기 위한 중간 단위
Review unit = language -> section/heading -> block -> lines/sentences
```

즉, 최종 검토 DB는 GridCell 좌표가 아니라 heading/section과 block 중심으로 설계해야 합니다. GridCell 정보는 근거와 추적용으로 유지합니다.

텍스트 추출은 문장 단위만 저장하지 않고, block, line, sentence 단위를 함께 저장하는 방향입니다. 다만 검토용 Excel에서는 `lines_text`를 우선 보여주고, sentence는 JSON 내부의 비교/검색 보조 데이터로 유지하는 것이 현재 방향입니다.

```text
block_type: heading | body | bullet | warning | table | navigation_ui | list_item | spec_table | regulatory_note
block_text
lines[]
sentences[]
```

이 방식은 다국어 번역에서 영어 1문장이 다른 언어 2~3문장으로 나뉘는 경우를 처리하기 쉽습니다.

현재 ZC 영어 content extraction POC는 아래 샘플에서 안정화되었습니다.

```text
BN68-20834D-00_SUG_Y25 TV ALL_ZC_L02_250710.0.pdf
BN68-25100A-00_SUG_Y26 TV ALL_ZC_L02_251222.0.pdf
BN68-25100B-00_SUG_Y26 TV ALL_ZC_L02_260122.0.pdf
```

최신 검토용 출력:

```text
outputs/content_poc_review_zc_eng_final_v3/
```

현재 다음 단계는 ZC `C-FRA`를 대상으로 영어 canonical heading과 localized heading을 매핑하고, 같은 heading rule과 block sequence가 다국어에서도 유지되는지 확인하는 것입니다.

## 15. 현재 주요 추출 리스크

다음 영역은 텍스트만으로 자동 판정하지 않고, 이미지 근거 또는 OCR 결과를 함께 남기는 방향이 적합합니다.

- cover / back cover 영역
- safety symbol table
- navigation / UI 영역
- 아이콘과 텍스트가 섞인 영역
- 표 형태의 영역

특히 `ZC_L02` 영어의 safety symbol explanation table은 향후 별도 table block으로 추출해야 합니다.

```text
block_type = safety_symbol_table
rows:
  symbol_image_crop
  label
  description
```

현재 POC에서는 safety symbol table, navigation/UI, package item list, model condition, specification table, regulatory note 등은 일반 body가 아니라 별도 block_type으로 분리하는 방향으로 구현되어 있습니다.
