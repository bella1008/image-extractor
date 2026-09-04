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

비개발자는 `semantic_document.md`를 먼저 열어 문서 순서, 제목 후보, 목록, 표, OSD 경로를 검토합니다. Markdown의 제목은 PDF source role 이름에서 찾은 source-role heading 후보이며, 검증된 표준 PDF heading이 아닙니다. `[CONTROL U+0003]` 같은 표시는 문자를 버린 결과가 아니라 XML 1.0에서 금지된 제어문자를 원래 위치에 드러낸 눈에 보이는 원본 추출 결함입니다. 이 진단 표시는 계속 유지하지만, 현재 승인 기준의 ZC 결과에는 한 건도 없어야 합니다.

PDF 내부의 MCID는 사람이 읽는 번호가 아니라 구조 노드와 페이지의 실제 글자를 연결하는 식별자입니다. 추출기는 이 값을 내부에 그대로 유지해 제목 아래에 어떤 본문이 속하는지 추적합니다. 텍스트는 원본 PDF 콘텐츠를 변경하지 않고 읽으며, pypdf의 강제 byte 모드에서 복합 글꼴을 먼저 해독한 뒤 일반 문자열로 만듭니다. 예전 실험처럼 가짜 `cm` 연산을 콘텐츠에 삽입하지 않습니다.

XML과 JSON은 감사 근거로 유지합니다. `raw_structure.xml`은 출처에서 관찰한 구조와 원본 증거를 보존하고, `semantic_document.xml`은 정규화된 구조와 함께 글머리표 `•`나 대시 `–` 같은 source label 텍스트도 보존합니다. `semantic_document.md`는 사람이 검토하기 쉬운 보기이며, 목록 기호를 Markdown 형식으로 정리하되 `1.`, `A.`, `(1)`처럼 의미 있는 순서 표시는 잃지 않습니다. `extraction_report.json`은 품질 게이트와 수치 및 heading 후보 근거를 제공합니다.

검토 우선순위는 다음 순서입니다. 한 번의 실행은 내부 작성자 잠금과 rollback 보호를 사용하는 하나의 트랜잭션에서 네 파일을 게시합니다. 이 잠금은 동시 작성자를 조정하기 위한 것이며 독자에게 일관된 스냅샷을 제공하지 않습니다.

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

입력은 PDF 원본 그대로 사용합니다. Acrobat에서 XML로 먼저 변환할 필요가 없으므로, 작업자가 파일을 한 번 더 가공하는 단계도 없습니다.

통합 테스트는 `TAGGED_PDF_ZC_SAMPLE`, 저장소 상대 `samples/SUG_RAW`, 사용자 홈의 개발용 `image-extractor/samples/SUG_RAW` 순서로 샘플을 찾습니다. 모두 없을 때만 샘플 통합 테스트를 명시적으로 건너뜁니다.

종료 코드는 다음과 같습니다.

- `0`: 추출 완료, 모든 하드 게이트 통과
- `1`: 추출과 저장은 완료했지만 하나 이상의 하드 게이트 실패
- `2`: 입력, 분석, 검증 또는 출력 트랜잭션 오류

종료 코드 `1`이어도 네 산출물이 모두 만들어질 수 있습니다. 예를 들어 글자는 정상 추출됐지만 PDF가 제목 역할을 표준 heading으로 선언하지 않았거나, Form XObject 안의 태그 텍스트를 아직 지원하지 않는 경우입니다. 따라서 비개발자는 “파일이 생성되지 않았다”는 뜻으로 이해하지 말고 `extraction_report.json`의 실패 게이트를 함께 확인해야 합니다.

## XML 보존 방식

XML 1.0에서 금지된 제어문자는 버리지 않고 정확한 위치에 `<control code="0001" />` 같은 노드로 기록합니다. 속성이나 메타데이터의 금지 문자는 UTF-8 Base64와 `*-encoding` 표식으로 보존합니다. 따라서 소비자는 일반 `itertext()`만 사용하지 말고 프로젝트의 `decode_data_element()`와 인코딩 표식을 사용해야 원문을 정확히 복원할 수 있습니다.

산출물은 형제 staging 디렉터리에서 모두 직렬화·재파싱한 뒤 게시됩니다. `--overwrite` 사용 시에도 지정된 네 파일만 교체하며, 코드가 포착한 게시 실패나 인터럽트가 발생하면 기존 파일 복구를 시도합니다. 기존 출력 디렉터리 안의 여러 파일은 순서대로 교체되므로 잠금을 무시하는 동시 독자에게 원자적인 묶음 스냅샷을 보장하지 않습니다. 프로세스 강제 종료나 전원 손실 뒤에는 남은 잠금·staging·backup과 산출물을 수동 검토해야 할 수 있습니다.

### 산출물 읽기 계약

추출·게시 중 네 산출물의 동시 읽기는 지원하지 않습니다. 잠금이 보이지 않는지 전후로 확인하는 방식도 잠금의 완전한 생성·삭제 주기를 놓칠 수 있으므로 묶음 일관성을 보장하지 않습니다. 사용자와 자동 독자는 추출 명령이 완전히 종료된 뒤에만 네 산출물을 열어야 합니다. 프로세스 강제 종료나 전원 손실 뒤에는 남은 형제 잠금(`.<출력-디렉터리-이름>.lock`)·staging·backup과 산출물을 수동 검토하며, 잠금을 자동 삭제하지 않습니다.

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

## 현재 샘플 검증 결과

2026-09-04에 ZC, ZA, ZG 원본 PDF를 직접 읽어 확인했습니다. 세 샘플 모두 marked PDF이며 구조와 body가 있고, unresolved MCID와 XML 금지 제어문자는 0개입니다. 다만 아래 남은 하드 게이트 때문에 어느 샘플도 전체 `pass`로 기록하지 않습니다.

### ZC

ZC 결과는 `status=fail`이며 CLI 종료 코드는 `1`입니다. 남은 실패는 `has_heading=false` 하나입니다. PDF의 사용자 heading 태그가 RoleMap에서 모두 `P`로 선언되어 있기 때문이며, 실제 source-role heading 후보 38개는 별도로 보존됩니다.

- 구조 요소 1,842개, 텍스트 조각 1,938개, body 1,410개
- unresolved MCID 0개, 알려진 텍스트 손실 진단 0개
- XML 금지 제어문자 0개, 영향 필드 0개
- 페이지 0: 텍스트 조각 947개, 21,978자, 제어문자 0개
- 페이지 1: 텍스트 조각 991개, 26,976자, 제어문자 0개
- 특수문자 `>`, `/`, `&`, `:`, `[`, `]`, `(`, `)` 개수가 PyMuPDF 기준과 모두 일치
- semantic XML source label: `•` 184개, `–` 38개
- Markdown에는 오래된 손상 표시 `Ł`, `Œ`, `[CONTROL U+...]`가 없음

| 문자 | 태그 텍스트 | PyMuPDF 기준 | 보존 게이트 |
| --- | ---: | ---: | --- |
| `>` | 54 | 54 | 통과 |
| `→` | 0 | 0 | 통과(기준에 없음) |
| `/` | 72 | 72 | 통과 |
| `&` | 1 | 1 | 통과 |
| `:` | 60 | 60 | 통과 |
| `[` | 2 | 2 | 통과 |
| `]` | 2 | 2 | 통과 |
| `(` | 83 | 83 | 통과 |
| `)` | 83 | 83 | 통과 |

영문 OSD 경로 자체는 다음과 같이 끊김 없이 복원되었습니다.

```text
( > left directional button > Settings > Support > Tips and User Guides > Open User Guide)
```

문장 연결 표본도 정상입니다.

```text
This symbol indicates that high voltage is present inside. It is dangerous to make any kind of contact with any internal part of this product.
```

프랑스어 복합 글꼴도 `Produit de catégorie II`, `Communiquez avec un centre de service homologué`, `Pour les modèles de 82 po, vous devrez être quatre`, `Le fait de tirer, de pousser ou de monter sur le téléviseur`, `Ne jamais placer un téléviseur dans une position instable`, `Wireless One Connect uniquement`으로 제어문자 없이 복원됩니다.

### ZA

ZA 결과는 `status=fail`입니다. 구조 요소 810개, 텍스트 조각 891개, body 608개이며, 2개 페이지 모두 제어문자 0개입니다. unresolved MCID와 알려진 텍스트 손실 진단은 0개이고 특수문자 보존 게이트도 통과합니다. 남은 실패는 ZC와 같은 `has_heading=false` 하나입니다. ZA 전용 보정 규칙은 추가하지 않았습니다.

### ZG

ZG 결과는 `status=fail`입니다. 구조 요소 6,148개, 텍스트 조각 6,696개, body 4,673개이며, 52개 페이지 모두 제어문자 0개입니다. unresolved MCID는 0개이고 특수문자 보존 게이트도 통과합니다.

남은 실패는 `has_heading=false`와 `no_known_text_loss=false`입니다. 후자는 아직 지원하지 않는 tagged Form XObject 진단 10건 때문입니다. 진단은 `/Im0`에 대해 페이지 인덱스 8, 9, 18, 19, 28, 29, 38, 39, 48, 49에서 발생하며 숨기거나 통과 처리하지 않습니다.

## 검증

```powershell
.venv\Scripts\python -m pytest tests -v
.venv\Scripts\python -m compileall src tests
```
