# XML adapter 구현 결과와 사용 방법

2026-09-10, 작업 브랜치 `codex/xml-review-v2`.

## 지금 가능한 일

PDF를 기존 XML 추출기로 추출한 뒤, 그 구조를 새 검토 시스템의 공통 데이터인 ReviewDocument로 변환한다. 체크리스트를 검사하거나 최종 Excel을 만드는 단계는 아직 아니다.

```text
PDF + 파일명/profile mapping
  → 기존 XML 추출기
  → 기존 네 파일
  → 파일 묶음·품질·언어 검사
  → ReviewDocument
  → review_document.json + review_run.json
```

`review_document.json`은 이후 체크리스트/Excel/화면이 사용할 원본 구조 데이터다. `extraction_report.json`은 추출기의 품질 검사 보고서이므로 두 JSON은 역할이 다르다. `review_run.json`은 파일들이 같은 새 실행에서 나온 것인지 확인하기 위한 hash 기록이다. 사용자 업무의 최종 Pass 결과가 아니다.

## 확인한 실물 결과

| PDF | 전체 노드 | 텍스트 조각 | 문단 | 표 | 언어별 텍스트 조각 |
|---|---:|---:|---:|---:|---|
| ZC L02 | 3,780 | 1,938 | 290 | 31 | ENG 947 / C-FRA 991 |
| XU ENG | 2,374 | 1,168 | 235 | 24 | ENG 1,168 |
| ZG BOOK | 12,844 | 6,696 | 1,328 | 146 | ENG 1,287 / DEU 1,359 / FRA 1,323 / ITA 1,343 / DUT 1,375 / 미배정 9 |

텍스트 조각은 XML의 text 요소 수다. 문장 수나 DB 행 수가 아니다. 여러 문장으로 된 문단도 그대로 한 문단으로 보존한다. 표 셀 안의 문단/목록/그림도 계층을 유지한다. 검토용 review_roles는 현재 모두 빈 값이다.

ZG 미배정 9개는 언어 북마크 밖 공통 표지 텍스트다. 삭제하거나 영어로 추측하지 않았다. 향후 표지 검토가 별도 범위로 처리해야 한다.

비교 기준은 `xml-markdown-review/samples/tagged_pdf_xml_poc/outputs/cross_profile_readability_{zc,xu,zg}_260908`이다. 세 프로필 모두 Semantic XML과 MD는 기존 파일과 바이트 단위로 동일했다. Raw XML과 추출 보고서는 원본 PDF 경로만 다르고 나머지 구조/내용은 동일했다. 이는 adapter 보존 검증이며 번역 의미·DB 적용·전체 프로필 승인 결과는 아니다.

## 결과 파일 위치

현재 작업장 루트의 다음 폴더:

- `outputs/xml_review_v2_zc_20260910/`
- `outputs/xml_review_v2_xu_20260910/`
- `outputs/xml_review_v2_zg_20260910_r2/`

각 폴더에 기존 네 파일과 새 JSON 두 파일이 있다. `outputs/xml_review_v2_zg_20260910/`는 공통 표지 처리 보완 전의 실패 근거 폴더다. 완료 receipt가 없으며 완료 결과로 사용하지 않는다. 파일을 삭제하지 않고 남겼다.

출력 폴더는 Git에 포함되지 않는다. 아래 명령으로 재생성할 수 있다.

## 지금 PC에서 실행하는 방법

PowerShell에서 아래 명령을 실행한다. 현재 검증에는 기존 XML 작업장의 Python 환경을 읽어서 사용했다. 실행 코드는 `xml-review-v2`의 코드를 명시적으로 사용한다.

```powershell
Set-Location 'C:\Users\bella\image-extractor\.worktrees\xml-review-v2'
$env:PYTHONPATH = (Resolve-Path '.\samples\tagged_pdf_xml_poc\src').Path
& '..\xml-markdown-review\samples\tagged_pdf_xml_poc\.venv\Scripts\python.exe' -m src.xml_review_run '.\samples\SUG_RAW\TV_ZC\BN68-25100B-00_SUG_Y26 TV ALL_ZC_L02_260122.0.pdf' --output '.\outputs\my_zc_review_001'
```

`--output`에는 아직 없는 새 폴더명을 사용한다. 기존 폴더는 비어 있어도 덮어쓰지 않는다. 명령 성공 시 `ReviewDocument created`가 표시된다. `checklist not evaluated`는 아직 체크리스트 검토 전이라는 뜻이다.

별도 PC나 독립 환경에서는 먼저 로컬 XML POC 패키지를 설치한다. 아래 설치 절차는 일반 설치 안내이며 이번 실물 검증은 위의 기존 환경을 사용했다.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .\samples\tagged_pdf_xml_poc
.\.venv\Scripts\python.exe -m src.xml_review_run '검토할_PDF_전체경로.pdf' --output '.\outputs\new_review_001'
```

폴더 이름에서 운영 정보를 추측하지 않는다. PDF 파일명과 `metadata/pdf_profile_mapping/pdf_profile_mapping.json`을 사용한다. 현재 단일 언어 연결에서 지원하지 않는 XML 언어 표기는 조용히 추측하지 않고 중단한다.

## 실행 오류의 의미

- `Use a new run directory`: 결과 폴더가 이미 있다. 새 이름으로 실행한다.
- `failed extraction gates`: 추출 품질 검사 실패. 체크리스트 문구 누락으로 해석하지 않는다.
- `hash mismatch`: 완료 기록과 파일 내용이 다르다. 파일을 혼합하거나 수정하지 말고 새로 추출한다.
- `unsupported extractor source version`: XML 추출기 코드가 검증 기준과 다르다. 새 버전에 대해 호환성 테스트 후 기준을 갱신해야 한다.
- `ambiguous ... language`, `page/path disagreement`: 언어 근거가 불충분하거나 충돌한다. 추출 근거를 점검해야 한다.

과거 산출물 폴더를 다시 해시해서 완료 기록을 만드는 기능은 제공하지 않는다. receipt는 새 실행 경로가 생성한다. 이 기록은 실수로 파일이 섞이거나 바뀐 것을 탐지하는 장치이며 전자서명은 아니다.

## 검증과 다음 단계

- 신규 adapter 테스트 30개, 루트 전체 138개 및 subtest 6개 통과.
- XML POC의 XML writer/output bundle/language intervals/Markdown 관련 테스트 511개 통과, 1개 생략(Windows symlink 미지원).
- `python -m compileall -q src tests`와 `git diff --check` 통과. POC 전체 테스트를 다시 실행한 것은 아니다.
- 기존 XML POC 코드, 메인의 DB, 기존 Streamlit/Excel 코드는 변경하지 않았다.

다음 단계는 기존 master Excel과 JSON 일치 여부를 확인하고, 새 v2 DB의 이관표/감사 결과와 체크리스트 평가기를 만드는 작업이다. 그 과정에서 실제 필요한 review_role과 범위를 정한다. Excel 결과 양식 및 화면 연결은 그 다음 단계다.
