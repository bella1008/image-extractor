# Time-Series Decoupling Detector v1.1 Design

## 1. Purpose and Scope

The module detects four independently evaluated forms of decoupling between two normally synchronized time series:

1. directional reversal;
2. magnitude divergence;
3. volatility mismatch;
4. phase shift or relationship loss.

It is a batch-oriented, unsupervised detector. It returns deterministic, LLM-readable Korean event descriptions and optionally produces an analyst-validation Matplotlib figure. It does not train or persist a model.

The implementation belongs in the repository's current flat `src/` package as `src/decoupling_detector.py`. Tests belong in `tests/test_decoupling_detector.py`.

## 2. Public Interface

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

Inputs:

- `ts1`, `ts2`: pandas `Series` with `DatetimeIndex`.
- `window_size`: rolling-statistic window measured in observations.
- `persistence`: number of consecutive anomalous observations required for confirmation.
- `enable_plot`: whether to create the validation figure; default `False`.
- `config`: optional `DecouplingConfig`. Omission selects adaptive defaults.

The return value is a tuple:

- `events`: `list[dict[str, str]]`;
- `plot_object`: a Matplotlib `Figure` when plotting is enabled, otherwise `None`.

Each event has exactly these fields:

```json
{
  "timestamp": "2026-07-18 10:00:00",
  "confirmed_at": "2026-07-18 21:00:00",
  "decoupling_type": "방향성 역전",
  "description": "10:00부터 ... 21:00까지 12에포크 연속 지속되어 이상 상태로 확정되었습니다."
}
```

`timestamp` is the first anomalous observation in a confirmed run. `confirmed_at` is the observation at which that run first reaches `persistence`. Timezone information is retained when the source index is timezone-aware. Events are sorted by `timestamp`, followed by a stable pattern order when timestamps match.

The stable `decoupling_type` values and ordering are `방향성 역전`, `값/위상 이탈`, `변동성 불일치`, and `반응 지연`. Timestamp strings use `pandas.Timestamp.isoformat(sep=" ")`, which yields the requested `YYYY-MM-DD HH:MM:SS` form for timezone-naive inputs and retains the UTC offset for timezone-aware inputs.

`DecouplingConfig` is an immutable dataclass with these controls:

- `epsilon=1e-8`;
- `mad_multiplier=3.5`;
- `max_lag=None`, resolved to `max(1, window_size // 4)`;
- `directional_correlation_threshold=0.0`;
- `magnitude_threshold=None` and `magnitude_floor=2.0`;
- `volatility_threshold=None` and `volatility_floor=log(2)`;
- `phase_lag_threshold=None`;
- `phase_correlation_drop_threshold=None` and `phase_correlation_drop_floor=0.2`.

An explicit pattern threshold replaces that pattern's adaptive threshold. Floors apply only while the corresponding explicit threshold is absent.

## 3. Input Alignment and Validation

The module performs these steps before computing statistics:

1. Require both inputs to be pandas `Series` with `DatetimeIndex`.
2. Reject duplicate timestamps and nonnumeric values.
3. Sort both indices and perform an inner join.
4. Retain the joined timeline for cadence inference, then remove rows where either value is non-finite.
5. Infer the expected cadence as the mode of positive joined-index differences. If several differences tie, use the smallest positive difference. A later valid pair is contiguous only when its delta equals this cadence.

Removing a NaN therefore cannot bridge a persistence run: either the removed point or the resulting timestamp gap breaks the run. The module does not resample or interpolate.

Validation errors use the following policy:

- wrong container or index type: `TypeError`;
- duplicate timestamps, nonnumeric values, invalid parameters, empty intersection, indeterminate cadence, or insufficient usable data: `ValueError`.

Parameter constraints are `window_size >= 3`, `persistence >= 1`, `epsilon > 0`, `mad_multiplier > 0`, and `1 <= max_lag < window_size`. After alignment, the data must yield at least `persistence` contiguous, finite observations for every statistic after rolling warm-up; otherwise analysis is rejected as insufficient rather than reported as normal.

## 4. Normalization and Shared Robust Statistics

Each input is independently normalized with a rolling Z-score:

```text
z[t] = (x[t] - rolling_mean[t]) / max(rolling_std[t], epsilon)
```

The rolling standard deviation uses `ddof=0` and requires a complete `window_size`. A constant window maps to a finite zero-centered value instead of raising or producing infinity.

`movement = z.diff()` is used for statistics describing how the series move. Magnitude uses the Z-score level gap directly.

Adaptive thresholds use all finite metric values in the current batch:

```text
median = median(metric)
robust_sigma = 1.4826 * median(abs(metric - median))
robust_range = mad_multiplier * max(robust_sigma, epsilon)
```

Using the full batch is intentional for this batch-only version. It provides a stable reference for early observations and is robust to a minority of anomalous points. It is not an online or no-look-ahead estimator.

## 5. Pattern Metrics and Anomaly Masks

### 5.1 Directional Reversal

Compute the rolling Pearson correlation between the two normalized movement series over `window_size` observations.

The default anomaly condition is:

```text
rolling_correlation < 0.0
```

`directional_correlation_threshold` overrides zero. Undefined correlation, including a zero-variance movement window, is not anomalous.

### 5.2 Magnitude Divergence

Compute both:

```text
signed_gap = z1 - z2
absolute_gap = abs(signed_gap)
```

The adaptive threshold is:

```text
max(median(absolute_gap) + robust_range(absolute_gap), magnitude_floor)
```

The anomaly condition is `absolute_gap > threshold`. A sign change in `signed_gap` is recorded as a crossing only when magnitude divergence is already anomalous; crossing alone does not create an event.

### 5.3 Volatility Mismatch

For each normalized movement series, compute a rolling standard deviation with `ddof=0`, then calculate:

```text
log_ratio = log((std1 + epsilon) / (std2 + epsilon))
baseline = median(log_ratio)
volatility_score = abs(log_ratio - baseline)
```

The adaptive score threshold is:

```text
max(robust_range(log_ratio), volatility_floor)
```

The anomaly condition is `volatility_score > threshold`. The signed ratio is retained so the description can identify which series became relatively more or less volatile.

### 5.4 Phase Shift or Relationship Loss

At each eligible endpoint, calculate signed Pearson cross-correlation over the movement window for all integer lags in `[-max_lag, max_lag]`. Lag `L` compares `ts1[t]` with `ts2[t + L]`; a positive lag means `ts1` leads `ts2` by `L` epochs. Each candidate uses only overlapping pairs from that window. A candidate needs at least three finite pairs.

Select the lag with the highest signed correlation. Ties are resolved by the smallest absolute lag, then by the smaller signed lag. This avoids treating an inverse relationship as a valid synchronized phase match.

Across all finite rolling results, compute:

```text
baseline_lag = median(best_lag)
baseline_peak_correlation = median(peak_correlation)
lag_shift = abs(best_lag - baseline_lag)
correlation_drop = baseline_peak_correlation - peak_correlation
```

The adaptive lag threshold is `max(1, ceil(robust_range(best_lag)))`. The adaptive relationship-loss threshold is `max(robust_range(peak_correlation), phase_correlation_drop_floor)`.

The phase mask is true when either:

- `lag_shift >= lag threshold`; or
- `correlation_drop > relationship-loss threshold`.

The two subconditions are retained for the event description. Explicit phase thresholds replace their adaptive counterparts.

## 6. Persistence and Debouncing

Each pattern produces its own Boolean mask. A true run is confirmed only when it contains `persistence` consecutive observations with the inferred cadence. A false value, undefined metric, removed observation, or timestamp gap terminates the run.

When a run is confirmed, the module emits exactly one event:

- `timestamp`: first observation of the run;
- `confirmed_at`: the `persistence`th observation of the run.

Further true observations do not emit repeated events. The detector re-arms only after that pattern returns to a non-anomalous state or encounters a continuity break. Different patterns never suppress or merge one another.

Descriptions are Korean, deterministic, and template-based. They include the start and confirmation times, the persistence count, the relevant metric at start and confirmation, and the threshold or baseline that caused the decision. Magnitude descriptions mention a crossing only when it coincides with the anomalous run. Phase descriptions distinguish lag movement from relationship loss.

## 7. Visualization

Plotting is completely optional. With `enable_plot=False`, the plotting helper is not called and the public result contains `None`. The module must not call `show()`, save a file, or mutate global Matplotlib style.

The selected analyst view is a small-multiples diagnostic figure:

- top full-width panel: raw `ts1` and `ts2` on twin Y axes;
- lower 2-by-2 panels: rolling correlation, absolute Z-score gap, volatility log-ratio, and best lag;
- the phase panel may use a secondary axis for peak cross-correlation;
- adaptive or overridden thresholds and relevant baselines appear as horizontal reference lines;
- event start is a solid vertical line, confirmation is a dashed vertical line, and the interval between them has light shading;
- each event is marked on the raw panel and on its corresponding metric panel.

All panels share the time axis. Legends are deduplicated so long batches with several events remain readable.

## 8. Dependencies and Repository Integration

The implementation explicitly adds `numpy`, `pandas`, and `matplotlib` to `requirements.txt`. Imports remain compatible with the repository's flat-package convention:

```python
from src.decoupling_detector import DecouplingConfig, detect_decoupling
```

No existing PDF extraction, review, metadata, or checklist behavior is changed.

## 9. Test Strategy

Development follows red-green-refactor. Each production behavior is introduced only after a focused failing test demonstrates the missing behavior.

Synthetic deterministic series cover:

- rolling normalization and finite constant-window behavior;
- each of the four pattern masks independently;
- simultaneous independent pattern events;
- exact start and confirmation timestamps;
- persistence boundaries and off-by-one cases;
- suppression during a long run and re-emission after recovery;
- inner join, sorting, NaN removal, and cadence breaks;
- zero volatility and epsilon handling;
- adaptive defaults and every explicit threshold override;
- positive and negative lag sign convention and deterministic tie-breaking;
- timezone preservation;
- invalid inputs, invalid config, empty intersection, and insufficient data;
- plotting disabled and enabled, including the selected panel structure and event markers.

Final verification consists of the focused detector test file, relevant broader tests if integration surfaces change, and:

```text
python -m compileall src tests scripts apps
```

## 10. Non-Goals

Version 1.1 does not include online state, supervised training, automatic resampling, interpolation, event severity, compound-event merging, file output, plot display, notification delivery, or external API calls.
