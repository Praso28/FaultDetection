from __future__ import annotations

import sys
from pathlib import Path
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from agent.anomaly import build_baseline, detect_anomaly
from agent.observer import aggregate
from simulation.injector import inject_fault
from simulation.metrics_gen import generate_normal


class AnomalyTests(unittest.TestCase):
    def test_normal_data_no_anomaly(self) -> None:
        baseline_snapshots = [aggregate(generate_normal("UPF", seed=i, count=30)) for i in range(100, 120)]
        baseline = build_baseline(baseline_snapshots)
        probe_normal = aggregate(generate_normal("UPF", seed=121, count=30))
        self.assertFalse(detect_anomaly(probe_normal, baseline=baseline))

    def test_fault_data_anomaly(self) -> None:
        baseline_snapshots = [aggregate(generate_normal("UPF", seed=i, count=30)) for i in range(200, 220)]
        baseline = build_baseline(baseline_snapshots)
        fault_snapshot = aggregate(inject_fault("F2", nf="UPF", seed=250, count=30))
        self.assertTrue(detect_anomaly(fault_snapshot, baseline=baseline))


if __name__ == "__main__":
    unittest.main()
