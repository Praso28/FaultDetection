from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


ALLOWED_ACTIONS = {"restart_nf", "scale_up_nf", "no_action"}
DESTRUCTIVE_ACTIONS = {"restart_nf", "scale_up_nf"}
COOLDOWN_SECONDS = 300  # 5 minutes
DEFAULT_MAX_EXECUTION_SECONDS = {
    "restart_nf": 30,
    "scale_up_nf": 60,
    "no_action": 0,
}


@dataclass(frozen=True)
class RollbackPlan:
    action_taken: str
    nf: str
    revert_steps: tuple[str, ...]


@dataclass(frozen=True)
class ExecutionResult:
    allowed: bool
    action: str
    nf: str
    incident_id: str
    idempotency_key: str
    status: str
    detail: str
    timeout_exceeded: bool = False
    rollback_plan: RollbackPlan | None = None


class Executor:
    def __init__(
        self,
        cooldown_seconds: int = COOLDOWN_SECONDS,
        max_execution_seconds: dict[str, int] | None = None,
    ) -> None:
        if cooldown_seconds < 0:
            raise ValueError("cooldown_seconds must be >= 0")
        self.cooldown_seconds = cooldown_seconds
        self.max_execution_seconds = dict(DEFAULT_MAX_EXECUTION_SECONDS)
        if max_execution_seconds is not None:
            self.max_execution_seconds.update(max_execution_seconds)
        for action, timeout in self.max_execution_seconds.items():
            if timeout < 0:
                raise ValueError(f"max_execution_seconds for {action} must be >= 0")
        self._nf_cooldown_until: dict[str, datetime] = {}
        self._incident_executed: set[str] = set()
        self._idempotency_results: dict[str, ExecutionResult] = {}

    def execute(
        self,
        action: str,
        nf: str,
        incident_id: str,
        idempotency_key: str,
        now: datetime | None = None,
        action_duration_seconds: int | None = None,
    ) -> ExecutionResult:
        current = now or datetime.now(timezone.utc)
        normalized_action = action.strip()

        if idempotency_key in self._idempotency_results:
            return self._idempotency_results[idempotency_key]

        if normalized_action not in ALLOWED_ACTIONS:
            raise ValueError(f"Action '{normalized_action}' is not allowed")

        rollback_plan = self._build_rollback_plan(action=normalized_action, nf=nf)

        if normalized_action == "no_action":
            result = self.no_action(
                nf=nf,
                incident_id=incident_id,
                idempotency_key=idempotency_key,
                rollback_plan=rollback_plan,
            )
            self._idempotency_results[idempotency_key] = result
            return result

        if incident_id in self._incident_executed:
            result = ExecutionResult(
                allowed=False,
                action=normalized_action,
                nf=nf,
                incident_id=incident_id,
                idempotency_key=idempotency_key,
                status="blocked",
                detail="one_action_per_incident_guardrail",
                rollback_plan=rollback_plan,
            )
            self._idempotency_results[idempotency_key] = result
            return result

        cooldown_until = self._nf_cooldown_until.get(nf)
        if cooldown_until is not None and current < cooldown_until:
            result = ExecutionResult(
                allowed=False,
                action=normalized_action,
                nf=nf,
                incident_id=incident_id,
                idempotency_key=idempotency_key,
                status="blocked",
                detail="cooldown_guardrail",
                rollback_plan=rollback_plan,
            )
            self._idempotency_results[idempotency_key] = result
            return result

        if self._is_timeout(
            action=normalized_action,
            action_duration_seconds=action_duration_seconds,
        ):
            result = ExecutionResult(
                allowed=False,
                action=normalized_action,
                nf=nf,
                incident_id=incident_id,
                idempotency_key=idempotency_key,
                status="blocked",
                detail="execution_timeout_guardrail",
                timeout_exceeded=True,
                rollback_plan=rollback_plan,
            )
            self._incident_executed.add(incident_id)
            self._nf_cooldown_until[nf] = current + timedelta(seconds=self.cooldown_seconds)
            self._idempotency_results[idempotency_key] = result
            return result

        if normalized_action == "restart_nf":
            result = self.restart_nf(
                nf=nf,
                incident_id=incident_id,
                idempotency_key=idempotency_key,
                rollback_plan=rollback_plan,
            )
        else:
            result = self.scale_up_nf(
                nf=nf,
                incident_id=incident_id,
                idempotency_key=idempotency_key,
                rollback_plan=rollback_plan,
            )

        self._incident_executed.add(incident_id)
        self._nf_cooldown_until[nf] = current + timedelta(seconds=self.cooldown_seconds)
        self._idempotency_results[idempotency_key] = result
        return result

    def restart_nf(
        self,
        nf: str,
        incident_id: str,
        idempotency_key: str,
        rollback_plan: RollbackPlan,
    ) -> ExecutionResult:
        return ExecutionResult(
            allowed=True,
            action="restart_nf",
            nf=nf,
            incident_id=incident_id,
            idempotency_key=idempotency_key,
            status="executed",
            detail="restart_invoked",
            rollback_plan=rollback_plan,
        )

    def scale_up_nf(
        self,
        nf: str,
        incident_id: str,
        idempotency_key: str,
        rollback_plan: RollbackPlan,
    ) -> ExecutionResult:
        return ExecutionResult(
            allowed=True,
            action="scale_up_nf",
            nf=nf,
            incident_id=incident_id,
            idempotency_key=idempotency_key,
            status="executed",
            detail="scale_up_invoked",
            rollback_plan=rollback_plan,
        )

    def no_action(
        self,
        nf: str,
        incident_id: str,
        idempotency_key: str,
        rollback_plan: RollbackPlan,
    ) -> ExecutionResult:
        return ExecutionResult(
            allowed=True,
            action="no_action",
            nf=nf,
            incident_id=incident_id,
            idempotency_key=idempotency_key,
            status="executed",
            detail="no_op",
            rollback_plan=rollback_plan,
        )

    def _is_timeout(self, action: str, action_duration_seconds: int | None) -> bool:
        if action_duration_seconds is None:
            return False
        timeout_limit = self.max_execution_seconds.get(action)
        if timeout_limit is None:
            return False
        return action_duration_seconds > timeout_limit

    def _build_rollback_plan(self, action: str, nf: str) -> RollbackPlan:
        if action == "restart_nf":
            return RollbackPlan(
                action_taken=action,
                nf=nf,
                revert_steps=("stop_nf", "start_nf", "wait_for_ready"),
            )
        if action == "scale_up_nf":
            return RollbackPlan(
                action_taken=action,
                nf=nf,
                revert_steps=("reduce_replicas_to_baseline",),
            )
        return RollbackPlan(
            action_taken=action,
            nf=nf,
            revert_steps=(),
        )
