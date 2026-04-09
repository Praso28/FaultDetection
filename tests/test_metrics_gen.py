from __future__ import annotations

import sys
from pathlib import Path
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from simulation.metrics_gen import generate_normal


class MetricsGeneratorTests(unittest.TestCase):
    def test_same_seed_same_output(self) -> None:
        run_a = generate_normal(nf="UPF", seed=123, count=5)
        run_b = generate_normal(nf="UPF", seed=123, count=5)
        self.assertEqual([e.to_dict() for e in run_a], [e.to_dict() for e in run_b])

    def test_different_seed_different_output(self) -> None:
        run_a = generate_normal(nf="UPF", seed=123, count=5)
        run_b = generate_normal(nf="UPF", seed=321, count=5)
        self.assertNotEqual([e.to_dict() for e in run_a], [e.to_dict() for e in run_b])


if __name__ == "__main__":
    unittest.main()
