from __future__ import annotations

import sys
from pathlib import Path
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from agent.confidence import CalibrationParams, SignalScores, compute_confidence, update_calibration
from agent.confidence import compute_temporal_consistency
from agent.history_buffer import HistoryBuffer
from agent.observer import aggregate
from simulation.injector import inject_fault
from simulation.metrics_gen import generate_normal


class ConfidenceTests(unittest.TestCase):
    def test_high_severity_maps_to_act_band(self) -> None:
        result = compute_confidence(
            SignalScores(log_determinism=1.0, metric_severity=0.95, temporal_consistency=0.9)
        )
        self.assertGreater(result.calibrated_confidence, 0.75)

    def test_medium_severity_maps_to_advise_band(self) -> None:
        result = compute_confidence(
            SignalScores(log_determinism=0.6, metric_severity=0.6, temporal_consistency=0.6)
        )
        self.assertGreaterEqual(result.calibrated_confidence, 0.4)
        self.assertLess(result.calibrated_confidence, 0.75)

    def test_low_severity_maps_to_escalate_band(self) -> None:
        result = compute_confidence(
            SignalScores(log_determinism=0.2, metric_severity=0.2, temporal_consistency=0.2)
        )
        self.assertLess(result.calibrated_confidence, 0.4)

    def test_online_calibration_update_is_deterministic(self) -> None:
        params = CalibrationParams(a=5.0, b=-3.0)
        updated_1 = update_calibration(params, base_score=0.7, observed_positive=True)
        updated_2 = update_calibration(params, base_score=0.7, observed_positive=True)
        self.assertEqual(updated_1, updated_2)

    def test_temporal_consistency_high_for_consecutive_faults(self) -> None:
        history = HistoryBuffer(max_windows=8)
        for seed in (201, 202, 203, 204):
            history.append(aggregate(inject_fault("F2", nf="UPF", seed=seed, count=30)))

        score = compute_temporal_consistency(history=history, fault_id="F2", target_nf="UPF", window_count=5)
        self.assertGreaterEqual(score, 0.8)

    def test_temporal_consistency_low_for_mostly_normal_windows(self) -> None:
        history = HistoryBuffer(max_windows=8)
        for seed in (301, 302, 303, 304):
            history.append(aggregate(generate_normal(nf="UPF", seed=seed, count=30)))

        score = compute_temporal_consistency(history=history, fault_id="F2", target_nf="UPF", window_count=5)
        self.assertLess(score, 0.6)


if __name__ == "__main__":
    unittest.main()
