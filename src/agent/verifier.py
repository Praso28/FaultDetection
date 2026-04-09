from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from agent.contracts import NFState, StateSnapshot

VERIFYING = "VERIFYING"
RESOLVED = "RESOLVED"
ROLLBACK = "ROLLBACK"
ESCALATED = "ESCALATED"


@dataclass(frozen=True)
class VerificationResult:
    state: str
    fault_id: str
    target_nf: str
    observed_windows: int
    rollback_triggered: bool
    escalated: bool
    detail: str


def verify_incident(
    fault_id: str,
    target_nf: str,
    post_action_snapshots: list[StateSnapshot],
    max_windows: int = 3,
    rollback_fn: Callable[[], None] | None = None,
) -> VerificationResult:
    observed = min(max_windows, len(post_action_snapshots))
    fault = fault_id.upper()

    for idx in range(observed):
        snapshot = post_action_snapshots[idx]
        state = snapshot.states.get(target_nf)
        if state is not None and _is_recovered(fault, state):
            return VerificationResult(
                state=RESOLVED,
                fault_id=fault,
                target_nf=target_nf,
                observed_windows=idx + 1,
                rollback_triggered=False,
                escalated=False,
                detail="recovered_within_verification_window",
            )

    if rollback_fn is not None:
        rollback_fn()

    return VerificationResult(
        state=ROLLBACK,
        fault_id=fault,
        target_nf=target_nf,
        observed_windows=observed,
        rollback_triggered=True,
        escalated=True,
        detail="recovery_failed_rollback_triggered",
    )


def _is_recovered(fault_id: str, state: NFState) -> bool:
    if fault_id == "F1":
        return (state.session_drop_count or 0) <= 10 and (state.connection_refused or 0) == 0

    if fault_id == "F2":
        return (
            (state.latency_ms or 0) <= 10
            and (state.cpu_pct or 0) <= 80
            and (state.packet_loss_pct or 0) <= 0.1
        )

    if fault_id == "F3":
        return (state.latency_ms or 0) <= 12 and (state.packet_loss_pct or 0) <= 0.5

    if fault_id == "F4":
        return (state.request_rate or 0) <= 5000 and (state.queue_length or 0) <= 1000

    if fault_id == "F5":
        return (state.error_log_count or 0) == 0

    return False
