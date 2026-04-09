from __future__ import annotations

from dataclasses import dataclass


ACT_THRESHOLD = 0.75
ADVISE_THRESHOLD = 0.4


@dataclass(frozen=True)
class Plan:
    mode: str
    action: str

    def to_dict(self) -> dict[str, str]:
        return {"mode": self.mode, "action": self.action}


def _action_for_fault(fault: str) -> str:
    if fault == "F1":
        return "restart_nf"
    if fault == "F2":
        return "scale_up_nf"
    return "no_action"


def decide(fault: str, confidence: float) -> Plan:
    fault_id = fault.upper()

    if confidence >= ACT_THRESHOLD:
        return Plan(mode="ACT", action=_action_for_fault(fault_id))

    if confidence >= ADVISE_THRESHOLD:
        return Plan(mode="ADVISE", action="no_action")

    return Plan(mode="ESCALATE", action="no_action")
