from __future__ import annotations

import sys
from pathlib import Path
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from agent.planner import decide


class PlannerTests(unittest.TestCase):
    def test_f1_high_confidence_act(self) -> None:
        plan = decide(fault="F1", confidence=0.9)
        self.assertEqual(plan.mode, "ACT")
        self.assertEqual(plan.action, "restart_nf")

    def test_f3_medium_confidence_advise(self) -> None:
        plan = decide(fault="F3", confidence=0.6)
        self.assertEqual(plan.mode, "ADVISE")
        self.assertEqual(plan.action, "no_action")

    def test_low_confidence_escalate(self) -> None:
        plan = decide(fault="F2", confidence=0.2)
        self.assertEqual(plan.mode, "ESCALATE")
        self.assertEqual(plan.action, "no_action")

    def test_f2_high_confidence_scale_action(self) -> None:
        plan = decide(fault="F2", confidence=0.8)
        self.assertEqual(plan.mode, "ACT")
        self.assertEqual(plan.action, "scale_up_nf")


if __name__ == "__main__":
    unittest.main()
