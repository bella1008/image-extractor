# AFRICA / ZG 동일 언어와 RTL 후속 검토 — 2026-09-13

## 결과

AFRICA의 공통 제목 21개가 ZG ENG/FRA와 각각 대응한다. 원문 비교 중 발견한
LTR 소수 공백 4곳과 Arabic 기호·괄호 4문단을 수정하고 새 XML/Markdown을 검증했다.
Hard gate는 0개다. 기존 포괄적 native/meaning Warning은 추출 gate에서 종료했다.
남은 사람 확인은 이미지인 아이콘·안전 심볼·barcode를 crop과 함께 보는 것이다.
Markdown placeholder만으로 그림 형상을 확인할 수 있다는 뜻은 아니다.

- 작업 PDF: `BN68-25031G-00_SUG_Y26 TV ALL_AFRICA_L05_251230.0.pdf`.
- 프로필: `AFRICA_L05 / BOOK / ENG, FRA, SPA, POR, ARA`.
- worktree: `C:/Users/bella/image-extractor/.worktrees/xml-markdown-review`.
- branch: `feature/xml-markdown-review`; 시작 HEAD `28723bbcb45674e28611c4d9cdd28d14d52a20e7`, 미커밋 변경 없음.
- 파일명/profile/실제 북마크 재확인. 북마크 p2/8/14/20/35, Arabic 본문 p35→30, 전체 p36→27.
- 사용자가 확인한 영국 영어 맥락으로 AFRICA ENG↔ZG ENG를 비교했다. canonical metadata의 영어 variant를 변경하지 않았다.

## 동일 언어 추출 이력 및 비교

ZG XML 기준은 `outputs/cross_profile_readability_zg_260908`이며
`BN68-25448A-00_SUG_Y26 TV ALL_ZG XN ZT_L05_260204.0.pdf`에서 추출됐다.
실제 북마크는 ENG p2, DEU p12, FRA p22, ITA p32, DUT p42다.
따라서 이번 동일 언어 비교는 ENG/FRA뿐이다. SPA/POR을 M-SPA/B-POR로 대체하지 않았다.
원래 요청한 ZC ENG 선행 구조 확인은 이전 검토에서 완료됐으며 이번 비교는 추가 검증이다.

루트 outputs의 기존 `content_poc.json`을 읽기 전용 조사한 결과 FRA 33개가 모두 ZG였다.
M-SPA 92개(ZX 72, LATIN 20), C-FRA 42개(ZC)가 있으나 다른 언어 코드다.
조사한 기록에는 SPA/POR/B-POR 결과가 없었다. 이는 조사 범위 밖의 이력 부재를 단정하는 결과가 아니다.
현재 비교는 legacy payload 대신 검증된 ZG XML 결과를 사용했다.

| 비교 | 대응 공통 제목 | 공백을 접은 본문 fragment 문자열 일치 | 제목 아래 XML 종류별 개수 일치 |
| --- | ---: | ---: | ---: |
| AFRICA ENG ↔ ZG ENG | 21 | 15/21 | 17/21 |
| AFRICA FRA ↔ ZG FRA | 21 | 13/21 | 17/21 |

제목 대응에서는 장 번호만 비교용으로 제거했다. 원문 제목은 변경하지 않았다.
본문 일치 수는 번역 정확도 점수가 아니다. fragment 경계·구두점 공백과 실제 문구 차이를 모두 포함하며,
각 차이는 PDF 이미지와 대조했다. 단순히 같은 언어/영국 영어라는 이유로 전체 문구를 같다고 처리하지 않았다.

원문에서 확인한 차이는 다음과 같다.

| 영역 | 확인한 원문 차이 | 근거 PDF 페이지 |
| --- | --- | --- |
| 공통 제목 이후 장 번호 | ZG에 One Connect 장과 cable holder가 있어 Initial Setup 이후 장 번호가 1 증가 | ZG ENG p5–6 / FRA p25–26 |
| 비밀번호/적합성 선언 | ZG에 비밀번호 변경, 서로 다른 리모컨 모델의 적합성 선언 2개가 존재 | ZG ENG p7,9,10 / FRA p27,29,30 |
| 안내문 | AFRICA에 website에서 매뉴얼을 내려받는 문단 추가 | AFRICA p2,8 / ZG p2,22 |
| 벽걸이/환기 | Samsung↔Samsung Electronics, 유선 One Connect 지원 범위 및 FRA 표현 차이 | AFRICA p3,9 / ZG p3,23 |
| 구성품 | ZG의 CI adapter/유선 One Connect 구성품과 추가 주석이 원문에 존재 | AFRICA p5,11 / ZG p5,25 |
| 마이크 | ZG에 그림의 switch 위치를 설명하는 caption 행 1개 추가 | AFRICA p6,12 / ZG p6,26 |
| 사양/규제 | 모델별 출력값, °F/°C 표시 순서, Wi-Fi 주파수 및 EU/UK 문구 범위가 실제로 다름 | AFRICA p7,13 / ZG p7–9,27–29 |
| FRA 표현 | `Mur-ancrage`↔`Ancrage mural`, `Capteur de la télécommande`↔`Capteur de télécommande` 등 | AFRICA p10,12 / ZG p24,26 |
| Jordan-only | AFRICA ENG p7와 ARA p30에만 원문 항목 존재 | FRA p13 / SPA p19 / POR p25에는 없음 |

ZG의 같은 이름을 가진 선언 제목 두 개는 서로 다른 원문 문서이므로 중복 추출로 삭제하지 않았다.
이 차이들은 제목/본문 누락이나 body 합침의 근거가 아니다. 원문별 구조 범위와 숫자를 유지했다.

## 새로 확인해 수정한 추출 결함

1. ENG/FRA/SPA/POR의 Wi-Fi `7.125`/`7,125`에 불필요한 공백이 들어갔다.
   ENG는 이 때문에 `7 .<br>125`로 문장 줄바꿈까지 생겼다. 원본 TJ에는 공백 glyph가 없고
   숫자와 구두점 사이 kerning 값만 있다. 같은 MCID의 단일 source operation 전체 문자열이
   교정 후 문자열과 정확히 일치할 때만 decimal 내부 공백을 제거한다.
2. ARA p30 사양의 세 문단에서 quote/paren/colon/slash 중립 기호의 MCID 내부 순서가
   물리 방향으로 남아 모델명에 quote가 붙거나 slash가 인치 괄호 안에 들어갔다.
   완전한 모델/인치/출력 패턴, RLM, 동일 baseline, 원문 기호 glyph의 단일 codepoint,
   x 진행/간격, 전체 문자 Counter가 확인될 때만 복원한다. 쉼표는 실제 x 좌표가
   모델의 오른쪽임을 확인한 이 패턴 안에서만 논리 순서로 옮긴다.
3. 같은 페이지 Wi-Fi 문단의 양 대괄호가 MCID의 반대 끝에 남았다.
   실제 glyph의 오른쪽/왼쪽 끝 위치와 추출된 문구·수치 패턴을 확인해 문단을 감싸도록 복원했다.

새 동작은 exact AFRICA BOOK 프로필 경로에만 연결한다. 현지어를 번역하거나 모델/수치를 바꾸지 않았다.
`src/content_poc.py`, GridCell, item_review, Excel/Streamlit, checklist DB와 다른 worktree는 변경하지 않았다.

Semantic의 네 문단에는 `display-direction="rtl"`와 source 근거 reason을 둔다.
Markdown은 대응하는 `<span dir="rtl">`를 사용한다. 별표 모델명은 HTML entity로 표시하여
Markdown 강조 처리 때문에 wildcard가 사라지지 않게 했다. 검토 시 inline HTML의 dir 속성을
지원하는 Markdown 미리보기를 사용한다. 전체 미리보기 HTML도 함께 생성했다.

## Arabic 확인 방법과 이전 Warning 정리

원문과 XML/Markdown의 문자·순서·표시 관계가 같으면 추출 품질에 별도의 아랍어 번역 승인이 필요하지 않다.
다만 문자열이 같아도 bidi 표시 결과가 같지는 않을 수 있어 이번에는 실제 렌더 화면까지 확인했다.
기존의 “자연스러운 조판을 보증하지 않는다”는 포괄적 문구는 구체적 결함과 검증 결과로 대체한다.

- 사양 p30: `S90H`의 42 / 48–83과 20 / 40, `LS03HE`의 43–85 / 98,
  `LS03HW`와 20 / 40이 어떤 괄호와 출력에 속하는지 원본 crop과 비교했다.
- 온도·습도: 모델/수치 순서 검증을 유지한다. 줄바꿈의 픽셀 위치가 같을 필요는 없고,
  음수 부호·범위 끝값·단위 소속 및 문단/목록 관계가 보존되어야 한다.
- Wi-Fi: 대괄호가 전체 주의문을 감싸며 `5.925`, `7.125`, `6.425` 순서/소속이 원문과 대응한다.
- `EC/1999/5`: p30 MCID819의 실제 PDF 표기다. ENG `1999/5/EC`로 바꾸지 않는다.
  사용자는 아래 비교 화면에서 라틴 문자/숫자만으로도 확인할 수 있다. 이 원문 차이는 추출 Warning에서 종료했다.
- 아이콘·안전 심볼·barcode: Markdown의 `[아이콘]`, `[그림: 텍스트 없음]`은 형상 재현이 아니다.
  이미 확인한 crop을 전반적 검토에도 함께 사용한다. OCR 결과나 번역 결과로 주장하지 않는다.

실제 새 Markdown 전체를 Marked GFM으로 파싱하고 로컬 Microsoft Edge에서 렌더했다.
네 span의 RTL/isolate 적용, 모델 별표의 literal 표시, 아래 source crop과의 대응을 확인했다.
사용자에게 아랍어 문장을 새로 번역하거나 언어 전문가에게 원문 표현을 승인받으라고 요구하지 않는다.

## 최종 산출물

폴더:
`C:/Users/bella/image-extractor/.worktrees/xml-markdown-review/samples/tagged_pdf_xml_poc/outputs/xml_review_africa_20260913_followup_final_v3`

이 폴더의 `raw_structure.xml`, `semantic_document.xml`, `semantic_document.md`,
`extraction_report.json`, `review_document.json`, `review_run.json`을 확인했다.
`semantic_document.preview.html`은 실제 Markdown의 전체 미리보기다.

근거 폴더:
`C:/Users/bella/image-extractor/.worktrees/xml-markdown-review/samples/tagged_pdf_xml_poc/outputs/xml_review_africa_20260913_same_language_review`

- `arabic_pdf_markdown_verified.png` / `.html`: PDF ↔ 현재 Markdown 표시 비교.
- `markdown_render_validation.json`: renderer, span text/direction, wildcard 검사.
- `same_language_comparison_accepted.json`, `same_language_diffs_accepted.md`: ZG ENG/FRA 대응과 차이, 페이지/MCID/XML 경로.
- `final_delta_audit.json`, `structure_audit_final.txt`: 문자·구조 보존 감사.
- 각 PDF 페이지 이미지, source crop, red/green/final test log 및 재생성 스크립트.

## 언어별 구조 수와 Gate

본문만 집계하며 paragraph는 중첩 wrapper를 포함하는 XML 컨테이너다.

| 언어 | 제목 | paragraph | list_item | table | row | cell | figure |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| ENG | 22 | 128 | 100 | 14 | 29 | 46 | 38 |
| FRA | 21 | 121 | 100 | 13 | 27 | 44 | 37 |
| SPA | 21 | 121 | 100 | 13 | 27 | 44 | 37 |
| POR | 21 | 121 | 100 | 13 | 27 | 44 | 37 |
| ARA | 22 | 128 | 100 | 14 | 29 | 46 | 38 |

공통 21개 제목마다 하위 구조 수가 다섯 언어에서 일치한다. Jordan은 ENG/ARA에
제목1/P7/table1/row2/cell2/figure1을 더하며 원본 근거 예외를 유지한다.
각 언어에는 안전 심볼 표1(9행/그림6), 사양표1(3행), 구성품 표1,
Controller 그림 표1, Microphone Type A–D 범례 표1, inline icon14가 있다.
표지/연락처/빈 페이지 수와 연락처 source_header/국가19행은 review_document에 따로 유지했다.

Raw XML은 이전 검증 결과와 byte-identical이다. 4,499개 fragment identity와 공백 제외
전체 문자를 보존했다. 변경된 text fragment는 16개(소수4, RTL 기호10, Wi-Fi 양 끝2),
모델과 분리한 쉼표 순서1곳, direction hint4곳이다. 기존 소속/구조/연락처 검증은 모두 유지된다.

Hard gate 0. 남은 Warning 1종은 사람의 최종 이미지 확인이다.
추출 검증 완료 상태이며 사용자 전반 검토를 받을 수 있다. DB 후보/승인은 진행하지 않았다.

## 테스트와 코드 검토

- 집중 AFRICA 테스트 7개 파일: **141 passed**.
- 전체 POC 실제 샘플 회귀: **1851 passed, 1 skipped**, 181.06초.
  Windows에서 symlink를 만들 수 없는 기존 테스트 1개 skip.
- 기존 ZC/ZG/LATIN/KR/XU 및 ZA/XY 실물, public reader/import, profile dispatch,
  Semantic XML/Markdown writer 회귀가 포함된다.
- root의 legacy public import 3개 통과. root `src/tests/scripts`와 POC `src/tests`
  compileall 통과. root apps/scripts는 현재 checkout에 검사할 폴더가 없다.
- 소수 real-source 실패4 → 수정 통과. RTL 실패3, 추가 경계 실패2,
  glyph 안전장치 실패4를 확인한 후 수정했다. 전체 suite는 최종 코드로 재실행했다.
- 독립 코드 검토에서 wildcard escape와 glyph 원자성/x 검증 두 경계를 지적받아
  실패 테스트로 재현·수정했다. 재검토에서 추가 P1/P2가 없었다.

변경 파일은 TODO/plan/POC README/기존 리뷰 안내/이 리뷰/스킬 검토안,
POC domain `africa_book`, `africa_numeric_text`, `africa_rtl_conditions`, `models`,
infrastructure `africa_actual_text`, `pypdf_reader`, `xml_writer`, `markdown_writer`,
tests `test_africa_book_integration`, `test_africa_numeric_text`, `test_africa_rtl_conditions`다.

검증한 변경만 현재 브랜치에 로컬 커밋한다. 전체 commit SHA와 정확한 파일 목록은
최종 review_run.json과 완료 응답에 기록한다. push/merge/rebase/정리 작업은 하지 않는다.

## sug-manual-review 스킬

별도 `2026-09-13-sug-manual-review-skill-audit.md`에 현재 workflow와 맞지 않는
Excel/legacy 키 중심 절차, 비교 언어/기준, RTL와 Warning 종료 기준 등을 정리했다.
이 요청은 스킬 검토이므로 전역 스킬은 수정하지 않고, 현재 worktree에 적용 가능한 수정안을 남겼다.
