# Tagged PDF XML 추출 POC

태그가 포함된 구조적 PDF에서 논리 구조와 텍스트를 XML로 복원할 수 있는지 확인하는 독립 실험 프로젝트입니다. 상위 `image-extractor`의 `src/`, Streamlit 앱, 체크리스트, 기존 추출 규칙을 import하거나 수정하지 않습니다.

## 1차 범위

- PDF `/StructTreeRoot`와 MCID를 이용한 구조·텍스트 추출
- 비개발자 검토용 `semantic_document.md`
- 표준 역할과 보수적 텍스트 연결을 적용한 `semantic_document.xml`
- 원본 구조를 보존한 `raw_structure.xml`
- 구조, heading 후보, 문자 보존, 참조 오류를 기록한 `extraction_report.json`

OCR, UI, 체크리스트 평가, 번역 및 buyer/language별 보정 규칙은 이번 단계에 포함하지 않습니다. `outputs/`는 `.gitignore` 대상이며 실제 산출물은 로컬에서만 생성하고 Git에 커밋하지 않습니다.

## 비개발자 검토와 감사 근거

비개발자는 `semantic_document.md`를 먼저 열어 문서 순서, 제목 후보, 목록, 표, OSD 경로를 검토합니다. Markdown의 제목은 PDF source role 이름에서 찾은 source-role heading 후보이며, 검증된 표준 PDF heading이 아닙니다. `[CONTROL U+0003]` 같은 표시는 문자를 버린 결과가 아니라 XML 1.0에서 금지된 제어문자를 원래 위치에 드러낸 눈에 보이는 원본 추출 결함입니다.

XML과 JSON은 감사 근거로 유지합니다. `semantic_document.xml`은 정규화된 구조와 원문 데이터를, `raw_structure.xml`은 PDF 태그 구조를, `extraction_report.json`은 품질 게이트와 수치 및 heading 후보 근거를 제공합니다. 한 번의 실행은 다음 네 파일을 잠금으로 보호되는 하나의 트랜잭션에서 게시합니다.

- `semantic_document.md`
- `semantic_document.xml`
- `raw_structure.xml`
- `extraction_report.json`

## 설치와 실행

Python 3.11 이상이 필요합니다.

```powershell
Set-Location .\samples\tagged_pdf_xml_poc
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"

$env:TAGGED_PDF_ZC_SAMPLE = (Resolve-Path `
  "..\SUG_RAW\0_TV_ZC\BN68-25100B-00_SUG_Y26 TV ALL_ZC_L02_260122.0.pdf" `
).Path

.venv\Scripts\tagged-pdf-extract.exe `
  "$env:TAGGED_PDF_ZC_SAMPLE" `
  --output "outputs\BN68-25100B-00" `
  --overwrite
```

통합 테스트는 `TAGGED_PDF_ZC_SAMPLE`, 저장소 상대 `samples/SUG_RAW`, 사용자 홈의 개발용 `image-extractor/samples/SUG_RAW` 순서로 샘플을 찾습니다. 모두 없을 때만 샘플 통합 테스트를 명시적으로 건너뜁니다.

종료 코드는 다음과 같습니다.

- `0`: 추출 완료, 모든 하드 게이트 통과
- `1`: 추출과 저장은 완료했지만 하나 이상의 하드 게이트 실패
- `2`: 입력, 분석, 검증 또는 출력 트랜잭션 오류

## XML 보존 방식

XML 1.0에서 금지된 제어문자는 버리지 않고 정확한 위치에 `<control code="0001" />` 같은 노드로 기록합니다. 속성이나 메타데이터의 금지 문자는 UTF-8 Base64와 `*-encoding` 표식으로 보존합니다. 따라서 소비자는 일반 `itertext()`만 사용하지 말고 프로젝트의 `decode_data_element()`와 인코딩 표식을 사용해야 원문을 정확히 복원할 수 있습니다.

산출물은 형제 staging 디렉터리에서 모두 직렬화·재파싱한 뒤 게시됩니다. `--overwrite` 사용 시에도 지정된 네 파일만 교체하며, 코드가 포착한 게시 실패나 인터럽트가 발생하면 기존 파일 복구를 시도합니다. 기존 출력 디렉터리 안의 여러 파일은 순서대로 교체되므로 잠금을 무시하는 동시 독자에게 원자적인 묶음 스냅샷을 보장하지 않습니다. 프로세스 강제 종료나 전원 손실 뒤에는 남은 잠금·staging·backup과 산출물을 수동 검토해야 할 수 있습니다.

### 산출물 독자 계약

출력 디렉터리가 `result`라면 잠금 경로는 같은 부모 디렉터리의 `.result.lock`, 일반식으로는 `.<출력-디렉터리-이름>.lock`입니다. 협력하는 독자는 파일을 열기 직전과 읽은 직후 이 경로를 확인하고, 잠금이 있는 동안에는 네 산출물을 읽지 말고 대기하거나 이번 읽기를 버린 뒤 재시도해야 합니다. 잠금이 계속 남아 있으면 자동 삭제하지 말고 중단된 게시 가능성을 수동 검토합니다.

## 품질 보고서와 하드 게이트

보고서 최상위에는 `source_path`, PDF가 선언한 `language`, `marked`, 원본 `role_map`, source role별 개수, heading 계층/후보 목록이 들어갑니다. 언어는 파일명이나 본문에서 추론하지 않습니다.

heading 목록은 구조 경로, source role, semantic role, level, 연결된 텍스트와 `/T` title을 기록합니다. `Heading2`, `NoTOC-Heading1`, `Cover_Title`, `Heading2_0_2`처럼 이름이 heading처럼 보이더라도 RoleMap 결과가 `P`이면 `source_role_candidate`로만 기록하며 `heading_count`에는 포함하지 않습니다. `Heading2_0_2`처럼 `Heading1`~`Heading6` 뒤에 숫자가 아닌 장식 suffix가 붙은 이름은 후보지만 `Heading20`, `H0`, `H7`은 후보가 아닙니다.

모든 하드 게이트가 참이어야 `status=pass`입니다.

- marked PDF이고 구조와 텍스트가 있는 body가 존재해야 합니다.
- 표준 `H`, `H1`~`H6`, `Title` 또는 검증된 RoleMap 대응 heading이 있어야 합니다. `H0`, `H7`~`H9`는 heading이 아닙니다.
- XML 직렬화와 왕복 검증이 성공해야 합니다.
- `unresolved_mcid`, `unresolved_page_reference`, `unsupported_objr`가 모두 0이어야 합니다.
- 알려진 텍스트 손실 진단인 `unresolved_mcid`, `unresolved_page_reference`, `unsupported_objr`, `unsupported_stream_mcr`, `tagged_form_xobject_unsupported`, `invalid_mcid`, `unsupported_structure_kid`가 모두 0이어야 합니다. 이 목록은 `domain/quality_diagnostics.py`에서 중앙 관리합니다. 단순 marked-content 범위 균형 경고는 그 자체로 텍스트 손실을 뜻하지 않으므로 포함하지 않습니다.
- 기준 텍스트에 등장한 필수 문자 `>`, `→`, `/`, `&`, `:`, `[`, `]`, `(`, `)`는 태그 텍스트에 기준 개수 이상 있어야 합니다. 기준에 없는 문자는 실패 원인이 아닙니다.

`resolved_references_reported`는 발견된 참조 진단에 조사 가능한 context가 있는지 별도로 보여주지만, context가 충분해도 미해결 참조가 하나라도 있으면 `resolved_references=false`로 실패합니다.

`special_character_counts_preserved`와 각 문자의 `count_preserved`는 문서 전체 문자 개수만 비교하는 보수적인 집계 proxy입니다. 특정 OSD 경로의 순서·문맥·문장 연결이 보존됐다는 뜻은 아닙니다. 지정 ZC OSD 경로의 문맥 보존은 아래 표본을 통합 테스트에서 직접 찾아 별도로 검증합니다.

## 지정 ZC PDF 결과

2026-09-03 재실행 결과는 `status=fail`, CLI 종료 코드 `1`입니다. XML 두 개와 JSON 생성·재파싱은 성공했으며 실패 이유는 두 가지입니다.

- `has_heading=false`: PDF의 사용자 heading 태그가 RoleMap에서 모두 `P`로 선언됨
- `special_character_counts_preserved=false`: 기준 대비 `/`, `:`, `(`, `)` 개수가 부족함

주요 수치는 다음과 같습니다.

- 구조 요소 1,842개, 텍스트 조각 1,938개
- 텍스트가 있는 body 요소 1,410개
- heading 0개, source-role heading 후보 38개
- 장식된 source role에서 `Troubleshooting`, `Specifications`, `Dépannage`, `Spécifications` 후보 추가 확인
- unknown 역할 0개
- unresolved MCID 0개, unresolved page reference 0개, unsupported OBJR 0개
- 알려진 텍스트 손실 진단 0개 (`no_known_text_loss=true`)
- 문자 일치율 `0.9798180073`
- 태그 텍스트 48,494자, 기준 텍스트 47,914자
- XML 금지 제어문자 608개, 영향 필드 44개
- 공백 연결 판단 1,060개

| 문자 | 태그 텍스트 | PyMuPDF 기준 | 보존 게이트 |
| --- | ---: | ---: | --- |
| `>` | 54 | 54 | 통과 |
| `→` | 0 | 0 | 통과(기준에 없음) |
| `/` | 69 | 72 | 실패 |
| `&` | 1 | 1 | 통과 |
| `:` | 56 | 60 | 실패 |
| `[` | 2 | 2 | 통과 |
| `]` | 22 | 2 | 통과 |
| `(` | 80 | 83 | 실패 |
| `)` | 79 | 83 | 실패 |

영문 OSD 경로 자체는 다음과 같이 끊김 없이 복원되었습니다.

```text
( > left directional button > Settings > Support > Tips and User Guides > Open User Guide)
```

문장 연결 표본도 정상입니다.

```text
This symbol indicates that high voltage is present inside. It is dangerous to make any kind of contact with any internal part of this product.
```

다만 일부 프랑스어 구간에는 PDF 디코딩 단계에서 생긴 제어문자와 손상 문자가 남아 있습니다. 현재 결과만으로 새 시스템의 기반을 확정하기보다는 source-role heading override의 PDF 근거와 특수문자 부족 구간의 콘텐츠 스트림·폰트 매핑을 다음 단계에서 조사해야 합니다.

## 검증

```powershell
.venv\Scripts\python -m pytest tests -v
.venv\Scripts\python -m compileall src tests
```
