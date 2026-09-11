# 체크리스트 v2 이관 초안 — 2026-09-11

## 이번에 한 일과 하지 않은 일

기존 장부를 덮어 고치지 않고, 항목을 빠짐없이 옮긴 새 장부와 대조표를 만들었다.
원문·승인·적용 범위·ID·근거 기록을 보존했다는 확인이지, XML 자동 검토가 완성됐다는 의미는 아니다.
원본 DB, XML 추출기, 기존 앱은 수정하지 않았다. v2 자동 합격/불합격 판정에도 연결하지 않았다.

사용자가 확인한 `source_token`의 의미는 **어느 자료에서 후보 문구를 가져왔는지**다.
직접 작성한 10행의 빈 값도 정상 값으로 보존했다. 이 열을 적용 제한으로 오해하면 114개 규칙의
검사 대상이 줄어든다. 이 잘못된 제한을 실제 코드에 적용하지 않았다.
PDF 문서 자체의 `DocumentContext.source_token`과는 구분한다.

## 파일을 보는 방법

이 worktree의 `metadata/checklist_v2/drafts/20260911/`에 보존했다.

- `checklist_v2_draft.xlsx`: 사람이 읽는 새 DB 초안과 대조표.
- `checklist_v2_draft.json`: 위 Excel을 다시 읽어 내보낸 비활성 초안. 운영 JSON이 아니다.
- `migration_audit.json`: 원본 해시, 행별 상태, 프로필별 적용 대상과 근거 경로 조사 기록.

Excel은 다음 순서로 읽는다.

1. **Summary**: 전체 수량과 열 이름 변경 설명.
2. **Checklist_V2**: 원본 547행. 기존 순서와 17개 값은 그대로이고 아래 네 열 이름만 다르다.
3. **Migration_Audit**: 기존 승인 상태와 새 XML 검증 상태를 구분한 행별 대조표.
4. **Scope_Differences**: 출처 열을 적용 제한으로 잘못 사용하면 빠지는 대상. 실제 제외 목록이 아니다.

| 기존 열 | 초안 열 | 의미 |
|---|---|---|
| status | approval_status | 기존 사람의 승인 상태 보존 |
| source_token | source_reference_token | 후보 문구의 출처, 빈 값 허용 |
| section_heading | legacy_section_heading | 기존 제목 제약을 감사용으로 보존 |
| block_type | legacy_block_type | 기존 구조 제약을 감사용으로 보존 |

`pending`은 원문/승인은 보존했지만 XML 검토와의 호환성은 확인 전이라는 뜻이다.
`excluded` 두 행은 기존 review/deprecated 상태이므로 실행 대상에서 제외한다는 뜻이지 삭제가 아니다.
새 XML 역할이나 위치 선택 규칙을 legacy 두 열 이름에 맞춰 억지로 만들지 않는다.

이 파일은 이번 검증 시점의 **동결 초안**이다. 검토 의견은 별도 메모에 남기고 원본과 이 초안을
운영 DB로 교체하지 않는다. 아직 일반적인 DB 편집·운영 배포 도구를 제공하는 단계가 아니다.
초안을 편집하면 대조표는 과거 상태가 되며, 현재 export 명령은 원본과 다른 값을 거절한다.

## 확인 결과

- 원본 Excel↔기존 JSON: 547행 일치. 구 exporter의 공백 정리·scope 별칭·배열 변환을 적용해 대조했다.
- 원본 Excel↔저장된 v2 Excel↔v2 JSON: 547 × 17 = **9,299개 필드 값**, 행 순서, ID 전부 보존.
- 승인 상태: approved 545 / review 1 / deprecated 1. 승인 추가·삭제 없음.
- common_id 125개. 같은 common_id 복수 행은 국가별 연락처/모델별 항목일 수 있으므로 자동 합치기 없음.
- 동결된 구 exporter와 547행 변환 결과를 별도로 대조했다.
- 구 `metadata_matches`와 73개 프로필/언어 조합 × 547행 = **39,931건** 적용 대상 판단 일치.
- 출처를 제한으로 오해할 때 발생하는 차이: 114개 규칙, 681개 규칙/프로필/언어 조합.
- 테스트: 이관 31개, 루트 전체 169 passed / 6 subtests passed. compileall src/tests/scripts 통과.
- 네 시트의 미리보기 확인. 저장 파일의 요약 수식 캐시 값 검증, 오류 셀 0개.

근거 경로 조사 결과는 **과거 승인의 재심사 결과가 아니다**.

| 기록 상태 | 행 수 | 다음 확인 |
|---|---:|---|
| 파일 존재 | 406 | 파일 내용/최종 검수 여부는 별도 재검증 |
| 기록된 경로 없음 | 63 | 실제 최종 산출물 위치 찾기; 분실로 단정하지 않음 |
| 폴더만 지정 | 24 | 해당 폴더 안의 정확한 파일 연결 |
| 설명문으로만 기록 | 54 | 확인 가능한 실제 근거 파일 연결 |

승인 상태는 위 조사 때문에 임의로 변경하지 않았다. 기존 제약의 XML 대응도 미확인 상태다.

## 다음 작업의 안전 기준

1. ZC ENG의 작은 규칙 집합부터, XML에서 검사할 제목/문단/표 행을 찾는 규칙을 정한다.
2. 원문은 보존하고 비교용 정규화만 별도로 한다. `<br>`나 문장 수로 DB 행을 나누지 않는다.
3. 서로 다른 목록 항목·표 행·언어를 이어 붙여 문구가 있다고 판단하지 않는다.
4. 지원하지 않는 제약/역할은 검토 미완료로 드러낸다. 조용히 제외하거나 Pass로 처리하지 않는다.
5. 정확한 node_id·페이지·언어와 매칭 근거를 기록하고, 해당 프로필/언어만 검증 완료로 표시한다.
6. ZC ENG 이후 C-FRA, 다른 buyer ENG, 해당 localized 순서로 검증 범위를 넓힌다.

## 재실행 방법 — 개발용

PowerShell에서 이 worktree로 이동한 뒤, 새 출력 폴더 이름을 사용한다.

```powershell
Set-Location C:\Users\bella\image-extractor\.worktrees\xml-review-v2
python -m scripts.audit_checklist_migration audit --project C:\Users\bella\image-extractor --output outputs/checklist_audit_NEW
```

고정 원본 해시와 다르면 중단한다. 임의로 고정 해시를 바꾸지 말고 새 기준점 합의부터 한다.
Excel 작성용 `scripts/build_checklist_v2_draft.mjs`는 개발 환경의 Artifact Tool을 사용한다.
실제 Python 검토 앱의 Node 의존성은 아니다. 이번 작성 환경에서는 출력 폴더에 스크립트를 복사하고
그 폴더의 node_modules를 번들 런타임에 연결하여 실행했다. 일반 담당자에게 이 작성 환경 설치를 요구하지 않는다.

Excel을 만든 뒤에는 반드시 아래처럼 **Excel을 다시 읽는 export**를 사용한다.

```powershell
python -m scripts.audit_checklist_migration export --workbook outputs/checklist_audit_NEW/checklist_v2_draft.xlsx --audit outputs/checklist_audit_NEW/migration_audit.json --output outputs/checklist_audit_NEW/checklist_v2_draft.json
python -m pytest tests -q
python -m compileall -q src tests scripts
git diff --check
```

이번 Artifact Tool 작성 프로세스는 저장 완료 로그 뒤 종료 코드 1을 반환했다. 원인은 미확인이다.
따라서 작성 프로세스 자체의 정상 종료를 주장하지 않는다. 산출물은 별도 reader로 다시 열어
전체 값·수식 캐시·오류 셀을 확인했고, Excel→JSON export는 종료 코드 0으로 통과했다.
향후 반복 생성 도구로 배포하기 전에는 이 개발용 프로세스 종료 문제를 조사해야 한다.

## 복구와 식별

원본 복구: `4b001ff9a1a4f8ef91bed75a8ab314f4189d9476`.
이번 작업 전 XML 연결 완료 커밋: `920f8906efba72e84f7fdb53949607ff4b0e0e7b`.
돌아갈 필요가 있으면 해당 커밋으로 별도 worktree를 만든다. 현재 작업을 hard reset하지 않는다.
백업 사용 절차는 `2026-09-10-recovery_kr.md`를 따른다.

| 파일 | SHA256 |
|---|---|
| 원본 master.xlsx | d6b0d4a5f3fd57b8eb3b6ea303a444878b9431ba66eed9a15c3692da0c5fa706 |
| 원본 master.json | c6c65d8ba2a02d340b14cd9b7ae2a049fd83e461c44aca83edff4fb451784d90 |
| 초안 XLSX | e3aa4c4d255d9aa48775317a3ce2e22c5e8c446a928c28d7c704669dac163fa1 |
| 초안 JSON | 9c0ff6c536517905f9a9d675da67ebbc8eeea23beebe8a9ee82dbce370e62762 |
| 감사 JSON | 0ebbd8a8ff133143a3aa466025768b61f3a9b7f513c19838727f024c48a5808b |

원본 Excel의 최종 해시는 읽기 전용 Python 검사로 재확인했다. PowerShell Get-FileHash는
다른 프로세스의 파일 공유 상태 때문에 읽지 못했지만, 원본을 닫거나 수정하지 않았다.
