from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone

from agent.auditor import AuditLogger
from agent.anomaly import build_baseline, detect_anomaly
from agent.collector import Collector
from agent.confidence import CalibrationParams, SignalScores, compute_confidence, compute_temporal_consistency
from agent.diagnoser import infer_fault
from agent.executor import ExecutionResult, Executor
from agent.history_buffer import HistoryBuffer
from agent.incident_manager import IncidentManager
from agent.observer import aggregate
from agent.planner import Plan, decide
from agent.verifier import VerificationResult, verify_incident
from simulation.injector import inject_fault
from simulation.metrics_gen import generate_normal


@dataclass(frozen=True)
class CycleOutcome:
    anomaly: bool
    fault: str | None
    target_nf: str | None
    confidence: float
    mode: str
    action: str
    execution_status: str
    verification_state: str | None


@dataclass(frozen=True)
class LoopConfig:
    window_seconds: int = 30
    max_cycles: int = 1


def _incident_id(fault: str, target_nf: str, window_start: str) -> str:
    raw = f"{fault}:{target_nf}:{window_start}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return digest[:16]


def _signal_scores_for_fault(
    fault: str,
    confidence_base: float,
    temporal_consistency: float | None = None,
) -> SignalScores:
    f = fault.upper()
    default_temporal = temporal_consistency

    def _temporal_with_floor(floor: float) -> float:
        if default_temporal is None:
            return floor
        return max(default_temporal, floor)

    if f == "F1":
        temporal_value = _temporal_with_floor(0.95)
        return SignalScores(
            log_determinism=1.0,
            metric_severity=max(confidence_base, 0.85),
            temporal_consistency=temporal_value,
        )
    if f == "F2":
        temporal_value = _temporal_with_floor(0.95)
        return SignalScores(
            log_determinism=0.85,
            metric_severity=max(confidence_base, 0.9),
            temporal_consistency=temporal_value,
        )
    if f == "F3":
        temporal_value = _temporal_with_floor(0.8)
        return SignalScores(
            log_determinism=0.4,
            metric_severity=min(confidence_base, 0.7),
            temporal_consistency=temporal_value,
        )
    if f == "F4":
        temporal_value = _temporal_with_floor(0.8)
        return SignalScores(
            log_determinism=0.35,
            metric_severity=confidence_base,
            temporal_consistency=temporal_value,
        )
    if f == "F5":
        temporal_value = _temporal_with_floor(0.75)
        return SignalScores(
            log_determinism=0.5,
            metric_severity=min(confidence_base, 0.5),
            temporal_consistency=temporal_value,
        )
    if default_temporal is None:
        default_temporal = 0.2
    return SignalScores(log_determinism=0.2, metric_severity=0.2, temporal_consistency=default_temporal)


def _make_post_action_snapshots(target_nf: str, seed: int, windows: int = 3):
    snapshots = []
    for idx in range(windows):
        events = generate_normal(nf=target_nf, seed=seed + idx, count=30)
        snapshots.append(aggregate(events))
    return snapshots


def build_default_baseline() -> dict:
    baseline_snapshots = []
    for nf in ("AMF", "SMF", "UPF", "NRF"):
        for seed in range(100, 110):
            baseline_snapshots.append(aggregate(generate_normal(nf=nf, seed=seed, count=30)))
    return build_baseline(baseline_snapshots)


def run_control_cycle(
    events,
    baseline,
    executor: Executor,
    calibration: CalibrationParams = CalibrationParams(),
    verification_seed: int = 900,
    auditor: AuditLogger | None = None,
    incident_mgr: IncidentManager | None = None,
    history: HistoryBuffer | None = None,
) -> CycleOutcome:
    snapshot = aggregate(events)
    if history is not None:
        history.append(snapshot)
    if auditor is not None:
        try:
            event_count = len(events)
        except TypeError:
            event_count = None
        auditor.log_cycle_start(snapshot.window_start, snapshot.window_end, event_count=event_count)

    anomaly = detect_anomaly(snapshot, baseline=baseline)
    if not anomaly:
        if auditor is not None:
            auditor.log_no_anomaly(snapshot.window_start, snapshot.window_end)
            auditor.log_cycle_outcome(
                anomaly=False,
                fault=None,
                target_nf=None,
                mode="NO_ANOMALY",
                action="no_action",
                execution_status="skipped",
                verification_state=None,
            )
        return CycleOutcome(
            anomaly=False,
            fault=None,
            target_nf=None,
            confidence=0.0,
            mode="NO_ANOMALY",
            action="no_action",
            execution_status="skipped",
            verification_state=None,
        )

    hypotheses = infer_fault(snapshot)
    if not hypotheses:
        if auditor is not None:
            auditor.log_anomaly_detected(fault=None, confidence_base=None)
            auditor.log_plan_decision(fault=None, confidence=0.0, mode="ESCALATE", action="no_action")
            auditor.log_cycle_outcome(
                anomaly=True,
                fault=None,
                target_nf=None,
                mode="ESCALATE",
                action="no_action",
                execution_status="skipped",
                verification_state=None,
            )
        return CycleOutcome(
            anomaly=True,
            fault=None,
            target_nf=None,
            confidence=0.0,
            mode="ESCALATE",
            action="no_action",
            execution_status="skipped",
            verification_state=None,
        )

    best = hypotheses[0]
    fault = str(best["fault"])
    target_nf = str(best["target_nf"])
    if auditor is not None:
        auditor.log_anomaly_detected(fault=fault, confidence_base=float(best["confidence_base"]))

    temporal_consistency: float | None = None
    if history is not None:
        temporal_consistency = compute_temporal_consistency(
            history=history,
            fault_id=fault,
            target_nf=target_nf,
            window_count=5,
        )

    scores = _signal_scores_for_fault(
        fault=fault,
        confidence_base=float(best["confidence_base"]),
        temporal_consistency=temporal_consistency,
    )
    confidence = compute_confidence(scores, calibration).calibrated_confidence

    if incident_mgr is not None and incident_mgr.is_suppressed(target_nf=target_nf, fault_id=fault):
        if auditor is not None:
            auditor.log(
                "incident_suppressed",
                {
                    "fault": fault,
                    "target_nf": target_nf,
                },
            )
            auditor.log_cycle_outcome(
                anomaly=True,
                fault=fault,
                target_nf=target_nf,
                mode="SUPPRESSED",
                action="no_action",
                execution_status="suppressed",
                verification_state=None,
            )
        return CycleOutcome(
            anomaly=True,
            fault=fault,
            target_nf=target_nf,
            confidence=confidence,
            mode="SUPPRESSED",
            action="no_action",
            execution_status="suppressed",
            verification_state=None,
        )

    incident_id: str
    if incident_mgr is not None:
        incident = incident_mgr.create(
            fault_id=fault,
            target_nf=target_nf,
            window_start=snapshot.window_start,
            confidence=confidence,
        )
        incident_id = incident.incident_id
        if auditor is not None:
            auditor.log(
                "incident_created",
                {
                    "incident_id": incident.incident_id,
                    "fault": fault,
                    "target_nf": target_nf,
                    "state": incident.state,
                },
            )
    else:
        incident_id = _incident_id(fault=fault, target_nf=target_nf, window_start=snapshot.window_start)

    plan: Plan = decide(fault=fault, confidence=confidence)
    if auditor is not None:
        auditor.log_plan_decision(fault=fault, confidence=confidence, mode=plan.mode, action=plan.action)

    if plan.mode != "ACT":
        if incident_mgr is not None:
            incident_mgr.transition(incident_id=incident_id, new_state="ESCALATED", detail=f"mode={plan.mode}")
            if auditor is not None:
                auditor.log(
                    "incident_transition",
                    {
                        "incident_id": incident_id,
                        "new_state": "ESCALATED",
                        "detail": f"mode={plan.mode}",
                    },
                )
        if auditor is not None:
            auditor.log_cycle_outcome(
                anomaly=True,
                fault=fault,
                target_nf=target_nf,
                mode=plan.mode,
                action=plan.action,
                execution_status="skipped",
                verification_state=None,
            )
        return CycleOutcome(
            anomaly=True,
            fault=fault,
            target_nf=target_nf,
            confidence=confidence,
            mode=plan.mode,
            action=plan.action,
            execution_status="skipped",
            verification_state=None,
        )

    idempotency_key = f"{incident_id}:{plan.action}"
    execution: ExecutionResult = executor.execute(
        action=plan.action,
        nf=target_nf,
        incident_id=incident_id,
        idempotency_key=idempotency_key,
        now=datetime.now(timezone.utc),
    )
    if auditor is not None:
        auditor.log_execution_attempt(
            incident_id=incident_id,
            action=plan.action,
            allowed=execution.allowed,
            status=execution.status,
            detail=execution.detail,
        )
    if incident_mgr is not None and execution.allowed:
        incident_mgr.transition(incident_id=incident_id, new_state="VERIFYING", detail="action_executed")
        if auditor is not None:
            auditor.log(
                "incident_transition",
                {
                    "incident_id": incident_id,
                    "new_state": "VERIFYING",
                    "detail": "action_executed",
                },
            )
    elif incident_mgr is not None and not execution.allowed:
        incident_mgr.transition(incident_id=incident_id, new_state="ESCALATED", detail=execution.detail)
        if auditor is not None:
            auditor.log(
                "incident_transition",
                {
                    "incident_id": incident_id,
                    "new_state": "ESCALATED",
                    "detail": execution.detail,
                },
            )

    verification_state: str | None = None
    if execution.allowed:
        post_action = _make_post_action_snapshots(target_nf=target_nf, seed=verification_seed)
        verify_result: VerificationResult = verify_incident(
            fault_id=fault,
            target_nf=target_nf,
            post_action_snapshots=post_action,
            max_windows=3,
        )
        verification_state = verify_result.state
        if incident_mgr is not None:
            final_state = "RESOLVED" if verify_result.state == "RESOLVED" else "ESCALATED"
            detail = "verification_recovered" if final_state == "RESOLVED" else "verification_failed_rollback"
            incident_mgr.transition(incident_id=incident_id, new_state=final_state, detail=detail)
            if auditor is not None:
                auditor.log(
                    "incident_transition",
                    {
                        "incident_id": incident_id,
                        "new_state": final_state,
                        "detail": detail,
                    },
                )
        if auditor is not None:
            auditor.log_verification_completed(
                fault=fault,
                state=verify_result.state,
                rollback_triggered=verify_result.rollback_triggered,
            )

    if auditor is not None:
        auditor.log_cycle_outcome(
            anomaly=True,
            fault=fault,
            target_nf=target_nf,
            mode=plan.mode,
            action=plan.action,
            execution_status=execution.status,
            verification_state=verification_state,
        )

    return CycleOutcome(
        anomaly=True,
        fault=fault,
        target_nf=target_nf,
        confidence=confidence,
        mode=plan.mode,
        action=plan.action,
        execution_status=execution.status,
        verification_state=verification_state,
    )


def run_control_cycle_from_collector(
    collector: Collector,
    baseline,
    executor: Executor,
    calibration: CalibrationParams = CalibrationParams(),
    verification_seed: int = 900,
    auditor: AuditLogger | None = None,
    incident_mgr: IncidentManager | None = None,
    history: HistoryBuffer | None = None,
    window_seconds: int = 30,
) -> CycleOutcome:
    events = collector.collect_window(duration_seconds=window_seconds)
    return run_control_cycle(
        events=events,
        baseline=baseline,
        executor=executor,
        calibration=calibration,
        verification_seed=verification_seed,
        auditor=auditor,
        incident_mgr=incident_mgr,
        history=history,
    )


def run_agent_loop(
    collector: Collector,
    baseline,
    executor: Executor,
    config: LoopConfig = LoopConfig(),
    calibration: CalibrationParams = CalibrationParams(),
    auditor: AuditLogger | None = None,
    incident_mgr: IncidentManager | None = None,
    history: HistoryBuffer | None = None,
) -> list[CycleOutcome]:
    outcomes: list[CycleOutcome] = []
    loop_history = history or HistoryBuffer(max_windows=max(10, config.max_cycles))
    for cycle_idx in range(config.max_cycles):
        outcome = run_control_cycle_from_collector(
            collector=collector,
            baseline=baseline,
            executor=executor,
            calibration=calibration,
            verification_seed=900 + cycle_idx,
            auditor=auditor,
            incident_mgr=incident_mgr,
            history=loop_history,
            window_seconds=config.window_seconds,
        )
        outcomes.append(outcome)
    return outcomes


def run_phase1_demo(fault_id: str = "F2", nf: str | None = None, seed: int = 42) -> dict:
    events = inject_fault(fault_id=fault_id, nf=nf, seed=seed)
    snapshot = aggregate(events)
    return snapshot.to_dict()


def run_phase7_demo(fault_id: str, seed: int = 42) -> dict:
    baseline = build_default_baseline()
    events = inject_fault(fault_id=fault_id, seed=seed)
    executor = Executor()
    outcome = run_control_cycle(events=events, baseline=baseline, executor=executor)
    return {
        "anomaly": outcome.anomaly,
        "fault": outcome.fault,
        "target_nf": outcome.target_nf,
        "confidence": outcome.confidence,
        "mode": outcome.mode,
        "action": outcome.action,
        "execution_status": outcome.execution_status,
        "verification_state": outcome.verification_state,
    }


if __name__ == "__main__":
    runtime_mode = str(os.getenv("AI5G_MODE", "LIVE")).upper().strip()
    if runtime_mode == "TEST":
        test_fault = str(os.getenv("AI5G_TEST_FAULT", "F2")).upper().strip() or "F2"
        try:
            test_seed = int(str(os.getenv("AI5G_TEST_SEED", "42")).strip())
        except ValueError:
            test_seed = 42

        output = run_phase7_demo(fault_id=test_fault, seed=test_seed)
        print(json.dumps(output, indent=2))
