from __future__ import annotations

import sys
from pathlib import Path
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from agent.observer import aggregate
from simulation.injector import inject_fault


class ObserverTests(unittest.TestCase):
    def test_aggregate_f2_thresholds(self) -> None:
        events = inject_fault("F2", nf="UPF", seed=7, count=30)
        snapshot = aggregate(events)
        upf = snapshot.states.get("UPF")

        self.assertIsNotNone(upf)
        assert upf is not None
        self.assertGreater(upf.latency_ms or 0, 10)
        self.assertGreater(upf.cpu_pct or 0, 80)
        self.assertGreater(upf.packet_loss_pct or 0, 0.1)


if __name__ == "__main__":
    unittest.main()
