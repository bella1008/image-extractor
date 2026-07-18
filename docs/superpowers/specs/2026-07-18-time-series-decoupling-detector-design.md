# 시계열 데이터 디커플링 감지 모듈 v1.1 설계

## 1. 목적과 범위

이 모듈은 평소 동기화되어 움직이는 두 시계열 사이에서 다음 네 가지 디커플링 패턴을 각각 독립적으로 감지한다.

1. 방향성 역전
2. 값/위상 이탈
3. 변동성 불일치
4. 반응 지연 또는 관계 단절

이 모듈은 배치 환경에서 동작하는 비지도 감지기다. 결정론적으로 생성된 LLM 해석용 한국어 이벤트 설명을 반환하며, 선택적으로 분석가 검증용 Matplotlib Figure를 생성한다. 모델을 학습하거나 저장하지 않는다.

현재 저장소의 평면형 `src/` 구조에 맞춰 `src/decoupling_detector.py`에 구현한다. 테스트는 `tests/test_decoupling_detector.py`에 둔다.

## 2. 공개 인터페이스

```python
events, plot_object = detect_decoupling(
    ts1,
    ts2,
    window_size,
    persistence,
    enable_plot=False,
    config=None,
)
```

입력값은 다음과 같다.

- `ts1`, `ts2`: `DatetimeIndex`를 사용하는 pandas `Series`
- `window_size`: 관측치 개수로 표현한 이동 통계 윈도우
- `persistence`: 이상 확정에 필요한 연속 이상 관측치 개수
- `enable_plot`: 검증용 Figure 생성 여부. 기본값은 `False`
- `config`: 선택적 `DecouplingConfig`. 생략하면 적응형 기본값을 사용

반환값은 다음 두 요소로 구성된 튜플이다.

- `events`: `list[dict[str, str]]`
- `plot_object`: 시각화가 활성화되면 Matplotlib `Figure`, 비활성화되면 `None`

각 이벤트는 정확히 다음 필드를 갖는다.

```json
{
  "timestamp": "2026-07-18 10:00:00",
  "confirmed_at": "2026-07-18 21:00:00",
  "decoupling_type": "방향성 역전",
  "description": "10:00부터 두 데이터의 이동 상관계수가 음수로 전환되었으며, 21:00까지 12에포크 연속 지속되어 이상 상태로 확정되었습니다."
}
```

`timestamp`는 확정된 이상 구간의 첫 관측 시각이다. `confirmed_at`은 해당 구간이 처음으로 `persistence`를 충족한 관측 시각이다. 입력 인덱스에 timezone이 있으면 결과에도 보존한다. 이벤트는 `timestamp` 순으로 정렬하고, 같은 시각에 여러 이벤트가 있으면 고정된 패턴 순서를 적용한다.

`decoupling_type`의 고정값과 순서는 `방향성 역전`, `값/위상 이탈`, `변동성 불일치`, `반응 지연`이다. 시각 문자열은 `pandas.Timestamp.isoformat(sep=" ")`으로 생성한다. 따라서 timezone이 없는 입력은 요구된 `YYYY-MM-DD HH:MM:SS` 형태가 되고, timezone이 있는 입력은 UTC offset까지 유지된다.

`DecouplingConfig`는 변경 불가능한 dataclass이며 다음 설정을 제공한다.

- `epsilon=1e-8`
- `mad_multiplier=3.5`
- `max_lag=None`: 실제 사용값은 `max(1, window_size // 4)`
- `directional_correlation_threshold=0.0`
- `magnitude_threshold=None`, `magnitude_floor=2.0`
- `volatility_threshold=None`, `volatility_floor=log(2)`
- `phase_lag_threshold=None`
- `phase_correlation_drop_threshold=None`, `phase_correlation_drop_floor=0.2`

패턴별 임계값을 명시하면 해당 적응형 임계값을 대체한다. 최소 변화폭인 floor는 대응하는 명시적 임계값이 없을 때만 적용한다.

## 3. 입력 정렬과 검증

통계량 계산 전에 다음 절차를 수행한다.

1. 두 입력이 모두 pandas `Series`이며 `DatetimeIndex`를 사용하는지 확인한다.
2. 중복 timestamp와 숫자가 아닌 값을 거부한다.
3. 두 인덱스를 정렬하고 Inner Join을 수행한다.
4. 결합된 전체 시간축으로 기준 주기를 추론한 뒤, 어느 한쪽이라도 유한한 값이 아닌 행을 제거한다.
5. 결합 인덱스에서 양수인 시간 간격의 최빈값을 기준 주기로 사용한다. 최빈값이 여러 개면 가장 작은 양수 간격을 선택한다. 이후 두 유효 관측치의 시간 차이가 기준 주기와 정확히 같을 때만 연속으로 본다.

따라서 NaN을 제거해도 persistence 구간이 이어지지 않는다. 제거된 관측치 자체나 그 결과로 생긴 timestamp 공백이 연속 구간을 끊는다. 리샘플링과 보간은 수행하지 않는다.

입력 오류 정책은 다음과 같다.

- 컨테이너 또는 인덱스 타입이 잘못된 경우: `TypeError`
- 중복 timestamp, 숫자가 아닌 값, 잘못된 파라미터, 빈 교집합, 추론할 수 없는 기준 주기, 분석하기에 부족한 데이터: `ValueError`

파라미터 제약은 `window_size >= 3`, `persistence >= 1`, `epsilon > 0`, `mad_multiplier > 0`, `1 <= max_lag < window_size`다. 정렬과 이동 통계 warm-up 이후 모든 통계량에서 유한하고 연속적인 관측치가 최소 `persistence`개 생성되어야 한다. 이를 만족하지 못하면 정상으로 보고하지 않고 데이터 부족 오류로 처리한다.

## 4. 정규화와 공통 robust 통계

두 입력은 각각 rolling Z-score로 정규화한다.

```text
z[t] = (x[t] - rolling_mean[t]) / max(rolling_std[t], epsilon)
```

이동 표준편차는 `ddof=0`을 사용하고 `window_size` 전체가 채워졌을 때만 계산한다. 값이 일정한 윈도우는 0으로 나누거나 무한대를 만들지 않고 유한한 0 중심 값으로 변환한다.

두 시계열이 어떻게 움직이는지를 나타내는 통계에는 `movement = z.diff()`를 사용한다. 값/위상 이탈에는 Z-score 수준 차이를 직접 사용한다.

적응형 임계값은 현재 배치에 포함된 모든 유한한 통계량으로 계산한다.

```text
median = median(metric)
robust_sigma = 1.4826 * median(abs(metric - median))
robust_range = mad_multiplier * max(robust_sigma, epsilon)
```

전체 배치를 사용하는 것은 배치 전용인 이 버전의 의도된 동작이다. 초기 관측치에도 안정적인 기준을 제공하고, 이상치가 전체의 소수라면 그 영향을 억제한다. 온라인 또는 미래 데이터 미참조 방식의 추정기는 아니다.

## 5. 패턴별 통계량과 이상 마스크

### 5.1. 방향성 역전

정규화된 두 movement 사이의 rolling Pearson correlation을 `window_size` 구간으로 계산한다.

기본 이상 조건은 다음과 같다.

```text
rolling_correlation < 0.0
```

`directional_correlation_threshold`를 설정하면 0을 대체한다. movement 변동성이 0인 윈도우를 포함해 상관계수를 계산할 수 없는 구간은 이상으로 보지 않는다.

### 5.2. 값/위상 이탈

다음 두 통계량을 계산한다.

```text
signed_gap = z1 - z2
absolute_gap = abs(signed_gap)
```

적응형 임계값은 다음과 같다.

```text
max(median(absolute_gap) + robust_range(absolute_gap), magnitude_floor)
```

이상 조건은 `absolute_gap > threshold`다. `signed_gap`의 부호 변화는 값/위상 이탈이 이미 이상인 경우에만 교차로 기록한다. 단순 교차만으로는 이벤트를 만들지 않는다.

### 5.3. 변동성 불일치

정규화된 두 movement에 대해 각각 `ddof=0`인 이동 표준편차를 계산하고 다음 통계량을 구한다.

```text
log_ratio = log((std1 + epsilon) / (std2 + epsilon))
baseline = median(log_ratio)
volatility_score = abs(log_ratio - baseline)
```

적응형 점수 임계값은 다음과 같다.

```text
max(robust_range(log_ratio), volatility_floor)
```

이상 조건은 `volatility_score > threshold`다. signed ratio는 이벤트 설명에서 어느 시계열의 상대 변동성이 증가하거나 감소했는지 나타내기 위해 유지한다.

### 5.4. 반응 지연 또는 관계 단절

계산 가능한 각 종료 시점에서 movement 윈도우를 기준으로 `[-max_lag, max_lag]` 범위의 모든 정수 lag에 대해 signed Pearson cross-correlation을 계산한다. Lag `L`은 `ts1[t]`와 `ts2[t + L]`를 비교한다. 양의 lag는 `ts1`이 `ts2`보다 `L`에포크 선행함을 뜻한다. 각 후보는 해당 윈도우 안에서 겹치는 관측치만 사용하며, 유한한 관측치 쌍이 최소 3개 있어야 한다.

Signed correlation이 가장 높은 lag를 선택한다. 동률이면 절댓값이 가장 작은 lag를 우선하고, 그래도 동률이면 signed lag가 더 작은 값을 선택한다. 이 규칙은 역방향 관계를 정상적인 위상 동기화로 잘못 취급하지 않도록 한다.

모든 유한한 rolling 결과에서 다음 기준값과 점수를 계산한다.

```text
baseline_lag = median(best_lag)
baseline_peak_correlation = median(peak_correlation)
lag_shift = abs(best_lag - baseline_lag)
correlation_drop = baseline_peak_correlation - peak_correlation
```

적응형 lag 임계값은 `max(1, ceil(robust_range(best_lag)))`다. 적응형 관계 단절 임계값은 `max(robust_range(peak_correlation), phase_correlation_drop_floor)`다.

다음 중 하나를 만족하면 반응 지연 이상 마스크를 참으로 설정한다.

- `lag_shift >= lag threshold`
- `correlation_drop > relationship-loss threshold`

두 하위 조건은 이벤트 설명을 위해 별도로 유지한다. 명시적 phase 임계값이 있으면 대응하는 적응형 임계값을 대체한다.

## 6. 지속성 검증과 Debouncing

각 패턴은 독립된 Boolean 이상 마스크를 생성한다. 참인 구간이 추론된 기준 주기로 `persistence`개 관측치 동안 연속될 때만 이벤트를 확정한다. 거짓 값, 정의되지 않은 통계량, 제거된 관측치 또는 timestamp 공백은 해당 연속 구간을 종료한다.

구간이 확정되면 다음 시각을 포함한 이벤트를 정확히 한 번 생성한다.

- `timestamp`: 해당 이상 구간의 첫 관측 시각
- `confirmed_at`: 해당 이상 구간에서 `persistence`번째 관측 시각

그 뒤 이상 상태가 계속되어도 같은 이벤트를 반복 생성하지 않는다. 해당 패턴이 정상 상태로 돌아오거나 연속성이 끊긴 뒤에만 다시 이벤트를 생성할 수 있다. 서로 다른 패턴의 이벤트는 억제하거나 합치지 않는다.

설명문은 결정론적인 한국어 템플릿으로 생성한다. 시작 시각, 확정 시각, persistence 개수, 시작·확정 시점의 관련 통계량, 판정을 만든 임계값 또는 기준값을 포함한다. 값/위상 이탈 설명은 교차가 이상 구간과 동시에 발생했을 때만 이를 언급한다. 반응 지연 설명은 lag 이동과 관계 단절을 구분한다.

## 7. 시각화

시각화는 완전히 선택적이다. `enable_plot=False`이면 plotting helper를 호출하지 않고 공개 반환값에 `None`을 넣는다. `show()`를 호출하거나 파일을 저장하거나 전역 Matplotlib style을 변경하지 않는다.

분석가 검증 화면은 합의된 소형 다중 패널 구조를 사용한다.

- 상단 전체 폭: 이중 Y축을 적용한 원본 `ts1`, `ts2`
- 하단 2×2 패널: rolling correlation, absolute Z-score gap, volatility log-ratio, best lag
- phase 패널에는 peak cross-correlation을 위한 보조 Y축을 둘 수 있음
- 적응형 또는 재정의된 임계값과 관련 기준값을 수평 기준선으로 표시
- 이벤트 시작은 수직 실선, 확정 시각은 수직 점선, 두 시점 사이는 옅은 음영으로 표시
- 각 이벤트는 원본 패널과 해당 패턴의 통계 패널에 표시

모든 패널은 시간축을 공유한다. 긴 배치에서 이벤트가 여러 개 발생해도 읽기 쉽도록 범례의 중복을 제거한다.

## 8. 의존성과 저장소 통합

`requirements.txt`에 `numpy`, `pandas`, `matplotlib`을 명시적으로 추가한다. 저장소의 평면형 패키지 규칙과 호환되는 공개 import는 다음과 같다.

```python
from src.decoupling_detector import DecouplingConfig, detect_decoupling
```

기존 PDF 추출, 검토, 메타데이터 또는 체크리스트 동작은 변경하지 않는다.

## 9. 테스트 전략

구현은 Red-Green-Refactor 순서로 진행한다. 각 운영 코드 동작은 해당 동작이 없어서 실패하는 집중 테스트를 먼저 확인한 뒤에만 추가한다.

결정론적인 합성 시계열로 다음을 검증한다.

- rolling 정규화와 값이 일정한 윈도우의 유한값 처리
- 네 패턴 각각의 독립 이상 마스크
- 같은 시각에 발생하는 독립 패턴 이벤트
- 정확한 시작 시각과 확정 시각
- persistence 경계와 off-by-one 사례
- 장기 이상 구간의 반복 억제와 정상화 후 재발
- Inner Join, 정렬, NaN 제거, 기준 주기 단절
- 변동성 0 구간과 epsilon 처리
- 적응형 기본값과 모든 명시적 임계값 override
- 양수·음수 lag의 부호 규칙과 결정론적 동률 처리
- timezone 보존
- 잘못된 입력·설정, 빈 교집합, 데이터 부족
- 시각화 On/Off, 합의된 패널 구성, 이벤트 마커

최종 검증은 감지기 집중 테스트, 통합 지점이 변경된 경우 관련 전체 테스트, 다음 컴파일 검사로 구성한다.

```text
python -m compileall src tests scripts apps
```

## 10. 제외 범위

v1.1에는 온라인 상태 관리, 지도학습, 자동 리샘플링, 보간, 이벤트 심각도, 복합 이벤트 병합, 파일 출력, plot 표시, 알림 전송 또는 외부 API 호출을 포함하지 않는다.
