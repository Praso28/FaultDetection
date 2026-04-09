from __future__ import annotations

import sys
from pathlib import Path
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from agent.contracts import NFState, StateSnapshot
from agent.diagnoser import infer_fault
from agent.observer import aggregate
from simulation.injector import inject_fault


class DiagnoserTests(unittest.TestCase):
    def test_inject_f2_returns_f2(self) -> None:
        snapshot = aggregate(inject_fault("F2", nf="UPF", seed=77, count=30))
        hypotheses = infer_fault(snapshot)
        self.assertGreater(len(hypotheses), 0)
        self.assertEqual(hypotheses[0]["fault"], "F2")

    def test_inject_f3_returns_f3(self) -> None:
        snapshot = aggregate(inject_fault("F3", nf="UPF", seed=78, count=30))
        hypotheses = infer_fault(snapshot)
        self.assertGreater(len(hypotheses), 0)
        self.assertEqual(hypotheses[0]["fault"], "F3")

    def test_overlap_priority_f2_over_f3(self) -> None:
        snapshot = StateSnapshot(
            window_start="2026-01-01T00:00:00Z",
            window_end="2026-01-01T00:00:30Z",
            states={
                "UPF": NFState(
                    cpu_pct=85.0,
                    latency_ms=14.0,
                    packet_loss_pct=0.7,
                    error_log_count=1,
                )
            },
        )
        hypotheses = infer_fault(snapshot)
        faults = [item["fault"] for item in hypotheses]
        self.assertIn("F2", faults)
        self.assertNotIn("F3", faults)


if __name__ == "__main__":
    unittest.main()
