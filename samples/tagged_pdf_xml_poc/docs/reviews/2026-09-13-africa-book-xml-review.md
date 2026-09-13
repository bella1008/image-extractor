# AFRICA_L05 BOOK XML 검토 기록

**판정: 추출 검증 미완료 / Hard gate 잔존.** 검증된 수정과 재현 근거를 저장했다.
혼합 RTL UI 경로의 논리적 읽기 순서가 남았다. 사람 확인만으로 코드 결함을
통과 처리하지 않으며 체크리스트 후보 생성이나 DB 작업은 진행하지 않았다.

## 대상과 시작 상태

- PDF: `BN68-25031G-00_SUG_Y26 TV ALL_AFRICA_L05_251230.0.pdf`
- 입력: `C:\Users\bella\image-extractor\.worktrees\xml-extractor-release\samples\SUG_RAW\TV_AFRICA\BN68-25031G-00_SUG_Y26 TV ALL_AFRICA_L05_251230.0.pdf`
- SHA-256: `cdc2123f2e1dde2f46314a9ef31bda0bdfb4b4455ff26436838004d65e05c848`
- 작업장: `C:\Users\bella\image-extractor\.worktrees\xml-markdown-review`
- 브랜치: `feature/xml-markdown-review`
- 시작 HEAD: `840512002a80a12b19c712116530ab69b1459c3a`; 미커밋 변경 없음.
- 파일명 parser와 canonical profile JSON 확인: `AFRICA_L05`, `BOOK`, ENG/FRA/SPA/POR/ARA.
- 실제 북마크: English 2쪽, Français 8쪽, Español 14쪽, Português 20쪽, العربية 35쪽.
  본문: ENG 2–7, FRA 8–13, SPA 14–19, POR 20–25, ARA 35→30쪽.
  표지를 포함한 ARA 읽기 순서는 36→27쪽이다. 28/29쪽은 본문 없는 간지이며
  원본 페이지 라벨을 보존했다. ENG 앞표지 1쪽, 연락처 뒷표지 26쪽을 확인했다.

## 수정 전 결함과 적용 범위

| 결함 | 수정 및 근거 |
| --- | --- |
| POR 20–34쪽, ARA 35–36쪽으로 잘못 나뉨 | 실제 북마크, Arabic script, 표지 및 연속 Article 근거로 POR 20–25, ARA 27–36 구간 확인 |
| Arabic 페이지가 앞에서 뒤로 출력됨 | Semantic Article 순서 36→27, Raw는 원래 순서 보존 |
| 화면의 04가 ToUnicode로 14가 되고 POR/ARA 제목 승격 실패 | PDF content ActualText 사용; 원 glyph 해석과 교체 근거 기록 |
| Markdown 장 번호 `0 1` 분리 | 검증된 승격 heading의 source digits만 01~04로 표시; audit metadata 제외 |
| MCID/Td flush로 RTL 단어·발음기호 분리 | 원 glyph 단위 역순과 MCID 소유권을 보존한 제한된 Semantic 복원 |

모든 새 동작은 정확한 AFRICA_L05 BOOK 언어 조합과 Arabic 근거가 있는 경로로
제한했다. 다른 profile/default reader는 유지했다. glyph 복원은 물리 한 줄,
동일 부모, 원 단어 경계, 완전한 MCID/문자 보존 등 검증을 모두 통과해야 한다.
최종 run은 241개 fragment의 glyph 기반 표시와 6개 paragraph의 MCID 순서를
정리했다. 공백 정리도 포함하므로 241개가 모두 독립 문장 오류였다는 뜻은 아니다.

- 35쪽 제목: 실제 PDF의 `قبل قراءة الدليل البسيط للمستخدم هذا`를 보존했다.
  문법상 자연스러운 추정 문구로 바꾸지 않았다. source path `0/17/1/0`,
  MCID 70/71/72를 Semantic에서 72/71/70으로 확인했다.
- 33쪽 MCID 339: `تجنُّب سقوط التلفزيون`. glyph `03ff`의 U+0651→U+064F를
  하나의 glyph로 보존했다. 코드포인트 단위로 뒤집지 않았다.
- 30쪽 MCID 842: `تعتّم الشاشة.`를 원 glyph로 복원했다.
- raw operand hex, glyph, font, text/current matrix, MCID, 이전/이후 문자열과
  source path를 report에 남겼다. 이 식별자는 checklist 고정 키가 아니다.

## ENG 기준 비교와 언어별 구조

ENG 비교 기준은 검증된 `outputs/cross_profile_readability_zc_260908`, 가장 가까운
BOOK 회귀 기준은 `outputs/cross_profile_readability_zg_260908`이다. AFRICA ENG의
장 01~04, 제목 하위 목록, 안전 심볼, 사양, 그림/범례, UI 및 표지를 PDF 1–7/26쪽과
대조한 뒤 FRA/SPA/POR를 AFRICA ENG와 비교했다. ZC의 Internet security 등
바이어별 원문 차이를 AFRICA 누락으로 강제하지 않았다.

다음은 표지·중첩 paragraph를 포함한 Semantic 컨테이너 수다. paragraph 수는
문장 수가 아니다. 제목 수는 source-role 후보와 승격 제목의 합이다.

| 언어 | 제목 | 승격 장 | paragraph | list_item | table | table_row | table_cell | figure |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| ENG | 22 | 4 | 200 | 100 | 15 | 49 | 100 | 39 |
| FRA | 21 | 4 | 121 | 100 | 13 | 27 | 44 | 37 |
| SPA | 21 | 4 | 121 | 100 | 13 | 27 | 44 | 37 |
| POR | 21 | 4 | 121 | 100 | 13 | 27 | 44 | 37 |
| ARA | 22 | 4 | 204 | 100 | 15 | 49 | 101 | 41 |

각 언어: 안전 심볼 표 1개(9행, 이미지 6개), 사양표 1개(3행), 구성품 표 1개,
Controller 그림 표 1개, Microphone Type A~D 범례 표 1개, inline icon 14개.
ENG/ARA에는 연락처 표 1개와 Jordan 규제 표 1개가 추가된다. 원문 표/목록/figure를
일반 body 하나로 합치지 않았다. 이 검토 분류는 legacy block type/DB 키가 아니다.

## 표지와 보존 근거

36쪽 전체를 90 dpi로 렌더링하고 1/26/27/36쪽의 로고, 제목, 등록/지원,
모델/시리얼, 연락처 제목/안내/머리글/국가 행, 저작권, QR/문서코드를 직접 확인했다.
29개 crop manifest와 추가 `p36_registration_full.png`, `p33_prevent_heading.png`를
남겼다. 앞선 잘린 crop 대신 `crops_v2` 및 보충 전체 영역 crop을 근거로 사용한다.

- 26쪽 source header: `Country/Region | Samsung Service Centre [전화 아이콘] | Website`.
  `review_document.json`의 `contact_tables.*.source_header`에는 머리글만 있다.
  국가/지역 19행은 `country_rows`로 분리했다. 27쪽은 반대 물리 열 순서다.
- RowSpan을 따라 국가/서비스센터/URL을 비교해 ENG/ARA 19행 전부 일치했다.
- 안전 심볼 표 이미지/설명 셀과 사양표 모델 조건/수치/단위의 셀 관계를 확인했다.
- 문서코드 `BN68-25031G-00`는 36쪽 barcode crop에서 확인했다. OCR 결과나
  파일명에서 복원된 XML 텍스트라고 주장하지 않는다.
- Raw/Semantic fragment 각각 4,499개. `(page-index, mcid, object-ref)` multiset 및
  공백을 제외한 전체 문자 multiset 일치. Markdown은 추가된 표/그림 표시를
  제외하면 Semantic과 알파벳 문자 수가 일치한다. 번호 heading 20개, inline icon 70개 대응.
- XML round-trip 통과, 미해결 참조/알려진 손실 진단/금지 제어문자 각각 0.
  문자 집계는 읽기 순서가 맞다는 증거를 대신하지 않는다.

## 남은 Hard gate와 Warning

**Hard: ARA 혼합 RTL UI 순서.** 35쪽 source path `0/17/1/2`는 PDF의 홈 아이콘부터
시작하는 경로와 달리 Markdown에서 `التلميحات وأدلة > الدعم > الإعدادات ...`가 먼저
나온다. `crops_v2/p35_navigation.png`와 XML MCID 79–92/figure 소유권이 직접 근거다.
여러 줄의 구분자/아이콘을 전체 역순으로 바꾸면 괄호·방향·문장 경계를 손상시킬 수
있다. 현재 순수 glyph 규칙으로 승인하지 않았으며 추가 추출 수정이 필요하다.

**Engine Hard: multilingual_heading_count_parity=false.** ENG/ARA 22개와
FRA/SPA/POR 21개 차이는 PDF에 실제 존재하는 Jordan-only subsection이다.
7/30쪽에 있고 13/19/25쪽에는 없다. 나머지 level/origin/번호 서명 gate는 통과한다.
원문 예외를 확인했지만 gate를 무조건 완화하거나 현지어 제목을 만들어 넣지 않았다.

Warning: 혼합 Arabic/Latin/숫자와 여러 baseline MCID의 줄 품질, 아이콘 의미,
안전 심볼/모델 조건의 사람 검토가 필요하다. UI 텍스트가 존재해도 순서가 틀리면
위 Hard로 취급한다. OCR 및 외부 API 의미 검토는 사용하지 않았다.
Global LCS 0.7957258032644351은 물리 baseline과 역순 RTL Semantic을 비교하므로
최종 승인 지표로 사용하지 않는다.

## 산출물과 검증

최종 폴더:
`C:\Users\bella\image-extractor\.worktrees\xml-markdown-review\samples\tagged_pdf_xml_poc\outputs\xml_review_africa_20260913_final_v2`

`raw_structure.xml`, `semantic_document.xml`, `semantic_document.md`,
`extraction_report.json`, `review_document.json`, `review_run.json`을 확인했다.
앞선 before/after/final 폴더는 보존했다. review_run에는 입력/bundle SHA-256,
시작 Git 상태, 로그, 보존 검사, 차단 문제와 최종 복구 commit을 기록한다.

POC 디렉터리 실행 명령:

```powershell
$env:PYTHONUTF8='1'
.venv\Scripts\python -m tagged_pdf_extractor.cli '<위 입력 PDF>' --output outputs/xml_review_africa_20260913_final_v2
.venv\Scripts\python -m pytest tests/test_africa_actual_text.py tests/test_africa_book_rules.py tests/test_africa_book_integration.py tests/test_africa_rtl.py -q
$env:TAGGED_PDF_REQUIRE_SAMPLES='1'
.venv\Scripts\python -m pytest tests -q
```

추출 CLI exit=1은 잔존 gate 때문에 예상된 결과다. 재실행에는 새 폴더를 사용한다.
집중 **50 passed**; 전체 **1760 passed, 1 skipped**. skip은 Windows symlink 기능
1건이다. 기존 ZC/ZG/LATIN/KR/XU와 ZA/XY 실물 회귀를 포함해 통과했다.
pytest temp를 repo 안에 둘 때 13개 fixture-isolation 테스트가 실제 metadata/samples를
조상 경로에서 발견해 실패했으나 기본 격리 temp로 재실행해 모두 통과했다.
이 문제 때문에 추출 규칙을 변경하지 않았다.

작업장 루트에서 `python -m compileall src tests scripts samples/tagged_pdf_xml_poc/src samples/tagged_pdf_xml_poc/tests`
exit=0. 루트 apps/scripts는 존재하지 않아 apps는 제외했고 scripts에는 파일이 없다.
기존 `src.content_poc` 공개 import 3개도 확인했다. XML/Markdown writer/public reader
및 profile scope 검사는 전체 POC suite에 포함된다.

## 변경 파일과 복구

- 루트 `TODO.md`, `docs/superpowers/plans/2026-09-13-africa-book-xml-validation.md`.
- POC `README.md`, 이 검토 기록.
- `application/extract_document.py`.
- `domain/models.py`, `numbered_heading_promotion.py`, 새 `africa_book.py`, `africa_rtl.py`.
- `infrastructure/pypdf_reader.py`, `pypdf_operation_text.py`, `xml_writer.py`, `markdown_writer.py`, 새 `africa_actual_text.py`, `africa_glyphs.py`.
- 새 테스트 `test_africa_actual_text.py`, `test_africa_book_rules.py`, `test_africa_book_integration.py`, `test_africa_rtl.py`.

검증된 코드/기록만 현 브랜치에 로컬 commit한다. 전체 commit 번호는 최종
review_run.json과 작업 메시지에 기록한다. 원격 push, 다른 branch/worktree,
item_review/Excel/Streamlit/체크리스트 DB는 변경하지 않았다.
