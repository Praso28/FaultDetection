from __future__ import annotations

import sys
from pathlib import Path
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from agent.collector import SimulationCollector
from agent.executor import Executor
from agent.main import LoopConfig, build_default_baseline, run_agent_loop, run_control_cycle_from_collector
from simulation.injector import inject_fault


class MainCollectorLoopTests(unittest.TestCase):
    def test_run_control_cycle_from_collector_with_simulation(self) -> None:
        baseline = build_default_baseline()
        executor = Executor(cooldown_seconds=0)

        collector = SimulationCollector(
            supplier=lambda nf, seed, count: inject_fault("F2", nf=nf, seed=seed, count=count)
        )
        collector.connect(
            {
                "source_type": "simulation",
                "target_nf": "UPF",
                "events_per_window": 30,
                "seed": 100,
            }
        )

        outcome = run_control_cycle_from_collector(
            collector=collector,
            baseline=baseline,
            executor=executor,
            verification_seed=1500,
            window_seconds=30,
        )

        self.assertTrue(outcome.anomaly)
        self.assertEqual(outcome.fault, "F2")
        self.assertEqual(outcome.mode, "ACT")

    def test_run_agent_loop_returns_expected_cycles(self) -> None:
        baseline = build_default_baseline()
        executor = Executor(cooldown_seconds=0)

        collector = SimulationCollector()
        collector.connect(
            {
                "source_type": "simulation",
                "target_nf": "UPF",
                "events_per_window": 30,
                "seed": 200,
            }
        )

        outcomes = run_agent_loop(
            collector=collector,
            baseline=baseline,
            executor=executor,
            config=LoopConfig(window_seconds=30, max_cycles=2),
        )

        self.assertEqual(len(outcomes), 2)
        self.assertTrue(all(outcome.mode in {"NO_ANOMALY", "ADVISE", "ACT", "ESCALATE", "SUPPRESSED"} for outcome in outcomes))


if __name__ == "__main__":
    unittest.main()
