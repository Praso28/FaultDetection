from __future__ import annotations

import json
import sys
from pathlib import Path
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from agent.contracts import Event, NFState, StateSnapshot


class ContractsTests(unittest.TestCase):
    def test_event_instantiation_and_validation(self) -> None:
        event = Event(
            timestamp="2026-03-18T10:00:00Z",
            nf="UPF",
            metric_type="latency",
            value=15.5,
            unit="ms",
        )
        self.assertEqual(event.nf, "UPF")

    def test_invalid_nf_raises(self) -> None:
        with self.assertRaises(ValueError):
            Event(
                timestamp="2026-03-18T10:00:00Z",
                nf="BAD",
                metric_type="latency",
                value=1,
                unit="ms",
            )

    def test_serialization(self) -> None:
        snapshot = StateSnapshot(
            window_start="2026-03-18T10:00:00Z",
            window_end="2026-03-18T10:00:30Z",
            states={"UPF": NFState(cpu_pct=82.1, latency_ms=15.5)},
        )
        encoded = json.dumps(snapshot.to_dict())
        self.assertIn("UPF", encoded)


if __name__ == "__main__":
    unittest.main()
