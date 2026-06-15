# SUG_RAW PDF Sample Analysis

분석 대상: `SUG_RAW` 내 SUG 매뉴얼 PDF 24개  
분석 일자: 2026-06-11  
분석 도구: PyMuPDF 1.27.2.3

## 1. 분석 요약

- PDF 24개 모두 파일명 파싱 가능
- PDF 24개 모두 텍스트 추출 가능
- 현재 샘플 기준 OCR 필수 PDF는 없음
- 확인된 페이지 규격은 A2, A3, A5
- `L05`, `L12`, `L16` book type 파일은 모두 PDF bookmark가 언어 구간 정보를 제공
- A2/A3 시트형 파일은 대부분 페이지 상단 모서리에 언어 약자가 텍스트로 표시됨

## 2. 폴더명 사용 기준

`TV_AFRICA`, `TV_ZA` 같은 폴더명은 샘플 정리용 참고값입니다.

운영 시스템에서 PDF를 업로드할 때는 폴더명이 없거나 의미가 없을 수 있으므로, 폴더명은 메타데이터 기준으로 사용하지 않습니다. 메타데이터는 파일명과 PDF 내부 정보 기준으로 추출합니다.

## 3. 파일명 메타데이터

현재 샘플 파일명은 아래 구조로 파싱됩니다.

```text
(매뉴얼코드)_(매뉴얼종류)_(출시연도 제품)_(바이어/판매지역)_(언어 토큰)_(날짜).0.pdf
```

예:

```text
BN68-25099A-00_SUG_Y26 TV ALL_ZA_ENG_251217.0.pdf
```

추출 필드:

```text
manual_code: BN68-25099A-00
manual_type: SUG
product_year: Y26
product: TV
target: ALL
buyer_region_token: ZA
language_token: ENG
date_code: 251217
```

주의:

- `buyer_region_token`에는 `AFRICA MENA`, `ZG XN ZT`, `SQ MI`처럼 공백이 포함될 수 있음
- `language_token`은 단일 언어 약어, 언어 수 토큰, 언어 조합 토큰 중 하나임
- 실제 포함 언어 목록은 `buyer_region_token + language_token` 기준의 매핑 DB로 확정하는 구조가 적합함

## 4. 페이지 규격

현재 샘플에서 확인된 페이지 규격은 아래와 같습니다.

| 공식 표기 | PDF 내부 크기 |
|---|---|
| A5 | `466.5 x 642.3` |
| A3 | `888.9 x 1237.6` |
| A2 | `1730.8 x 1237.6` |

문서와 리포트에서는 `A2`, `A3`, `A5`를 우선 표기하고, 필요 시 괄호 안에 PDF 내부 크기를 함께 표기합니다.

## 5. 문서 타입 정의

현재 샘플 기준 SUG 문서 타입은 아래 4가지로 정의할 수 있습니다.

| 타입 | 파일명 기준 | 확인된 구조 | 언어 식별 기준 |
|---|---|---|---|
| 단일 언어 시트 | `ENG`, `KOR`, `ARA`, `INS`, `TPE` 등 | A3, 2페이지 | 파일명 언어 토큰 + 페이지 상단 언어 약자 |
| L02 양면 2언어 시트 | `L02` | A2, 2페이지 | 파일명 매핑 + 각 페이지 상단 언어 약자 |
| 언어 조합 시트 | `ENRU`, `HEAR` 등 | A2, 2페이지 | 파일명 조합 토큰 + 각 페이지 상단 언어 약자 |
| Book Type 다국어 | `L05`, `L12`, `L16` | A5, 다페이지 | PDF bookmark의 언어 구간 정보 |

중요한 점:

- `L02`는 언어 2개를 의미하지만 실제 언어명은 바이어별 매핑 DB로 확정해야 함
- `ENRU`는 단일 언어가 아니라 `ENG + RUS` 조합으로 해석해야 함
- `HEAR`는 현재 샘플에서 `HEB + ARA` 언어 라벨이 확인됨
- book type은 좌측 상단 고정 라벨이 아니라 PDF bookmark를 1차 기준으로 쓰는 것이 가장 안정적임

## 6. 실제 샘플 분류

### 6.1 단일 언어 시트

| 파일 토큰 | 페이지 | 규격 | 확인된 언어 라벨 |
|---|---:|---|---|
| `ASIA_ENG` | 2 | A3 | `ENG` |
| `KR_KOR` | 2 | A3 | `KOR` |
| `TK_ARA` | 2 | A3 | `ARA` |
| `UA_ENG` | 2 | A3 | `ENG` |
| `XD_INS` | 2 | A3 | `INS` |
| `XU_ENG` | 2 | A3 | `ENG` |
| `XY_ENG` | 2 | A3 | `ENG` |
| `ZA_ENG` | 2 | A3 | `ENG` |
| `ZW_TPE` | 2 | A3 | 언어 라벨 미제공, 파일명 기준 확인 |

`ZW_TPE`는 실제 PDF에서 언어 라벨이 제공되지 않습니다. 파일명상 TPE 단일 언어이며 텍스트도 중국어 번체로 추출되므로, 이 케이스는 파일명 기준으로 언어를 확인합니다.

### 6.2 L02 양면 2언어 시트

| 파일 토큰 | 페이지 | 규격 | 확인된 언어 라벨 |
|---|---:|---|---|
| `LATIN_L02` | 2 | A2 | `ENG`, `M-SPA` |
| `MENA_L02` | 2 | A2 | `ENG`, `ARA` |
| `TK_L02` | 2 | A2 | `ENG`, `TUR` |
| `XT_L02` | 2 | A2 | `ENG`, `THA` |
| `ZC_L02` | 2 | A2 | `ENG`, `C-FRA` |
| `ZX_L02` | 2 | A2 | `ENG`, `M-SPA` |

### 6.3 언어 조합 시트

| 파일 토큰 | 페이지 | 규격 | 확인된 언어 라벨 |
|---|---:|---|---|
| `PY_ENRU` | 2 | A2 | `RUS`, `ENG` |
| `SQ MI_HEAR` | 2 | A2 | `HEB`, `ARA` |

### 6.4 Book Type 다국어

| 파일 토큰 | 페이지 | 규격 | bookmark 언어 수 |
|---|---:|---|---:|
| `AFRICA MENA_L05` | 44 | A5 | 5 |
| `AFRICA_L05` | 36 | A5 | 5 |
| `CE_L05` | 44 | A5 | 5 |
| `XC_L12` | 124 | A5 | 12 |
| `XH_L16` | 164 | A5 | 16 |
| `ZG XN ZT_L05` | 52 | A5 | 5 |

Book type은 모든 샘플에서 PDF bookmark가 언어 정보를 제공합니다. 따라서 언어 구간 분리의 기준은 bookmark로 정의합니다.

## 7. Book Type 언어 구성 확인 결과

### AFRICA MENA_L05

```text
English
Français
Español
Português
العربية
```

### AFRICA_L05

```text
English
Français
Español
Português
العربية
```

### CE_L05

```text
Русский
English
Қазақ
Монгол
Кыргызча
```

### XC_L12

```text
English
Français
Español
Português
Deutsch
Svenska
Dansk
Norsk
Suomi
Català
Galego
Euskara
```

### XH_L16

```text
English
Magyar
Polski
Ελληνικά
Български
Hrvatski
Čeština
Slovenčina
Română
Srpski
Shqip
Македонски
Slovenščina
Latviešu
Lietuvių kalba
Eesti
```

### ZG XN ZT_L05

```text
English
Deutsch
Français
Italiano
Nederlands
```

## 8. 언어 식별 규칙

실제 샘플 기준으로 언어 식별은 아래 순서가 적합합니다.

```text
1. 파일명에서 buyer_region_token과 language_token 추출
2. 매핑 DB로 PDF에 포함된 언어 목록 확정
3. 문서 타입 분류
4. 시트형이면 페이지 상단 모서리 언어 약자로 페이지별 언어 검증
5. book type이면 PDF bookmark로 언어별 구간 확정
6. bookmark가 깨진 비정상 파일만 대표 문구 또는 문자 스크립트 분석으로 예외 처리
```

이 규칙에서 파일명은 “포함 언어 목록”을 정의하는 기준이고, PDF 내부 라벨/bookmark는 “실제 페이지 또는 페이지 구간”을 분리하는 기준입니다.

## 9. 텍스트 추출 품질

현재 샘플은 모두 텍스트 레이어가 있어 PyMuPDF로 텍스트 추출이 가능합니다.

주의가 필요한 언어:

- 아랍어: RTL 방향성 때문에 문장부호와 순서 정규화 필요
- 히브리어: RTL 방향성 때문에 위치/순서 정규화 필요
- 태국어: 조합문자와 폰트 인코딩 영향으로 정규화 필요
- 중국어 번체: `ZW_TPE`는 언어 라벨 미제공 케이스이므로 파일명 기준으로 처리

## 10. 이미지/아이콘 검토 주의점

PyMuPDF의 raster image 기준으로는 총 80개 이미지가 확인됐습니다.

하지만 이미지 수가 0이라고 해서 아이콘이 없다고 단정하면 안 됩니다. 아이콘이나 규격 마크가 vector drawing, 폰트 glyph, 도형 조합으로 들어갈 수 있기 때문입니다.

이미지/아이콘 검토는 아래 방식이 적합합니다.

```text
1. PDF 페이지 렌더링
2. 기준 아이콘과 시각적 비교
3. 후보 영역 crop
4. 리포트에 캡처 첨부
5. 필요 시 수동 확인
```

## 11. 설계 반영 사항

### 11.1 파일명 파서

파일명 파서는 반드시 필요합니다. PDF 업로드 직후 파일명에서 매뉴얼 코드, 바이어/판매지역, 언어 토큰, 날짜를 추출합니다.

### 11.2 문서 타입 분류기

문서 타입은 `language_token`, 페이지 수, 페이지 규격으로 분류합니다.

```text
L05/L12/L16 + A5 + 다페이지 -> Book Type 다국어
L02 + A2 + 2페이지 -> L02 양면 2언어 시트
ENRU/HEAR 등 + A2 + 2페이지 -> 언어 조합 시트
ENG/KOR/ARA 등 + A3 + 2페이지 -> 단일 언어 시트
```

### 11.3 언어 구간 분리

시트형은 페이지 단위로 언어를 분리합니다.  
Book type은 bookmark 기준으로 언어별 구간을 분리합니다.

### 11.4 검토 엔진

검토 엔진은 전체 PDF 텍스트만 검색하면 안 됩니다. 반드시 언어별 페이지 또는 언어별 페이지 구간 단위로 필수 문구를 검토해야 합니다.

## 12. 결론

제공된 샘플은 초기 설계 검증용으로 충분히 좋습니다.

확정 가능한 내용:

- 파일명 규칙은 안정적으로 파싱 가능
- 폴더명은 운영 메타데이터에서 제외
- 페이지 규격은 A2/A3/A5로 정리 가능
- 시트형은 페이지 상단 언어 약자가 주요 검증 포인트
- book type은 bookmark가 언어 구간 분리 기준
- 모든 샘플은 텍스트 추출 가능

운영 기준:

- `ZW_TPE`처럼 언어 라벨이 없는 단일 언어 PDF는 파일명 기준으로 처리
- book type은 bookmark가 항상 제공되는 전제이므로 side label 또는 하단 언어 라벨 분석은 기본 검토 로직에서 제외
