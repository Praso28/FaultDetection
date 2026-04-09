from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from agent.executor import Executor


class ExecutorTests(unittest.TestCase):
    def test_negative_cooldown_rejected(self) -> None:
        with self.assertRaises(ValueError):
            Executor(cooldown_seconds=-1)

    def test_negative_timeout_rejected(self) -> None:
        with self.assertRaises(ValueError):
            Executor(max_execution_seconds={"restart_nf": -10})

    def test_invalid_action_rejected(self) -> None:
        executor = Executor()
        with self.assertRaises(ValueError):
            executor.execute(
                action="delete_nf",
                nf="UPF",
                incident_id="inc-1",
                idempotency_key="k-1",
                now=datetime(2026, 1, 1, tzinfo=timezone.utc),
            )

    def test_action_blocked_during_cooldown(self) -> None:
        executor = Executor(cooldown_seconds=300)
        t0 = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

        first = executor.execute(
            action="restart_nf",
            nf="SMF",
            incident_id="inc-1",
            idempotency_key="k-1",
            now=t0,
        )
        second = executor.execute(
            action="scale_up_nf",
            nf="SMF",
            incident_id="inc-2",
            idempotency_key="k-2",
            now=t0,
        )

        self.assertTrue(first.allowed)
        self.assertEqual(first.status, "executed")
        self.assertIsNotNone(first.rollback_plan)
        self.assertFalse(second.allowed)
        self.assertEqual(second.detail, "cooldown_guardrail")

    def test_one_action_per_incident(self) -> None:
        executor = Executor(cooldown_seconds=300)
        t0 = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

        first = executor.execute(
            action="restart_nf",
            nf="SMF",
            incident_id="inc-100",
            idempotency_key="k-100",
            now=t0,
        )
        second = executor.execute(
            action="scale_up_nf",
            nf="UPF",
            incident_id="inc-100",
            idempotency_key="k-101",
            now=t0,
        )

        self.assertTrue(first.allowed)
        self.assertIsNotNone(first.rollback_plan)
        self.assertFalse(second.allowed)
        self.assertEqual(second.detail, "one_action_per_incident_guardrail")

    def test_idempotency_key_returns_same_result(self) -> None:
        executor = Executor(cooldown_seconds=300)
        t0 = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

        first = executor.execute(
            action="restart_nf",
            nf="SMF",
            incident_id="inc-500",
            idempotency_key="dup-key",
            now=t0,
        )
        second = executor.execute(
            action="restart_nf",
            nf="SMF",
            incident_id="inc-999",
            idempotency_key="dup-key",
            now=t0,
        )

        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
