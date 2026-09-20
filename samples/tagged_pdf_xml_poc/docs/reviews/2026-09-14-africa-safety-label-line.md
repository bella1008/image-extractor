# AFRICA ARA p35 안전 표 경고 문구 줄바꿈

사용자 직접 ARA 검토에서 안전 표의 `خطر التعرض لصدمة كهربائية. لا تفتحه.`가
HTML 두 줄로 표시된다는 지적이 있었다. 그 외 ARA에는 추가 문제를 발견하지 못했다는
사용자 의견도 기록했다.

대상 PDF: `BN68-25031G-00_SUG_Y26 TV ALL_AFRICA_L05_251230.0.pdf`,
`AFRICA_L05 / BOOK / ENG,FRA,SPA,POR,ARA`. 북마크 순서와 ARA 역방향 읽기는 유지했다.
작업장 `C:/Users/bella/image-extractor/.worktrees/xml-markdown-review`,
브랜치 `feature/xml-markdown-review`, 시작 HEAD `26aa7245075ea4113d0a11de8f37a43072d491f9`,
시작 미커밋 변경 없음.

## 원인과 수정

원본 PDF p35의 이 경고는 한 줄이다. 화면 자동 감김이 아니라 MCID104의 문장 분리 offset 27이
Markdown에 `<br>`을 넣었다. AFRICA BOOK ARA의 실제 경고 문자열과 9행 안전 표의 둘째 행,
ColSpan 2 셀, 단일 plain paragraph 구조를 확인하여 이 라벨을 한 단위로 유지한다.
다른 프로필·언어·문구·표 구조와 표 밖 동일 문구에는 일반 문장 분리를 계속 적용한다.
일반 경고 본문과 5개 언어 Eco Sensor 문단의 문장 분리도 유지한다.

Raw XML은 수정 전 실행과 byte 동일하다. Semantic XML 변경은 해당 text의 display-role,
sentence-break-offsets, sentence-break-reason 속성 3개 제거뿐이다. Markdown 전체 diff도 해당
`<br>` 하나와 그 표시용 줄바꿈 제거뿐이다. 원문 글자·순서·표·다른 언어에는 변경이 없다.
사용자 입력의 글자 모양을 다시 전사하지 않고 PDF에서 확인한 `لا`를 그대로 유지했다.

## 결과와 검증

최종 출력:
`C:/Users/bella/image-extractor/.worktrees/xml-markdown-review/samples/tagged_pdf_xml_poc/outputs/xml_review_africa_20260914_ara_safety_label_final`.
Raw/Semantic XML, MD, extraction_report, review_document, review_run을 함께 보존했다.

[새 HTML](../../outputs/xml_review_africa_20260914_ara_safety_label_review/semantic_document.preview.html),
[PDF와 실제 Markdown DOM 비교](../../outputs/xml_review_africa_20260914_ara_safety_label_review/label_comparison.png).
1360px Edge viewport에서 이 경고의 `<br>` 0개, 실제 text rect 한 줄을 확인했다.
HTML 전체 텍스트와 2,317개 구조 요소 서명은 같은 MD의 렌더링과 일치한다.
폭을 고정하는 nowrap CSS는 추가하지 않았다.

집중 테스트 328 passed / 1 skipped, 전체 XML POC 1,915 passed / 1 skipped.
기존 ZC/ZG, semantic XML/Markdown writer와 public import 호환 경로가 포함된다.
public import 3개 별도 확인. root `compileall src tests scripts` 및 POC `compileall src tests` 실행 성공.
root apps/scripts는 없으므로 scripts는 `Can't list scripts`, 존재하는 폴더는 정상 컴파일했다.
skip은 Windows symlink 사용 불가이다. 독립 리뷰 P1/P2 0개이며 reviewer의 8개 단위 테스트도 통과했다.

추출 Hard gate 0개. 원문/구조가 동일하므로 이전 196개 ENG–ARA 의미 대응과 언어별 구조 집계를
승계한다. 본문 제목 ENG/ARA 22, FRA/SPA/POR 21; P 128/121/121/121/128;
LI 모두 100; 표 14/13/13/13/14; 행 29/27/27/27/29; 셀 46/44/44/44/46;
그림 38/37/37/37/38. 안전 심볼·사양·구성품·Controller·마이크 특수 구조는 그대로다.
원문 의미 차이 9건과 기존 이미지 검토 기록은 이전 전체 보고서에서 확인할 수 있다.
이번 사용자의 직접 검토 의견은 ARA 표시 검토 기록에 추가했다.

변경 파일: XML POC `domain/africa_safety_label_readability.py`, `domain/readability_formatting.py`,
`tests/test_africa_safety_label_readability.py`, `tests/test_africa_book_integration.py`, 이 보고서와 root TODO.
다른 worktree, GridCell, item_review, Excel/Streamlit, DB는 변경하지 않았다.
기존 출력 폴더도 보존했다. 로컬 복구 commit 전체 번호는 최종 `review_run.json`에 기록한다.
