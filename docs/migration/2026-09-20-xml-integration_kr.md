# 최신 XML 추출기 통합 기록 — 2026-09-20

## 범위와 복구 기준

- 작업장: `codex/xml-review-v2`. 기존 최상위 작업장과 원본 XML 작업장은 변경하지 않았다.
- 통합 전 v2: `e5076d5e3163266f535cae829042400adfef8bc3`.
- 로컬 복구 브랜치: `codex/pre-xml-integration-20260920`.
- 통합한 XML 추출기: `813489261096f87cf6a613e5cb1feeb0fd2914a6`.
- 공통 출발점: `840512002a80a12b19c712116530ab69b1459c3a`.
- 최신 추출기 source SHA-256: `f46c72b75627f030ec7ec78c5cd34e3eede2b2e50edaf3a53407f8db97991477`.
- 기존 복구 커밋·Git bundle·다른 worktree·기존 결과는 삭제하지 않았다. 원본 DB와 프로필 매핑도 수정하지 않았다.
- 원격 push는 하지 않는다. 이 통합에 포함된 XML 원본의 최근 3개 커밋은 기존 원격 백업보다 최신이다.

## 무엇을 합쳤는가

`PDF → 최신 XML/사람 확인용 MD → adapter → ReviewDocument → 현재 ZC ENG 체크리스트 관찰 → 통합 Excel/JSON`.

추출기 `src/tagged_pdf_extractor`는 incoming 커밋과 동일하다. 추출 문구·RTL 보정·문단 배치 규칙을 v2 쪽에서 다시 만들지 않았다. 수정한 연결부는 `src/xml_review_gate.py`, `src/xml_source_replay.py`, `src/semantic_xml_reader.py`다. Markdown을 읽어 기계 검토 데이터를 만드는 방식은 아니다.

새 추출기는 원본 raw XML과 사람이 읽는 semantic XML의 노드 위치가 항상 같지 않다. 원문 근거가 있는 문단 재배치, 합성 목록 묶음, RTL 글자/순서 복원 때문이다. 새 계약 `tagged-pdf-xml/8134892`는 PDF·프로필·추출기 해시를 확인하고 같은 원본에서 네 산출물을 재현해 대조한다. 검증 후에만 구조가 정렬된 임시 데이터로 adapter의 값·언어·노드 검사를 수행한다. 원본 raw XML은 바꾸지 않는다. 경로 이동 시 raw/report의 원본 디렉터리만 비교에서 정규화한다.

이것은 추출 결과의 기술적 일관성 검사이며, 같은 추출기 자체가 원본 내용을 완벽하게 해석했다는 독립 증명은 아니다. PDF와 사람의 확인 기록은 별도로 유지한다.

### 호환성 처리

- 과거 `8405120` 계약 결과는 기존의 엄격한 raw/semantic 위치·값 검사로 읽는다. 과거 receipt나 산출물의 해시를 새 값으로 덮어쓰지 않는다.
- 새 추출기의 `info` 기록은 원본 재현까지 일치해야 수용한다. `error`와 알 수 없는 severity는 차단한다.
- AFRICA의 Jordan Only 헤딩 차이는 검증된 원본 해시와 예외 근거, 원래 불일치 기록을 모두 유지한다. 언어별 헤딩 수를 억지로 동일하게 만들지 않는다.
- AFRICA에서 두 언어에 걸친 Article 3개는 언어 미배정으로 둔다. 각 하위 노드·문장은 검증된 언어를 유지한다. 상위 Article 전체를 단일 언어의 매칭 구간으로 쓰지 않는다.
- ReviewDocument schema는 `/1` 유지. 원문 구조·표시 속성·출처 경로는 보존하고 새 업무 role을 임의로 부여하지 않는다.

### 성능상 제한

안정화 단계에서는 검증마다 원본을 재현한다. 현재 새 PDF의 통합 실행은 최초 추출 1회와 검증용 재현 5회를 수행할 수 있다. 추가 결과를 사용자에게 중복 제공하는 것은 아니지만 실행 시간이 증가한다. 해시로 묶인 실행 단위 검증 근거 재사용은 후속 최적화다. 검증을 생략하거나 실패 gate를 통과시키는 방식으로 속도를 높이지 않는다.

## 회귀 검증

- 통합 전 v2: `600 passed, 4 skipped`.
- 통합 전 최신 XML: `2524 passed, 1 skipped`.
- 통합 후 XML 전체: `2524 passed, 1 skipped`. 명시적으로 표본 필수 모드 사용. skip은 Windows symlink 권한 관련 1개.
- 최종 v2 전체: `616 passed, 4 skipped` (421.39초). skip 4개는 선택적 Node/Artifact 작성 경로이며, 기본 Python 작성기와 실제 ZC XLSX는 별도로 통과했다.
- 바이어별 실제 재추출: 14 PDF / 32개 프로필·언어 조합 기술 검사 통과. 정확한 파일·해시는 [실행 근거](evidence/20260920-xml-integration.json)에 보존한다. XL은 공식 프로필 누락으로 별도 차단했다.
- 마지막 코드 수정 후 `compileall src tests scripts` 통과. POC src/tests/scripts도 컴파일 통과. `pip check`: broken requirements 없음. `git diff --check` 통과.
- 구조/문구/표시 속성/노드 순서 보존 검사는 `scripts/audit_xml_integration.py`로 재실행할 수 있다. 매번 새로운 출력 폴더를 지정한다.

| 표본 | 검증 언어 | ReviewDocument 노드 | 최종 실행 폴더 (`outputs/` 아래) |
|---|---|---:|---|
| ZC_L02 | ENG, C-FRA | 3780 | xml_integration_20260920_r1/ZC_L02 |
| XU_ENG | ENG | 2378 | xml_integration_20260920_r1/XU_ENG |
| ZG XN ZT_L05 | ENG, DEU, FRA, ITA, DUT | 12864 | xml_integration_20260920_r1/ZG_XN_ZT_L05 |
| AFRICA_L05 | ENG, FRA, SPA, POR, ARA | 8887 | xml_integration_20260920_r4/AFRICA_L05 |
| CE_L05 | RUS, ENG, KAZ, MON, KYR | 10604 | xml_integration_20260920_r1/CE_L05 |
| TK_L02 | ENG, TUR | 4728 | xml_integration_20260920_r1/TK_L02 |
| TK_ARA | ARA | 2513 | xml_integration_20260920_r2/TK_ARA |
| MENA_L02 | ENG, ARA | 3957 | xml_integration_20260920_r2/MENA_L02 |
| SQ MI_HEAR | HEB, ARA | 4259 | xml_integration_20260920_r2/SQ_MI_HEAR |
| XT_L02 | ENG, THA | 3706 | xml_integration_20260920_r1/XT_L02 |
| ZW_TPE | TPE | 2362 | xml_integration_20260920_r2/ZW_TPE |
| PY_ENRU | RUS, ENG | 4674 | xml_integration_20260920_r1/PY_ENRU |
| UA_ENG | ENG | 2244 | xml_integration_20260920_r1/UA_ENG |
| XD_INS | INS | 3376 | xml_integration_20260920_r1/XD_INS |

초기 실패 폴더는 진단 이력으로 남겼다. 같은 이름의 r1/r2 실패를 최종 결과로 사용하지 않는다. 최종 완료 여부는 `review_run.json` 존재와 소비자 검증으로 확인한다.

### ZC 결과 레포트

기존 `outputs/checklist_reviewer_zc_20260915_python`과 새 `outputs/checklist_integrated_zc_20260920_r1` 비교:

- 547행 동결 DB 유지, 적용 체크 59건, 구성품 14건, 조건 안내 후보 12건.
- 기존 관찰 분포·항목별 결과·업무 미판정 상태 동일. 새 Pass/Fail 또는 DB 승인 없음.
- Excel 4시트, Summary 12행 유지. 1,232개 셀 위치의 값·스타일, 행높이·열너비·고정창 동일. 표시용 JSON도 동일.
- 검토자 양식 변경이 없으므로 이 통합 때문에 Excel 양식을 다시 확인할 필요는 없다. 기존에 예정한 사용성 검토는 별도다.

독립 코드 검토에서 신규 source replay와 과거 archive 호환을 확인했다. 실제 구/신 ZC archive의 노드 3,780개 재구성이 모두 가능했다. AFRICA의 언어를 지정한 상위 노드에 다른 언어의 텍스트 자손이 들어 있지 않은 것도 별도 확인했다.

배포 확인용 ZIP(`outputs/review_pilot_20260920_integration_check`)은 133개 파일의 해시를 검증하고, 한글·공백 경로에서 `start_review.py --check`와 새 PDF 입력→ZC Excel/JSON 전체 실행을 통과했다. 최종 커밋 기준 ZIP은 후속 배포 확인 기록을 따른다. 이번 실행은 현재 PC의 다른 경로 테스트이며 다른 물리 PC에서의 재설치를 했다는 뜻은 아니다.

### 최종 커밋·배포 확인

- 병합 커밋: `52ca5d79985ac485e9e232ddbe8c28f91f65eef9`. 부모는 기존 v2 `e5076d5`와 최신 XML `8134892`다.
- 최종 ZIP: `outputs/review_pilot_20260920_integrated/review-pilot.zip`.
- ZIP SHA-256: `d4c27dcf554b4f2bf7654a0479d3820013e64b7ae64dd1752e6019651df3f09a`.
- manifest source_revision은 위 병합 커밋이며 working_tree_changed=false, 배포 파일 133개다.
- 압축 해제 위치 `outputs/review_pilot_20260920_integrated/최종 실행 검증`에서 PYTHONPATH를 비우고 self-check 및 새 PDF→ZC Excel/JSON CLI 전체 실행을 다시 통과했다. 실행 결과 `outputs/zc_fresh`의 완료 기록과 표시 JSON도 확인했다. 기존과 체크59/구성품14 및 표시 내용 동일.
- 코드 수정은 이 병합 커밋에 모두 포함된다. 이후 배포 확인 기록을 저장하는 문서 전용 커밋은 ZIP의 프로그램 코드와 다르지 않다.
- GitHub push, `main` 전환, 기존 worktree 삭제는 하지 않았다.

## 다른 PC로 옮길 때 발견한 사항

- 배포 builder가 현재 경로만 지워서 과거 작성자의 경로가 동결 원장 출처에 남던 문제를 재현했다. 배포 snapshot에서만 과거 worktree 경로를 정리하고 Excel/JSON/seed 해시를 다시 맞춘다. 원본 DB 바이트는 그대로다.
- 일부 XML 테스트가 옛 PC의 `2_TV_*` 절대 경로나 worktree 밖 표본을 참조했다. 이 작업장의 `samples/SUG_RAW/TV_*`로 수정했다. runtime 추출 소스 해시는 변하지 않는다.
- XL PDF는 기존 최상위 폴더에만 있고 Git에는 없었다. 같은 파일을 `samples/SUG_RAW/TV_XL`에 보존했다. SHA-256: `dce6f5417123809235904c6ce3e7a1ff32aadc57df0a28e2a74d2c676b15a849`.
- XL은 사용자 확인값 `region=INDIA`, `buyer_codes=XL`과 기존 source-verified `A3/ENG/1`을 합쳐 canonical `XL_ENG`로 등록했다. 시험용 overlay는 제거했다. 실제 PDF를 다시 추출해 XML→MD→ReviewDocument 보존 검사를 통과했으며, 별도 근거는 [XL canonical 실행 기록](evidence/20260920-xl-canonical-integration.json)에 보존한다. 이 기술 확인은 XL 체크리스트 지원이나 사람 원문·업무 승인을 뜻하지 않는다.
- 표지 제목 bold 요청 HR-20260914-002: 새 ZC MD ENG 제목은 bold, C-FRA 제목은 아직 일반 텍스트다. 전체 해결로 표시하지 않는다.

## 다음 단계

1. 이 통합의 기술 검사 결과와 기존 바이어별 사람 확인 기록을 구분하여 유지한다.
2. XL 공식 매핑 등록과 기술 연결 검사는 완료했다. 사람 확인 상태와 XL 체크리스트 적용 범위는 별도로 관리한다.
3. 기존 master 내용을 기준으로 v2 체크리스트의 항목 단위·적용 범위를 정립하고 결과 레포트를 고도화한다.
4. 통합본을 충분히 사용한 뒤 옛 폴더의 유지/보관/삭제를 별도 결정한다. Git worktree 폴더를 탐색기에서 먼저 삭제하지 않는다.

이 작업은 전체 바이어/언어의 업무 승인, 다국어 의미·맞춤법 검토, 나머지 세 검토 기능 구현, `main` 전환 또는 공개 배포가 아니다.
