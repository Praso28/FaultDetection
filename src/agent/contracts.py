from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

VALID_NFS = {"AMF", "SMF", "UPF", "NRF"}
VALID_METRIC_TYPES = {
    "latency",
    "cpu",
    "packet_loss",
    "session_rate",
    "request_rate",
    "queue_length",
    "session_drop_count",
    "connection_refused",
}
VALID_UNITS = {"ms", "%", "count", "mbps", "bool", "per_s"}
VALID_LOG_TYPES = {"info", "warning", "error", "fatal"}


def _validate_iso8601_utc(timestamp: str) -> None:
    parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include timezone")
    if parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError("timestamp must be UTC")


@dataclass(frozen=True)
class Event:
    timestamp: str
    nf: str
    metric_type: str
    value: float
    unit: str
    log_type: str = "info"
    message: str = ""

    def __post_init__(self) -> None:
        _validate_iso8601_utc(self.timestamp)
        if self.nf not in VALID_NFS:
            raise ValueError(f"Invalid nf '{self.nf}'")
        if self.metric_type not in VALID_METRIC_TYPES:
            raise ValueError(f"Invalid metric_type '{self.metric_type}'")
        if self.unit not in VALID_UNITS:
            raise ValueError(f"Invalid unit '{self.unit}'")
        if self.log_type not in VALID_LOG_TYPES:
            raise ValueError(f"Invalid log_type '{self.log_type}'")

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "nf": self.nf,
            "metric_type": self.metric_type,
            "value": self.value,
            "unit": self.unit,
            "log_type": self.log_type,
            "message": self.message,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Event":
        return cls(
            timestamp=payload["timestamp"],
            nf=payload["nf"],
            metric_type=payload["metric_type"],
            value=float(payload["value"]),
            unit=payload["unit"],
            log_type=payload.get("log_type", "info"),
            message=payload.get("message", ""),
        )


@dataclass(frozen=True)
class NFState:
    cpu_pct: float | None = None
    latency_ms: float | None = None
    packet_loss_pct: float | None = None
    session_drop_count: int | None = None
    request_rate: float | None = None
    queue_length: float | None = None
    error_log_count: int | None = None
    connection_refused: int | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in self.__dict__.items():
            if value is not None:
                result[key] = value
        return result


@dataclass(frozen=True)
class StateSnapshot:
    window_start: str
    window_end: str
    states: dict[str, NFState] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_iso8601_utc(self.window_start)
        _validate_iso8601_utc(self.window_end)
        for nf_name in self.states:
            if nf_name not in VALID_NFS:
                raise ValueError(f"Invalid nf in snapshot '{nf_name}'")

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "window_start": self.window_start,
            "window_end": self.window_end,
        }
        for nf_name, state in self.states.items():
            payload[nf_name] = state.to_dict()
        return payload
