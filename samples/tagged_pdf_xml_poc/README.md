# Tagged PDF XML 추출 POC

태그가 포함된 구조적 PDF에서 원본 구조와 텍스트를 XML로 보존할 수 있는지 확인하는 독립 실험 프로젝트입니다. 상위 `image-extractor`의 `src/`, Streamlit 앱, 체크리스트 및 기존 추출 규칙을 import하거나 수정하지 않습니다.

## 범위

1차 범위는 PDF 태그 트리와 MCID 텍스트를 읽어 다음 산출물을 만드는 것입니다.

- `raw_structure.xml`: 원본 태그명, RoleMap, 계층, 페이지, MCID, 원문 조각 보존
- `semantic_document.xml`: 표준 역할명과 보수적으로 연결한 텍스트
- `extraction_report.json`: 구조·문자 보존·품질 게이트·텍스트 연결 판단 기록

`outputs/`는 저장소의 `.gitignore` 대상입니다. 실제 산출물은 로컬에 생성되며 커밋하지 않습니다. 동일한 PDF와 명령으로 언제든 재현할 수 있습니다.

XML-to-Markdown, OCR, UI, 체크리스트 평가, 언어/바이어별 보정 규칙은 1차 범위에서 제외합니다.

## 설치 및 실행

Python 3.11 이상이 필요합니다.

```powershell
cd C:\Users\bella\image-extractor\samples\tagged_pdf_xml_poc
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
```

```powershell
.venv\Scripts\tagged-pdf-extract.exe `
  "C:\Users\bella\image-extractor\samples\SUG_RAW\0_TV_ZC\BN68-25100B-00_SUG_Y26 TV ALL_ZC_L02_260122.0.pdf" `
  --output "outputs\BN68-25100B-00" `
  --overwrite
```

`--overwrite`를 생략하면 세 필수 산출물 중 하나라도 이미 있을 때 쓰기를 시작하지 않습니다.

종료 코드는 다음과 같습니다.

- `0`: 추출 완료, 모든 하드 게이트 통과
- `1`: 추출과 산출물 저장은 완료됐지만 하나 이상의 하드 게이트 실패
- `2`: 입력, 분석, 자원 한도, 검증 또는 출력 트랜잭션 오류

종료 코드 `1`은 프로그램 실행 실패가 아니라 PDF 구조에 대한 POC 판정 결과입니다.

## XML 보존 규칙

XML 1.0에서 허용되지 않는 제어문자는 버리지 않고 정확한 위치에 자식 노드로 기록합니다.

```xml
<text>앞부분<control code="0001" />뒷부분</text>
```

속성이나 메타데이터에 XML 금지 문자가 있으면 UTF-8 Base64 값과 인접한 인코딩 표식을 사용합니다.

```xml
<element title="...base64..." title-encoding="base64-utf8" />
```

lone surrogate가 포함된 경우 `base64-utf8-surrogatepass`가 사용될 수 있습니다. 따라서 후속 소비자는 일반 `itertext()`만 사용하지 말고 `<control>` 노드와 `*-encoding` 표식을 해독해야 합니다. 프로젝트의 `decode_data_element()`와 XML 왕복 검증 로직이 이 규칙을 적용합니다.

출력은 형제 staging 경로에서 XML·JSON 생성과 재파싱을 모두 완료한 뒤 게시합니다. 기존 출력에 덮어쓸 때는 세 필수 파일만 백업·교체하며, 실패하면 복원합니다. 복원이나 정리가 완전히 끝나지 못한 경우 복구 경로와 게시 상태를 예외에 남깁니다. CLI가 `outputs committed`를 출력했다면 세 산출물은 이미 게시됐지만 임시 경로 정리에 실패한 상태입니다.

## 품질 측정

페이지 텍스트 기준선은 PyMuPDF로 독립 추출하며, 태그 텍스트와 비교할 때만 NFC 정규화와 연속 공백 축약을 적용합니다. 원본 XML 텍스트는 이 과정에서 바뀌지 않습니다.

문자 일치율은 근사 윈도우가 아닌 정확한 LCS 길이를 기준으로 합니다. 짧은 쪽 문자열에 대한 bit-parallel 방식 또는 자원 한도 내 sparse 방식을 선택합니다. 메모리·매칭 쌍 예산을 모두 초과하면 부정확한 값을 만들지 않고 `QualityEvaluationLimitError`와 종료 코드 `2`를 반환합니다. 사용한 방식과 추정 자원은 보고서의 `comparison_mode`, `comparison_parameters`에 기록됩니다.

하드 게이트는 marked PDF, 구조 존재, heading, 텍스트가 있는 body, XML 왕복, unresolved MCID 보고 여부입니다.

## 지정 ZC PDF 실행 결과

2026-09-03 실행 결과는 `status=fail`, CLI 종료 코드 `1`입니다. 세 파일 생성과 XML/JSON 재파싱은 성공했지만 `has_heading=false`였습니다.

- 구조 요소 1,842개, 텍스트 조각 1,938개
- 텍스트가 있는 body 요소 1,410개
- unresolved MCID 0개, unknown 역할 0개
- 문자 일치율 0.979818 (`bit_parallel_lcs`)
- 태그 텍스트 48,494자, 기준 텍스트 47,914자
- XML 금지 제어문자 608개, 영향 필드 44개
- 공백 연결 판단 1,060개

가장 중요한 발견은 PDF에 `Heading2`, `Heading3`, `NoTOC-Heading1`, `NoTOC-Heading2`, `NoTOC-Heading3`, `Cover_Title` 같은 사용자 태그가 실제로 존재하지만, PDF의 `/RoleMap`이 이 태그들을 모두 표준 `P`로 지정한다는 점입니다. 따라서 현재 추출기는 임의로 제목을 추론하지 않으며 `heading_count=0`으로 판정합니다. raw XML은 정확한 `source-role`을 보존하므로, 다음 단계에서 PDF 근거를 확인한 명시적 override 규칙을 설계할 수 있습니다.

영문 OSD 경로는 다음처럼 계층과 특수문자를 유지했습니다.

```text
( > left directional button > Settings > Support > Tips and User Guides > Open User Guide)
```

문장 연결도 다음 영문 예시에서는 끊김 없이 복원됐습니다.

```text
This symbol indicates that high voltage is present inside. It is dangerous to make any kind of contact with any internal part of this product.
```

반면 일부 프랑스어 조각에는 원본 PDF 텍스트 해석 단계에서 나온 제어문자와 손상된 글자가 남아 있습니다. XML은 이를 손실 없이 안전하게 기록하지만, 의미상 올바른 문장 복원까지 보장한다는 뜻은 아닙니다.

특수문자 수는 다음과 같습니다.

| 문자 | 태그 XML 원문 | PyMuPDF 기준선 |
| --- | ---: | ---: |
| `>` | 54 | 54 |
| `→` | 0 | 0 |
| `/` | 69 | 72 |
| `&` | 1 | 1 |
| `:` | 56 | 60 |
| `[` | 2 | 2 |
| `]` | 22 | 2 |
| `(` | 80 | 83 |
| `)` | 79 | 83 |

이 차이는 XML 직렬화 손실이 아닙니다. XML 왕복 게이트는 통과했으며, 태그 트리와 독립 페이지 텍스트 추출기가 서로 다른 원문 스트림과 디코딩 결과를 읽어서 발생한 측정 차이입니다. 특히 추가 `]`와 제어문자는 태그 텍스트의 디코딩 이상을 후속 검토 대상으로 보여 줍니다.

현재 결과만으로 새 시스템의 기반으로 확정하기에는 이릅니다. 다음 단계에서는 source role 기반 heading override를 실제 PDF 근거로 검증하고, 프랑스어 제어문자 구간의 콘텐츠 스트림과 폰트 매핑을 조사해야 합니다.

## 테스트

```powershell
.venv\Scripts\python -m pytest tests -v
.venv\Scripts\python -m compileall src tests
```

통합 테스트는 `TAGGED_PDF_ZC_SAMPLE` 환경 변수로 다른 샘플 경로를 지정할 수 있습니다. 환경 변수와 기본 절대 경로 모두 사용할 수 없을 때만 명시적으로 건너뜁니다.
