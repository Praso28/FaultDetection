from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass
class AuditLogger:
    path: Path

    def __init__(self, file_path: str | Path) -> None:
        self.path = Path(file_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._seq = 0
        self._stats: dict[str, Any] = {
            "incident_count": 0,
            "action_count": 0,
            "confidence_distribution": {"low": 0, "medium": 0, "high": 0},
            "fault_frequency": {},
        }

    def log_cycle_start(self, window_start: str, window_end: str, event_count: int | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "window_start": window_start,
            "window_end": window_end,
        }
        if event_count is not None:
            payload["event_count"] = event_count
        return self.log("cycle_start", payload)

    def log_no_anomaly(self, window_start: str, window_end: str) -> dict[str, Any]:
        return self.log(
            "no_anomaly",
            {
                "window_start": window_start,
                "window_end": window_end,
            },
        )

    def log_anomaly_detected(self, fault: str | None, confidence_base: float | None) -> dict[str, Any]:
        return self.log(
            "anomaly_detected",
            {
                "fault": fault,
                "confidence_base": confidence_base,
            },
        )

    def log_plan_decision(self, fault: str | None, confidence: float, mode: str, action: str) -> dict[str, Any]:
        return self.log(
            "plan_decision",
            {
                "fault": fault,
                "confidence": confidence,
                "mode": mode,
                "action": action,
            },
        )

    def log_execution_attempt(
        self,
        incident_id: str,
        action: str,
        allowed: bool,
        status: str,
        detail: str,
    ) -> dict[str, Any]:
        return self.log(
            "execution_attempt",
            {
                "incident_id": incident_id,
                "action": action,
                "allowed": allowed,
                "status": status,
                "detail": detail,
            },
        )

    def log_verification_completed(
        self,
        fault: str,
        state: str,
        rollback_triggered: bool,
    ) -> dict[str, Any]:
        return self.log(
            "verification_completed",
            {
                "fault": fault,
                "state": state,
                "rollback_triggered": rollback_triggered,
            },
        )

    def log_cycle_outcome(
        self,
        anomaly: bool,
        fault: str | None,
        target_nf: str | None,
        mode: str,
        action: str,
        execution_status: str,
        verification_state: str | None,
    ) -> dict[str, Any]:
        return self.log(
            "cycle_outcome",
            {
                "anomaly": anomaly,
                "fault": fault,
                "target_nf": target_nf,
                "mode": mode,
                "action": action,
                "execution_status": execution_status,
                "verification_state": verification_state,
            },
        )

    def log(self, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        self._seq += 1
        self._update_stats(event_type=event_type, payload=payload)
        entry: dict[str, Any] = {
            "seq": self._seq,
            "timestamp": _utc_now_iso(),
            "event_type": event_type,
            "payload": payload,
        }
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, separators=(",", ":"), ensure_ascii=False))
            f.write("\n")
        return entry

    def observability_snapshot(self) -> dict[str, Any]:
        fault_frequency = dict(self._stats["fault_frequency"])
        confidence_distribution = dict(self._stats["confidence_distribution"])
        return {
            "incident_count": int(self._stats["incident_count"]),
            "action_count": int(self._stats["action_count"]),
            "confidence_distribution": confidence_distribution,
            "fault_frequency": fault_frequency,
        }

    def _update_stats(self, event_type: str, payload: dict[str, Any]) -> None:
        if event_type == "anomaly_detected":
            self._stats["incident_count"] += 1
            fault = payload.get("fault")
            if isinstance(fault, str) and fault:
                frequency: dict[str, int] = self._stats["fault_frequency"]
                frequency[fault] = frequency.get(fault, 0) + 1

            confidence_base = payload.get("confidence_base")
            if isinstance(confidence_base, (int, float)):
                confidence = float(confidence_base)
                distribution: dict[str, int] = self._stats["confidence_distribution"]
                if confidence < 0.5:
                    distribution["low"] += 1
                elif confidence < 0.8:
                    distribution["medium"] += 1
                else:
                    distribution["high"] += 1

        if event_type == "execution_attempt":
            action = payload.get("action")
            allowed = payload.get("allowed")
            if isinstance(action, str) and action != "no_action" and bool(allowed):
                self._stats["action_count"] += 1