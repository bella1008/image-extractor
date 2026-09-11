# 기존 Excel 양식 조사와 v2 표시 계약 초안

상태: 실제 파일을 읽어 조사한 **양식 초안**. 기존 추출 결과나 업무 판정을 새 시스템의 정답으로 복사하지 않는다. 사용자의 최종 양식 검수는 아직이다.

## 조사 표본

메인의 기존 파일을 읽기만 했으며 변경하지 않았다.

- 최종 검토 리포트 표본: `outputs/dispatch_gate_zc_rebaseline_260713/version_pair_same_dispatch_260714/review_report_v2_same_dispatch_ordered_content_raw/review_report_260714_132907.xlsx`
  - SHA256 `a0de537f072500c48fd817c7f1c4903759a6ee73b249c6f38d0e8dd21c434fc8`
  - Summary, Checklist Results, Diff Summary, Diff Raw Comparison, Safety Table Compare, Navigation UI Compare, Spec Table Compare, Regulatory Note Compare, Doc Table Compare, Cover Compare, Model Spec Check.
- 추출 검수 표본: `outputs/dispatch_gate_zc_rebaseline_260713/content/BN68-25100B-00/ZC_L02_ENG/BN68-25100B-00_ZC_L02_ENG_260713_1040_content_review.xlsx`
  - SHA256 `5f8c7554a79485882d4e77cbf24815d3ee50fca55fe093387d05aac81fed5ee6`
  - Content Summary, Content Review, Safety Tables, Navigation UI, Spec Tables, Doc Tables, Regulatory Notes.

오래된 TODO의 `_final_registry/zc_l02_eng_cfra_260709_v22_manifest.json`은 현재 메인에 없었다. 위 파일은 존재·내용·hash를 확인한 양식 참고 표본이며, 사용자가 v2 양식 기준본으로 새 승인했다는 뜻은 아니다.

## 재사용의 정확한 의미

검토 리포트 `Checklist Results`의 기준 문구와 실제 근거를 나란히 보여주는 방식을 유지한다. 기존 Python exporter를 import하지 않는다. 새 관찰 JSON을 `review_report_view.py`가 표시용 행/열로 바꾸고, 출력기는 이 표만 그린다.

| 기존 값/기능 | v2 초안 |
|---|---|
| scope, exclude_scope, common_id, check_id | 보존 |
| section_heading, language | 기준 제목과 규칙 언어로 보존. XML 관찰 제목과 혼동하지 않음 |
| required_text, evidence_excerpt | 좌우 비교 유지. 원문 문자열 유지 |
| result | 이번 관찰 단계에서는 전부 needs_review. 근거 발견을 pass로 바꾸지 않음 |
| block_type, scope_type, system_check_type | 일반 결과 열에서는 제외. 기존 원본 규칙은 observation.json에 모두 보존 |
| evidence_block_order, cell_order | 구 좌표를 흉내 내지 않음. 페이지와 새 evidence_ids로 대체 |
| 파란 헤더 D9EAF7, 노란 검토 FFF4CE | 양식 초안에서 유지. 합격 녹색은 사용하지 않음 |
| 자동 필터, A2 고정창, 긴 문구 줄바꿈 | 유지 |
| Diff/Model/특수 비교 시트 | 아직 검토가 구현되지 않았으므로 완료처럼 빈 시트를 생성하지 않음 |

## 초안의 시트

아래는 이미 생성된 최초 초안의 구성이다. 후속 사용자 피드백은 `docs/superpowers/specs/2026-09-11-item-review-and-evidence-display-design_kr.md`에 기록했다. 다음 개정은 판정/설명 두 열 권고안, 문서 단위 출처 패널, 노드 ID+태그+페이지 추적, CHK-002 item별 검토 단위에 맞춘다. 최초 초안 파일 자체는 아직 변경하지 않았다.

1. `Summary`: 적용 수, 엄격한 근거/구조 후보/분산 근거/미해결 수, 지원 범위와 미구현 기능.
2. `Checklist Results`: 적용 59개. 기준과 실제 문구, needs_review, 관찰 종류/사유, 페이지, 근거 ID, 빈 reviewer_note.
3. `Source Evidence`: 원문 근거를 별도 행으로 보존. strict/candidate/fragment를 구별하며 XML 위치로 추적한다.
4. `Excluded Rules`: 적용 대상 아님/기존 비승인 488개. 삭제하지 않았다는 대조 기록.

표와 본문에 흩어진 SAFETY-008은 일반 evidence_excerpt를 비워 두고 `distributed_fragments` 및 근거 ID를 표시한다. 조각들을 이어 붙여 전체 일치처럼 보이게 하지 않는다. 리뷰어 메모는 출력 사본의 의견란이지 DB 승인 입력란이 아니다.

## 출력 계약 테스트

`tests/test_review_report_view.py`는 원본 문구/규칙 불변, 페이지 1-based 표시, 후보와 분산 근거 구분, 제외 행 보존, 자동 승인 거절을 검사한다. 파일 바이트 동일성을 요구하지 않는다. 생성된 Excel은 표시 계약 초안이며 배포용 Python Excel writer나 최종 양식 승인이 완료된 것은 아니다.
