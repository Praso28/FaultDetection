from __future__ import annotations

import sys
from pathlib import Path
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from agent.history_buffer import HistoryBuffer
from agent.observer import aggregate
from simulation.injector import inject_fault
from simulation.metrics_gen import generate_normal


class HistoryBufferTests(unittest.TestCase):
    def test_trend_detection_up(self) -> None:
        history = HistoryBuffer(max_windows=10)

        for seed in (10, 11, 12, 13, 14):
            history.append(aggregate(inject_fault("F2", nf="UPF", seed=seed, count=30)))

        ratio = history.compute_monotonic_ratio(nf="UPF", metric_name="latency_ms", direction="up", window_count=5)
        self.assertGreaterEqual(ratio, 0.5)
        self.assertTrue(history.is_trending("UPF", "latency_ms", "up", threshold=0.5, window_count=5))

    def test_fault_match_ratio_and_consecutive(self) -> None:
        history = HistoryBuffer(max_windows=6)

        history.append(aggregate(generate_normal(nf="UPF", seed=100, count=30)))
        history.append(aggregate(inject_fault("F2", nf="UPF", seed=101, count=30)))
        history.append(aggregate(inject_fault("F2", nf="UPF", seed=102, count=30)))
        history.append(aggregate(inject_fault("F2", nf="UPF", seed=103, count=30)))

        ratio = history.recent_fault_match_ratio(fault_id="F2", target_nf="UPF", window_count=4)
        consecutive = history.consecutive_fault_matches(fault_id="F2", target_nf="UPF", window_count=4)

        self.assertGreater(ratio, 0.5)
        self.assertEqual(consecutive, 3)


if __name__ == "__main__":
    unittest.main()
