from __future__ import annotations

import sys
from pathlib import Path
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from agent.evaluation import evaluate_phase9


class EvaluationTests(unittest.TestCase):
    def test_evaluation_metrics_shape_and_determinism(self) -> None:
        report_a = evaluate_phase9(runs_per_fault=5, baseline_runs=10, mixed_runs=10, seed_start=777)
        report_b = evaluate_phase9(runs_per_fault=5, baseline_runs=10, mixed_runs=10, seed_start=777)

        self.assertEqual(report_a.to_dict(), report_b.to_dict())
        self.assertGreaterEqual(report_a.detection_accuracy, 0.0)
        self.assertLessEqual(report_a.detection_accuracy, 100.0)
        self.assertGreaterEqual(report_a.false_positive_rate, 0.0)
        self.assertLessEqual(report_a.false_positive_rate, 100.0)
        self.assertGreaterEqual(report_a.recovery_success_rate, 0.0)
        self.assertLessEqual(report_a.recovery_success_rate, 100.0)


if __name__ == "__main__":
    unittest.main()
