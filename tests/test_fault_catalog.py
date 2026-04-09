from __future__ import annotations

import sys
from pathlib import Path
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from agent.observer import aggregate
from rules.fault_catalog import evaluate_rules
from simulation.injector import inject_fault


class FaultCatalogTests(unittest.TestCase):
    def test_detects_f2(self) -> None:
        snapshot = aggregate(inject_fault("F2", nf="UPF", seed=11, count=30))
        faults = {h.fault for h in evaluate_rules(snapshot)}
        self.assertIn("F2", faults)

    def test_detects_f3(self) -> None:
        snapshot = aggregate(inject_fault("F3", nf="UPF", seed=12, count=30))
        faults = {h.fault for h in evaluate_rules(snapshot)}
        self.assertIn("F3", faults)


if __name__ == "__main__":
    unittest.main()
