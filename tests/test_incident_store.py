from __future__ import annotations

import sys
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from agent.incident_store import IncidentStore


class IncidentStoreTests(unittest.TestCase):
    def test_save_and_load_incident(self) -> None:
        with TemporaryDirectory() as tmpdir:
            store = IncidentStore(Path(tmpdir) / "incidents.jsonl")
            record = {
                "incident_id": "abc123",
                "fault_id": "F2",
                "target_nf": "UPF",
                "window_start": "2026-03-18T10:00:00Z",
                "confidence": 0.91,
                "state": "DETECTED",
                "created_at": "2026-03-18T10:00:00Z",
                "updated_at": "2026-03-18T10:00:00Z",
                "detail": "",
            }
            store.save(record)

            loaded = store.load("abc123")
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded["fault_id"], "F2")

    def test_save_updates_existing_record(self) -> None:
        with TemporaryDirectory() as tmpdir:
            store = IncidentStore(Path(tmpdir) / "incidents.jsonl")
            store.save(
                {
                    "incident_id": "abc123",
                    "fault_id": "F2",
                    "target_nf": "UPF",
                    "window_start": "2026-03-18T10:00:00Z",
                    "confidence": 0.91,
                    "state": "DETECTED",
                    "created_at": "2026-03-18T10:00:00Z",
                    "updated_at": "2026-03-18T10:00:00Z",
                    "detail": "",
                }
            )
            store.save(
                {
                    "incident_id": "abc123",
                    "fault_id": "F2",
                    "target_nf": "UPF",
                    "window_start": "2026-03-18T10:00:00Z",
                    "confidence": 0.93,
                    "state": "VERIFYING",
                    "created_at": "2026-03-18T10:00:00Z",
                    "updated_at": "2026-03-18T10:01:00Z",
                    "detail": "action_executed",
                }
            )

            rows = store.query({"incident_id": "abc123"})
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["state"], "VERIFYING")

    def test_query_and_bulk_export(self) -> None:
        with TemporaryDirectory() as tmpdir:
            store = IncidentStore(Path(tmpdir) / "incidents.jsonl")
            store.save(
                {
                    "incident_id": "i1",
                    "fault_id": "F1",
                    "target_nf": "SMF",
                    "window_start": "2026-03-18T10:00:00Z",
                    "confidence": 0.9,
                    "state": "RESOLVED",
                    "created_at": "2026-03-18T10:00:00Z",
                    "updated_at": "2026-03-18T10:01:00Z",
                    "detail": "ok",
                }
            )
            store.save(
                {
                    "incident_id": "i2",
                    "fault_id": "F2",
                    "target_nf": "UPF",
                    "window_start": "2026-03-18T10:05:00Z",
                    "confidence": 0.95,
                    "state": "ESCALATED",
                    "created_at": "2026-03-18T10:05:00Z",
                    "updated_at": "2026-03-18T10:07:00Z",
                    "detail": "verification_failed",
                }
            )

            resolved = store.query({"state": "RESOLVED"})
            self.assertEqual(len(resolved), 1)
            self.assertEqual(resolved[0]["incident_id"], "i1")

            exported = store.bulk_export(start_ts="2026-03-18T10:01:00Z", end_ts="2026-03-18T10:10:00Z")
            self.assertEqual(len(exported), 1)
            self.assertEqual(exported[0]["incident_id"], "i2")


if __name__ == "__main__":
    unittest.main()
