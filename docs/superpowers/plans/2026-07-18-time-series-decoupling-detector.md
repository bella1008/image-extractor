# Time-Series Decoupling Detector Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 단위와 스케일이 다른 두 pandas 시계열의 네 가지 디커플링 패턴을 비지도 방식으로 감지하고, 시작·확정 시각이 포함된 한국어 이벤트와 선택적 검증 Figure를 반환한다.

**Architecture:** 공개 API와 설정, 입력 정렬, 통계 계산, persistence/debouncing, 이벤트 설명, plotting을 `src/decoupling_detector.py` 안의 작은 함수로 분리한다. 모든 패턴은 독립된 Boolean 마스크를 만들고 공통 persistence 함수로 이벤트를 확정하며, plotting은 `enable_plot=True`일 때만 지연 import한다.

**Tech Stack:** Python 3.11+, NumPy, pandas, Matplotlib, `unittest`

---

## 파일 구성

- 생성: `src/decoupling_detector.py` — 공개 API, 설정 dataclass, 통계량, 이벤트, 시각화
- 생성: `tests/test_decoupling_detector.py` — 합성 시계열 기반 단위·통합 테스트
- 수정: `requirements.txt` — NumPy, pandas, Matplotlib 직접 의존성 추가
- 참조: `docs/superpowers/specs/2026-07-18-time-series-decoupling-detector-design.md`

현재 작업 트리에 다른 변경이 많으므로 실행을 시작할 때 `using-git-worktrees` 지침으로 격리된 worktree를 만든다. 아래 커밋은 모두 그 worktree에서 수행한다.

### Task 1: 공개 설정과 기본 검증 계약

**Files:**
- Create: `src/decoupling_detector.py`
- Create: `tests/test_decoupling_detector.py`
- Modify: `requirements.txt`

- [ ] **Step 1: 모듈과 설정 계약을 요구하는 실패 테스트 작성**

```python
import math
import unittest

import pandas as pd

from src.decoupling_detector import DecouplingConfig, detect_decoupling


class DecouplingConfigTests(unittest.TestCase):
    def test_default_config_matches_design(self):
        config = DecouplingConfig()

        self.assertEqual(config.epsilon, 1e-8)
        self.assertEqual(config.mad_multiplier, 3.5)
        self.assertIsNone(config.max_lag)
        self.assertEqual(config.directional_correlation_threshold, 0.0)
        self.assertIsNone(config.magnitude_threshold)
        self.assertEqual(config.magnitude_floor, 2.0)
        self.assertIsNone(config.volatility_threshold)
        self.assertEqual(config.volatility_floor, math.log(2.0))
        self.assertIsNone(config.phase_lag_threshold)
        self.assertIsNone(config.phase_correlation_drop_threshold)
        self.assertEqual(config.phase_correlation_drop_floor, 0.2)

    def test_public_api_rejects_non_series_inputs(self):
        with self.assertRaisesRegex(TypeError, "pandas Series"):
            detect_decoupling([1, 2, 3], [1, 2, 3], window_size=3, persistence=1)
```

- [ ] **Step 2: 테스트가 모듈 부재로 실패하는지 확인**

Run: `python -m unittest tests.test_decoupling_detector.DecouplingConfigTests -v`

Expected: FAIL 또는 ERROR with `ModuleNotFoundError: No module named 'src.decoupling_detector'`

- [ ] **Step 3: 의존성을 보존적으로 추가하고 최소 공개 골격 구현**

`requirements.txt`의 기존 세 줄을 유지한 채 다음을 추가한다.

```text
numpy>=1.26
pandas>=2.2
matplotlib>=3.8
```

`src/decoupling_detector.py`를 다음 내용으로 시작한다.

```python
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class DecouplingConfig:
    epsilon: float = 1e-8
    mad_multiplier: float = 3.5
    max_lag: int | None = None
    directional_correlation_threshold: float = 0.0
    magnitude_threshold: float | None = None
    magnitude_floor: float = 2.0
    volatility_threshold: float | None = None
    volatility_floor: float = math.log(2.0)
    phase_lag_threshold: int | None = None
    phase_correlation_drop_threshold: float | None = None
    phase_correlation_drop_floor: float = 0.2


def detect_decoupling(
    ts1: pd.Series,
    ts2: pd.Series,
    window_size: int,
    persistence: int,
    enable_plot: bool = False,
    config: DecouplingConfig | None = None,
) -> tuple[list[dict[str, str]], Any | None]:
    if not isinstance(ts1, pd.Series) or not isinstance(ts2, pd.Series):
        raise TypeError("ts1 and ts2 must be pandas Series")
    raise ValueError("insufficient data for decoupling analysis")
```

- [ ] **Step 4: 설정 테스트가 통과하는지 확인**

Run: `python -m unittest tests.test_decoupling_detector.DecouplingConfigTests -v`

Expected: PASS, 2 tests

- [ ] **Step 5: 첫 계약 커밋**

```bash
git add requirements.txt src/decoupling_detector.py tests/test_decoupling_detector.py
git commit -m "Add decoupling detector configuration contract"
```

### Task 2: 입력 정렬, 기준 주기, rolling Z-score

**Files:**
- Modify: `src/decoupling_detector.py`
- Modify: `tests/test_decoupling_detector.py`

- [ ] **Step 1: 정렬·Inner Join·결측 제거·상수 구간 테스트 작성**

```python
from src.decoupling_detector import _rolling_zscore, _validate_and_align


class AlignmentAndNormalizationTests(unittest.TestCase):
    def test_aligns_on_inner_join_sorts_and_keeps_inferred_hourly_cadence(self):
        left_index = pd.to_datetime([
            "2026-07-18 03:00",
            "2026-07-18 01:00",
            "2026-07-18 02:00",
            "2026-07-18 04:00",
        ])
        right_index = pd.date_range("2026-07-18 00:00", periods=5, freq="h")
        ts1 = pd.Series([3.0, 1.0, float("nan"), 4.0], index=left_index)
        ts2 = pd.Series(range(5), index=right_index, dtype=float)

        frame, cadence = _validate_and_align(ts1, ts2)

        self.assertEqual(list(frame.index), list(pd.to_datetime([
            "2026-07-18 01:00",
            "2026-07-18 03:00",
            "2026-07-18 04:00",
        ])))
        self.assertEqual(cadence, pd.Timedelta(hours=1))
        self.assertEqual(list(frame.columns), ["ts1", "ts2"])

    def test_constant_window_zscore_is_finite_zero(self):
        series = pd.Series(
            [5.0] * 8,
            index=pd.date_range("2026-07-18", periods=8, freq="h"),
        )

        result = _rolling_zscore(series, window_size=4, epsilon=1e-8)

        self.assertTrue(result.iloc[3:].notna().all())
        self.assertTrue((result.iloc[3:] == 0.0).all())

    def test_infers_daily_cadence(self):
        index = pd.date_range("2026-07-01", periods=5, freq="D")
        ts1 = pd.Series(np.arange(5), index=index, dtype=float)
        ts2 = pd.Series(np.arange(5) * 2, index=index, dtype=float)

        frame, cadence = _validate_and_align(ts1, ts2)

        self.assertEqual(len(frame), 5)
        self.assertEqual(cadence, pd.Timedelta(days=1))

    def test_rejects_duplicate_datetime_index(self):
        index = pd.to_datetime(["2026-07-18", "2026-07-18"])
        ts1 = pd.Series([1.0, 2.0], index=index)
        ts2 = pd.Series([1.0, 2.0], index=index)

        with self.assertRaisesRegex(ValueError, "duplicate"):
            _validate_and_align(ts1, ts2)
```

- [ ] **Step 2: 새 helper 부재로 실패하는지 확인**

Run: `python -m unittest tests.test_decoupling_detector.AlignmentAndNormalizationTests -v`

Expected: ERROR with import failure for `_rolling_zscore` or `_validate_and_align`

- [ ] **Step 3: 입력 정렬과 정규화 최소 구현**

`src/decoupling_detector.py`에 추가한다.

```python
def _validate_and_align(
    ts1: pd.Series,
    ts2: pd.Series,
) -> tuple[pd.DataFrame, pd.Timedelta]:
    if not isinstance(ts1, pd.Series) or not isinstance(ts2, pd.Series):
        raise TypeError("ts1 and ts2 must be pandas Series")
    if not isinstance(ts1.index, pd.DatetimeIndex) or not isinstance(ts2.index, pd.DatetimeIndex):
        raise TypeError("ts1 and ts2 must use DatetimeIndex")
    if ts1.index.has_duplicates or ts2.index.has_duplicates:
        raise ValueError("duplicate timestamps are not allowed")
    if not pd.api.types.is_numeric_dtype(ts1.dtype) or not pd.api.types.is_numeric_dtype(ts2.dtype):
        raise ValueError("ts1 and ts2 must contain numeric values")

    joined = pd.concat(
        [ts1.sort_index().rename("ts1"), ts2.sort_index().rename("ts2")],
        axis=1,
        join="inner",
    )
    if joined.empty:
        raise ValueError("ts1 and ts2 have no common timestamps")

    deltas = joined.index.to_series().diff().dropna()
    positive_deltas = deltas[deltas > pd.Timedelta(0)]
    if positive_deltas.empty:
        raise ValueError("unable to infer time cadence")
    counts = positive_deltas.value_counts()
    cadence = min(counts[counts == counts.max()].index)

    finite = np.isfinite(joined["ts1"].to_numpy(dtype=float))
    finite &= np.isfinite(joined["ts2"].to_numpy(dtype=float))
    aligned = joined.loc[finite].astype(float)
    if aligned.empty:
        raise ValueError("no finite aligned observations")
    return aligned, cadence


def _rolling_zscore(
    series: pd.Series,
    window_size: int,
    epsilon: float,
) -> pd.Series:
    mean = series.rolling(window_size, min_periods=window_size).mean()
    std = series.rolling(window_size, min_periods=window_size).std(ddof=0)
    denominator = std.clip(lower=epsilon)
    return (series - mean) / denominator
```

- [ ] **Step 4: 정렬·정규화 테스트 통과 확인**

Run: `python -m unittest tests.test_decoupling_detector.AlignmentAndNormalizationTests -v`

Expected: PASS, 4 tests

- [ ] **Step 5: 입력 처리 커밋**

```bash
git add src/decoupling_detector.py tests/test_decoupling_detector.py
git commit -m "Add aligned rolling normalization"
```

### Task 3: Robust 기준, 방향성 역전, 값/위상 이탈

**Files:**
- Modify: `src/decoupling_detector.py`
- Modify: `tests/test_decoupling_detector.py`

- [ ] **Step 1: 통계량과 override 동작의 실패 테스트 작성**

```python
from src.decoupling_detector import (
    _directional_metrics,
    _magnitude_metrics,
    _robust_range,
)


class DirectionalAndMagnitudeTests(unittest.TestCase):
    def test_robust_range_ignores_outlier_majority_effect(self):
        metric = pd.Series([1.0, 1.0, 1.0, 1.1, 20.0])

        median, spread = _robust_range(metric, multiplier=3.5, epsilon=1e-8)

        self.assertEqual(median, 1.0)
        self.assertLess(spread, 1.0)

    def test_directional_mask_is_true_for_persistent_inverse_movement(self):
        movement1 = pd.Series([1.0, -1.0] * 8)
        movement2 = -movement1

        correlation, mask = _directional_metrics(
            movement1,
            movement2,
            window_size=4,
            threshold=0.0,
        )

        self.assertAlmostEqual(correlation.iloc[-1], -1.0)
        self.assertTrue(mask.iloc[-1])

    def test_directional_threshold_can_be_overridden(self):
        movement1 = pd.Series([1.0, -1.0] * 8)
        movement2 = -movement1

        correlation, mask = _directional_metrics(
            movement1,
            movement2,
            window_size=4,
            threshold=-1.1,
        )

        self.assertAlmostEqual(correlation.iloc[-1], -1.0)
        self.assertFalse(mask.iloc[-1])

    def test_magnitude_override_and_crossing_are_reported_separately(self):
        z1 = pd.Series([-0.5, 1.5, 2.5])
        z2 = pd.Series([0.5, -1.5, -2.5])
        config = DecouplingConfig(magnitude_threshold=2.0)

        signed_gap, absolute_gap, crossing, threshold, mask = _magnitude_metrics(
            z1,
            z2,
            config,
        )

        self.assertEqual(threshold, 2.0)
        self.assertTrue(crossing.iloc[1])
        self.assertTrue(mask.iloc[1])
        self.assertEqual(absolute_gap.iloc[-1], 5.0)
```

- [ ] **Step 2: helper 부재로 실패하는지 확인**

Run: `python -m unittest tests.test_decoupling_detector.DirectionalAndMagnitudeTests -v`

Expected: ERROR with import failure for the new metric helpers

- [ ] **Step 3: Robust 기준과 두 패턴 구현**

`src/decoupling_detector.py`에 추가한다.

```python
def _robust_range(
    metric: pd.Series,
    multiplier: float,
    epsilon: float,
) -> tuple[float, float]:
    finite = metric[np.isfinite(metric.to_numpy(dtype=float))]
    if finite.empty:
        raise ValueError("metric has no finite values")
    median = float(finite.median())
    mad = float((finite - median).abs().median())
    robust_sigma = 1.4826 * mad
    return median, multiplier * max(robust_sigma, epsilon)


def _directional_metrics(
    movement1: pd.Series,
    movement2: pd.Series,
    window_size: int,
    threshold: float,
) -> tuple[pd.Series, pd.Series]:
    correlation = movement1.rolling(
        window_size,
        min_periods=window_size,
    ).corr(movement2)
    mask = correlation.lt(threshold).fillna(False)
    return correlation, mask


def _magnitude_metrics(
    z1: pd.Series,
    z2: pd.Series,
    config: DecouplingConfig,
) -> tuple[pd.Series, pd.Series, pd.Series, float, pd.Series]:
    signed_gap = z1 - z2
    absolute_gap = signed_gap.abs()
    if config.magnitude_threshold is None:
        median, spread = _robust_range(
            absolute_gap,
            config.mad_multiplier,
            config.epsilon,
        )
        threshold = max(median + spread, config.magnitude_floor)
    else:
        threshold = float(config.magnitude_threshold)

    previous_sign = np.sign(signed_gap.shift(1))
    current_sign = np.sign(signed_gap)
    crossing = previous_sign.ne(current_sign)
    crossing &= previous_sign.ne(0) & current_sign.ne(0)
    mask = absolute_gap.gt(threshold).fillna(False)
    crossing &= mask
    return signed_gap, absolute_gap, crossing.fillna(False), threshold, mask
```

- [ ] **Step 4: 두 패턴 테스트 통과 확인**

Run: `python -m unittest tests.test_decoupling_detector.DirectionalAndMagnitudeTests -v`

Expected: PASS, 4 tests

- [ ] **Step 5: 방향성·Magnitude 커밋**

```bash
git add src/decoupling_detector.py tests/test_decoupling_detector.py
git commit -m "Add directional and magnitude metrics"
```

### Task 4: 변동성 불일치

**Files:**
- Modify: `src/decoupling_detector.py`
- Modify: `tests/test_decoupling_detector.py`

- [ ] **Step 1: 변동성 비율과 0 변동성 실패 테스트 작성**

```python
from src.decoupling_detector import _volatility_metrics


class VolatilityTests(unittest.TestCase):
    def test_volatility_override_detects_ratio_change(self):
        movement1 = pd.Series([1.0, -1.0] * 8)
        movement2 = pd.Series([1.0, -1.0] * 4 + [4.0, -4.0] * 4)
        config = DecouplingConfig(volatility_threshold=0.5)

        log_ratio, score, baseline, threshold, mask = _volatility_metrics(
            movement1,
            movement2,
            window_size=4,
            config=config,
        )

        self.assertEqual(threshold, 0.5)
        self.assertTrue(np.isfinite(log_ratio.dropna()).all())
        self.assertTrue(mask.iloc[-1])
        self.assertGreater(score.iloc[-1], threshold)

    def test_both_constant_movements_do_not_divide_by_zero(self):
        movement1 = pd.Series([0.0] * 8)
        movement2 = pd.Series([0.0] * 8)

        log_ratio, score, baseline, threshold, mask = _volatility_metrics(
            movement1,
            movement2,
            window_size=4,
            config=DecouplingConfig(),
        )

        self.assertTrue(np.isfinite(log_ratio.dropna()).all())
        self.assertEqual(baseline, 0.0)
        self.assertFalse(mask.any())
```

- [ ] **Step 2: 변동성 helper 부재로 실패 확인**

Run: `python -m unittest tests.test_decoupling_detector.VolatilityTests -v`

Expected: ERROR with import failure for `_volatility_metrics`

- [ ] **Step 3: signed log-ratio 기반 변동성 구현**

`src/decoupling_detector.py`에 추가한다.

```python
def _volatility_metrics(
    movement1: pd.Series,
    movement2: pd.Series,
    window_size: int,
    config: DecouplingConfig,
) -> tuple[pd.Series, pd.Series, float, float, pd.Series]:
    std1 = movement1.rolling(window_size, min_periods=window_size).std(ddof=0)
    std2 = movement2.rolling(window_size, min_periods=window_size).std(ddof=0)
    log_ratio = np.log((std1 + config.epsilon) / (std2 + config.epsilon))
    baseline, spread = _robust_range(
        log_ratio,
        config.mad_multiplier,
        config.epsilon,
    )
    score = (log_ratio - baseline).abs()
    if config.volatility_threshold is None:
        threshold = max(spread, config.volatility_floor)
    else:
        threshold = float(config.volatility_threshold)
    mask = score.gt(threshold).fillna(False)
    return log_ratio, score, baseline, threshold, mask
```

- [ ] **Step 4: 변동성 테스트 통과 확인**

Run: `python -m unittest tests.test_decoupling_detector.VolatilityTests -v`

Expected: PASS, 2 tests

- [ ] **Step 5: 변동성 커밋**

```bash
git add src/decoupling_detector.py tests/test_decoupling_detector.py
git commit -m "Add volatility mismatch metric"
```

### Task 5: 반응 지연과 관계 단절

**Files:**
- Modify: `src/decoupling_detector.py`
- Modify: `tests/test_decoupling_detector.py`

- [ ] **Step 1: lag 부호, 동률 규칙, 관계 단절 실패 테스트 작성**

```python
from src.decoupling_detector import _phase_metrics, _rolling_cross_correlation


class PhaseShiftTests(unittest.TestCase):
    def test_positive_lag_means_ts1_leads_ts2(self):
        source = pd.Series(np.sin(np.arange(80) / 3.0))
        delayed = source.shift(2)

        best_lag, peak = _rolling_cross_correlation(
            source,
            delayed,
            window_size=30,
            max_lag=4,
            epsilon=1e-8,
        )

        self.assertEqual(best_lag.iloc[-1], 2.0)
        self.assertGreater(peak.iloc[-1], 0.99)

    def test_relationship_loss_sets_phase_mask(self):
        rng = np.random.default_rng(7)
        source = pd.Series(np.sin(np.arange(140) / 4.0))
        comparison = source.copy()
        comparison.iloc[100:] = rng.normal(size=40)
        config = DecouplingConfig(
            max_lag=4,
            phase_lag_threshold=99,
            phase_correlation_drop_threshold=0.2,
        )

        result = _phase_metrics(
            source,
            comparison,
            window_size=24,
            max_lag=4,
            config=config,
        )

        self.assertTrue(result["loss_mask"].iloc[-1])
        self.assertTrue(result["mask"].iloc[-1])
        self.assertFalse(result["lag_mask"].iloc[-1])
```

- [ ] **Step 2: phase helper 부재로 실패 확인**

Run: `python -m unittest tests.test_decoupling_detector.PhaseShiftTests -v`

Expected: ERROR with import failure for phase helpers

- [ ] **Step 3: rolling cross-correlation과 phase 점수 구현**

`src/decoupling_detector.py`에 추가한다.

```python
def _pearson_for_lag(
    x: np.ndarray,
    y: np.ndarray,
    lag: int,
    epsilon: float,
) -> float:
    if lag > 0:
        x_overlap, y_overlap = x[:-lag], y[lag:]
    elif lag < 0:
        x_overlap, y_overlap = x[-lag:], y[:lag]
    else:
        x_overlap, y_overlap = x, y
    finite = np.isfinite(x_overlap) & np.isfinite(y_overlap)
    x_valid, y_valid = x_overlap[finite], y_overlap[finite]
    if len(x_valid) < 3:
        return math.nan
    if np.std(x_valid) <= epsilon or np.std(y_valid) <= epsilon:
        return math.nan
    return float(np.corrcoef(x_valid, y_valid)[0, 1])


def _rolling_cross_correlation(
    movement1: pd.Series,
    movement2: pd.Series,
    window_size: int,
    max_lag: int,
    epsilon: float,
) -> tuple[pd.Series, pd.Series]:
    best_lag = pd.Series(math.nan, index=movement1.index, dtype=float)
    peak = pd.Series(math.nan, index=movement1.index, dtype=float)
    for end in range(window_size - 1, len(movement1)):
        start = end - window_size + 1
        x = movement1.iloc[start : end + 1].to_numpy(dtype=float)
        y = movement2.iloc[start : end + 1].to_numpy(dtype=float)
        candidates = [
            (lag, _pearson_for_lag(x, y, lag, epsilon))
            for lag in range(-max_lag, max_lag + 1)
        ]
        finite_candidates = [
            item for item in candidates if math.isfinite(item[1])
        ]
        if not finite_candidates:
            continue
        selected_lag, selected_corr = max(
            finite_candidates,
            key=lambda item: (item[1], -abs(item[0]), -item[0]),
        )
        best_lag.iloc[end] = float(selected_lag)
        peak.iloc[end] = selected_corr
    return best_lag, peak


def _phase_metrics(
    movement1: pd.Series,
    movement2: pd.Series,
    window_size: int,
    max_lag: int,
    config: DecouplingConfig,
) -> dict[str, object]:
    best_lag, peak = _rolling_cross_correlation(
        movement1,
        movement2,
        window_size,
        max_lag,
        config.epsilon,
    )
    baseline_lag, lag_spread = _robust_range(
        best_lag,
        config.mad_multiplier,
        config.epsilon,
    )
    baseline_peak, peak_spread = _robust_range(
        peak,
        config.mad_multiplier,
        config.epsilon,
    )
    lag_threshold = (
        max(1, math.ceil(lag_spread))
        if config.phase_lag_threshold is None
        else int(config.phase_lag_threshold)
    )
    drop_threshold = (
        max(peak_spread, config.phase_correlation_drop_floor)
        if config.phase_correlation_drop_threshold is None
        else float(config.phase_correlation_drop_threshold)
    )
    lag_shift = (best_lag - baseline_lag).abs()
    correlation_drop = baseline_peak - peak
    lag_mask = lag_shift.ge(lag_threshold).fillna(False)
    loss_mask = correlation_drop.gt(drop_threshold).fillna(False)
    return {
        "best_lag": best_lag,
        "peak_correlation": peak,
        "baseline_lag": baseline_lag,
        "baseline_peak_correlation": baseline_peak,
        "lag_shift": lag_shift,
        "correlation_drop": correlation_drop,
        "lag_threshold": float(lag_threshold),
        "correlation_drop_threshold": drop_threshold,
        "lag_mask": lag_mask,
        "loss_mask": loss_mask,
        "mask": lag_mask | loss_mask,
    }
```

- [ ] **Step 4: phase 테스트 통과 확인**

Run: `python -m unittest tests.test_decoupling_detector.PhaseShiftTests -v`

Expected: PASS, 2 tests

- [ ] **Step 5: phase 커밋**

```bash
git add src/decoupling_detector.py tests/test_decoupling_detector.py
git commit -m "Add phase shift and relationship loss metrics"
```

### Task 6: Persistence, 시간 단절, Debouncing

**Files:**
- Modify: `src/decoupling_detector.py`
- Modify: `tests/test_decoupling_detector.py`

- [ ] **Step 1: 시작·확정 시각과 재발 테스트 작성**

```python
from src.decoupling_detector import _confirmed_runs


class PersistenceTests(unittest.TestCase):
    def test_emits_start_and_confirmation_once_for_long_run(self):
        index = pd.date_range("2026-07-18 10:00", periods=8, freq="h")
        mask = pd.Series([True, True, True, True, True, True, False, False], index=index)

        runs = _confirmed_runs(
            mask,
            cadence=pd.Timedelta(hours=1),
            persistence=4,
        )

        self.assertEqual(runs, [(index[0], index[3])])

    def test_gap_breaks_persistence_and_recovery_rearms(self):
        index = pd.to_datetime([
            "2026-07-18 10:00",
            "2026-07-18 11:00",
            "2026-07-18 13:00",
            "2026-07-18 14:00",
            "2026-07-18 15:00",
            "2026-07-18 16:00",
            "2026-07-18 17:00",
            "2026-07-18 18:00",
            "2026-07-18 19:00",
        ])
        mask = pd.Series(
            [True, True, True, True, True, False, True, True, True],
            index=index,
        )

        runs = _confirmed_runs(
            mask,
            cadence=pd.Timedelta(hours=1),
            persistence=3,
        )

        self.assertEqual(runs, [
            (index[2], index[4]),
            (index[6], index[8]),
        ])
```

- [ ] **Step 2: persistence helper 부재로 실패 확인**

Run: `python -m unittest tests.test_decoupling_detector.PersistenceTests -v`

Expected: ERROR with import failure for `_confirmed_runs`

- [ ] **Step 3: 공통 연속 구간 스캐너 구현**

`src/decoupling_detector.py`에 추가한다.

```python
def _confirmed_runs(
    mask: pd.Series,
    cadence: pd.Timedelta,
    persistence: int,
) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    runs: list[tuple[pd.Timestamp, pd.Timestamp]] = []
    start: pd.Timestamp | None = None
    previous: pd.Timestamp | None = None
    length = 0

    for timestamp, anomalous in mask.fillna(False).items():
        timestamp = pd.Timestamp(timestamp)
        contiguous = previous is not None and timestamp - previous == cadence
        if not bool(anomalous):
            start = None
            length = 0
            previous = timestamp
            continue
        if length == 0 or not contiguous:
            start = timestamp
            length = 1
        else:
            length += 1
        if length == persistence and start is not None:
            runs.append((start, timestamp))
        previous = timestamp
    return runs
```

- [ ] **Step 4: persistence 테스트 통과 확인**

Run: `python -m unittest tests.test_decoupling_detector.PersistenceTests -v`

Expected: PASS, 2 tests

- [ ] **Step 5: persistence 커밋**

```bash
git add src/decoupling_detector.py tests/test_decoupling_detector.py
git commit -m "Add persistent event debouncing"
```

### Task 7: 공개 감지 흐름과 한국어 이벤트

**Files:**
- Modify: `src/decoupling_detector.py`
- Modify: `tests/test_decoupling_detector.py`

- [ ] **Step 1: 공개 API, 독립 이벤트, timezone 실패 테스트 작성**

```python
class PublicDetectionTests(unittest.TestCase):
    def test_detects_directional_event_with_start_and_confirmed_at(self):
        index = pd.date_range(
            "2026-07-15",
            periods=140,
            freq="h",
            tz="Asia/Seoul",
        )
        values = np.sin(np.arange(140) / 2.5)
        ts1 = pd.Series(values, index=index)
        ts2_values = values.copy()
        ts2_values[95:] *= -1
        ts2 = pd.Series(ts2_values, index=index)
        config = DecouplingConfig(
            magnitude_threshold=100.0,
            volatility_threshold=100.0,
            phase_lag_threshold=100,
            phase_correlation_drop_threshold=2.0,
        )

        events, figure = detect_decoupling(
            ts1,
            ts2,
            window_size=12,
            persistence=4,
            enable_plot=False,
            config=config,
        )

        directional = [
            event for event in events
            if event["decoupling_type"] == "방향성 역전"
        ]
        self.assertEqual(len(directional), 1)
        start = pd.Timestamp(directional[0]["timestamp"])
        confirmed = pd.Timestamp(directional[0]["confirmed_at"])
        self.assertEqual(confirmed - start, pd.Timedelta(hours=3))
        self.assertEqual(str(start.tz), "Asia/Seoul")
        self.assertIn("4에포크", directional[0]["description"])
        self.assertIsNone(figure)

    def test_same_timestamp_masks_create_independent_events(self):
        index = pd.date_range("2026-07-18", periods=4, freq="h")
        metrics = pd.DataFrame(index=index)
        metrics["rolling_correlation"] = -0.5
        metrics["absolute_gap"] = 3.0
        metrics["signed_gap"] = 3.0
        metrics["crossing"] = False
        metrics["volatility_log_ratio"] = 1.0
        metrics["volatility_score"] = 1.0
        metrics["best_lag"] = 2.0
        metrics["peak_correlation"] = 0.2
        metrics["lag_shift"] = 2.0
        metrics["correlation_drop"] = 0.8
        masks = {
            "방향성 역전": pd.Series(True, index=index),
            "값/위상 이탈": pd.Series(True, index=index),
            "변동성 불일치": pd.Series(True, index=index),
            "반응 지연": pd.Series(True, index=index),
        }
        thresholds = {
            "directional": 0.0,
            "magnitude": 2.0,
            "volatility_baseline": 0.0,
            "volatility": 0.7,
            "phase_baseline_lag": 0.0,
            "phase_baseline_peak": 1.0,
            "phase_lag": 1.0,
            "phase_correlation_drop": 0.2,
        }

        events = _events_from_masks(
            masks,
            metrics,
            thresholds,
            cadence=pd.Timedelta(hours=1),
            persistence=3,
        )

        self.assertEqual(
            [event["decoupling_type"] for event in events],
            ["방향성 역전", "값/위상 이탈", "변동성 불일치", "반응 지연"],
        )
        self.assertTrue(all(event["timestamp"] == index[0].isoformat(sep=" ") for event in events))
        self.assertTrue(all(event["confirmed_at"] == index[2].isoformat(sep=" ") for event in events))
```

테스트 import 목록에 `_events_from_masks`를 추가한다.

- [ ] **Step 2: 공개 흐름 미구현으로 실패 확인**

Run: `python -m unittest tests.test_decoupling_detector.PublicDetectionTests -v`

Expected: FAIL because `detect_decoupling` still raises insufficient-data error or `_events_from_masks` is absent

- [ ] **Step 3: 설정 검증과 이벤트 템플릿 구현**

`src/decoupling_detector.py`에 다음 상수와 helper를 추가한다.

```python
_PATTERN_ORDER = (
    "방향성 역전",
    "값/위상 이탈",
    "변동성 불일치",
    "반응 지연",
)


def _resolved_max_lag(config: DecouplingConfig, window_size: int) -> int:
    return config.max_lag if config.max_lag is not None else max(1, window_size // 4)


def _validate_parameters(
    window_size: int,
    persistence: int,
    config: DecouplingConfig,
) -> int:
    max_lag = _resolved_max_lag(config, window_size)
    if window_size < 3:
        raise ValueError("window_size must be at least 3")
    if persistence < 1:
        raise ValueError("persistence must be at least 1")
    if config.epsilon <= 0 or config.mad_multiplier <= 0:
        raise ValueError("epsilon and mad_multiplier must be positive")
    if not 1 <= max_lag < window_size:
        raise ValueError("max_lag must satisfy 1 <= max_lag < window_size")
    numeric_thresholds = [
        config.magnitude_threshold,
        config.volatility_threshold,
        config.phase_correlation_drop_threshold,
    ]
    if any(value is not None and value < 0 for value in numeric_thresholds):
        raise ValueError("explicit thresholds must be non-negative")
    if config.phase_lag_threshold is not None and config.phase_lag_threshold < 1:
        raise ValueError("phase_lag_threshold must be at least 1")
    return max_lag


def _value_at(metrics: pd.DataFrame, column: str, timestamp: pd.Timestamp) -> float:
    return float(metrics.at[timestamp, column])


def _description(
    pattern: str,
    start: pd.Timestamp,
    confirmed: pd.Timestamp,
    persistence: int,
    metrics: pd.DataFrame,
    thresholds: dict[str, float],
) -> str:
    start_text = start.isoformat(sep=" ")
    confirmed_text = confirmed.isoformat(sep=" ")
    if pattern == "방향성 역전":
        first = _value_at(metrics, "rolling_correlation", start)
        last = _value_at(metrics, "rolling_correlation", confirmed)
        return (
            f"{start_text}부터 이동 상관계수가 {first:.4f}로 방향성 임계값 "
            f"{thresholds['directional']:.4f} 미만이 되었고, {confirmed_text}의 "
            f"{last:.4f}까지 {persistence}에포크 연속 지속되어 방향성 역전으로 확정되었습니다."
        )
    if pattern == "값/위상 이탈":
        first = _value_at(metrics, "absolute_gap", start)
        last = _value_at(metrics, "absolute_gap", confirmed)
        crossing = bool(metrics.at[start, "crossing"])
        crossing_text = " 시작 시점에 두 정규화 값의 교차도 확인되었습니다." if crossing else ""
        return (
            f"{start_text}부터 Z-score 격차가 {first:.4f}로 임계값 "
            f"{thresholds['magnitude']:.4f}을 초과했고, {confirmed_text}의 "
            f"{last:.4f}까지 {persistence}에포크 연속 지속되어 값/위상 이탈로 확정되었습니다."
            f"{crossing_text}"
        )
    if pattern == "변동성 불일치":
        first = _value_at(metrics, "volatility_log_ratio", start)
        last = _value_at(metrics, "volatility_log_ratio", confirmed)
        relative = "ts1" if last > thresholds["volatility_baseline"] else "ts2"
        return (
            f"{start_text}부터 변동성 log-ratio가 {first:.4f}로 기준 "
            f"{thresholds['volatility_baseline']:.4f}에서 임계 거리 "
            f"{thresholds['volatility']:.4f} 이상 이탈했고, {confirmed_text}의 "
            f"{last:.4f}까지 {persistence}에포크 연속 지속되어 {relative}의 상대 변동성이 "
            "더 큰 변동성 불일치로 확정되었습니다."
        )
    start_lag = _value_at(metrics, "best_lag", start)
    start_drop = _value_at(metrics, "correlation_drop", start)
    lag = _value_at(metrics, "best_lag", confirmed)
    drop = _value_at(metrics, "correlation_drop", confirmed)
    reason = (
        "최적 lag 이동과 관계 강도 하락"
        if (
            _value_at(metrics, "lag_shift", confirmed) >= thresholds["phase_lag"]
            and drop > thresholds["phase_correlation_drop"]
        )
        else "최적 lag 이동"
        if _value_at(metrics, "lag_shift", confirmed) >= thresholds["phase_lag"]
        else "관계 강도 하락"
    )
    return (
        f"{start_text}부터 최적 lag {start_lag:.0f}, 상관 하락폭 {start_drop:.4f}로 "
        f"반응 지연 이상이 시작되었고, {confirmed_text}에 최적 lag {lag:.0f}, "
        f"상관 하락폭 {drop:.4f} 상태로 {persistence}에포크 연속 지속되어 "
        f"{reason}에 의한 반응 지연으로 확정되었습니다."
    )


def _events_from_masks(
    masks: dict[str, pd.Series],
    metrics: pd.DataFrame,
    thresholds: dict[str, float],
    cadence: pd.Timedelta,
    persistence: int,
) -> list[dict[str, str]]:
    events: list[dict[str, str]] = []
    for pattern in _PATTERN_ORDER:
        for start, confirmed in _confirmed_runs(masks[pattern], cadence, persistence):
            events.append({
                "timestamp": start.isoformat(sep=" "),
                "confirmed_at": confirmed.isoformat(sep=" "),
                "decoupling_type": pattern,
                "description": _description(
                    pattern,
                    start,
                    confirmed,
                    persistence,
                    metrics,
                    thresholds,
                ),
            })
    order = {pattern: position for position, pattern in enumerate(_PATTERN_ORDER)}
    events.sort(key=lambda event: (
        pd.Timestamp(event["timestamp"]),
        order[event["decoupling_type"]],
    ))
    return events
```

- [ ] **Step 4: 공개 orchestration 구현**

기존 `detect_decoupling` 본문을 다음으로 교체한다.

```python
def detect_decoupling(
    ts1: pd.Series,
    ts2: pd.Series,
    window_size: int,
    persistence: int,
    enable_plot: bool = False,
    config: DecouplingConfig | None = None,
) -> tuple[list[dict[str, str]], Any | None]:
    active_config = config or DecouplingConfig()
    max_lag = _validate_parameters(window_size, persistence, active_config)
    frame, cadence = _validate_and_align(ts1, ts2)
    minimum_length = 2 * window_size + persistence - 1
    if len(frame) < minimum_length:
        raise ValueError(
            f"insufficient data: need at least {minimum_length} aligned observations"
        )
    z1 = _rolling_zscore(frame["ts1"], window_size, active_config.epsilon)
    z2 = _rolling_zscore(frame["ts2"], window_size, active_config.epsilon)
    movement1, movement2 = z1.diff(), z2.diff()

    correlation, directional_mask = _directional_metrics(
        movement1,
        movement2,
        window_size,
        active_config.directional_correlation_threshold,
    )
    signed_gap, absolute_gap, crossing, magnitude_threshold, magnitude_mask = (
        _magnitude_metrics(z1, z2, active_config)
    )
    log_ratio, volatility_score, volatility_baseline, volatility_threshold, volatility_mask = (
        _volatility_metrics(movement1, movement2, window_size, active_config)
    )
    phase = _phase_metrics(
        movement1,
        movement2,
        window_size,
        max_lag,
        active_config,
    )

    metrics = pd.DataFrame({
        "rolling_correlation": correlation,
        "signed_gap": signed_gap,
        "absolute_gap": absolute_gap,
        "crossing": crossing,
        "volatility_log_ratio": log_ratio,
        "volatility_score": volatility_score,
        "best_lag": phase["best_lag"],
        "peak_correlation": phase["peak_correlation"],
        "lag_shift": phase["lag_shift"],
        "correlation_drop": phase["correlation_drop"],
    }, index=frame.index)
    required = [
        "rolling_correlation",
        "absolute_gap",
        "volatility_log_ratio",
        "best_lag",
        "peak_correlation",
    ]
    for column in required:
        finite_mask = metrics[column].notna()
        if not _confirmed_runs(finite_mask, cadence, persistence):
            raise ValueError(f"insufficient data for metric: {column}")

    masks = {
        "방향성 역전": directional_mask,
        "값/위상 이탈": magnitude_mask,
        "변동성 불일치": volatility_mask,
        "반응 지연": phase["mask"],
    }
    thresholds = {
        "directional": active_config.directional_correlation_threshold,
        "magnitude": magnitude_threshold,
        "volatility_baseline": volatility_baseline,
        "volatility": volatility_threshold,
        "phase_baseline_lag": float(phase["baseline_lag"]),
        "phase_baseline_peak": float(phase["baseline_peak_correlation"]),
        "phase_lag": float(phase["lag_threshold"]),
        "phase_correlation_drop": float(phase["correlation_drop_threshold"]),
    }
    events = _events_from_masks(
        masks,
        metrics,
        thresholds,
        cadence,
        persistence,
    )
    figure = (
        _build_validation_plot(frame, metrics, thresholds, events)
        if enable_plot
        else None
    )
    return events, figure
```

`_build_validation_plot`은 Task 8에서 추가한다. Task 7 동안 `enable_plot=False` 테스트만 실행하므로 이름 조회는 발생하지 않는다.

- [ ] **Step 5: 공개 감지 테스트 통과 확인**

Run: `python -m unittest tests.test_decoupling_detector.PublicDetectionTests -v`

Expected: PASS, 2 tests

- [ ] **Step 6: 공개 감지 흐름 커밋**

```bash
git add src/decoupling_detector.py tests/test_decoupling_detector.py
git commit -m "Build decoupling events from independent masks"
```

### Task 8: 선택적 분석가 검증 Figure

**Files:**
- Modify: `src/decoupling_detector.py`
- Modify: `tests/test_decoupling_detector.py`

- [ ] **Step 1: plot On/Off와 패널 구조 실패 테스트 작성**

```python
class PlottingTests(unittest.TestCase):
    def test_enable_plot_returns_small_multiples_figure(self):
        index = pd.date_range("2026-07-10", periods=120, freq="h")
        values = np.sin(np.arange(120) / 3.0)
        ts1 = pd.Series(values, index=index)
        ts2 = pd.Series(values * 1.5 + 10.0, index=index)

        events, figure = detect_decoupling(
            ts1,
            ts2,
            window_size=12,
            persistence=3,
            enable_plot=True,
        )

        self.assertIsInstance(events, list)
        self.assertIsNotNone(figure)
        titles = {axis.get_title() for axis in figure.axes}
        self.assertIn("Raw Series", titles)
        self.assertIn("Rolling Correlation", titles)
        self.assertIn("Z-score Gap", titles)
        self.assertIn("Volatility Log-Ratio", titles)
        self.assertIn("Best Lag", titles)
        self.assertGreaterEqual(len(figure.axes), 7)

        import matplotlib.pyplot as plt
        plt.close(figure)
```

- [ ] **Step 2: plotting helper 부재로 실패 확인**

Run: `python -m unittest tests.test_decoupling_detector.PlottingTests -v`

Expected: FAIL with `NameError: name '_build_validation_plot' is not defined`

- [ ] **Step 3: B형 소형 다중 패널 Figure 구현**

`src/decoupling_detector.py`에 추가한다.

```python
def _build_validation_plot(
    frame: pd.DataFrame,
    metrics: pd.DataFrame,
    thresholds: dict[str, float],
    events: list[dict[str, str]],
) -> Any:
    import matplotlib.pyplot as plt

    figure = plt.figure(figsize=(15, 11), constrained_layout=True)
    grid = figure.add_gridspec(3, 2, height_ratios=[1.35, 1.0, 1.0])
    raw_axis = figure.add_subplot(grid[0, :])
    raw_twin = raw_axis.twinx()
    correlation_axis = figure.add_subplot(grid[1, 0], sharex=raw_axis)
    gap_axis = figure.add_subplot(grid[1, 1], sharex=raw_axis)
    volatility_axis = figure.add_subplot(grid[2, 0], sharex=raw_axis)
    lag_axis = figure.add_subplot(grid[2, 1], sharex=raw_axis)
    phase_twin = lag_axis.twinx()

    raw_axis.plot(frame.index, frame["ts1"], color="tab:blue", label="ts1")
    raw_twin.plot(frame.index, frame["ts2"], color="tab:orange", label="ts2")
    raw_axis.set_title("Raw Series")
    raw_axis.set_ylabel("ts1")
    raw_twin.set_ylabel("ts2")

    correlation_axis.plot(
        metrics.index,
        metrics["rolling_correlation"],
        color="tab:purple",
        label="correlation",
    )
    correlation_axis.axhline(
        thresholds["directional"],
        color="gray",
        linestyle=":",
        label="threshold",
    )
    correlation_axis.set_title("Rolling Correlation")

    gap_axis.plot(
        metrics.index,
        metrics["absolute_gap"],
        color="tab:green",
        label="absolute gap",
    )
    gap_axis.axhline(
        thresholds["magnitude"],
        color="gray",
        linestyle=":",
        label="threshold",
    )
    gap_axis.set_title("Z-score Gap")

    volatility_axis.plot(
        metrics.index,
        metrics["volatility_log_ratio"],
        color="tab:red",
        label="log-ratio",
    )
    baseline = thresholds["volatility_baseline"]
    volatility_threshold = thresholds["volatility"]
    volatility_axis.axhline(baseline, color="gray", linestyle="-.", label="baseline")
    volatility_axis.axhline(
        baseline + volatility_threshold,
        color="gray",
        linestyle=":",
        label="threshold",
    )
    volatility_axis.axhline(
        baseline - volatility_threshold,
        color="gray",
        linestyle=":",
    )
    volatility_axis.set_title("Volatility Log-Ratio")

    lag_axis.plot(
        metrics.index,
        metrics["best_lag"],
        color="tab:blue",
        label="best lag",
    )
    lag_baseline = thresholds["phase_baseline_lag"]
    lag_threshold = thresholds["phase_lag"]
    lag_axis.axhline(lag_baseline, color="gray", linestyle="-.", label="baseline lag")
    lag_axis.axhline(lag_baseline + lag_threshold, color="gray", linestyle=":")
    lag_axis.axhline(lag_baseline - lag_threshold, color="gray", linestyle=":")
    phase_twin.plot(
        metrics.index,
        metrics["peak_correlation"],
        color="tab:orange",
        alpha=0.65,
        label="peak correlation",
    )
    phase_twin.axhline(
        thresholds["phase_baseline_peak"] - thresholds["phase_correlation_drop"],
        color="tab:orange",
        linestyle=":",
        label="correlation-loss threshold",
    )
    lag_axis.set_title("Best Lag")
    phase_twin.set_ylabel("peak corr")

    panel_by_pattern = {
        "방향성 역전": correlation_axis,
        "값/위상 이탈": gap_axis,
        "변동성 불일치": volatility_axis,
        "반응 지연": lag_axis,
    }
    for event in events:
        start = pd.Timestamp(event["timestamp"])
        confirmed = pd.Timestamp(event["confirmed_at"])
        for axis in (raw_axis, panel_by_pattern[event["decoupling_type"]]):
            axis.axvline(start, color="crimson", linewidth=1.2)
            axis.axvline(confirmed, color="crimson", linestyle="--", linewidth=1.0)
            axis.axvspan(start, confirmed, color="crimson", alpha=0.08)

    for axis in (
        raw_axis,
        raw_twin,
        correlation_axis,
        gap_axis,
        volatility_axis,
        lag_axis,
        phase_twin,
    ):
        handles, labels = axis.get_legend_handles_labels()
        unique = dict(zip(labels, handles))
        if unique:
            axis.legend(unique.values(), unique.keys(), loc="best", fontsize=8)
        axis.grid(alpha=0.2)
    figure.autofmt_xdate()
    return figure
```

- [ ] **Step 4: plot 테스트 통과 확인**

Run: `python -m unittest tests.test_decoupling_detector.PlottingTests -v`

Expected: PASS, 1 test

- [ ] **Step 5: 시각화 커밋**

```bash
git add src/decoupling_detector.py tests/test_decoupling_detector.py
git commit -m "Add optional decoupling validation figure"
```

### Task 9: 예외·회귀 테스트와 최종 검증

**Files:**
- Modify: `tests/test_decoupling_detector.py`

- [ ] **Step 1: 잘못된 설정, 데이터 부족, 시간 단절 회귀 테스트 추가**

```python
class ErrorHandlingTests(unittest.TestCase):
    def test_rejects_invalid_window_persistence_and_lag(self):
        index = pd.date_range("2026-07-18", periods=20, freq="h")
        ts1 = pd.Series(np.arange(20), index=index, dtype=float)
        ts2 = ts1.copy()

        for kwargs in (
            {"window_size": 2, "persistence": 1},
            {"window_size": 4, "persistence": 0},
        ):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    detect_decoupling(ts1, ts2, **kwargs)
        with self.assertRaisesRegex(ValueError, "max_lag"):
            detect_decoupling(
                ts1,
                ts2,
                window_size=4,
                persistence=1,
                config=DecouplingConfig(max_lag=4),
            )

    def test_rejects_insufficient_data_instead_of_returning_normal(self):
        index = pd.date_range("2026-07-18", periods=12, freq="h")
        ts1 = pd.Series(np.arange(12), index=index, dtype=float)
        ts2 = ts1.copy()

        with self.assertRaisesRegex(ValueError, "insufficient data"):
            detect_decoupling(ts1, ts2, window_size=8, persistence=4)

    def test_rejects_non_datetime_nonnumeric_and_empty_intersection(self):
        with self.assertRaisesRegex(TypeError, "DatetimeIndex"):
            _validate_and_align(
                pd.Series([1.0, 2.0], index=[0, 1]),
                pd.Series([1.0, 2.0], index=[0, 1]),
            )

        dates = pd.date_range("2026-07-18", periods=2, freq="h")
        with self.assertRaisesRegex(ValueError, "numeric"):
            _validate_and_align(
                pd.Series(["a", "b"], index=dates),
                pd.Series([1.0, 2.0], index=dates),
            )

        with self.assertRaisesRegex(ValueError, "common timestamps"):
            _validate_and_align(
                pd.Series([1.0, 2.0], index=dates),
                pd.Series(
                    [1.0, 2.0],
                    index=pd.date_range("2026-07-19", periods=2, freq="h"),
                ),
            )

    def test_nan_gap_cannot_complete_persistence(self):
        index = pd.date_range("2026-07-18", periods=8, freq="h")
        mask = pd.Series([True, True, True, True, True, True, True], index=index.delete(3))

        runs = _confirmed_runs(mask, pd.Timedelta(hours=1), persistence=4)

        self.assertEqual(runs, [(index[4], index[7])])
```

- [ ] **Step 2: 새 회귀 테스트가 현재 구현을 정확히 검증하는지 확인**

Run: `python -m unittest tests.test_decoupling_detector.ErrorHandlingTests -v`

Expected: PASS, 4 tests

- [ ] **Step 3: 감지기 전체 집중 테스트 실행**

Run: `python -m unittest tests.test_decoupling_detector -v`

Expected: PASS, 23 tests, 0 failures, 0 errors

- [ ] **Step 4: 기존 핵심 모듈에 대한 비회귀 테스트 실행**

Run: `python -m unittest tests.test_run_logging tests.test_pdf_diff tests.test_dashboard_view -v`

Expected: PASS, 0 failures, 0 errors

- [ ] **Step 5: 프로젝트 규칙의 컴파일 검증 실행**

Run: `python -m compileall src tests scripts apps`

Expected: exit code 0 and no `SyntaxError`

- [ ] **Step 6: 변경 범위와 공백 오류 확인**

Run: `git diff --check`

Expected: no output

Run: `git status --short`

Expected: 이 기능에서 변경된 파일은 `requirements.txt`, `src/decoupling_detector.py`, `tests/test_decoupling_detector.py`뿐이며, 기존 사용자 변경은 격리 worktree에 없어야 한다.

- [ ] **Step 7: 최종 구현 커밋**

```bash
git add requirements.txt src/decoupling_detector.py tests/test_decoupling_detector.py
git commit -m "Verify decoupling detector edge cases"
```

## 완료 조건

- 공개 API가 `(events, plot_object)`를 반환한다.
- 네 패턴이 독립적으로 감지되고 같은 시각의 이벤트가 병합되지 않는다.
- 이벤트가 `timestamp`와 `confirmed_at`을 모두 포함한다.
- 결측과 시간 간격 단절이 persistence를 초기화한다.
- 장기 이상 상태에서 동일 이벤트가 반복되지 않는다.
- 모든 적응형 임계값은 전체 배치 median/MAD를 사용하고 설정값으로 재정의할 수 있다.
- `enable_plot=False`는 `None`, `True`는 합의된 B형 Figure를 반환한다.
- 집중 테스트, 비회귀 테스트, compileall, `git diff --check`가 모두 통과한다.
