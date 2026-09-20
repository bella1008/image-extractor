# CE BOOK XML 검증 실행 계획

승인 범위: 기존 xml-markdown-review worktree / feature/xml-markdown-review에서 CE PDF를
현재 XML POC로 추출하고 필요한 결함 수정·검증·로컬 커밋까지 진행한다. 사용자 추가 승인 대기 없음.
GridCell/item_review/Excel/Streamlit/DB/다른 worktree를 수정하지 않는다.

입력: BN68-26318A-00_SUG_Y26 TV ALL_CE_L05_260422.0.pdf.
실제 프로필 CE_L05 BOOK 및 북마크 RUS p2, ENG p10, KAZ p18, MON p26, KYR p34.
44페이지. 시작 SHA 4aa80dd9193b972ebff4aa2af194c0abd59e74fb, clean.
근거 폴더 samples/tagged_pdf_xml_poc/outputs/xml_review_ce_20260914_evidence.

1. 수정 전 현재 추출기를 xml_review_ce_20260914_before에 실행하고 실패/진단을 기록한다.
2. PDF 표지·뒷표지·각 언어 모든 페이지를 렌더링한다. semantic source/page/path와 연결하고
   CE ENG를 검증된 ZC ENG 및 가까운 AFRICA/ZG BOOK ENG와 구조적으로 비교한다.
3. CE ENG 통과 후 RUS/KAZ/MON/KYR를 CE ENG와 제목별로 대응시킨다. 표/목록/모델조건/경고/UI,
   문자 보존/글꼴/읽기 순서를 확인한다. 원문 차이는 crop과 실제 추출 문자열로만 증명한다.
4. 결함은 실패 테스트부터 작성한다. 현재 XML POC의 CE 전용 프로필 경로에서 최소 수정하고
   매번 새로운 폴더에 추출한다. 번역이나 추측한 제목을 runtime mapping에 넣지 않는다.
5. 구조 Hard gate가 없어지면 집중/관련 회귀/public imports/compileall, 실제 Markdown DOM 보존
   검증을 실행한다. reviewer 검토를 거쳐 review bundle/HTML/한국어 보고서와 로컬 commit을 남긴다.

AFRICA의 전 언어 사용자 확정은 별도 acceptance 문서에 기록한다. 과거 결과 폴더는 보존한다.
