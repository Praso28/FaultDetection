from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from agent.auditor import AuditLogger
from agent.executor import Executor
from agent.main import build_default_baseline, run_control_cycle
from simulation.injector import inject_fault
from simulation.metrics_gen import generate_normal


class AuditorTests(unittest.TestCase):
    def test_jsonl_entries_are_valid_and_monotonic(self) -> None:
        with TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "audit.jsonl"
            auditor = AuditLogger(log_path)

            auditor.log_cycle_start("2026-03-18T10:00:00Z", "2026-03-18T10:00:30Z", event_count=30)
            auditor.log_plan_decision(fault="F2", confidence=0.91, mode="ACT", action="scale_up_nf")
            auditor.log_cycle_outcome(
                anomaly=True,
                fault="F2",
                target_nf="UPF",
                mode="ACT",
                action="scale_up_nf",
                execution_status="executed",
                verification_state="RESOLVED",
            )

            with log_path.open("r", encoding="utf-8") as f:
                lines = [line.strip() for line in f if line.strip()]

            self.assertEqual(len(lines), 3)
            parsed = [json.loads(line) for line in lines]
            self.assertEqual([row["seq"] for row in parsed], [1, 2, 3])
            self.assertEqual(parsed[0]["event_type"], "cycle_start")
            self.assertEqual(parsed[1]["event_type"], "plan_decision")
            self.assertEqual(parsed[2]["event_type"], "cycle_outcome")

    def test_control_loop_logs_no_anomaly_path(self) -> None:
        with TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "audit.jsonl"
            auditor = AuditLogger(log_path)

            baseline = build_default_baseline()
            executor = Executor(cooldown_seconds=0)
            events = generate_normal(nf="UPF", seed=777, count=30)

            outcome = run_control_cycle(events=events, baseline=baseline, executor=executor, auditor=auditor)
            self.assertFalse(outcome.anomaly)

            with log_path.open("r", encoding="utf-8") as f:
                entries = [json.loads(line) for line in f if line.strip()]

            event_types = [entry["event_type"] for entry in entries]
            self.assertEqual(event_types, ["cycle_start", "no_anomaly", "cycle_outcome"])

    def test_control_loop_logs_act_path(self) -> None:
        with TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "audit.jsonl"
            auditor = AuditLogger(log_path)

            baseline = build_default_baseline()
            executor = Executor(cooldown_seconds=0)
            events = inject_fault(fault_id="F2", seed=42)

            outcome = run_control_cycle(
                events=events,
                baseline=baseline,
                executor=executor,
                verification_seed=1000,
                auditor=auditor,
            )

            self.assertEqual(outcome.mode, "ACT")
            self.assertEqual(outcome.execution_status, "executed")

            with log_path.open("r", encoding="utf-8") as f:
                entries = [json.loads(line) for line in f if line.strip()]

            event_types = [entry["event_type"] for entry in entries]
            self.assertEqual(
                event_types,
                [
                    "cycle_start",
                    "anomaly_detected",
                    "plan_decision",
                    "execution_attempt",
                    "verification_completed",
                    "cycle_outcome",
                ],
            )

            stats = auditor.observability_snapshot()
            self.assertGreaterEqual(stats["incident_count"], 1)
            self.assertGreaterEqual(stats["action_count"], 1)
            self.assertIn("confidence_distribution", stats)
            self.assertIn("fault_frequency", stats)


if __name__ == "__main__":
    unittest.main()