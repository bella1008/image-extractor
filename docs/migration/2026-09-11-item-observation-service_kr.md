# 새 원장과 현재 PDF의 항목별 검토 연결

## 이번 단계의 의미

원장에 14개 항목을 저장하는 것에서 한 단계 더 나아가, **검토할 PDF에서 그 14개 항목의 원문을 다시 찾는 경로**를 연결한다. 기존 547행 검토 경로와 별도이며, 아직 업무상 합격·불합격을 결정하는 evaluator는 아니다.

예를 들어 원장을 만들었던 PDF에서 Power Box가 발견됐더라도, 새 PDF에서도 발견됐다고 간주하지 않는다. 새 PDF의 XML을 다시 읽고 해당 제목 범위 안의 목록을 조사한다. 새 문서에 없는 항목에 예전 문서의 근거를 붙이지 않는다.

## 입력과 출력

```text
항목 원장 Excel + Excel에서 내보낸 JSON + 고정된 원문 대조 기준
  → 세 파일이 일치하는지 검증

검토 대상 PDF → XML 추출/품질 검사 → ReviewDocument
  → 원장의 14개 항목을 현재 문서에서 조사
  → 항목별 JSON + 완료 기록 → 같은 폴더에 결과 Excel 추가
```

이미 검증된 XML 추출 묶음이 있으면 PDF→XML 과정을 생략하고 재사용할 수 있다. 이 경우에도 원본 PDF와 추출 기록·해시는 다시 검증한다. Markdown은 묶음의 무결성 확인에 포함하지만, 검토 문구를 Markdown에서 파싱하지 않는다.

원장을 편집하고 JSON을 다시 내보내지 않았거나 JSON만 직접 고쳤으면 검토 시작을 거부한다. 제안·메모가 원장과 결과 JSON 사이에서 서로 달라지는 일을 막기 위한 검사다.

## 결과를 읽는 방법

사용자용 결과는 계속 `검토 판정`과 `설명` 두 열로 읽는다. 판정은 모두 `검토 필요`이며 설명으로 다음을 구분한다.

| 내부 구분 | 의미 |
|---|---|
| found | 현재 제목 범위에서 항목 전체 문구에 대응하는 목록 근거가 한 곳 있음 |
| ambiguous | 항목 전체 문구가 여러 곳에 있어 대응 위치 확인이 필요함 |
| not_found | 조사한 범위의 목록에서 전체 문구를 찾지 못함. 아직 업무상 누락 판정은 아님 |
| not_examined | 제목·언어·적용 범위를 확정하지 못해 항목 조사를 하지 못함 |

`Power Box`와 `Power Box Cable x 2`, `Remote Control`과 `Standard Remote Control`은 서로 다른 항목이다. 단순 부분 문자열 포함 여부로 섞지 않는다. 기존 공백 비교 규칙과 별도로 기록하는 원문 선두 별표만 허용하며 수량과 괄호 조건은 보존한다.

부모 CHK-002는 이전 DB와 연결하기 위한 기록이다. 부모와 하위 항목을 합쳐 15개 검사로 세지 않는다.

## 현재 근거와 과거 출처를 구분한다

화면과 Excel Summary의 **검토 대상 PDF**는 이번에 조사한 문서다. 상세 근거의 노드 ID·태그·페이지와 조건 안내도 이 문서에서 가져온다. JSON의 `target_source`에 파일명과 PDF/XML 해시가 들어간다. 해시와 내부 파일 경로는 사용자 요약에 표시하지 않는다.

**원장 작성 당시 출처**는 원장을 처음 만들 때 참고한 문서다. JSON의 `master_source`에 별도로 남긴다. 두 파일명이 같아도 해시가 다르면 다른 추출본일 수 있다.

담당자 제안은 각 항목의 `author_proposal`에 보존한다. 제안문을 실행하거나 그 내용으로 적용 여부를 자동 승인하지 않는다. 모델 적용은 `unknown`, 조건 관계는 `unverified`로 유지한다.

## 안전 경계

- 현재 지원은 ZC_L02 / A2 / ENG의 CHK-002 항목 파일럿이다. 다른 바이어·언어를 지원한다고 표시하지 않는다.
- 별표 조건 안내를 찾는 것과 실제 모델별 필수 여부를 결정하는 것은 별개다.
- 기존 DB와 새 작성 원장을 변경하지 않는다. 새 실행은 별도 출력 폴더를 사용한다.
- 입력이 실행 중 바뀌거나 저장된 결과가 생성 내용과 다르면 완료 기록을 발행하지 않는다. 실패 폴더는 진단용으로 남기고 재사용하지 않는다.
- 완료 기록 없이 JSON만 있다고 정상 완료로 취급하지 않는다. `read_completed_item_review`는 완료 기록과 파일 해시를 함께 검증한다.
- 새 실행에서는 HTML을 생성하지 않는다. 과거 v1 완료 기록을 읽을 때만 그 기록에 포함된 기존 HTML까지 검증한다.

지금 사용자에게 모델 적용 기준의 즉시 확정을 요구하지 않는다. 기준 자료와 승인 절차가 준비될 때 실제 업무 판정을 별도로 연결한다.

## 실행 방법 — PowerShell

다음은 이 작업장에 이미 설치한 전용 Python 환경을 사용하는 명령이다. `--output`은 **아직 없는 폴더 이름**으로 매번 바꾼다. 원장 위치를 생략하면 `metadata/checklist_v2/item_master_drafts/20260911/`의 검증된 세 파일을 사용한다.

```powershell
Set-Location 'C:\Users\bella\image-extractor\.worktrees\xml-review-v2'
$env:PYTHONPATH = (Resolve-Path 'samples/tagged_pdf_xml_poc/src').Path
$env:PYTHONIOENCODING = 'utf-8'

# PDF를 새로 추출하고 항목별 근거를 조사한다.
.venv/Scripts/python.exe -m scripts.run_item_review_v2 'samples/SUG_RAW/TV_ZC/BN68-25100B-00_SUG_Y26 TV ALL_ZC_L02_260122.0.pdf' --output outputs/my_item_review_001

# 또는, 검증된 기존 추출 묶음을 재사용한다. 위의 환경 설정은 이 경우에도 필요하다.
.venv/Scripts/python.exe -m scripts.run_item_review_v2 'samples/SUG_RAW/TV_ZC/BN68-25100B-00_SUG_Y26 TV ALL_ZC_L02_260122.0.pdf' --output outputs/my_item_review_002 --bundle outputs/review_service_zc_20260911_r2/extraction
```

완료하면 다음 파일이 생긴다.

- `item_observation.json`: 현재 근거와 원장 정의가 함께 저장된 기계 판독용 결과.
- `item_review_complete.json`: JSON이 완성됐고 내용이 일치함을 확인하는 v2 기록. 업무 승인서는 아니다.
- `extraction/`: 새 PDF 추출 모드에서만 생성하는 XML·MD·ReviewDocument·추출 완료 기록.

Excel 작성 환경을 설정한 후 `.venv/Scripts/python.exe -m scripts.export_item_review_excel outputs/my_item_review_001`을 실행하면 **동일 폴더**에 `item_review.xlsx`가 추가된다. 설정과 화면 사용법은 [Excel·화면 안내](2026-09-11-item-excel-ui_kr.md)를 따른다.

실패하면 가능한 경우 `item_review_failed.json`에 원인이 남는다. 실패한 출력 폴더는 진단용이며 정상 결과로 사용하지 않는다. 환경이나 입력을 수정한 뒤 **다른 새 출력 폴더**로 실행한다. 이미 만든 결과를 프로그램에서 읽을 때는 JSON만 직접 읽지 않고 다음 검증 함수를 사용한다.

```python
from pathlib import Path
from src.item_review_service import read_completed_item_review

report = read_completed_item_review(Path('outputs/my_item_review_001'))
print(report['summary'])
```

이 함수는 보관된 결과의 해시와 상태를 검증한다. 나중에 입력 PDF가 이동해도 보관 결과를 읽을 수 있지만, 기록된 해시는 전자서명이나 업무 승인 증명이 아니다.

## 2026-09-11 실물 실행 결과

- 새 PDF 실행: `outputs/item_review_zc_20260911_fresh/`.
- 검증 묶음 재사용: `outputs/item_review_zc_20260911_reuse_r2/`.
- 두 실행의 항목 결과 전체가 동일: 14개 중 단일 근거 14개, 복수 근거/미발견/범위 미확정 각 0개, 조건 안내 후보가 있는 항목 12개.
- 14개 모두 `needs_review`, 모델 적용 `unknown`, 조건 관계 `unverified`. 기존 547행 결과와 별도이며 합산하지 않는다.
- 새 Semantic XML과 Markdown은 이전 검증 실행과 바이트 단위로 동일하다.
  - XML SHA256: `8cecca8b0f41583e961a486d2bd157b81c9a59d7f4bc7ec87e47d5a0b1d6354c`
  - MD SHA256: `0acc00334f304e45ba764ebd646bb17e9c1269ef86dbf77a872235d7de575dbc`
- 첫 재사용 시도 `outputs/item_review_zc_20260911_reuse/`는 실행 명령에서 `PYTHONPATH`를 빠뜨려 실패했다. 완료 기록이 없고 실패 기록만 남았다. 환경 설정을 포함한 위 명령으로 새 폴더에서 재실행해 성공했다.
- HTML 자동 검사는 통과했다. 이 세션의 브라우저 도구가 로컬 파일 열기를 정책상 차단해 **브라우저 실물 렌더 검수는 수행하지 못했다**. 다른 경로로 제한을 우회하지 않았으며, 배포 양식 승인을 받았다고 간주하지 않는다.

## 다음 연결 범위

기술 검증: 새 항목 연결 집중 테스트 73개와 루트 전체 테스트 435개 통과, `compileall src tests scripts` 통과. 독립 명세 검토와 코드 품질 검토도 통과했다. 기존 XML POC 전체 테스트를 이번에 다시 실행했다는 의미는 아니다. 원본 DB Excel/JSON, 동결 547행 초안, 새 항목 원장 세 파일의 해시는 이전 값과 동일하다.

2026-09-11 당시 검증 기록은 위에 보존했다. 2026-09-13 현재는 같은 폴더에 결과 Excel을 추가하고 Streamlit에서 읽는 경로까지 연결했으며, 새 HTML은 생성하지 않는다. 다른 체크리스트의 항목 분리와 모델 조건에 따른 업무 판정은 후속 범위다. 작성용 원장 Excel과 검토 결과 Excel은 서로 다른 용도다.
