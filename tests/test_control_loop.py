from __future__ import annotations

import sys
from pathlib import Path
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from agent.executor import Executor
from agent.main import build_default_baseline, run_control_cycle, run_phase7_demo
from simulation.injector import inject_fault
from simulation.metrics_gen import generate_normal


class ControlLoopTests(unittest.TestCase):
    def test_all_faults_run_end_to_end(self) -> None:
        baseline = build_default_baseline()
        executor = Executor(cooldown_seconds=0)

        expected_modes = {
            "F1": "ACT",
            "F2": "ACT",
            "F3": "ADVISE",
            "F4": "ADVISE",
            "F5": "ADVISE",
        }

        for idx, fault_id in enumerate(("F1", "F2", "F3", "F4", "F5")):
            with self.subTest(fault=fault_id):
                events = inject_fault(fault_id=fault_id, seed=500 + idx)
                outcome = run_control_cycle(
                    events=events,
                    baseline=baseline,
                    executor=executor,
                    verification_seed=800 + idx,
                )
                self.assertTrue(outcome.anomaly)
                self.assertEqual(outcome.fault, fault_id)
                self.assertEqual(outcome.mode, expected_modes[fault_id])

                if fault_id in {"F1", "F2"}:
                    self.assertEqual(outcome.execution_status, "executed")
                    self.assertEqual(outcome.verification_state, "RESOLVED")
                else:
                    self.assertEqual(outcome.execution_status, "skipped")

    def test_normal_run_has_no_anomaly(self) -> None:
        baseline = build_default_baseline()
        executor = Executor(cooldown_seconds=0)
        events = generate_normal(nf="UPF", seed=999, count=30)
        outcome = run_control_cycle(events=events, baseline=baseline, executor=executor)

        self.assertFalse(outcome.anomaly)
        self.assertEqual(outcome.mode, "NO_ANOMALY")
        self.assertEqual(outcome.action, "no_action")

    def test_phase7_demo_f4_seed_changes_confidence(self) -> None:
        run_a = run_phase7_demo(fault_id="F4", seed=1)
        run_b = run_phase7_demo(fault_id="F4", seed=2)

        self.assertEqual(run_a["fault"], "F4")
        self.assertEqual(run_b["fault"], "F4")
        self.assertNotEqual(run_a["confidence"], run_b["confidence"])


if __name__ == "__main__":
    unittest.main()
