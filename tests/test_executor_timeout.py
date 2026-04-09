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


class ExecutorTimeoutTests(unittest.TestCase):
    def test_timeout_blocks_action_and_sets_rollback_plan(self) -> None:
        executor = Executor(cooldown_seconds=0, max_execution_seconds={"restart_nf": 1})
        t0 = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

        result = executor.execute(
            action="restart_nf",
            nf="SMF",
            incident_id="inc-timeout-1",
            idempotency_key="k-timeout-1",
            now=t0,
            action_duration_seconds=3,
        )

        self.assertFalse(result.allowed)
        self.assertTrue(result.timeout_exceeded)
        self.assertEqual(result.detail, "execution_timeout_guardrail")
        self.assertIsNotNone(result.rollback_plan)
        self.assertEqual(result.rollback_plan.action_taken, "restart_nf")
        self.assertIn("wait_for_ready", result.rollback_plan.revert_steps)

    def test_non_timeout_executes_and_has_rollback_plan(self) -> None:
        executor = Executor(cooldown_seconds=0, max_execution_seconds={"scale_up_nf": 10})
        t0 = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

        result = executor.execute(
            action="scale_up_nf",
            nf="UPF",
            incident_id="inc-timeout-2",
            idempotency_key="k-timeout-2",
            now=t0,
            action_duration_seconds=5,
        )

        self.assertTrue(result.allowed)
        self.assertFalse(result.timeout_exceeded)
        self.assertEqual(result.status, "executed")
        self.assertIsNotNone(result.rollback_plan)
        self.assertEqual(result.rollback_plan.action_taken, "scale_up_nf")


if __name__ == "__main__":
    unittest.main()
