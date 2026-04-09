from __future__ import annotations

import sys
from pathlib import Path
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from agent.observer import aggregate
from agent.planner_llm import LLMConfig, generate_explanation
from simulation.injector import inject_fault


class PlannerLLMTests(unittest.TestCase):
    def test_f2_explanation_matches_reasoning(self) -> None:
        snapshot = aggregate(inject_fault("F2", nf="UPF", seed=42, count=30))
        text = generate_explanation(snapshot, fault="F2", confidence=0.88, use_llm=False)

        self.assertIn("F2", text)
        self.assertIn("latency", text)
        self.assertIn("cpu", text)
        self.assertIn("packet_loss", text)

    def test_llm_mode_fallback_to_deterministic(self) -> None:
        snapshot = aggregate(inject_fault("F3", nf="UPF", seed=45, count=30))

        def failing_requester(prompt: str, model: str, config: LLMConfig) -> str:
            raise RuntimeError("llm unavailable")

        text = generate_explanation(
            snapshot,
            fault="F3",
            confidence=0.64,
            use_llm=True,
            requester=failing_requester,
        )

        self.assertIn("F3", text)
        self.assertIn("confidence=0.640", text)


if __name__ == "__main__":
    unittest.main()
