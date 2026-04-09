from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone

from agent.incident_store import IncidentStore


ACTIVE_STATES = {"DETECTED", "VERIFYING"}
TERMINAL_STATES = {"RESOLVED", "ESCALATED", "ROLLBACK"}
ALLOWED_STATES = ACTIVE_STATES | TERMINAL_STATES


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _incident_id(fault_id: str, target_nf: str, window_start: str) -> str:
    raw = f"{fault_id}:{target_nf}:{window_start}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return digest[:16]


@dataclass
class Incident:
    incident_id: str
    fault_id: str
    target_nf: str
    window_start: str
    confidence: float
    state: str
    created_at: str
    updated_at: str
    detail: str = ""

    def to_dict(self) -> dict[str, str | float]:
        return {
            "incident_id": self.incident_id,
            "fault_id": self.fault_id,
            "target_nf": self.target_nf,
            "window_start": self.window_start,
            "confidence": self.confidence,
            "state": self.state,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "detail": self.detail,
        }


class IncidentManager:
    def __init__(self, store: IncidentStore | None = None) -> None:
        self._store = store
        self._incidents: dict[str, Incident] = {}
        self._active_by_nf: dict[str, str] = {}

    def create(self, fault_id: str, target_nf: str, window_start: str, confidence: float) -> Incident:
        active = self.get_active(target_nf=target_nf)
        if active is not None:
            return active

        now = _utc_now_iso()
        incident = Incident(
            incident_id=_incident_id(fault_id=fault_id, target_nf=target_nf, window_start=window_start),
            fault_id=fault_id,
            target_nf=target_nf,
            window_start=window_start,
            confidence=confidence,
            state="DETECTED",
            created_at=now,
            updated_at=now,
        )
        self._incidents[incident.incident_id] = incident
        self._active_by_nf[target_nf] = incident.incident_id
        self._persist(incident)
        return incident

    def get(self, incident_id: str) -> Incident | None:
        return self._incidents.get(incident_id)

    def get_active(self, target_nf: str) -> Incident | None:
        active_id = self._active_by_nf.get(target_nf)
        if active_id is None:
            return None
        return self._incidents.get(active_id)

    def is_suppressed(self, target_nf: str, fault_id: str | None = None) -> bool:
        active = self.get_active(target_nf=target_nf)
        if active is None:
            return False
        if fault_id is None:
            return True
        return active.fault_id == fault_id

    def transition(self, incident_id: str, new_state: str, detail: str = "") -> Incident:
        if new_state not in ALLOWED_STATES:
            raise ValueError(f"Unsupported incident state '{new_state}'")

        incident = self._incidents.get(incident_id)
        if incident is None:
            raise ValueError(f"Unknown incident_id '{incident_id}'")

        incident.state = new_state
        incident.updated_at = _utc_now_iso()
        incident.detail = detail

        if new_state in ACTIVE_STATES:
            self._active_by_nf[incident.target_nf] = incident_id
        else:
            active = self._active_by_nf.get(incident.target_nf)
            if active == incident_id:
                self._active_by_nf.pop(incident.target_nf, None)
        self._persist(incident)
        return incident

    def list_by_state(self, state: str) -> list[Incident]:
        return [incident for incident in self._incidents.values() if incident.state == state]

    def list_all(self) -> list[Incident]:
        return list(self._incidents.values())

    def _persist(self, incident: Incident) -> None:
        if self._store is None:
            return
        self._store.save(incident.to_dict())
