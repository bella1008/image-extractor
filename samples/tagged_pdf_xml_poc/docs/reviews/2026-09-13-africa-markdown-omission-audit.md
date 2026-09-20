# AFRICA Markdown 누락 지적 재검증 — 2026-09-13

대상은 `BN68-25031G-00_SUG_Y26 TV ALL_AFRICA_L05_251230.0.pdf`,
`AFRICA_L05 / BOOK / ENG, FRA, SPA, POR, ARA`다. 북마크 및 ARA p36→27 순서를 유지한다.
작업장은 `C:/Users/bella/image-extractor/.worktrees/xml-markdown-review`, 브랜치는
`feature/xml-markdown-review`다. 시작 HEAD는 `46167a0be671ef44ed996fd27f847bb9d0cf32a9`,
미커밋 변경은 없었다. 이전 출력과 다른 worktree, DB, legacy/Excel/Streamlit 코드는 수정하지 않았다.

## 사용자 지적과 실제 원인

- **QN9\*\*H: 90 와트**: 이전 실제 XML/MD에는 있었지만, 제공한 비교 이미지가
  `span[dir=rtl]` 중 수정된 세 문단만 선택했다. PDF crop에는 네 번째 모델 행이 포함되어
  비교 범위가 달랐다. 비교 자료의 결함이며 해당 모델 행의 추출 누락은 아니었다.
- **마침표**: 이전 비교 이미지의 규제 표기는 직접 입력한 `EC/1999/5`여서 마침표를
  누락했다. 실제 XML/MD에는 마침표가 있었지만 코드 앞에 배치되어 불필요한 `<br>`가 생겼다.
  규제 문장을 포함해 ARA 16곳에서 Latin 끝말과 마침표의 순서를 바로잡았다.
  문장부호를 임의로 버리지 않는다. RTL 문장에서 논리적으로 마지막인 마침표는
  화면에서 코드 왼쪽에 나타날 수 있다. `EC/1999/5`는 PDF의 실제 표기를 유지한다.
- **추가 발견: 별표 120개**: 5개 언어의 여러 모델 목록에서 Markdown 강조 문법이 별표를
  소비했다. XML과 MD 텍스트 파일에 있다는 사실만으로 화면 보존을 입증할 수 없었다.
  모델 별표를 literal escape하여 전체 원문 별표 255개를 모두 표시한다.
- **추가 발견: ARA p31 모델 구분**: 별표를 복원한 화면과 PDF를 비교하자 별도 RLM 조각
  왼쪽의 슬래시가 잘못된 Latin 구간에 합쳐져 모델 두 개가 붙어 보였다.
  12개 지원 모델의 순서와 11개 구분 슬래시를 원문대로 연결했다.

`glyph`는 PDF가 그리는 글자 모양 단위다. 아랍어는 연결되는 위치에 따라 모양이 달라지고,
여러 문자가 하나의 모양으로 그려질 수도 있어 문자 코드뿐 아니라 그려진 모양과 위치를 대조했다.
사용자가 glyph 정보를 직접 해석해야 검토할 수 있다는 뜻은 아니다.

## 수정 범위

- `domain/africa_inline_order.py`: 기존 `AFRICA_L05 + BOOK + ARA` dispatch 안에서만 처리한다.
  단독 마침표를 RTL 문장 경계로 분리하되, 같은 baseline에서 양쪽 숫자와 바로 이어진
  소수점은 LTR 숫자로 유지한다. 슬래시는 바로 오른쪽에 순수 RLM/Cf가 있고 양쪽 위치가
  인접할 때만 RTL 구분자로 분리한다. 일반 URL 슬래시는 유지한다.
- `infrastructure/markdown_writer.py`: 모델 별표의 Markdown 출력 escape를 추가했다.
  이것은 PDF 내용/모델 판단 규칙이 아니라 문자 표시 규칙이다. 일반 본문, 목록, 표,
  제목, 혼합 제목에서 같은 표시를 제공한다. 기존 강조 제목 및 RTL span은 유지한다.
- 기존 ZC/ZG 검증 helper가 Markdown의 `\*`를 원문 추가 문자로 세던 부분은
  CommonMark의 literal 별표로 해석하도록 보완했다. 실제 원문 기대값은 바꾸지 않았다.

## 최종 산출물과 근거

최종 출력 폴더(기존 폴더 보존):

`C:/Users/bella/image-extractor/.worktrees/xml-markdown-review/samples/tagged_pdf_xml_poc/outputs/xml_review_africa_20260913_omission_final_v3`

이 폴더에 `raw_structure.xml`, `semantic_document.xml`, `semantic_document.md`,
`extraction_report.json`, `review_document.json`, `review_run.json`을 저장했다.

근거 폴더:

`C:/Users/bella/image-extractor/.worktrees/xml-markdown-review/samples/tagged_pdf_xml_poc/outputs/xml_review_africa_20260913_omission_audit`

- `arabic_pdf_markdown_complete.png/.html`: 지적된 네 모델 행과 규제 문장 전체.
  오른쪽은 실제 전체 MD를 Marked로 파싱한 DOM에서 XML 원문과 일치하는 문단을 가져온다.
  검토용 행 번호만 분리하며 원문을 직접 입력하지 않는다. RTL 문단 방향을 명시한다.
- `all_periods.html`, `period_comparison_01.png`…`16.png`: 16개 전체 문단과 원문 crop.
  source MCID의 baseline/가로 범위를 독립 PyMuPDF 글자 좌표에 연결해 crop 범위를 정했다.
- `semantic_document.preview.html`: 실제 전체 MD의 읽기용 미리보기. 아랍어가 들어 있는
  문단에 RTL 방향을 적용한다. 글꼴/자동 줄바꿈은 원본 PDF와 다르다.
- `character_audit.json`: 전체 83,731자의 공백 제외 순서가 XML과 실제 Markdown DOM에서 일치.
  19 article 및 실제 writer 경계를 유지한 442개 검토 단위도 모두 일치한다.
  숫자와 문장부호를 제외하지 않는다. 별표 255개, 마침표 975개를 보존하고 의도하지 않은 강조는 0개다.
  PDF 불릿/번호는 MD 목록 마커로 표현되므로 대응 정책을 별도로 기록한다.
- `pdf_ascii_audit.json`: 독립 PyMuPDF로 36쪽 전체의 숫자 `0–9`, `* . : /`를 대조하여
  36쪽 모두 일치했다. 본문에 포함하지 않는 페이지 하단 쪽번호 30개만 위치와 함께 제외 기록했다.
  이 검사는 전체 문자나 읽기 순서 판정이 아닌, 해당 숫자/기호 개수의 독립 확인이다.
- Raw XML은 이전 결과와 byte-identical이며 4,499개 fragment의 ID와 텍스트는 그대로다.
  이번 Semantic 변경은 해당 문단 안의 순서이며 제목/표/행/셀/그림의 소속은 그대로다.

## 구조 수와 Gate

아래는 본문 XML 구조 수다. 중첩 paragraph wrapper를 포함하며 문장 수는 아니다.

| 언어 | 제목 | paragraph | list_item | table | row | cell | figure |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| ENG | 22 | 128 | 100 | 14 | 29 | 46 | 38 |
| FRA | 21 | 121 | 100 | 13 | 27 | 44 | 37 |
| SPA | 21 | 121 | 100 | 13 | 27 | 44 | 37 |
| POR | 21 | 121 | 100 | 13 | 27 | 44 | 37 |
| ARA | 22 | 128 | 100 | 14 | 29 | 46 | 38 |

공통 21개 제목의 하위 구조가 일치한다. ENG/ARA에만 실제 있는 Jordan 부분의 차이는 유지한다.
언어마다 안전 심볼 표1/그림6, 사양표1/행3, 구성품 표1, Controller 그림 표1,
Microphone Type A–D 표1, inline icon14가 있다. ENG/ARA 연락처의 국가19행과 source header는 유지된다.
ZG ENG/FRA 동일 언어 비교와 SPA/POR에 ZG 대응 언어가 없다는 이전 결론도 유지된다.

Hard gate 0. 이 작업에서 발견한 텍스트 누락/기호 순서 결함은 해소했다.
이미지인 아이콘·안전 심볼·barcode의 형상은 Markdown 텍스트가 재현하지 않으므로
최종 사람 검토에는 원본 crop을 함께 사용한다. 외부 의미 API/OCR/DB 후보 작업은 하지 않았다.

## 검증과 복구

초기 실패 11개, 분리 소수점 실패1개, 분리 RLM/슬래시 실패1개를 확인한 후 수정했다.
집중 테스트 347개, 전체 POC 회귀 1,871개 통과/1개 skip, ZC 재검사13개,
legacy public import3개와 compileall을 최종 코드로 확인했다. skip은 기존 Windows symlink 기능 검사다.
로그 경로, 전체 commit SHA와 변경 파일은 `review_run.json`에 기록한다.
일반 별표 escape의 ZC/ZG 표시 변경도 실제 샘플 회귀에 포함한다.

변경 파일은 위 runtime 2개, `test_africa_book_integration.py`, `test_africa_inline_order.py`,
`test_markdown_model_literals.py`, `test_layout_regression.py`, `test_zc_integration.py`,
이 보고서, 이전 보고서 안내, 스킬 검토안, TODO다. 전역 스킬 자체는 수정하지 않았다.
