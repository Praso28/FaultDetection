from __future__ import annotations

import sys
from pathlib import Path
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from agent.observer import aggregate
from agent.verifier import RESOLVED, ROLLBACK, verify_incident
from simulation.injector import inject_fault
from simulation.metrics_gen import generate_normal


class VerifierTests(unittest.TestCase):
    def test_f1_recovery_resolved(self) -> None:
        _fault_snapshot = aggregate(inject_fault("F1", nf="SMF", seed=501, count=30))

        post_windows = [
            aggregate(generate_normal("SMF", seed=601 + i, count=30))
            for i in range(3)
        ]

        result = verify_incident(
            fault_id="F1",
            target_nf="SMF",
            post_action_snapshots=post_windows,
            max_windows=3,
        )

        self.assertEqual(result.state, RESOLVED)
        self.assertFalse(result.rollback_triggered)

    def test_f2_failure_triggers_rollback(self) -> None:
        _fault_snapshot = aggregate(inject_fault("F2", nf="UPF", seed=700, count=30))
        post_windows = [
            aggregate(inject_fault("F2", nf="UPF", seed=710 + i, count=30))
            for i in range(3)
        ]

        rollback_calls: list[str] = []

        def rollback() -> None:
            rollback_calls.append("called")

        result = verify_incident(
            fault_id="F2",
            target_nf="UPF",
            post_action_snapshots=post_windows,
            max_windows=3,
            rollback_fn=rollback,
        )

        self.assertEqual(result.state, ROLLBACK)
        self.assertTrue(result.rollback_triggered)
        self.assertEqual(len(rollback_calls), 1)


if __name__ == "__main__":
    unittest.main()
