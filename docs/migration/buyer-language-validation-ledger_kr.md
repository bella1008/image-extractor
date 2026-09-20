# 바이어·언어별 XML / ReviewDocument 검증 대장

갱신: 2026-09-20. XML `8134892` 통합의 기술 검사 14 PDF/32개 언어 조합을 추가했습니다. 사람 확인 상태는 자동 승격하지 않았습니다.

## 기록 범위와 해석

- 목록 기준: `metadata/pdf_profile_mapping/pdf_profile_mapping.json`의 23개 프로필, 73개 프로필·언어 조합. 프로필 하나에 여러 buyer_codes가 포함될 수 있으므로 바이어 수와 동일하지 않습니다.
- 각 언어를 별도 행으로 관리합니다. 매핑 추가 시 빠진 행을 먼저 등록합니다. 매핑 밖 신규 파일도 발견 즉시 미등록 대상으로 추가합니다.
- 아래는 프로필별 현황표이며 승인 범위는 반드시 별도 PDF/실행 기록에 묶습니다. 같은 바이어·언어라도 연도·모델·파일 해시가 다르면 추가 기록입니다.
- `미조사`는 결과가 없다는 단정이 아닙니다. 다른 터미널의 결과와 승인 기록을 확인하기 전 상태입니다. 기존 GridCell 검수 완료를 XML 검수 완료로 옮기지 않습니다.
- `기술 확인`은 기존 adapter 보존 검증 기록과 이번 파일 해시 대조를 뜻합니다. 원본 PDF 전체 내용의 사람 승인을 뜻하지 않습니다.
- 사람 확인은 `미요청 / 확인 요청 / 일부 확인 / 확인 완료 / 수정 후 재확인`으로 기록합니다. 요청·부분 확인을 완료로 합치지 않습니다. 표본 검토 범위 밖은 미확인으로 남깁니다.
- 이 문서는 작업/승인 기록입니다. 현재 runtime에 사람 승인 자동 차단 장치를 추가한 것은 아닙니다. 에이전트는 AGENTS 규칙에 따라 미확인 범위의 운영 승인·DB 반영을 진행하지 않습니다.

## 전체 대상 목록

### RUN-20260920-INTEGRATION

- 정확한 PDF 파일명·해시·언어별 텍스트 조각 수·완료 receipt 해시는 [실행 근거](evidence/20260920-xml-integration.json)에 보존한다.
- 최신 추출기의 XML/MD와 ReviewDocument 사이의 노드 순서·텍스트·속성·근거 보존 검사다. 번역 의미/맞춤법 검사나 PDF 전체 사람 승인이 아니다.
- ZC, XU, ZG, AFRICA, CE, TK(ENG/TUR 및 ARA), MENA, SQ MI, XT, ZW, PY, UA, XD의 해당 PDF가 기술 검사 통과했다. 아래 표에서 기존 사람 확인 상태와 요청 상태는 유지했다.
- AFRICA/CE/ZG의 공통 영역 텍스트 75/50/9개는 언어 미배정으로 보존했다. 언어가 없다는 이유로 삭제하거나 임의 언어에 편입하지 않았다.
- **추가 미등록 대상 XL_ENG**: `BN68-25031J-00...260306.0.pdf`, ENG. 추출기 자체 테스트는 통과하지만 canonical profile 부재로 ReviewDocument 연결은 차단. 공식 buyer/region/profile 확인이 필요하며 위 32조합에는 포함하지 않는다.
- 이번 adapter 통합만으로 새 PDF 원문 대조를 요청할 근거는 발견되지 않았다. 기존 미확인 언어 및 기존 요청은 그대로 남는다. HR-20260914-002의 ZC C-FRA 연락처 제목 bold는 미해결이며 ENG만 반영됐다.

아래 표의 `기술 확인`은 반드시 실행 근거의 PDF 버전 범위로 읽는다.

| source_token | buyer_codes | 유형 | 언어 | XML 자동 검사 | ReviewDocument 보존 검사 | PDF 전체 사람 확인 | 요청 상태 | 근거 |
|---|---|---|---|---|---|---|---|---|
| AFRICA MENA_L05 | AFRICA;MENA | BOOK | ENG | 미조사 | 미조사 | 미조사 | 미요청 | — |
| AFRICA MENA_L05 | AFRICA;MENA | BOOK | FRA | 미조사 | 미조사 | 미조사 | 미요청 | — |
| AFRICA MENA_L05 | AFRICA;MENA | BOOK | SPA | 미조사 | 미조사 | 미조사 | 미요청 | — |
| AFRICA MENA_L05 | AFRICA;MENA | BOOK | POR | 미조사 | 미조사 | 미조사 | 미요청 | — |
| AFRICA MENA_L05 | AFRICA;MENA | BOOK | ARA | 미조사 | 미조사 | 미조사 | 미요청 | — |
| AFRICA_L05 | AFRICA | BOOK | ENG | 기술 확인 | 기술 확인 | 미조사 | 미요청 | RUN-20260920-INTEGRATION |
| AFRICA_L05 | AFRICA | BOOK | FRA | 기술 확인 | 기술 확인 | 미조사 | 미요청 | RUN-20260920-INTEGRATION |
| AFRICA_L05 | AFRICA | BOOK | SPA | 기술 확인 | 기술 확인 | 미조사 | 미요청 | RUN-20260920-INTEGRATION |
| AFRICA_L05 | AFRICA | BOOK | POR | 기술 확인 | 기술 확인 | 미조사 | 미요청 | RUN-20260920-INTEGRATION |
| AFRICA_L05 | AFRICA | BOOK | ARA | 기술 확인 | 기술 확인 | 미조사 | 미요청 | RUN-20260920-INTEGRATION |
| ASIA_ENG | ASIA | A3 | ENG | 미조사 | 미조사 | 미조사 | 미요청 | — |
| CE_L05 | CE | BOOK | RUS | 기술 확인 | 기술 확인 | 미조사 | 미요청 | RUN-20260920-INTEGRATION |
| CE_L05 | CE | BOOK | ENG | 기술 확인 | 기술 확인 | 미조사 | 미요청 | RUN-20260920-INTEGRATION |
| CE_L05 | CE | BOOK | KAZ | 기술 확인 | 기술 확인 | 미조사 | 미요청 | RUN-20260920-INTEGRATION |
| CE_L05 | CE | BOOK | MON | 기술 확인 | 기술 확인 | 미조사 | 미요청 | RUN-20260920-INTEGRATION |
| CE_L05 | CE | BOOK | KYR | 기술 확인 | 기술 확인 | 미조사 | 미요청 | RUN-20260920-INTEGRATION |
| KR_KOR | KR | A3 | KOR | 미조사 | 미조사 | 미조사 | 미요청 | — |
| LATIN_L02 | LATIN | A2 | ENG | 미조사 | 미조사 | 미조사 | 미요청 | — |
| LATIN_L02 | LATIN | A2 | M-SPA | 미조사 | 미조사 | 미조사 | 미요청 | — |
| MENA_L02 | MENA | A2 | ENG | 기술 확인 | 기술 확인 | 미조사 | 미요청 | RUN-20260920-INTEGRATION |
| MENA_L02 | MENA | A2 | ARA | 기술 확인 | 기술 확인 | 미조사 | 미요청 | RUN-20260920-INTEGRATION |
| PY_ENRU | PY | A2 | RUS | 기술 확인 | 기술 확인 | 미조사 | 미요청 | RUN-20260920-INTEGRATION |
| PY_ENRU | PY | A2 | ENG | 기술 확인 | 기술 확인 | 미조사 | 미요청 | RUN-20260920-INTEGRATION |
| SQ MI_HEAR | SQ;MI | A2 | HEB | 기술 확인 | 기술 확인 | 미조사 | 미요청 | RUN-20260920-INTEGRATION |
| SQ MI_HEAR | SQ;MI | A2 | ARA | 기술 확인 | 기술 확인 | 미조사 | 미요청 | RUN-20260920-INTEGRATION |
| TK_ARA | TK | A3 | ARA | 기술 확인 | 기술 확인 | 미조사 | 미요청 | RUN-20260920-INTEGRATION |
| TK_L02 | TK | A2 | ENG | 기술 확인 | 기술 확인 | 미조사 | 미요청 | RUN-20260920-INTEGRATION |
| TK_L02 | TK | A2 | TUR | 기술 확인 | 기술 확인 | 미조사 | 미요청 | RUN-20260920-INTEGRATION |
| UA_ENG | UA | A3 | ENG | 기술 확인 | 기술 확인 | 미조사 | 미요청 | RUN-20260920-INTEGRATION |
| XC_L12 | XC | BOOK | ENG | 미조사 | 미조사 | 미조사 | 미요청 | — |
| XC_L12 | XC | BOOK | FRA | 미조사 | 미조사 | 미조사 | 미요청 | — |
| XC_L12 | XC | BOOK | SPA | 미조사 | 미조사 | 미조사 | 미요청 | — |
| XC_L12 | XC | BOOK | POR | 미조사 | 미조사 | 미조사 | 미요청 | — |
| XC_L12 | XC | BOOK | DEU | 미조사 | 미조사 | 미조사 | 미요청 | — |
| XC_L12 | XC | BOOK | SWE | 미조사 | 미조사 | 미조사 | 미요청 | — |
| XC_L12 | XC | BOOK | DAN | 미조사 | 미조사 | 미조사 | 미요청 | — |
| XC_L12 | XC | BOOK | NOR | 미조사 | 미조사 | 미조사 | 미요청 | — |
| XC_L12 | XC | BOOK | FIN | 미조사 | 미조사 | 미조사 | 미요청 | — |
| XC_L12 | XC | BOOK | CAT | 미조사 | 미조사 | 미조사 | 미요청 | — |
| XC_L12 | XC | BOOK | GLG | 미조사 | 미조사 | 미조사 | 미요청 | — |
| XC_L12 | XC | BOOK | EUS | 미조사 | 미조사 | 미조사 | 미요청 | — |
| XD_INS | XD | A3 | INS | 기술 확인 | 기술 확인 | 미조사 | 미요청 | RUN-20260920-INTEGRATION |
| XH_L16 | XH | BOOK | ENG | 미조사 | 미조사 | 미조사 | 미요청 | — |
| XH_L16 | XH | BOOK | HUN | 미조사 | 미조사 | 미조사 | 미요청 | — |
| XH_L16 | XH | BOOK | POL | 미조사 | 미조사 | 미조사 | 미요청 | — |
| XH_L16 | XH | BOOK | GRE | 미조사 | 미조사 | 미조사 | 미요청 | — |
| XH_L16 | XH | BOOK | BUL | 미조사 | 미조사 | 미조사 | 미요청 | — |
| XH_L16 | XH | BOOK | CRO | 미조사 | 미조사 | 미조사 | 미요청 | — |
| XH_L16 | XH | BOOK | CZE | 미조사 | 미조사 | 미조사 | 미요청 | — |
| XH_L16 | XH | BOOK | SLK | 미조사 | 미조사 | 미조사 | 미요청 | — |
| XH_L16 | XH | BOOK | ROM | 미조사 | 미조사 | 미조사 | 미요청 | — |
| XH_L16 | XH | BOOK | SER | 미조사 | 미조사 | 미조사 | 미요청 | — |
| XH_L16 | XH | BOOK | ALB | 미조사 | 미조사 | 미조사 | 미요청 | — |
| XH_L16 | XH | BOOK | MKD | 미조사 | 미조사 | 미조사 | 미요청 | — |
| XH_L16 | XH | BOOK | SLV | 미조사 | 미조사 | 미조사 | 미요청 | — |
| XH_L16 | XH | BOOK | LAT | 미조사 | 미조사 | 미조사 | 미요청 | — |
| XH_L16 | XH | BOOK | LTU | 미조사 | 미조사 | 미조사 | 미요청 | — |
| XH_L16 | XH | BOOK | EST | 미조사 | 미조사 | 미조사 | 미요청 | — |
| XT_L02 | XT | A2 | ENG | 기술 확인 | 기술 확인 | 미조사 | 미요청 | RUN-20260920-INTEGRATION |
| XT_L02 | XT | A2 | THA | 기술 확인 | 기술 확인 | 미조사 | 미요청 | RUN-20260920-INTEGRATION |
| XU_ENG | XU | A3 | ENG | 기술 확인 | 기술 확인 | 완료 근거 미확정 | 미요청 | BASE-2; RUN-20260920-INTEGRATION |
| XY_ENG | XY | A3 | ENG | 미조사 | 미조사 | 미조사 | 미요청 | — |
| ZA_ENG | ZA | A3 | ENG | 미조사 | 미조사 | 미조사 | 미요청 | — |
| ZC_L02 | ZC | A2 | ENG | 기술 확인 | 기술 확인 | 부분 확인 | 텍스트 확인 완료 2026-09-14 / 표지 bold 표시 후속 | BASE-1, HR-20260914-002, RUN-20260915-PILOT-ZC; RUN-20260920-INTEGRATION |
| ZC_L02 | ZC | A2 | C-FRA | 기술 확인 | 기술 확인 | 부분 확인 | 텍스트 확인 완료 2026-09-14 / 표지 bold 표시 후속 | BASE-1, HR-20260914-002, RUN-20260915-PILOT-ZC; RUN-20260920-INTEGRATION |
| ZG XN ZT_L05 | ZG;XN;ZT | BOOK | ENG | 기술 확인 | 기술 확인 | 완료 근거 미확정 | 미요청 | BASE-3; RUN-20260920-INTEGRATION |
| ZG XN ZT_L05 | ZG;XN;ZT | BOOK | DEU | 기술 확인 | 기술 확인 | 완료 근거 미확정 | 미요청 | BASE-3; RUN-20260920-INTEGRATION |
| ZG XN ZT_L05 | ZG;XN;ZT | BOOK | FRA | 기술 확인 | 기술 확인 | 완료 근거 미확정 | 미요청 | BASE-3; RUN-20260920-INTEGRATION |
| ZG XN ZT_L05 | ZG;XN;ZT | BOOK | ITA | 기술 확인 | 기술 확인 | 완료 근거 미확정 | 미요청 | BASE-3; RUN-20260920-INTEGRATION |
| ZG XN ZT_L05 | ZG;XN;ZT | BOOK | DUT | 기술 확인 | 기술 확인 | 완료 근거 미확정 | 미요청 | BASE-3; RUN-20260920-INTEGRATION |
| ZW_TPE | ZW | A3 | TPE | 기술 확인 | 기술 확인 | 미조사 | 미요청 | RUN-20260920-INTEGRATION |
| ZX_L02 | ZX | A2 | ENG | 미조사 | 미조사 | 미조사 | 미요청 | — |
| ZX_L02 | ZX | A2 | M-SPA | 미조사 | 미조사 | 미조사 | 미요청 | — |

ZG/XN/ZT 공통 표지의 언어 미배정 텍스트 조각 9개는 위 5언어 확인에 포함시키지 않습니다. 별도 확인 대상이며, 표지/그림 등 언어 미배정 요소가 언어별 집계 밖에서 빠지지 않도록 관리합니다.

## 실물 실행 근거

아래 해시는 2026-09-13에 원본 PDF와 완료 기록 및 산출물을 대조했습니다. 기존 변환 검증 기록: [XML adapter 실물 검증](2026-09-10-xml-adapter-validation_kr.md).

### BASE-1: ZC_L02

- PDF: [BN68-25100B-00_SUG_Y26 TV ALL_ZC_L02_260122.0.pdf](<../../samples/SUG_RAW/TV_ZC/BN68-25100B-00_SUG_Y26 TV ALL_ZC_L02_260122.0.pdf>)
- 언어: ENG, C-FRA. 표지 등 미배정 범위는 별도 기록.
- 추출/변환 폴더: [outputs/xml_review_v2_zc_20260910](../../outputs/xml_review_v2_zc_20260910/)
- PDF SHA-256: `e7ae68f7e314b500425bb81608aa1f3a1fe683ee555d7ea38db705b42649c4a1`
- Semantic XML SHA-256: `8cecca8b0f41583e961a486d2bd157b81c9a59d7f4bc7ec87e47d5a0b1d6354c`
- MD SHA-256: `0acc00334f304e45ba764ebd646bb17e9c1269ef86dbf77a872235d7de575dbc`
- ReviewDocument SHA-256: `c7dd27a0b23b520b29cb6815bc88480c5d3d710f6cdc5e4fed077621dbb7f1db`
- 추출 완료 기록 SHA-256: `3d2be6ad88564824e1866fd8040b0972d8920eb135f129498b8650014580264a`
- 추출 계약: `tagged-pdf-xml/8405120`; 추출기 SHA-256: `fc64c8bc8e7909b27ed413fc802736b3a48fa5463f6316dba9e43f882ed3aa1e`.
- 사람 전체 확인자/확인일/확인 범위/승인 근거: 미확정. 자동 검사 수치로 채우지 않음.

### BASE-2: XU_ENG

- PDF: [BN68-24437C-01_SUG_Y26 TV ALL_XU_ENG_260129.0.pdf](<../../samples/SUG_RAW/TV_XU/BN68-24437C-01_SUG_Y26 TV ALL_XU_ENG_260129.0.pdf>)
- 언어: ENG. 표지 등 미배정 범위는 별도 기록.
- 추출/변환 폴더: [outputs/xml_review_v2_xu_20260910](../../outputs/xml_review_v2_xu_20260910/)
- PDF SHA-256: `f6d2a6d7c19672bcba92e1bfaaee364cdbcd8538006057a52af2f4ebb7e047f7`
- Semantic XML SHA-256: `7b06b466493de44b1af6578159cb142e4125963c85bb70adcb2a85dba54c75a9`
- MD SHA-256: `bd38072f0c60b53ae4da332288e7a5f7b96b88e9c194242b208b48aa3a218e9e`
- ReviewDocument SHA-256: `4df631346da8875bca7425c0cfa995c0657a3e03a5b54f0b7aef4aa34af52074`
- 추출 완료 기록 SHA-256: `84fcee2ba244510930b775f1ea422637e41f554fdaece5cdfe3a2776d19e347d`
- 추출 계약: `tagged-pdf-xml/8405120`; 추출기 SHA-256: `fc64c8bc8e7909b27ed413fc802736b3a48fa5463f6316dba9e43f882ed3aa1e`.
- 사람 전체 확인자/확인일/확인 범위/승인 근거: 미확정. 자동 검사 수치로 채우지 않음.

### BASE-3: ZG XN ZT_L05

- PDF: [BN68-25448A-00_SUG_Y26 TV ALL_ZG XN ZT_L05_260204.0.pdf](<../../samples/SUG_RAW/TV_ZG/BN68-25448A-00_SUG_Y26 TV ALL_ZG XN ZT_L05_260204.0.pdf>)
- 언어: ENG, DEU, FRA, ITA, DUT. 표지 등 미배정 범위는 별도 기록.
- 추출/변환 폴더: [outputs/xml_review_v2_zg_20260910_r2](../../outputs/xml_review_v2_zg_20260910_r2/)
- PDF SHA-256: `931ccb150d7166812d071e13842f2268fc42ce653fbbcf7f0ae1d83e1979bb54`
- Semantic XML SHA-256: `c94c77732cc945d143e52706db9b53249f4bbf1e6f7f921d53bb37ebf6d5e522`
- MD SHA-256: `5fa04ca3632eeea6507beaab3e93ae3761d80264222594a366adb58c0e92a2bc`
- ReviewDocument SHA-256: `35bc9b088e63443b82c8d04c58f4e915f0786b45556e708ad37c6440add8b811`
- 추출 완료 기록 SHA-256: `b90e5f51dec93480dc3a50f73d84151227053f1d97c7b583ebcde1ed26b3d56e`
- 추출 계약: `tagged-pdf-xml/8405120`; 추출기 SHA-256: `fc64c8bc8e7909b27ed413fc802736b3a48fa5463f6316dba9e43f882ed3aa1e`.
- 사람 전체 확인자/확인일/확인 범위/승인 근거: 미확정. 자동 검사 수치로 채우지 않음.

## 기존 사람 확인 기록의 취급

TODO의 과거 기록에는 ZG의 DEU/FRA 문장 경계 및 ITA 부제 등 일부 항목, XU의 Warranty/RF 표 등에 대한 manual review가 있습니다. 이를 삭제하거나 “한 번도 검토하지 않음”으로 바꾸지 않습니다. 다만 확인자·정확한 PDF/추출본·확인 범위가 연결되기 전에는 전체 언어/전체 페이지의 누락 검수 완료로 확대하지 않습니다. 기존 ZC 기준 검수에도 같은 원칙을 적용합니다.

## 현재 확인 요청

### HR-20260913-001: ZC_L02 / ENG · C-FRA

- 요청일: 2026-09-13. 대상: BASE-1의 `BN68-25100B-00_SUG_Y26 TV ALL_ZC_L02_260122.0.pdf`.
- 이유: adapter/통합 실행 보존 검사는 있으나 현재 기록만으로 원본 전체 누락 검수의 사람 확인 범위를 확정할 수 없음.
- 비교 자료: BASE-1 원본 PDF와 [동일 추출본 MD](../../outputs/xml_review_v2_zc_20260910/semantic_document.md).
- 확인 범위: ENG와 C-FRA를 각각 확인. 제목·본문 누락, 읽는 순서, 표의 행/셀과 목록 항목, 그림·아이콘 주변 문구의 연결. 표지·뒷표지 포함. MD로 그림을 판단할 수 없으면 PDF 그림 위치를 지정하여 추가 근거 요청.
- 자동 추가 점검 2026-09-13: PyMuPDF PDF 텍스트와 MD/ReviewDocument 문자열을 토큰 기준으로 대조했다. PDF 2페이지, PDF 토큰 7,951개, MD 토큰 8,572개, ReviewDocument 문자열 토큰 168,165개. 3글자 이상 고유 PDF 토큰 중 MD와 ReviewDocument 양쪽의 미포함 후보는 `boîtierwireless` 1개이며, MD/ReviewDocument에는 `boîtier Wireless`처럼 띄어쓰기 있는 형태가 존재하므로 의미 누락으로 보지 않는다. 이 점검은 자동 텍스트 보존 확인이며 그림·아이콘 시각 요소와 사람의 전체 원문 승인으로 확대하지 않는다.
- 응답 기록 2026-09-14: 사용자가 `outputs/xml_review_v2_zc_20260910/semantic_document.md` 기준으로 ZC ENG와 C-FRA의 나머지 텍스트 확인을 완료했다고 보고했다. 표지의 연락처 제목 `Contact Samsung world wide` 및 `Comment contacter Samsung dans le monde`는 원본 PDF에서 bold로 보이나 현재 MD에는 bold가 표시되지 않는다고 지적했다.
- 과거 동일 PDF/동일 추출본에서 이미 확인했다면 그 기록과 범위를 연결하여 중복 검수를 줄임. 단순 “진행해”는 원본 검수 승인으로 보지 않음.
- 운영 반영: 사람 확인 범위가 확정되기 전에는 이 기술 검사 결과만으로 운영 승인이나 DB 후보 승인을 부여하지 않음. 독립적인 개발·자동 대조는 계속 가능.

### HR-20260914-002: 표지 연락처 제목 bold 표시 후속

- 요청일: 2026-09-14. 대상: ZC_L02 ENG/C-FRA에서 사용자가 확인한 표지 연락처 제목.
- 사용자 확인: MD에는 `Contact Samsung world wide`와 `Comment contacter Samsung dans le monde`가 일반 텍스트로 표시되지만 원본 PDF에서는 bold로 보인다.
- 자동 확인: `BN68-25100B-00_SUG_Y26 TV ALL_ZC_L02_260122.0.pdf`의 해당 두 줄은 PyMuPDF 기준 모두 `font=SamsungOne-600`, `size=7.0`으로 추출된다. 현재 `semantic_document.md`에는 각각 491행, 999행에 일반 텍스트로 출력된다.
- 범위 참고: 샘플 PDF의 `Contact Samsung world wide` 계열 표지 연락처 제목도 확인 가능한 범위에서는 `SamsungOne-600`으로 관찰된다. 다만 모든 언어의 번역 제목을 사람이 확인했다는 뜻은 아니며, 언어별 추출 결과가 생길 때 같은 이슈를 계속 기록한다.
- 현재 판단: 문구 누락이 아니라 표지 연락처 제목의 시각적 강조 표시가 MD/ReviewDocument 표시 계층에 아직 반영되지 않은 표시 품질 이슈다.
- 후속 방향: ReviewDocument의 표지 연락처 제목 역할 또는 MD display hint로 보존할지 결정한 뒤, 특정 문구 하드코딩 없이 font weight와 표지 연락처 구조를 함께 사용해 fail-closed로 처리한다.

## RUN-20260915-PILOT-ZC: PC 배포 경로 보존 검사

- 실행일: 2026-09-15. source_token `ZC_L02`, buyer `ZC`, doc_type `A2`, 추출 언어 ENG/C-FRA, PDF 1~2페이지.
- PDF: `BN68-25100B-00_SUG_Y26 TV ALL_ZC_L02_260122.0.pdf`.
- PDF SHA-256: `e7ae68f7e314b500425bb81608aa1f3a1fe683ee555d7ea38db705b42649c4a1`.
- 폴더: `outputs/review_pilot_20260915_smoke/다른 PC 검토 프로그램/outputs/zc_fresh/_internal/extraction/`.
- 추출기: `tagged-pdf-xml/8405120`, SHA-256 `fc64c8bc8e7909b27ed413fc802736b3a48fa5463f6316dba9e43f882ed3aa1e`.
- XML SHA-256: `8cecca8b0f41583e961a486d2bd157b81c9a59d7f4bc7ec87e47d5a0b1d6354c`.
- MD SHA-256: `0acc00334f304e45ba764ebd646bb17e9c1269ef86dbf77a872235d7de575dbc`.
- ReviewDocument SHA-256: `c7dd27a0b23b520b29cb6815bc88480c5d3d710f6cdc5e4fed077621dbb7f1db`.
- 추출 완료 기록 SHA-256: `3d2be6ad88564824e1866fd8040b0972d8920eb135f129498b8650014580264a`.
- 자동 검사: 별도 Python 설치 환경에서 새 추출. XML/MD/ReviewDocument는 `outputs/checklist_20260914_130233_25dbc00a184e/_internal/extraction/`와 바이트 동일. 체크리스트 출력은 ENG만 59개/하위14개, C-FRA 체크리스트는 실행하지 않음.
- 사람 확인: 추가 요청 없음. 추출 내용 변경이 없는 실행 경로 검사로 기존 HR-20260914-002의 확인 범위를 계승하며 확대하지 않음. 다국어 의미 일치 검사나 그림·아이콘의 추가 시각 승인은 수행하지 않음.
- 미해결: 표지 연락처 제목 bold 표시 후속은 그대로 유지.

## 새 실행을 등록하는 방법

새 PDF마다 다음 필드를 가진 기록을 추가하고 위 프로필·언어 행에서 연결합니다. 여러 실행은 과거 기록을 지우지 않고 추가합니다.

`기록 ID / source_token / buyer_codes / doc_type / 언어 / PDF 파일명·SHA-256 / 추출 폴더·완료기록 해시 / 추출기 버전 / XML·MD·ReviewDocument 해시 / 자동 검사 결과와 범위 / 사람 확인 요청일·사유 / 확인자·확인일 / PDF 페이지·노드·확인 항목 / 부분·전체 범위 / 미해결 사항 / 재확인 상태 / 승인 대화·문서 근거`

원본 내용이나 추출 구조가 바뀌면 영향받는 언어/구간의 사람 확인을 `수정 후 재확인`으로 남깁니다. 바이트/구조 동일성이 입증된 단순 실행 경로 변경은 기존 확인 근거와 동일성 검사를 연결할 수 있지만, 승인 범위를 넓힐 수는 없습니다.
