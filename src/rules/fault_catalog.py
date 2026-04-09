from __future__ import annotations

from dataclasses import dataclass

from agent.contracts import NFState, StateSnapshot


@dataclass(frozen=True)
class FaultHypothesis:
    fault: str
    target_nf: str
    confidence_base: float
    rule_hits: tuple[str, ...]


def _ratio(value: float | None, threshold: float, inverse: bool = False) -> float:
    if value is None:
        return 0.0
    if inverse:
        if value <= 0:
            return 1.0
        return min(1.0, threshold / value)
    if threshold <= 0:
        return 0.0
    return min(1.0, value / threshold)


def _f1_match(nf: str, state: NFState) -> FaultHypothesis | None:
    hits: list[str] = []
    has_session_drop = (state.session_drop_count or 0) > 10
    has_conn_refused = (state.connection_refused or 0) > 0
    if has_session_drop:
        hits.append("session_drop_count>10")
    if has_conn_refused:
        hits.append("connection_refused>0")
    if state.error_log_count and state.error_log_count > 0 and (has_session_drop or has_conn_refused):
        hits.append("error_log_count>0")
    if not (has_session_drop or has_conn_refused):
        return None
    score = min(1.0, 0.4 + 0.3 * len(hits))
    return FaultHypothesis("F1", nf, round(score, 3), tuple(hits))


def _f2_match(nf: str, state: NFState) -> FaultHypothesis | None:
    hits: list[str] = []
    if (state.latency_ms or 0) > 10:
        hits.append("latency_ms>10")
    if (state.cpu_pct or 0) > 80:
        hits.append("cpu_pct>80")
    if (state.packet_loss_pct or 0) > 0.1:
        hits.append("packet_loss_pct>0.1")
    if not hits:
        return None
    sev = (
        _ratio(state.latency_ms, 10)
        + _ratio(state.cpu_pct, 80)
        + _ratio(state.packet_loss_pct, 0.1)
    ) / 3
    score = min(1.0, 0.4 + 0.6 * sev)
    return FaultHypothesis("F2", nf, round(score, 3), tuple(hits))


def _f3_match(nf: str, state: NFState) -> FaultHypothesis | None:
    hits: list[str] = []
    if (state.latency_ms or 0) > 12:
        hits.append("latency_ms>12")
    if (state.packet_loss_pct or 0) > 0.5:
        hits.append("packet_loss_pct>0.5")
    if (state.cpu_pct is not None) and state.cpu_pct < 50:
        hits.append("cpu_pct<50")
    if len(hits) < 2:
        return None
    sev = (
        _ratio(state.latency_ms, 12)
        + _ratio(state.packet_loss_pct, 0.5)
        + _ratio(state.cpu_pct, 50, inverse=True)
    ) / 3
    score = min(1.0, 0.35 + 0.6 * sev)
    return FaultHypothesis("F3", nf, round(score, 3), tuple(hits))


def _f4_match(nf: str, state: NFState) -> FaultHypothesis | None:
    hits: list[str] = []
    request_rate = state.request_rate or 0
    queue_length = state.queue_length or 0

    if request_rate > 5000:
        hits.append("request_rate>5000")
    if queue_length > 1000:
        hits.append("queue_length>1000")
    if len(hits) < 2:
        return None

    request_excess = min(1.0, max(0.0, (request_rate - 5000.0) / 5000.0))
    queue_excess = min(1.0, max(0.0, (queue_length - 1000.0) / 1000.0))
    sev = 0.75 + (0.25 * ((request_excess + queue_excess) / 2.0))
    score = min(1.0, 0.4 + 0.55 * sev)
    return FaultHypothesis("F4", nf, round(score, 3), tuple(hits))


def _f5_match(nf: str, state: NFState) -> FaultHypothesis | None:
    cpu_ok = state.cpu_pct is None or state.cpu_pct < 60
    latency_ok = state.latency_ms is None or state.latency_ms < 10
    packet_ok = state.packet_loss_pct is None or state.packet_loss_pct < 0.1
    has_errors = (state.error_log_count or 0) > 0
    if cpu_ok and latency_ok and packet_ok and has_errors:
        score = min(1.0, 0.5 + min(0.4, (state.error_log_count or 0) * 0.05))
        return FaultHypothesis("F5", nf, round(score, 3), ("metrics_normal", "error_logs_present"))
    return None


def evaluate_rules(snapshot: StateSnapshot) -> list[FaultHypothesis]:
    matches: list[FaultHypothesis] = []
    for nf, state in snapshot.states.items():
        for matcher in (_f1_match, _f2_match, _f3_match, _f4_match, _f5_match):
            result = matcher(nf, state)
            if result is not None:
                matches.append(result)
    return matches


def has_threshold_breach(snapshot: StateSnapshot) -> bool:
    return len(evaluate_rules(snapshot)) > 0
