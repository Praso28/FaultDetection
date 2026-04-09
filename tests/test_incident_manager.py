from __future__ import annotations

import sys
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from agent.executor import Executor
from agent.incident_manager import IncidentManager
from agent.incident_store import IncidentStore
from agent.main import build_default_baseline, run_control_cycle
from simulation.injector import inject_fault


class IncidentManagerTests(unittest.TestCase):
    def test_lifecycle_transitions_and_suppression(self) -> None:
        mgr = IncidentManager()

        incident = mgr.create(
            fault_id="F2",
            target_nf="UPF",
            window_start="2026-03-18T10:00:00Z",
            confidence=0.91,
        )
        self.assertEqual(incident.state, "DETECTED")
        self.assertTrue(mgr.is_suppressed(target_nf="UPF", fault_id="F2"))

        mgr.transition(incident.incident_id, "VERIFYING", detail="action_executed")
        self.assertEqual(mgr.get(incident.incident_id).state, "VERIFYING")

        mgr.transition(incident.incident_id, "RESOLVED", detail="verification_recovered")
        self.assertEqual(mgr.get(incident.incident_id).state, "RESOLVED")
        self.assertFalse(mgr.is_suppressed(target_nf="UPF", fault_id="F2"))

    def test_unknown_incident_transition_raises(self) -> None:
        mgr = IncidentManager()
        with self.assertRaises(ValueError):
            mgr.transition("does-not-exist", "ESCALATED", detail="bad")

    def test_control_cycle_suppresses_when_active_incident_exists(self) -> None:
        baseline = build_default_baseline()
        executor = Executor(cooldown_seconds=0)
        mgr = IncidentManager()

        active = mgr.create(
            fault_id="F2",
            target_nf="UPF",
            window_start="2026-03-18T10:00:00Z",
            confidence=0.88,
        )
        self.assertEqual(active.state, "DETECTED")

        outcome = run_control_cycle(
            events=inject_fault(fault_id="F2", seed=123),
            baseline=baseline,
            executor=executor,
            incident_mgr=mgr,
        )

        self.assertTrue(outcome.anomaly)
        self.assertEqual(outcome.mode, "SUPPRESSED")
        self.assertEqual(outcome.action, "no_action")
        self.assertEqual(outcome.execution_status, "suppressed")

    def test_persistence_updates_with_transitions(self) -> None:
        with TemporaryDirectory() as tmpdir:
            store = IncidentStore(Path(tmpdir) / "incidents.jsonl")
            mgr = IncidentManager(store=store)

            incident = mgr.create(
                fault_id="F1",
                target_nf="SMF",
                window_start="2026-03-18T10:00:00Z",
                confidence=0.92,
            )
            saved = store.load(incident.incident_id)
            self.assertIsNotNone(saved)
            self.assertEqual(saved["state"], "DETECTED")

            mgr.transition(incident.incident_id, "VERIFYING", detail="action_executed")
            saved = store.load(incident.incident_id)
            self.assertIsNotNone(saved)
            self.assertEqual(saved["state"], "VERIFYING")
            self.assertEqual(saved["detail"], "action_executed")


if __name__ == "__main__":
    unittest.main()
