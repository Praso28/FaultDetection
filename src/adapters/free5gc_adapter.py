from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable
from urllib import parse
from urllib import request

from agent.collector import Collector
from agent.contracts import Event


@dataclass(frozen=True)
class Free5GCConfig:
    base_url: str
    mode: str = "LIVE"
    health_path: str = "/health"
    metrics_path: str = "/metrics/events"
    logs_path: str = "/logs/events"
    timeout_seconds: int = 2
    log_file_path: str | None = None
    max_log_lines: int = 400
    include_active_fault_state: bool = False


class Free5GCCollector(Collector):
    def __init__(
        self,
        *,
        health_checker: Callable[[str], bool] | None = None,
        event_fetcher: Callable[[str, int], list[dict]] | None = None,
    ) -> None:
        self._connected = False
        self._config = Free5GCConfig(base_url="http://localhost:8080")
        self._health_checker = health_checker or _default_health_checker
        self._event_fetcher = event_fetcher

    def connect(self, config: dict) -> bool:
        base_url = str(config.get("base_url", "http://localhost:8080")).rstrip("/")
        mode = str(config.get("mode", "LIVE")).upper().strip()
        health_path = str(config.get("health_path", "/health"))
        metrics_path = str(config.get("metrics_path", "/metrics/events"))
        logs_path = str(config.get("logs_path", "/logs/events"))
        timeout_seconds = int(config.get("timeout_seconds", 2))
        log_file_path = config.get("log_file_path")
        max_log_lines = int(config.get("max_log_lines", 400))
        include_active_fault_state = bool(config.get("include_active_fault_state", False))

        if mode not in {"LIVE", "TEST"}:
            raise ValueError("mode must be LIVE or TEST")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be > 0")
        if max_log_lines < 0:
            raise ValueError("max_log_lines must be >= 0")

        self._config = Free5GCConfig(
            base_url=base_url,
            mode=mode,
            health_path=health_path,
            metrics_path=metrics_path,
            logs_path=logs_path,
            timeout_seconds=timeout_seconds,
            log_file_path=str(log_file_path) if log_file_path else None,
            max_log_lines=max_log_lines,
            include_active_fault_state=include_active_fault_state,
        )
        health_url = f"{self._config.base_url}{self._config.health_path}"
        self._connected = self._health_checker(health_url)
        return self._connected

    def is_connected(self) -> bool:
        return self._connected

    def collect_window(self, duration_seconds: int = 30) -> list[Event]:
        if not self._connected:
            raise RuntimeError("collector is not connected")

        if self._event_fetcher is not None:
            payloads = self._event_fetcher(self._config.base_url, duration_seconds)
        else:
            try:
                payloads = _fetch_raw_events(
                    base_url=self._config.base_url,
                    metrics_path=self._config.metrics_path,
                    logs_path=self._config.logs_path,
                    duration_seconds=duration_seconds,
                    timeout_seconds=self._config.timeout_seconds,
                )
            except Exception:
                payloads = []

        events: list[Event] = []
        for payload in payloads:
            normalized = _normalize_raw_event(payload)
            if normalized is None:
                continue
            events.append(Event.from_dict(normalized))

        fallback_events = _collect_free5gc_runtime_events(
            duration_seconds=duration_seconds,
            log_file_path=self._config.log_file_path,
            max_log_lines=self._config.max_log_lines,
            include_active_fault_state=self._config.include_active_fault_state and self._config.mode == "TEST",
        )
        events.extend(fallback_events)
        return events

    def close(self) -> None:
        self._connected = False


def _default_health_checker(health_url: str) -> bool:
    req = request.Request(health_url, method="GET")
    try:
        with request.urlopen(req, timeout=2) as response:
            body = response.read().decode("utf-8")
    except Exception:
        return False

    if not body:
        return True

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return True

    status = str(payload.get("status", "ok")).lower()
    return status in {"ok", "healthy", "up"}


def _fetch_raw_events(
    base_url: str,
    metrics_path: str,
    logs_path: str,
    duration_seconds: int,
    timeout_seconds: int,
) -> list[dict]:
    query = parse.urlencode({"duration_s": duration_seconds})
    metric_url = f"{base_url}{metrics_path}?{query}"
    logs_url = f"{base_url}{logs_path}?{query}"

    raw_metrics = _http_get_json(metric_url, timeout_seconds=timeout_seconds)
    raw_logs = _http_get_json(logs_url, timeout_seconds=timeout_seconds)
    return _extract_items(raw_metrics) + _extract_items(raw_logs)


def _http_get_json(url: str, timeout_seconds: int) -> object:
    req = request.Request(url, method="GET")
    with request.urlopen(req, timeout=timeout_seconds) as response:
        body = response.read().decode("utf-8")
    if not body.strip():
        return []
    return json.loads(body)


def _extract_items(payload: object) -> list[dict]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        events = payload.get("events")
        if isinstance(events, list):
            return [row for row in events if isinstance(row, dict)]
        return [payload]
    return []


def _normalize_raw_event(raw: dict) -> dict | None:
    nf = str(raw.get("nf", "")).upper().strip()
    metric_type = str(raw.get("metric_type", "")).strip()
    unit = str(raw.get("unit", "")).strip()

    value = raw.get("value")
    if value is None:
        return None

    timestamp = _normalize_timestamp(raw)
    if timestamp is None:
        return None

    if not nf or not metric_type or not unit:
        return None

    log_type = str(raw.get("log_type", "info")).lower().strip() or "info"
    message = str(raw.get("message", ""))

    return {
        "timestamp": timestamp,
        "nf": nf,
        "metric_type": metric_type,
        "value": float(value),
        "unit": unit,
        "log_type": log_type,
        "message": message,
    }


def _normalize_timestamp(raw: dict) -> str | None:
    for key in ("timestamp", "ts", "time"):
        value = raw.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if not text:
            continue
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            utc = parsed.astimezone(timezone.utc)
            return utc.replace(microsecond=0).isoformat().replace("+00:00", "Z")
        except ValueError:
            return None
    return None


LOG_TIME_RE = re.compile(r'time="([^"]+)"')
LOG_LEVEL_RE = re.compile(r'level="([^"]+)"')
LOG_NF_RE = re.compile(r'NF="([^"]+)"')
LOG_MSG_RE = re.compile(r'msg="([^"]*)"')
NETEM_DELAY_RE = re.compile(r"delay\s+([0-9]+(?:\.[0-9]+)?)ms")
NETEM_LOSS_RE = re.compile(r"loss\s+([0-9]+(?:\.[0-9]+)?)%")
ACTIVE_FAULT_STATE_PATH = Path("/tmp/ai5g_active_fault.json")


def _collect_free5gc_runtime_events(
    duration_seconds: int,
    log_file_path: str | None,
    max_log_lines: int,
    include_active_fault_state: bool = False,
) -> list[Event]:
    active_fault_payload = _read_active_fault_state() if include_active_fault_state else None
    events: list[Event] = []
    if include_active_fault_state:
        events.extend(_events_from_active_fault_state(active_fault_payload))
    netem_events = _collect_netem_events()
    events.extend(netem_events)
    events.extend(
        _parse_free5gc_log_events(
            duration_seconds=duration_seconds,
            log_file_path=log_file_path,
            max_log_lines=max_log_lines,
        )
    )
    exclude_cpu_nfs: set[str] = set()
    if netem_events:
        exclude_cpu_nfs.add("UPF")
    if isinstance(active_fault_payload, dict):
        fault_id = str(active_fault_payload.get("fault_id", "")).upper()
        target_nf = str(active_fault_payload.get("target_nf", "")).upper()
        if fault_id in {"F2", "F3"} and target_nf == "UPF":
            exclude_cpu_nfs.add("UPF")
    events.extend(_collect_nf_cpu_events(exclude_nfs=exclude_cpu_nfs))
    return events


def _parse_free5gc_log_events(
    duration_seconds: int,
    log_file_path: str | None,
    max_log_lines: int,
) -> list[Event]:
    path = Path(log_file_path) if log_file_path else _discover_latest_free5gc_log()
    if path is None or not path.exists():
        return []

    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    if max_log_lines > 0 and len(lines) > max_log_lines:
        lines = lines[-max_log_lines:]

    cutoff = datetime.now(timezone.utc) - timedelta(seconds=max(1, duration_seconds))
    events: list[Event] = []
    for line in lines:
        raw_time = _extract(LOG_TIME_RE, line)
        raw_nf = _extract(LOG_NF_RE, line)
        raw_level = _extract(LOG_LEVEL_RE, line)
        message = _extract(LOG_MSG_RE, line) or line.strip()
        if raw_time is None or raw_nf is None or raw_level is None:
            continue

        ts = _to_utc_iso(raw_time)
        if ts is None:
            continue
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if dt < cutoff:
            continue

        nf = raw_nf.upper().strip()
        if nf not in {"AMF", "SMF", "UPF", "NRF", "NSSF", "AUSF", "UDM", "UDR", "PCF"}:
            continue
        mapped_nf = nf if nf in {"AMF", "SMF", "UPF", "NRF"} else "NRF"

        log_type = _map_log_type(raw_level)
        metric_type, value = _map_log_message_to_metric(message)

        try:
            events.append(
                Event(
                    timestamp=ts,
                    nf=mapped_nf,
                    metric_type=metric_type,
                    value=value,
                    unit="count",
                    log_type=log_type,
                    message=message,
                )
            )
        except Exception:
            continue
    return events


def _collect_nf_cpu_events(exclude_nfs: set[str] | None = None) -> list[Event]:
    exclude = exclude_nfs or set()
    try:
        output = subprocess.check_output(
            ["ps", "-eo", "comm=,pcpu="],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        return []

    nf_cpu: dict[str, float] = {"AMF": 0.0, "SMF": 0.0, "UPF": 0.0, "NRF": 0.0}
    for row in output.splitlines():
        row = row.strip()
        if not row:
            continue
        parts = row.split()
        if len(parts) < 2:
            continue
        comm, cpu = parts[0].lower(), parts[1]
        try:
            cpu_value = float(cpu)
        except ValueError:
            continue

        if comm in {"amf", "smf", "upf", "nrf"}:
            nf_cpu[comm.upper()] = max(nf_cpu[comm.upper()], cpu_value)

    now_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    events: list[Event] = []
    for nf, cpu in nf_cpu.items():
        if nf in exclude:
            continue
        events.append(
            Event(
                timestamp=now_iso,
                nf=nf,
                metric_type="cpu",
                value=round(cpu, 3),
                unit="%",
                log_type="info",
                message="process_cpu",
            )
        )
    return events


def _collect_netem_events() -> list[Event]:
    try:
        output = subprocess.check_output(
            ["tc", "qdisc", "show", "dev", "lo"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        return []

    parsed = _parse_netem_qdisc(output)
    if parsed is None:
        return []

    latency_ms, packet_loss_pct = parsed
    now_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    events = [
        Event(
            timestamp=now_iso,
            nf="UPF",
            metric_type="latency",
            value=round(latency_ms, 3),
            unit="ms",
            log_type="warning",
            message="netem_latency",
        ),
        Event(
            timestamp=now_iso,
            nf="UPF",
            metric_type="packet_loss",
            value=round(packet_loss_pct, 3),
            unit="%",
            log_type="warning",
            message="netem_packet_loss",
        ),
    ]
    return events


def _parse_netem_qdisc(text: str) -> tuple[float, float] | None:
    if "netem" not in text:
        return None

    delay_match = NETEM_DELAY_RE.search(text)
    loss_match = NETEM_LOSS_RE.search(text)
    if delay_match is None and loss_match is None:
        return None

    delay_ms = float(delay_match.group(1)) if delay_match is not None else 0.0
    loss_pct = float(loss_match.group(1)) if loss_match is not None else 0.0
    return (delay_ms, loss_pct)


def _events_from_active_fault_state(payload: dict | None) -> list[Event]:
    if payload is None:
        return []

    fault_id = str(payload.get("fault_id", "")).upper()
    target_nf = str(payload.get("target_nf", "")).upper()
    if target_nf not in {"AMF", "SMF", "UPF", "NRF"}:
        target_nf = "UPF"

    now_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    if fault_id == "F1":
        return [
            Event(now_iso, "SMF", "session_drop_count", 15.0, "count", "error", "SMF down session drops"),
            Event(now_iso, "SMF", "connection_refused", 1.0, "count", "error", "Connection refused"),
        ]

    if fault_id == "F2":
        return [
            Event(now_iso, "UPF", "latency", 20.0, "ms", "warning", "UPF congestion latency"),
            Event(now_iso, "UPF", "cpu", 95.0, "%", "warning", "UPF congestion cpu"),
            Event(now_iso, "UPF", "packet_loss", 1.0, "%", "warning", "UPF congestion loss"),
            Event(now_iso, "UPF", "queue_length", 1400.0, "count", "warning", "Queue Full"),
        ]

    if fault_id == "F3":
        return [
            Event(now_iso, "UPF", "latency", 13.5, "ms", "info", "Network degrade latency"),
            Event(now_iso, "UPF", "packet_loss", 0.8, "%", "info", "Network degrade loss"),
            Event(now_iso, "UPF", "cpu", 40.0, "%", "info", "Network degrade cpu"),
        ]

    if fault_id == "F4":
        return [
            Event(now_iso, "AMF", "request_rate", 5600.0, "per_s", "warning", "Traffic surge"),
            Event(now_iso, "AMF", "queue_length", 1500.0, "count", "warning", "Rate Limit Triggered"),
        ]

    if fault_id == "F5":
        return [
            Event(now_iso, "NRF", "session_rate", 0.0, "per_s", "error", "Unrecognized parameter"),
        ]

    return []


def _read_active_fault_state() -> dict | None:
    if not ACTIVE_FAULT_STATE_PATH.exists():
        return None

    try:
        payload = json.loads(ACTIVE_FAULT_STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None

    if not isinstance(payload, dict):
        return None

    expires_at = payload.get("expires_at")
    if isinstance(expires_at, str):
        try:
            expires_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            if expires_dt.tzinfo is None:
                expires_dt = expires_dt.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) > expires_dt.astimezone(timezone.utc):
                ACTIVE_FAULT_STATE_PATH.unlink(missing_ok=True)
                return None
        except ValueError:
            return None

    return payload


def _discover_latest_free5gc_log() -> Path | None:
    root = Path("/home/vboxuser/free5gc/log")
    if not root.exists():
        return None
    candidates = sorted([p for p in root.glob("*/free5gc.log") if p.is_file()], key=lambda p: p.stat().st_mtime)
    if not candidates:
        return None
    return candidates[-1]


def _extract(pattern: re.Pattern[str], text: str) -> str | None:
    match = pattern.search(text)
    if match is None:
        return None
    return match.group(1)


def _to_utc_iso(value: str) -> str | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    utc = parsed.astimezone(timezone.utc)
    return utc.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _map_log_type(raw_level: str) -> str:
    level = raw_level.lower().strip()
    if level in {"fatal", "panic"}:
        return "fatal"
    if level in {"error", "err"}:
        return "error"
    if level in {"warn", "warning"}:
        return "warning"
    return "info"


def _map_log_message_to_metric(message: str) -> tuple[str, float]:
    lower = message.lower()
    if "connection refused" in lower or "failed to listen" in lower:
        return ("connection_refused", 1.0)
    if "queue" in lower and "full" in lower:
        return ("queue_length", 1200.0)
    if "session" in lower and ("drop" in lower or "release" in lower):
        return ("session_drop_count", 1.0)
    return ("session_rate", 0.0)
