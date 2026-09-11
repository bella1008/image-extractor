# CHK-002 항목별 v2 원장

## 이 파일의 위치와 역할

이번 원장은 전체 547개 체크리스트를 교체하는 운영 DB가 아니다. `CHK-002-ZC-ENG` 한 묶음을 14개 구성품으로 관리하는 **별도 작성용 원장 초안**이다. 기존 원본 DB와 547행 이관 초안은 그대로 보존한다.

부모 항목은 기존 문구와 출처를 보존하는 연결 고리다. 부모 1개와 하위 14개를 15개의 검사로 중복 집계하지 않는다. 하위 항목은 `source_check_id + item_key`로 식별하고, Excel 행 순서나 XML 노드 번호는 항목 ID로 사용하지 않는다.

## 무엇을 입력하는가

편집 영역에는 다음 세 가지만 기록한다.

- `proposed_model_rule`: 특정 모델에 적용할 조건의 제안. 예: 담당자가 확인한 모델별 구성품 기준. 프로그램 명령어나 자동 실행 조건식이 아니다.
- `proposal_evidence`: 위 제안을 뒷받침하는 자료의 위치 또는 설명.
- `reviewer_note`: 검토 의견이나 보류 이유.

비어 있어도 내보낼 수 있다. 모르는 내용을 억지로 채울 필요가 없다. 제안을 입력하더라도 적용 여부는 `unknown`, 조건 확인은 `unverified`로 유지한다. 이 단계에는 승인 버튼이나 자동 합격/불합격 기능이 없다.

기존 문구, 고정 ID, 범위, 출처, XML 근거 등은 보존 영역이다. 실수로 바꾸거나 행을 삭제하면 JSON 내보내기가 중단된다. 문구 자체를 정식 개정하거나 새 항목을 추가하는 기능은 원문 대조를 수반하는 별도 개정 절차에서 연결한다.

## 문구 발견과 모델 적용은 다르다

`Power Box`라는 문구가 PDF 목록에 있다는 사실과, 특정 TV 모델에 Power Box가 반드시 제공되어야 한다는 기준은 다르다.

현재 원문에서 구성품 14개를 찾았고, 그중 12개에는 별표가 있다. 별표 항목 근처에는 TV 모델에 따라 일부 구성품이 포함되지 않을 수 있다는 안내가 있다. 이 안내와 항목의 관계는 근거 후보로 보존하며, 구체적인 모델별 필수 여부로 자동 번역하지 않는다. 별표가 없는 두 항목도 무조건 필수라고 확정하지 않는다.

보증서 항목의 지역 예외 괄호와 두 항목의 `x 2` 수량도 원문 그대로 보존한다.

## 파일 흐름

```text
검증된 PDF/XML 추출본 + 동결된 기존 DB
  → 출처와 원문이 고정된 작성 기준(seed)
  → 새 Excel 원장에 담당자 제안 기록
  → Excel 내용 검증
  → 별도 draft JSON
```

JSON의 입력은 Excel이다. seed는 출처가 바뀌거나 항목이 사라지지 않았는지 대조하기 위한 기준이며, 사용자가 JSON을 직접 고치는 흐름이 아니다. 결과 리포트용 Excel과 이 작성용 원장은 목적이 다르다.

내보내기 성공은 파일 구조와 보존 검사를 통과했다는 뜻이다. 업무 승인이나 모델 조건 검증 통과를 뜻하지 않는다. 현재 ReviewService는 계속 기존 동결 DB 관찰 경로를 사용하며, 이 파일로 자동 교체되지 않는다.

## 이후 연결 순서

1. 이 원장 구조와 편집·검증 경로를 실물로 검증한다.
2. 모델별 적용 기준을 확인할 수 있는 자료와 사람의 승인 절차를 연결한다. 자료가 없는 항목은 보류할 수 있어야 한다.
3. 나머지 항목 묶음과 표 관계도 각각 원문을 확인해 정의한다. 줄바꿈 수만 보고 자동 분리하지 않는다.
4. 그다음 항목별 evaluator, 결과 리포트, 화면과 PC 실행 도구를 연결한다.

따라서 지금 전체 DB를 다시 입력하거나 모델 조건을 즉시 확정할 필요는 없다.

## 시트를 읽는 방법

| 시트 | 용도 | 수정 여부 |
|---|---|---|
| Items | 14개 하위 항목. `required_text`는 기준 문구, 노란색 세 열은 담당자 제안 | 노란색 세 열만 수정 |
| Parent | 기존 CHK-002 원본의 17개 필드. 과거 approved 이력도 그대로 보존 | 보존 |
| Source Evidence | 실제 원문·조건 안내와 노드 ID·태그·페이지 | 보존 |
| Source | PDF 이름과 정확한 추출본 해시, 원문 구간 등 | 보존 |
| Guide | 입력 칸과 미확정 상태의 의미 | 보존 |

`Items.evidence_refs`와 `condition_refs`는 Source Evidence의 `evidence_id`를 가리킨다. 하나의 항목에 여러 근거를 연결할 수 있다. XML의 실제 위치 번호는 Source Evidence의 `source_node_ids`에서 확인한다. 이 둘은 서로 다른 ID다.

Source Evidence의 `details_json`은 전체 근거 구조를 보존하는 기술 상세다. 평소에는 왼쪽 원문·노드·태그·페이지 열을 보면 된다. 원문의 공백까지 보존하므로 눈에 보이는 모양을 정리하려고 내용을 다시 입력하지 않는다.

이 파일은 수식을 실행하는 계산용 Excel이 아니다. 수식·오류 셀이 입력되면 거부한다. 메모가 `=`로 시작해야 한다면 Excel에서 앞에 작은따옴표를 붙여 일반 텍스트로 입력한다.

## 실제 파일과 사용 방법

작업 폴더: `C:\Users\bella\image-extractor\.worktrees\xml-review-v2`.

- 편집할 파일: `outputs/item_master_20260911/checklist_item_master.xlsx`.
- 처음 생성한 원장 보관본: `metadata/checklist_v2/item_master_drafts/20260911/checklist_item_master.xlsx`.
- 원문 대조 기준: 같은 보관 폴더의 `master_seed.json`.
- 최초 Excel에서 내보낸 결과: 같은 보관 폴더의 `checklist_item_master.json`.

1. 편집할 Excel을 열고 `Items`의 노란색 세 열에 필요한 제안·자료·메모를 입력한다. 지금 바로 입력하지 않아도 된다.
2. 저장하고 Excel을 닫는다.
3. 아래 명령을 실행한다. 두 번째 실행부터는 `my_item_draft_01.json`을 `my_item_draft_02.json`처럼 새 이름으로 바꾼다. 기존 파일을 덮어쓰지 않는다.

```powershell
Set-Location C:\Users\bella\image-extractor\.worktrees\xml-review-v2
.venv\Scripts\python.exe -m scripts.export_item_master outputs/item_master_20260911/checklist_item_master.xlsx --seed metadata/checklist_v2/item_master_drafts/20260911/master_seed.json --expected-seed-sha256 2229a46be82d9f7b3a6aa316c079eea93f15481050d2e44020c850ddfc73e268 --output outputs/item_master_20260911/my_item_draft_01.json
```

긴 해시값은 현재 대조 기준의 고정 번호다. 위 명령을 그대로 사용하면 된다. 오류를 없애려고 변경된 seed의 해시를 새로 계산하여 끼워 넣으면 보존 검사를 우회하므로 그렇게 사용하지 않는다. 새 기준 개정 시에는 원문 재검증 후 별도 번호로 발행한다. 해시는 변경 감지용이며 누가 승인했는지를 인증하지는 않는다.

내보내기가 실패하면 기존 파일은 유지된다. `immutable source changed`는 보존 칸 변경, `row count differs`는 행 개수 변경, `formula/error cell`은 수식 또는 오류 셀, `use a fresh output`은 이미 있는 출력 이름을 뜻한다. 오류를 무시하거나 JSON을 직접 고치지 말고 해당 입력을 확인한다.

개발 시 원문을 다시 검증하여 새 seed를 준비하는 명령:

```powershell
$env:PYTHONPATH = (Resolve-Path samples/tagged_pdf_xml_poc/src).Path
.venv\Scripts\python.exe -m scripts.prepare_item_master outputs/review_service_zc_20260911_r2 "samples/SUG_RAW/TV_ZC/BN68-25100B-00_SUG_Y26 TV ALL_ZC_L02_260122.0.pdf" --output outputs/new_item_master/master_seed.json
```

원장 최초 제작용 JavaScript는 개발 환경의 Artifact Tool을 사용한다. 동료 PC에서는 이 도구가 필요 없다. Excel 편집과 Python 내보내기만 사용한다. 다만 현재는 개발 작업장용 경로이며, 동료 PC용 배포 묶음이나 일반 화면 연결까지 완료한 것은 아니다.

## 검증 기록

- 변경 전 기준: `5949efabccbb595b32e64fda6ccf35365098b192`. 변경 전 333개 테스트 통과.
- 실제 ZC 추출본을 다시 검증해 seed 생성. 독립 검토에서도 원본 PDF/XML/추출 완료 기록/동결 Excel과 정확히 일치함을 확인했다.
- 생성 Excel의 전체 셀을 seed와 대조하여 JSON 내보내기 통과: 부모 17필드, 하위 항목 14개, 원문 및 조건 후보 근거 26개, 조건 참조가 있는 항목 12개.
- 5개 시트와 상세 영역 렌더 확인. Items는 `C2` 고정 창, 나머지는 `A2`. 모든 표의 필터, 노란색 편집 칸, 수식·오류 셀 없음 확인.
- 편집 제안·메모 보존, 행 순서 변경, 누락/중복/출처 수정 거부, 수식/오류 거부, 저장 중 입력 변경, 기존 출력 덮어쓰기 방지는 자동 테스트로 검증한다. Excel 데스크톱에서 직접 클릭하여 편집하는 검수는 수행하지 않았다.
- 원장 보관본 SHA256: `7cf4cf627c20f58fea299a1dde6855a068fc1d7ace2b54ca4cff720f740b035c`. JSON에 기록된 입력 Excel 해시와 일치한다.
- 새 집중 테스트 29개, 기존 항목 제안 테스트와 합쳐 46개 통과. 전용 v2 전체 `python -m pytest tests -q`는 362개 통과, `compileall -q src tests scripts` 통과. `apps` 폴더는 없다. 추출 코드는 바꾸지 않았으며 별도 XML POC 전체 테스트를 이번에 다시 실행한 것은 아니다.
- 독립 명세 검토와 코드 품질 검토 통과. 메인의 기존 DB Excel/JSON 해시는 기존 복구 기준과 동일하다. 작성용 임시 의존성 연결만 제거했으며 실제 공용 라이브러리나 기존 산출물은 삭제하지 않았다.
