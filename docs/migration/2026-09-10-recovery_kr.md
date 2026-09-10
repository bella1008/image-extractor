# XML v2 시작 전 복구 기준점

작성일: 2026-09-10. 이 파일의 커밋은 성공한 운영 릴리스가 아니라 당시 파일 상태를 보존한 복구 지점이다.

## 저장한 Git 번호

| 구분 | 전체 커밋 ID | 브랜치 |
|---|---|---|
| 미커밋 기존 코드·DB까지 포함한 복구 기준 | `4b001ff9a1a4f8ef91bed75a8ab314f4189d9476` | `codex/pre-xml-review-v2-20260910` |
| XML 추출기 기준 | `840512002a80a12b19c712116530ab69b1459c3a` | `feature/xml-markdown-review` |
| 백업 직전 메인 HEAD | `ccedbab32c3a70304128541082829465e8d07a16` | `main` |

메인 HEAD만으로는 당시 미커밋 체크리스트와 앱을 복구할 수 없다. 기존 시스템 복구에는 첫 번째 번호를 사용한다.

## 보존 범위와 한계

- 기존 추적 파일의 현재 내용 및 삭제 상태 전체.
- 미추적 파일 중 `src`, `apps`, `tests`, `scripts`, `metadata`, `docs`, `samples/SUG_RAW`, `samples/tagged_pdf_xml_poc`, `.codex/skills`의 Git ignore 제외 파일.
- 체크리스트 master Excel/JSON/CSV와 해당 metadata 폴더의 과거 이력 및 후보 파일.
- 현재 이동된 샘플 PDF 경로. 폴더명은 운영 메타데이터가 아니다.
- main의 HEAD, 실제 index, 작업 파일을 바꾸지 않고 임시 index와 `git commit-tree`로 저장했다. 백업 전후 HEAD/index SHA256/작업 상태 일치를 검사했다.
- Git이 설정에 따라 CRLF/LF를 정규화할 수 있다. 이는 소스 내용 복구용이며 파일 바이트·수정 시각·스테이징 구분의 완전한 디스크 이미지가 아니다.
- 미추적 `tmp`, `dist`, `REF`, `utputs`, `.superpowers`와 ignore된 출력물·가상환경·비밀 설정은 이 백업의 범위가 아니다. 해당 파일은 기존 폴더에 그대로 있다. 과거 보고서의 evidence 경로는 별도 보존 여부를 DB 이관 시 확인해야 한다.
- 다른 worktree의 미커밋 작업은 포함하지 않는다. XML 기준 worktree는 저장 시점 clean이었다. 별도 `xml-extractor-release` 작업은 이번 통합 대상이 아니다.

## 저장소와 별도로 읽을 수 있는 백업

위 복구 브랜치와 XML 브랜치의 전체 이력을 Git bundle로 저장했다.

`C:/Users/bella/image-extractor/.worktrees/migration-backups-20260910/pre-xml-review-v2.bundle`

SHA256: `9D7B8B1AA4F6574D6D36172292D5C90CA205573CF22191FEA27048EB65DD37B6`

`git bundle verify` 결과: 유효, prerequisite 없는 complete history, 위 두 ref 포함.
같은 PC 디스크에 있는 로컬 백업이므로 디스크 장애용 외부 백업까지 완료된 것은 아니다. 외부 전송은 하지 않았다.

## 안전하게 과거 코드를 여는 방법

현재 작업을 덮어쓰지 않고 새 폴더에서 확인한다. 아래 목적 폴더가 이미 있으면 다른 새 이름을 사용한다.

```powershell
git -C C:/Users/bella/image-extractor worktree add --detach C:/Users/bella/image-extractor/.worktrees/recovery-pre-v2 4b001ff9a1a4f8ef91bed75a8ab314f4189d9476
```

원래 저장소를 이용할 수 없으면 bundle로 별도 복제할 수 있다.

```powershell
git clone -b codex/pre-xml-review-v2-20260910 C:/Users/bella/image-extractor/.worktrees/migration-backups-20260910/pre-xml-review-v2.bundle C:/Users/bella/image-extractor-recovered-20260910
```

복구 명령은 안내용으로만 기록했다. 실제 복구/덮어쓰기는 실행하지 않았다.

## 원본 데이터 SHA256

| 파일 | SHA256 |
|---|---|
| `metadata/checklist/mvp_checklist_master.xlsx` | `D6B0D4A5F3FD57B8EB3B6EA303A444878B9431BA66EED9A15C3692DA0C5FA706` |
| `metadata/checklist/mvp_checklist_master.json` | `C6C65D8BA2A02D340B14CD9B7AE2A049FD83E461C44ACA83EDFF4FB451784D90` |
| `metadata/pdf_profile_mapping/pdf_profile_mapping.json` | `0ECDC5A2876376DD171524F3062BF190B76136A3DD780CEC10AA106C70726699` |

새 작업: `C:/Users/bella/image-extractor/.worktrees/xml-review-v2`, branch `codex/xml-review-v2`, XML 기준 커밋에서 시작.
