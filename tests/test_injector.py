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


class InjectorTests(unittest.TestCase):
    def test_f2_pattern(self) -> None:
        events = inject_fault("F2", nf="UPF", seed=42, count=30)
        snapshot = aggregate(events)
        state = snapshot.states["UPF"]
        self.assertIsNotNone(state.latency_ms)
        self.assertIsNotNone(state.cpu_pct)
        self.assertIsNotNone(state.packet_loss_pct)
        self.assertGreater(state.latency_ms, 10)
        self.assertGreater(state.cpu_pct, 80)
        self.assertGreater(state.packet_loss_pct, 0.1)

    def test_f3_pattern(self) -> None:
        events = inject_fault("F3", nf="UPF", seed=42, count=30)
        snapshot = aggregate(events)
        state = snapshot.states["UPF"]
        self.assertIsNotNone(state.latency_ms)
        self.assertIsNotNone(state.cpu_pct)
        self.assertIsNotNone(state.packet_loss_pct)
        self.assertGreater(state.latency_ms, 12)
        self.assertGreater(state.packet_loss_pct, 0.5)
        self.assertLess(state.cpu_pct, 50)


if __name__ == "__main__":
    unittest.main()
