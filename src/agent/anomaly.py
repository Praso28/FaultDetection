from __future__ import annotations

from dataclasses import dataclass
from math import sqrt

from agent.contracts import StateSnapshot
from rules.fault_catalog import has_threshold_breach


@dataclass(frozen=True)
class BaselineStats:
    mean: float
    std: float


def build_baseline(snapshots: list[StateSnapshot]) -> dict[str, dict[str, BaselineStats]]:
    buckets: dict[str, dict[str, list[float]]] = {}
    for snapshot in snapshots:
        for nf, state in snapshot.states.items():
            nf_bucket = buckets.setdefault(nf, {})
            for metric_name in ("cpu_pct", "latency_ms", "packet_loss_pct", "request_rate", "queue_length"):
                value = getattr(state, metric_name)
                if value is None:
                    continue
                nf_bucket.setdefault(metric_name, []).append(float(value))

    baseline: dict[str, dict[str, BaselineStats]] = {}
    for nf, metrics in buckets.items():
        baseline[nf] = {}
        for metric_name, values in metrics.items():
            mean = sum(values) / len(values)
            if len(values) <= 1:
                std = 1.0
            else:
                variance = sum((v - mean) ** 2 for v in values) / len(values)
                std = sqrt(variance) or 1.0
            baseline[nf][metric_name] = BaselineStats(mean=mean, std=std)

    return baseline


def detect_anomaly(
    snapshot: StateSnapshot,
    baseline: dict[str, dict[str, BaselineStats]] | None = None,
    z_threshold: float = 3.0,
) -> bool:
    if has_threshold_breach(snapshot):
        return True

    if not baseline:
        return False

    z_breach_count = 0
    for nf, state in snapshot.states.items():
        nf_baseline = baseline.get(nf, {})
        for metric_name in ("cpu_pct", "latency_ms", "packet_loss_pct", "request_rate", "queue_length"):
            value = getattr(state, metric_name)
            stats = nf_baseline.get(metric_name)
            if value is None or stats is None:
                continue
            z_score = abs((value - stats.mean) / stats.std)
            if z_score > z_threshold:
                z_breach_count += 1

    return z_breach_count >= 2
