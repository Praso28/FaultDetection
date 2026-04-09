from __future__ import annotations

from datetime import datetime, timedelta, timezone
import random
from typing import Iterable

from agent.contracts import Event


def _timestamp_series(count: int, start_ts: datetime | None = None) -> Iterable[str]:
    start = start_ts or datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    for idx in range(count):
        yield (start + timedelta(seconds=idx)).isoformat().replace("+00:00", "Z")


def generate_normal(nf: str, seed: int, count: int = 30) -> list[Event]:
    rng = random.Random(seed)
    events: list[Event] = []
    for ts in _timestamp_series(count):
        cpu = rng.uniform(20.0, 50.0)
        latency = rng.uniform(3.0, 8.0)
        packet_loss = rng.uniform(0.0, 0.05)
        request_rate = rng.uniform(900.0, 1400.0)
        queue_len = rng.uniform(50.0, 150.0)

        events.extend(
            [
                Event(ts, nf, "cpu", round(cpu, 3), "%"),
                Event(ts, nf, "latency", round(latency, 3), "ms"),
                Event(ts, nf, "packet_loss", round(packet_loss, 3), "%"),
                Event(ts, nf, "request_rate", round(request_rate, 3), "per_s"),
                Event(ts, nf, "queue_length", round(queue_len, 3), "count"),
            ]
        )
    return events


def generate_fault(fault_id: str, nf: str, seed: int, count: int = 30) -> list[Event]:
    events = generate_normal(nf=nf, seed=seed, count=count)
    fault = fault_id.upper()
    fault_rng = random.Random(f"{fault}:{nf}:{seed}:{count}")

    adjusted: list[Event] = []
    for event in events:
        val = event.value
        log_type = event.log_type
        message = event.message

        if fault == "F1":
            if event.metric_type == "session_drop_count":
                val = 15.0
            if event.metric_type == "request_rate":
                val = 0.0
            if event.metric_type == "queue_length":
                val = 0.0
            if event.metric_type == "cpu":
                val = 10.0
            if event.metric_type == "latency":
                val = 50.0
            if event.metric_type == "packet_loss":
                val = 2.0
        elif fault == "F2":
            if event.metric_type == "cpu":
                val = max(val, fault_rng.uniform(82.0, 96.0))
            elif event.metric_type == "latency":
                val = max(val, fault_rng.uniform(11.0, 22.0))
            elif event.metric_type == "packet_loss":
                val = max(val, fault_rng.uniform(0.08, 0.3))
            elif event.metric_type == "queue_length":
                val = max(val, fault_rng.uniform(1000.0, 1700.0))
        elif fault == "F3":
            if event.metric_type == "cpu":
                val = min(val, fault_rng.uniform(32.0, 49.0))
            elif event.metric_type == "latency":
                val = max(val, fault_rng.uniform(12.2, 20.0))
            elif event.metric_type == "packet_loss":
                val = max(val, fault_rng.uniform(0.45, 1.1))
        elif fault == "F4":
            if event.metric_type == "request_rate":
                val = max(val, fault_rng.uniform(5000.0, 7000.0))
            elif event.metric_type == "queue_length":
                val = max(val, fault_rng.uniform(1000.0, 1800.0))
        elif fault == "F5":
            pass
        else:
            raise ValueError(f"Unsupported fault_id '{fault_id}'")

        adjusted.append(
            Event(
                timestamp=event.timestamp,
                nf=event.nf,
                metric_type=event.metric_type,
                value=round(val, 3),
                unit=event.unit,
                log_type=log_type,
                message=message,
            )
        )

    if fault == "F1":
        adjusted.append(
            Event(
                timestamp=adjusted[-1].timestamp,
                nf=nf,
                metric_type="connection_refused",
                value=1.0,
                unit="bool",
                log_type="error",
                message="ERROR: Connection Timeout",
            )
        )
        adjusted.append(
            Event(
                timestamp=adjusted[-1].timestamp,
                nf=nf,
                metric_type="session_drop_count",
                value=15.0,
                unit="count",
                log_type="error",
                message="ERROR: Connection Timeout",
            )
        )
    elif fault == "F2":
        adjusted.append(
            Event(
                timestamp=adjusted[-1].timestamp,
                nf=nf,
                metric_type="queue_length",
                value=round(fault_rng.uniform(1400.0, 1900.0), 3),
                unit="count",
                log_type="warning",
                message="WARN: Queue Full",
            )
        )
    elif fault == "F5":
        adjusted.append(
            Event(
                timestamp=adjusted[-1].timestamp,
                nf=nf,
                metric_type="cpu",
                value=35.0,
                unit="%",
                log_type="error",
                message="ERROR: Unrecognized parameter",
            )
        )

    return adjusted
