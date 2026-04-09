from __future__ import annotations

from dataclasses import dataclass

from agent.executor import Executor
from agent.main import build_default_baseline, run_control_cycle
from simulation.injector import inject_fault
from simulation.metrics_gen import generate_normal


@dataclass(frozen=True)
class EvaluationReport:
    detection_accuracy: float
    false_positive_rate: float
    recovery_success_rate: float
    mixed_anomaly_rate: float
    runs_per_fault: int
    baseline_runs: int
    mixed_runs: int

    def to_dict(self) -> dict[str, float | int]:
        return {
            "detection_accuracy": self.detection_accuracy,
            "false_positive_rate": self.false_positive_rate,
            "recovery_success_rate": self.recovery_success_rate,
            "mixed_anomaly_rate": self.mixed_anomaly_rate,
            "runs_per_fault": self.runs_per_fault,
            "baseline_runs": self.baseline_runs,
            "mixed_runs": self.mixed_runs,
        }


def evaluate_phase9(
    runs_per_fault: int = 100,
    baseline_runs: int = 100,
    mixed_runs: int = 100,
    seed_start: int = 1000,
) -> EvaluationReport:
    baseline = build_default_baseline()

    detection_total = 0
    detection_correct = 0

    act_total = 0
    act_recovered = 0

    fault_ids = ("F1", "F2", "F3", "F4", "F5")

    for fault_index, fault_id in enumerate(fault_ids):
        for i in range(runs_per_fault):
            run_seed = seed_start + (fault_index * 10000) + i
            executor = Executor(cooldown_seconds=0)
            outcome = run_control_cycle(
                events=inject_fault(fault_id=fault_id, seed=run_seed),
                baseline=baseline,
                executor=executor,
                verification_seed=run_seed + 500000,
            )

            detection_total += 1
            if outcome.fault == fault_id:
                detection_correct += 1

            if outcome.mode == "ACT":
                act_total += 1
                if outcome.verification_state == "RESOLVED":
                    act_recovered += 1

    false_positives = 0
    for i in range(baseline_runs):
        run_seed = seed_start + 900000 + i
        executor = Executor(cooldown_seconds=0)
        normal_events = generate_normal(nf="UPF", seed=run_seed, count=30)
        outcome = run_control_cycle(events=normal_events, baseline=baseline, executor=executor)
        if outcome.anomaly:
            false_positives += 1

    mixed_anomaly_hits = 0
    mixed_pairs = (("F2", "F3"), ("F1", "F5"), ("F4", "F2"), ("F3", "F5"))
    for i in range(mixed_runs):
        run_seed = seed_start + 1200000 + i
        f_a, f_b = mixed_pairs[i % len(mixed_pairs)]
        events_a = inject_fault(fault_id=f_a, seed=run_seed, count=15)
        events_b = inject_fault(fault_id=f_b, seed=run_seed + 1, count=15)
        merged_events = events_a + events_b

        executor = Executor(cooldown_seconds=0)
        outcome = run_control_cycle(
            events=merged_events,
            baseline=baseline,
            executor=executor,
            verification_seed=run_seed + 600000,
        )
        if outcome.anomaly:
            mixed_anomaly_hits += 1

    detection_accuracy = round(100.0 * detection_correct / max(1, detection_total), 2)
    false_positive_rate = round(100.0 * false_positives / max(1, baseline_runs), 2)
    recovery_success_rate = round(100.0 * act_recovered / max(1, act_total), 2)
    mixed_anomaly_rate = round(100.0 * mixed_anomaly_hits / max(1, mixed_runs), 2)

    return EvaluationReport(
        detection_accuracy=detection_accuracy,
        false_positive_rate=false_positive_rate,
        recovery_success_rate=recovery_success_rate,
        mixed_anomaly_rate=mixed_anomaly_rate,
        runs_per_fault=runs_per_fault,
        baseline_runs=baseline_runs,
        mixed_runs=mixed_runs,
    )
