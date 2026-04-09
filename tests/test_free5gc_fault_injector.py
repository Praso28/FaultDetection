from __future__ import annotations

import sys
from pathlib import Path
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from adapters.free5gc_fault_injector import ACTIVE_FAULT_STATE_PATH, Free5GCFaultInjector


class Free5GCFaultInjectorTests(unittest.TestCase):
    def tearDown(self) -> None:
        ACTIVE_FAULT_STATE_PATH.unlink(missing_ok=True)

    def test_inject_f1_generates_expected_commands(self) -> None:
        injector = Free5GCFaultInjector(dry_run=True)
        result = injector.inject(fault_id="F1", target_nf="SMF", intensity=1.0, duration_s=30)

        self.assertTrue(result.applied)
        self.assertEqual(result.fault_id, "F1")
        self.assertEqual(result.target_nf, "SMF")
        self.assertTrue(any("pkill" in command for command in result.commands))
        self.assertTrue(any("./bin/smf" in command for command in result.rollback_commands))

    def test_inject_f2_generates_tc_commands(self) -> None:
        injector = Free5GCFaultInjector(dry_run=True)
        result = injector.inject(fault_id="F2", target_nf="UPF", intensity=1.5, duration_s=30)

        self.assertEqual(result.fault_id, "F2")
        self.assertTrue(any("tc qdisc" in command for command in result.commands))
        self.assertTrue(any("tc qdisc del" in command for command in result.rollback_commands))

    def test_invalid_fault_raises(self) -> None:
        injector = Free5GCFaultInjector(dry_run=True)
        with self.assertRaises(ValueError):
            injector.inject(fault_id="F99", target_nf="UPF")

    def test_state_file_written_and_cleared(self) -> None:
        injector = Free5GCFaultInjector(dry_run=True)
        result = injector.inject(fault_id="F2", target_nf="UPF", duration_s=5)
        self.assertTrue(ACTIVE_FAULT_STATE_PATH.exists())
        self.assertTrue(injector.rollback(result))
        self.assertFalse(ACTIVE_FAULT_STATE_PATH.exists())

    def test_non_fatal_command_pattern_allows_applied(self) -> None:
        injector = Free5GCFaultInjector(dry_run=False, command_runner=lambda _cmd: 1)
        result = injector.inject(fault_id="F1", target_nf="SMF", duration_s=5)
        self.assertTrue(result.applied)
        self.assertTrue(ACTIVE_FAULT_STATE_PATH.exists())

    def test_inject_rejected_in_live_mode(self) -> None:
        injector = Free5GCFaultInjector(mode="LIVE", dry_run=True)
        with self.assertRaises(PermissionError):
            injector.inject(fault_id="F2", target_nf="UPF", duration_s=5)

    def test_invalid_mode_raises(self) -> None:
        with self.assertRaises(ValueError):
            Free5GCFaultInjector(mode="INVALID", dry_run=True)


if __name__ == "__main__":
    unittest.main()
