from __future__ import annotations

from dataclasses import dataclass
from math import exp

from agent.history_buffer import HistoryBuffer


@dataclass(frozen=True)
class SignalScores:
    log_determinism: float
    metric_severity: float
    temporal_consistency: float


@dataclass(frozen=True)
class ConfidenceResult:
    base_score: float
    calibrated_confidence: float


@dataclass(frozen=True)
class CalibrationParams:
    a: float = 5.0
    b: float = -3.0


def _clamp_01(value: float) -> float:
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def compute_base_score(scores: SignalScores) -> float:
    """Compute S = 0.5L + 0.3M + 0.2H with clamped signal bounds."""
    l = _clamp_01(scores.log_determinism)
    m = _clamp_01(scores.metric_severity)
    h = _clamp_01(scores.temporal_consistency)
    return round((0.5 * l) + (0.3 * m) + (0.2 * h), 6)


def calibrate_confidence(base_score: float, params: CalibrationParams = CalibrationParams()) -> float:
    """Compute C = 1 / (1 + exp(-(a*S + b)))."""
    s = _clamp_01(base_score)
    z = (params.a * s) + params.b
    confidence = 1.0 / (1.0 + exp(-z))
    return round(confidence, 6)


def compute_confidence(
    scores: SignalScores,
    params: CalibrationParams = CalibrationParams(),
) -> ConfidenceResult:
    base = compute_base_score(scores)
    calibrated = calibrate_confidence(base, params)
    return ConfidenceResult(base_score=base, calibrated_confidence=calibrated)


def update_calibration(
    params: CalibrationParams,
    base_score: float,
    observed_positive: bool,
    learning_rate: float = 0.05,
) -> CalibrationParams:
    """One-step deterministic Platt-style update for online calibration."""
    s = _clamp_01(base_score)
    c = calibrate_confidence(s, params)
    y = 1.0 if observed_positive else 0.0
    error = y - c
    next_a = params.a + (learning_rate * error * s)
    next_b = params.b + (learning_rate * error)
    return CalibrationParams(a=round(next_a, 6), b=round(next_b, 6))


def compute_temporal_consistency(
    history: HistoryBuffer,
    fault_id: str,
    target_nf: str,
    window_count: int = 5,
) -> float:
    if window_count < 1:
        return 0.0

    presence_ratio = history.recent_fault_match_ratio(
        fault_id=fault_id,
        target_nf=target_nf,
        window_count=window_count,
    )
    consecutive = history.consecutive_fault_matches(
        fault_id=fault_id,
        target_nf=target_nf,
        window_count=window_count,
    )

    trend_signals = _fault_trend_signals(fault_id)
    if not trend_signals:
        trend_score = 0.0
    else:
        trend_hits = 0
        for metric_name, direction in trend_signals:
            if history.is_trending(
                nf=target_nf,
                metric_name=metric_name,
                direction=direction,
                threshold=0.6,
                window_count=window_count,
            ):
                trend_hits += 1
        trend_score = trend_hits / len(trend_signals)

    if consecutive >= 3:
        return 1.0

    score = (0.6 * presence_ratio) + (0.4 * trend_score)
    return round(_clamp_01(score), 6)


def _fault_trend_signals(fault_id: str) -> tuple[tuple[str, str], ...]:
    key = fault_id.upper()
    if key == "F1":
        return (("session_drop_count", "up"), ("connection_refused", "up"))
    if key == "F2":
        return (("latency_ms", "up"), ("cpu_pct", "up"), ("packet_loss_pct", "up"))
    if key == "F3":
        return (("latency_ms", "up"), ("packet_loss_pct", "up"), ("cpu_pct", "down"))
    if key == "F4":
        return (("request_rate", "up"), ("queue_length", "up"))
    if key == "F5":
        return (("error_log_count", "up"),)
    return ()
