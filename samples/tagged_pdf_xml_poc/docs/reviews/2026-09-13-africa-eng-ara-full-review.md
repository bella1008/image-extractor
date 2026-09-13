# AFRICA BOOK ENG–ARA 전체 검토 및 문장 표시 수정

대상: `BN68-25031G-00_SUG_Y26 TV ALL_AFRICA_L05_251230.0.pdf`.
프로필은 `AFRICA_L05 / BOOK / ENG,FRA,SPA,POR,ARA`이며 실제 북마크 순서를 유지한다.
ENG 본문은 PDF p2–7, ARA 본문은 p35→30, ARA 전체 구간은 p36→27이다.
작업장: `C:/Users/bella/image-extractor/.worktrees/xml-markdown-review`,
브랜치: `feature/xml-markdown-review`, 시작 HEAD:
`7d5f732746de80aeb6cb4e85c5d773567401367e`. 시작 미커밋 변경은 없었다.

## 결과와 검토 경로

추출 Hard gate는 0개다. 아랍어 번역이 영어와 완전히 같다는 판정은 하지 않는다.
원문 의미·조건 차이 9건(그중 세로/가로 설치 조건 1건은 우선 확인 대상)과 이미지 검토를 남긴다.
원문 작성자가 결정할 표현을 추출기에서 번역하거나 고치지 않았다.

최종 출력 절대 경로:
`C:/Users/bella/image-extractor/.worktrees/xml-markdown-review/samples/tagged_pdf_xml_poc/outputs/xml_review_africa_20260913_eng_ara_final`.
이 폴더에 `raw_structure.xml`, `semantic_document.xml`, `semantic_document.md`,
`extraction_report.json`, `review_document.json`, `review_run.json`이 있다.

검토용 HTML:
[semantic_document.preview.html](../../outputs/xml_review_africa_20260913_eng_ara_full_review/semantic_document.preview.html).
전체 대응 원문과 한국어 판정:
[meaning_review.md](../../outputs/xml_review_africa_20260913_eng_ara_full_review/meaning_review.md),
[원본 crop 비교](../../outputs/xml_review_africa_20260913_eng_ara_full_review/source_comparison.html).

## 수정 내용과 근거

1. ENG p7 `The screen dims.`의 Eco Sensor 문단은 문장 두 개와 작은 설정 아이콘 두 개로
   구성된다. 기존 문장 detector가 figure를 포함한 문단 전체를 제외하여 줄바꿈을 놓쳤다.
   검증된 AFRICA BOOK 프로필에서만 작은 inline icon 앞뒤의 텍스트 구간을 문장 검사한다.
   아이콘을 가로질러 문장을 추측하지 않는다. ENG/FRA/SPA/POR/ARA 5개 문단에 각각 `<br>` 1개를
   추가했고 XML의 source-fragment offset과 Markdown이 일치한다. 검증되지 않은 그림은 계속 제외한다.
2. ARA 전체 의미 대조 중 안전 관련 9개 문단/목록에서 원래 같은 줄인 PDF glyph 조각의 순서가
   뒤섞인 것을 추가 발견했다. 같은 MCID가 아주 작은 baseline reset이나 별도 결합 부호로 나뉘어
   이전 복원이 보류되었는데, 이를 완료로 판단했던 이전 검토의 한계다. 10개 MCID를 수정했다:
   p35 `118,120,40`, p34 `156,190,195,277`, p33 `315`, p32 `387,437`.
   같은 글꼴·한 물리 줄·이어지는 x 좌표·동일 문자 구성·결합 부호의 자음 위치 근거가 모두 있어야 복원한다.
   다른 열, 실제 다른 줄, 역방향 좌표, 떨어진 부호, ActualText 일반 문자, 다른 본문 스타일은 거부한다.
   Raw XML과 노드 ID/원본 경로는 보존했다. 단어를 번역하거나 새로 넣지 않았다.
3. PDF는 아랍어 제목 `SamsungOneArabic-600` 7pt, 본문 `SamsungOneArabic-400` 6.5pt를 사용한다.
   설정 항목에는 600 강조도 있다. 원래 모든 문장이 같은 굵기는 아니다.
   기존 HTML은 Arial에서 제목/본문 모두 18px, weight는 700/400이었다.
   새 HTML은 아랍어 Tahoma, 제목 23px/700, 본문 18px/400 및 제목 구분선을 사용한다.
   이는 검토용 재조판이며 원본의 모든 inline 글꼴 강조를 재현한다는 뜻은 아니다.

수정 경로는 XML POC 내부뿐이다. `readability_profile`은 검증에 사용하는 문서 맥락이며,
기존 한 인자 readability 호출과 public imports도 유지했다. GridCell, item_review, Excel/Streamlit,
체크리스트 DB, 다른 작업장은 변경하지 않았다.

## 구조 및 데이터 비교

본문의 동일 범위를 비교했다. P는 중첩 wrapper를 포함하는 XML paragraph 수이며 문장 수가 아니다.

| 항목 | ENG | ARA |
|---|---:|---:|
| 제목(챕터 포함) | 22 | 22 |
| 번호 챕터 | 4 | 4 |
| XML paragraph | 128 | 128 |
| list | 33 | 33 |
| list_item(챕터 승격 제외) | 100 | 100 |
| list_body / label | 104 / 104 | 104 / 104 |
| table | 14 | 14 |
| table_row | 29 | 29 |
| table_cell | 46 | 46 |
| figure / inline icon | 38 / 14 | 38 / 14 |
| 겹치지 않는 텍스트 대응 단위 | 196 | 196 |
| 검토한 모델 토큰 출현 | 35 | 35 |

22개 제목 각각의 하위 P/목록/표/행/셀/그림 수도 동일하다.
안전 심볼 표는 각각 1개(9행·그림 6개), 사양표 1개(3행), 포장 구성품 표 1개,
Controller 그림 표 1개, 마이크 Type A–D 표 1개, Jordan 규제 표 1개다.
모델 35개 출현을 비교했으며 사양·모델·LAN·Wi-Fi의 21개 대응 행에서 모든 숫자의 표기와 순서가 같다.
출력·크기 조건, 섭씨/화씨, 습도와 비응축 조건도 문장 의미로 확인했다.
설정 경로 4개를 단계별로 읽었고 대응 순서와 기능이 같다. 아이콘 모양은 crop 근거 대상이다.

표지 및 연락처는 본문 수에 넣지 않았다. 양쪽 19개 국가 행의 국가·전화/WhatsApp·URL은
rowspan을 풀어서 모두 일치한다. 헤더는 데이터 행과 분리했다. 연락처 XML 셀은 ENG 54/ARA 55개다.
ENG ALGERIA/TUNISIA의 URL 공유 셀 하나를 ARA가 두 셀로 반복한 실제 레이아웃 차이다.
ARA의 의도적 빈 페이지 안내 2개와 표지 문서 코드/바코드는 별도 source 구조다.

원본 저장 단위 수는 같을 필요가 없다. 본문 ENG/ARA span 210/220, text fragment 827/977,
article 1/6, section 5/8이다. 한 언어에서 여러 페이지를 감싸는 wrapper가 있으면 본문 전용 집계에서
제외되므로 이 wrapper 수를 누락 개수로 해석하지 않는다. 텍스트 단위와 실제 읽기 순서를 함께 확인했다.

다른 언어의 본문 수는 그대로다: FRA/SPA/POR 각각 제목 21, P 121, LI 100, 표 13, 행 27, 셀 44,
그림 37. Jordan 전용 부분을 제외한 공통 21개 제목과 하위 구조는 5개 언어 모두 일치한다.
ZG에는 ENG/FRA만 같은 언어가 있으며 이전 동일 언어 비교 근거는 유지했다. SPA와 M-SPA,
POR와 B-POR를 서로 같은 기준으로 쓰지 않았다.

## 의미 판정

196개 대응 단위 모두를 로컬에서 읽고 부정/금지, 적용 조건, 조치, 예외, 수치 소속을 비교했다.
182개는 추가 의미 차이를 찾지 못했다. 4개는 어색한 원문/오탈자 등 표현 기록, 9개는 의미 확인 Warning,
1개는 규제 번호 원문 표기 차이로 기록했다. 표지·연락처·빈 페이지는 위 별도 검토에 포함했다.
이는 일괄 번역 동등성 보증이나 번역 승인 판정이 아니다.

우선 확인할 원문 차이:

- **Pair 124 / ENG p6·ARA p31:** ENG `vertically`(세로 설치), ARA `أفقيًا`(가로 설치).
  LS03H의 Portrait Mode 조건이 반대이다. `98LS03HE` 제외 조건은 모두 있다.
- **Pair 61 / p4·p33:** ENG는 TV가 가구 밖으로 돌출되지 않도록 하라는 지시,
  ARA는 가장자리에서 흔들리지 않도록 하라는 표현이다.
- **Pair 145 / p6·p31:** ENG의 microphone **switch**, ARA는 마이크라고만 표현한다.
- 나머지 Warning은 열 관련 설치 금지 장치(31), 보유/보관·이동 적용 조건(68), 교체/이동(69),
  포장재 뒤 위치 표현(118), 단자/케이블 덮개 명칭(185), 실내/집 안 범위(195)다.
  모두 해당 ARA PDF crop에서 원문을 확인했고 한국어 설명과 대응 원문을 전체 보고서에 남겼다.
- Pair 193의 `1999/5/EC` / `EC/1999/5`는 원문 표기 차이다. 임의 정렬하거나 고치지 않았다.
- Pair 78의 `قك`는 원문 오탈자 후보다. bracket 설치 높이 조건은 대응하며 원문을 유지했다.

## 보존·테스트·Gate

- 수정 전 현재 추출기를 `xml_review_africa_20260913_sentence_baseline`에 실행했다.
- 최종 Raw XML은 baseline과 byte 동일, 4,499개 fragment ID 보존.
  모든 fragment에서 공백 제외 문자 multiset이 같고, 구조 경로·태그·순서도 같다.
  이 검사는 글자 순서를 증명하지 않으므로 별도로 10개 복원 줄의 PDF 좌표와 전체 의미를 확인했다.
- Semantic XML → 실제 Marked/Edge Markdown 렌더링: 공백 제외 83,731자 순서 일치,
  19 article 및 442 writer unit 전부 일치, 원본 별표 255개 보존.
- 전체 PDF 36페이지의 숫자 및 `* . : /` inventory 일치. 쪽번호 30개는 위치와 제외 사유를 기록했다.
- 새 HTML과 같은 MD의 렌더링 결과: 텍스트 및 2,318개 heading/list/table/link/br 요소 서명 일치.
  PDF가 아니라 MD–HTML 사이의 표시 검증임을 구별한다.
- 집중: **365 passed, 1 skipped**. 전체 XML POC: **1,906 passed, 1 skipped** (195.52초).
  skip은 Windows symlink 사용 불가이다. 실제 실패한 초기 로그도 보존했다.
- 전체 suite에 ZC/ZG 및 기존 언어 회귀, semantic XML/Markdown writer, output bundle 검사가 포함된다.
  독립 리뷰의 비대상 프로필 문단 조합 399개도 HEAD와 결과가 같았다. 미해결 P1/P2 0개.
- public imports 3개 통과. root `python -m compileall src tests scripts`와 POC `src tests` 통과.
  root `apps`, `scripts`는 없으므로 `Can't list scripts`를 기록했다. 실제 존재하는 디렉터리는 컴파일 성공했다.
- 추출 Hard gate **0**, 원문 의미 Warning **9**, 이미지/crop 검토 **1**.
  상태는 **추출 검증 완료 / 원문 표현의 사람 검토 필요**다. 체크리스트 후보나 DB 승인은 진행하지 않았다.

## 변경 파일과 복구

`src/tagged_pdf_extractor/` 아래 `application/extract_document.py`, `domain/models.py`,
`domain/readability_formatting.py`, `domain/africa_rtl.py`, `infrastructure/markdown_writer.py`;
`tests/test_africa_book_integration.py`, `tests/test_africa_rtl.py`, `tests/test_readability_formatting.py`;
이 보고서, skill audit 제안 문서, root `TODO.md`.

로컬 commit 전체 번호와 산출물 SHA256은 최종 `review_run.json`에 기록한다.
기존 결과 폴더는 보존했다. push/merge/rebase는 수행하지 않았다.
