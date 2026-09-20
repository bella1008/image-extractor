# CE 문장 소속 수정의 기존 바이어 적용 범위 확인

사용자 요청: CE에서 수정한 (1) 전원 첫 불릿의 연속문장과 (2) 서비스 비용 도입문 아래 (a)/(b) 조건을 다른 바이어·언어, 특히 유럽 ZG에서도 검토했는지 확인.

작업 브랜치 feature/xml-markdown-review, 시작 HEAD `7f6c77fb107e42f114a5ae2621c9b446b3443a49`, 시작 미커밋 변경 없음. 이 요청에서는 기존 결과를 감사하고 현행 코드로 다시 추출했다. Runtime 규칙을 확장하거나 수정하지 않았다.

## 기존 검증 범위의 정정

CE의 이전 수정은 RUS/ENG/KAZ/MON/KYR 5개 언어에 대해 실제 PDF 기반 두 구조를 검증했다. ZC/ZG/AFRICA 회귀 테스트 통과는 이 두 관계를 모든 바이어·언어에서 직접 검수했다는 뜻이 아니다.

기존 `tests/test_layout_regression.py::_assert_zg_continuation_source_equivalence`는 ZG FRA의 전원 연속문장에 display-role=list-continuation이 생기는지 직접 검사한다. 이 검사만으로 모든 언어의 소속을 보증하지 못한다. 비용 안내 두 하위 조건의 소속을 ZG/XU에서 검사하는 해당 전용 회귀는 없었다. 1,980개 통과라는 이전 결과는 사실이지만 검사 범위의 빈틈이 있었다.

## 현재 코드 재추출 결과

파일명/profile mapping 및 BOOK 북마크로 바이어·언어를 확인했다. 각 바이어는 새 폴더에 재추출했다. 현재 extractor의 기본 gate는 모두 PASS지만, 이번에 PDF 원문과 실제 HTML DOM으로 확인한 소속 gate는 아래처럼 실패한다.

| 바이어/source_token | 문서 유형 | 확인 언어 | 1. 전원 연속문장 | 2. 비용 하위 조건 |
|---|---|---|---|---|
| ZG XN ZT_L05 | BOOK | ENG/DEU/FRA/ITA/DUT | 5개 모두 기존 연결 처리 확인 | 5개 모두 독립 문단, 미해결 |
| ZC_L02 | A2 | ENG/C-FRA | ENG 연결, C-FRA 독립 문단 미해결 | 대응 조건 검사 대상 없음 |
| AFRICA_L05 | BOOK | ENG/FRA/SPA/POR/ARA | ENG/FRA/SPA/POR 연결, ARA 독립 문단 미해결 | 대응 조건 검사 대상 없음 |
| LATIN_L02 | A2 | ENG/M-SPA | 2개 모두 기존 연결 처리 확인 | 대응 조건 검사 대상 없음 |
| XU_ENG | A3 | ENG | 기존 연결 처리 확인 | 독립 문단, 미해결 |

5개 바이어, 15개 언어. 전원 관계 15곳: 연결 13, 결함 2. 비용 관계 6개 언어 묶음: 결함 6. 합계 8개 구조 차단 문제이며 수정 완료로 보고하지 않는다. CE 5개 언어의 수정 검증 결과는 유지된다. 아직 확인하지 않은 다른 바이어·파일·언어로 일반화하지 않는다.

## 원문 및 렌더링 근거

- ZG 원문 전원 p2/12/22/32/42: 첫 불릿의 이어지는 설명. 현재 semantic XML은 원본 paragraph를 유지하면서 list-continuation과 preceding-list-item/body 경로로 소속을 명시한다. Markdown을 렌더링한 HTML에서도 같은 LI 안에 있다. CE의 span 재배치와 내부 표현 방식은 다르지만 소속은 연결되어 있다.
- ZC C-FRA 원문 p2: 전원 설명의 첫 불릿과 같은 들여쓰기이며 새 불릿 기호가 없다. 현재 XML/HTML에서 독립 paragraph/P로 분리됨.
- AFRICA ARA 원문 p35: RTL 첫 불릿 아래 동일 들여쓰기의 설명이다. 현재 XML/HTML에서 독립 paragraph/P로 분리됨. 기존 사용자 검토 이력은 보존하되, 이 구체적인 소속 결함은 새 미해결 항목으로 기록한다.
- ZG 비용 원문 p8/18/28/38/48: 각 언어 도입문보다 (a)/(b)가 들여쓰기되어 있다. 현재 semantic XML은 세 paragraph를 형제 노드로 두고, HTML도 세 개의 독립 P다.
- XU ENG 비용 원문 p2: ZG ENG와 같은 관계 및 같은 분리 결함.
- 모든 21개 관계를 원문 crop 및 현재 Markdown 렌더링과 연결했다. HTML DOM에서 전원 target의 LI 조상 유무와 비용 도입문 다음 노드가 P인지 확인했다. pipeline PASS와 별도로 실패를 기록했다.
- 번역 의미를 변경하거나 추정한 현지어 표현을 runtime mapping에 추가하지 않았다. 외부 의미 검토 API를 사용하지 않았다.

## 후속 수정 범위

- ZC_L02 A2 C-FRA, AFRICA_L05 BOOK ARA: 첫 불릿 전원 연속문장 소속과 줄바꿈 회귀 추가.
- ZG XN ZT_L05 BOOK 5언어, XU_ENG A3 ENG: 비용 도입문 아래 두 조건의 소속 회귀 추가.
- 이미 연결된 ZG 등 13곳의 소속을 보존하고, 각 source_token/doc_type/language 및 실제 PDF 근거에 맞춰 수정해야 한다. CE에 사용한 규칙을 이름만 바꿔 무조건 적용하지 않는다.
- 위 8개를 수정한 뒤 새 출력에 원문/문자/DOM 검사와 관련 회귀를 수행해야 한다. 이번 감사는 수정 전 상태를 확인한 것이며 해당 바이어의 재승인이 아니다.

## 산출물

절대 경로:
`C:/Users/bella/image-extractor/.worktrees/xml-markdown-review/samples/tagged_pdf_xml_poc/outputs/xml_review_cross_buyer_20260914_ownership_audit`

- ownership_findings.html: 21개 관계의 PDF crop와 현재 Markdown 표시 비교
- ownership_audit.json: 언어/페이지/노드/소속/DOM 결과
- manifest.json: 입력 파일명, SHA256, profile, 실제 북마크, 추출 HEAD
- source_regions.json: 원문 영역 정보 (ARA p35 이미지는 RTL 왼쪽 열의 전원 영역으로 수동 crop 보정)
- ZG, ZC, AFRICA, LATIN, XU 하위 폴더: raw_structure.xml, semantic_document.xml, semantic_document.md, extraction_report.json, semantic_document.preview.html, review_document.json, review_run.json
- extract_current.py/build_audit.py/render_audit.cjs: 이번 확인 재현 보조 스크립트

Runtime 또는 테스트 코드는 수정하지 않았으므로 전체 pytest/compileall을 다시 실행하지 않았다. 현행 코드로 실제 PDF 5개를 재추출하고, 별도 21개 소속 검사를 수행했다. 과거 테스트 수를 이번 검사 수로 다시 주장하지 않는다.
