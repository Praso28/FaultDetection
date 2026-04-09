from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone

from agent.contracts import Event, NFState, StateSnapshot


def _event_dt(event: Event) -> datetime:
    return datetime.fromisoformat(event.timestamp.replace("Z", "+00:00")).astimezone(timezone.utc)


def aggregate(events: list[Event], window_seconds: int = 30) -> StateSnapshot:
    if not events:
        now = datetime.now(timezone.utc).replace(microsecond=0)
        return StateSnapshot(
            window_start=(now - timedelta(seconds=window_seconds)).isoformat().replace("+00:00", "Z"),
            window_end=now.isoformat().replace("+00:00", "Z"),
            states={},
        )

    sorted_events = sorted(events, key=_event_dt)
    end_dt = _event_dt(sorted_events[-1])
    start_dt = end_dt - timedelta(seconds=window_seconds)
    window_events = [event for event in sorted_events if _event_dt(event) >= start_dt]

    buckets: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    error_counts: dict[str, int] = defaultdict(int)

    for event in window_events:
        buckets[event.nf][event.metric_type].append(event.value)
        if event.log_type in {"error", "fatal"}:
            error_counts[event.nf] += 1

    states: dict[str, NFState] = {}
    for nf, metric_values in buckets.items():
        cpu = _avg(metric_values.get("cpu", []))
        latency = _avg(metric_values.get("latency", []))
        packet_loss = _avg(metric_values.get("packet_loss", []))
        request_rate = _avg(metric_values.get("request_rate", []))
        queue_len = _avg(metric_values.get("queue_length", []))
        session_drop = int(sum(metric_values.get("session_drop_count", []))) if metric_values.get("session_drop_count") else None
        connection_refused = int(sum(metric_values.get("connection_refused", []))) if metric_values.get("connection_refused") else None

        states[nf] = NFState(
            cpu_pct=cpu,
            latency_ms=latency,
            packet_loss_pct=packet_loss,
            session_drop_count=session_drop,
            request_rate=request_rate,
            queue_length=queue_len,
            error_log_count=error_counts.get(nf, 0),
            connection_refused=connection_refused,
        )

    return StateSnapshot(
        window_start=start_dt.isoformat().replace("+00:00", "Z"),
        window_end=end_dt.isoformat().replace("+00:00", "Z"),
        states=states,
    )


def _avg(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 3)
