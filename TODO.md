# TODO

## 완료

- 프로젝트 목적과 전체 방향 정리
  - 문서: `README.md`
  - 목표: 전자 제품 매뉴얼 PDF 자동 검토 시스템
  - 핵심 방향: 완전 자동 판정보다 자동 추출, 자동 비교, 사람이 확인 가능한 근거 제공

- SUG 샘플 PDF 24개 분석
  - 샘플 위치: `samples/SUG_RAW/`
  - 문서: `SUG_RAW_ANALYSIS.md`
  - 확인 내용:
    - 파일명 메타데이터 파싱 가능
    - PDF 텍스트 추출 가능
    - 페이지 크기: `A2`, `A3`, `A5`
    - `A2`, `A3` 문서는 페이지 상단 언어 라벨 확인 가능
    - `BOOK` 문서는 PDF bookmark 기준으로 언어 구간 분리 가능

- PDF 프로필 메타데이터 정리
  - 기준 파일: `metadata/pdf_profile_mapping/pdf_profile_mapping.json`
  - 보조 파일:
    - `metadata/pdf_profile_mapping/pdf_profile_mapping.xlsx`
    - `metadata/pdf_profile_mapping/pdf_profile_mapping.csv`
  - 컬럼:
    - `source_token`
    - `region`
    - `buyer_codes`
    - `languages`
    - `doc_type`
    - `language_count`
  - 결정 사항:
    - `region`은 대표 지역 코드로 관리
    - 기존 대분류 `REGION`, 대표 국가, `ref_row`는 관리하지 않음
    - `C-FRA`, `M-SPA`, `B-POR`는 별도 언어 코드로 유지
    - `BOOK` 언어 순서는 실제 PDF bookmark 순서 기준
    - `AFRICA MENA_L05`는 `region=AFRICA`, `doc_type=BOOK`으로 정규화

- 프로젝트 폴더 정리
  - 기준 메타데이터: `metadata/`
  - 샘플 PDF: `samples/`
  - 참고 기준표: `REF/260612_manual_lan_region.xlsx`
  - 에이전트 작업 규칙: `AGENTS.md`
  - 임시 분석 산출물과 임시 스크립트 삭제

## 진행 방향

- 1차 구현은 로컬 실행형 Python 앱으로 시작
  - 사용자는 각자 PC에서 프로젝트 폴더를 받고 Python과 라이브러리를 설치
  - `run_app.bat` 또는 명령어로 앱 실행
  - 화면은 브라우저에서 열리지만, 실제 실행은 각자 PC에서 수행

- UI는 우선 Streamlit을 고려
  - PDF 업로드
  - 모델코드 입력
  - 검토 옵션 선택
  - 진행 로그 표시
  - 결과 리포트 다운로드

- 장기적으로는 사내 웹 시스템으로 확장 가능하게 설계
  - 핵심 검토 로직은 `src/` 아래에 분리
  - Streamlit은 초기 UI 역할만 담당
  - 이후 필요 시 FastAPI + React 또는 사내 표준 웹 시스템으로 전환

## 다음 작업

### 1. Python 프로젝트 기본 구조 생성

```text
src/
  domain/
  application/
  infrastructure/
  interfaces/
```

- `domain/`
  - 핵심 데이터 모델과 업무 규칙
  - 예: PDF 프로필, 파일명 파싱 결과, PDF 구조, 검증 결과

- `application/`
  - 업무 흐름 조합
  - 예: 파일명 파싱 -> 프로필 조회 -> PDF 구조 분석 -> 검증 결과 생성

- `infrastructure/`
  - 파일, JSON, PDF 라이브러리 접근
  - 예: `pdf_profile_mapping.json` 로딩, PyMuPDF 기반 PDF 분석

- `interfaces/`
  - 실행 입구
  - 초기에는 CLI 또는 Streamlit 앱

### 2. PDF 파일명 파서 구현

- 입력 예:

```text
BN68-25100A-00_SUG_Y26 TV ALL_ZC_L02_251222.0.pdf
```

- 추출 값:
  - `manual_code`
  - `manual_type`
  - `product_info`
  - `buyer_region_token`
  - `language_token`
  - `source_token`
  - `date_code`

### 3. PDF 프로필 매핑 로더 구현

- 입력:

```text
metadata/pdf_profile_mapping/pdf_profile_mapping.json
```

- 기능:
  - 전체 프로필 로드
  - `source_token` 기준 조회
  - 없는 `source_token`이면 명확한 오류 반환

### 4. 실제 PDF 구조 분석기 구현

- 확인 항목:
  - 페이지 수
  - 페이지 크기
  - `A2`, `A3`, `BOOK` 판정
  - `BOOK` bookmark 언어 목록
  - `A2`, `A3` 상단 언어 라벨

### 5. 매핑과 실제 PDF 비교

- 비교 항목:
  - `doc_type`
  - `language_count`
  - `languages`

- 불일치 시 처리:
  - 자동 실패 처리보다 수동 확인 필요로 분류
  - 실제 PDF가 변경된 것인지, `pdf_profile_mapping` 수정이 필요한지 판단할 수 있게 표시

### 6. 체크리스트 Excel 구조 설계

- 목적:
  - 운영 DB가 아니라 체크리스트 입력/import 양식

- 후보 시트:
  - `required_phrases`
  - `spec_rules`
  - `icon_rules`
  - `exceptions`

- 우선순위:
  - 필수 문구 검토용 `required_phrases`부터 설계

### 7. Streamlit 로컬 앱 초안

- 기능:
  - 신규 PDF 업로드
  - 이전 버전 PDF 업로드
  - 모델코드 입력
  - 검토 옵션 선택
  - PDF 프로필 조회 결과 표시
  - PDF 구조 분석 결과 표시
  - 매핑 비교 결과 표시

## 보류 / 추후 결정

- 결과 리포트 1차 형식
  - HTML
  - Excel
  - 둘 다

- 모델 사양값 연동
  - MVP에 포함할지 추후 결정

- 이미지/아이콘 검토
  - 초기 MVP에서는 자동 판정보다 후보 탐지와 수동 확인 중심으로 검토

- 검토 이력 저장
  - 로컬 파일 저장으로 시작할지, DB를 둘지 추후 결정

- 사내 서버 배포
  - 로컬 앱 검증 후 필요 시 검토
