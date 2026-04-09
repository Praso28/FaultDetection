from __future__ import annotations

import sys
from pathlib import Path
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from adapters.free5gc_fault_injector import ACTIVE_FAULT_STATE_PATH, Free5GCFaultInjector
from adapters.scenario_runner import load_scenarios, run_scenarios
from agent.collector import SimulationCollector
from agent.executor import Executor
from agent.main import build_default_baseline
from simulation.injector import inject_fault


class ScenarioRunnerTests(unittest.TestCase):
    def tearDown(self) -> None:
        ACTIVE_FAULT_STATE_PATH.unlink(missing_ok=True)

    def test_load_scenarios(self) -> None:
        scenarios = load_scenarios(PROJECT_ROOT / "scenarios" / "free5gc_scenarios.yaml")
        self.assertGreaterEqual(len(scenarios), 5)
        self.assertEqual(scenarios[0].fault_id, "F1")

    def test_run_single_scenario_with_simulated_fault(self) -> None:
        scenarios = load_scenarios(PROJECT_ROOT / "scenarios" / "free5gc_scenarios.yaml")
        scenario = next(s for s in scenarios if s.fault_id == "F2")

        collector = SimulationCollector(
            supplier=lambda nf, seed, count: inject_fault("F2", nf=nf, seed=seed, count=count)
        )
        collector.connect(
            {
                "source_type": "simulation",
                "target_nf": "UPF",
                "events_per_window": 30,
                "seed": 101,
            }
        )

        injector = Free5GCFaultInjector(dry_run=True)
        results = run_scenarios(
            scenarios=[scenario],
            injector=injector,
            collector=collector,
            baseline=build_default_baseline(),
            executor=Executor(cooldown_seconds=0),
        )

        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].passed)
        self.assertEqual(results[0].actual_mode, "ACT")
        self.assertFalse(ACTIVE_FAULT_STATE_PATH.exists())


if __name__ == "__main__":
    unittest.main()
