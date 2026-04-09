from __future__ import annotations

import sys
from pathlib import Path
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from adapters.free5gc_adapter import Free5GCCollector
from agent.collector import SimulationCollector


class CollectorTests(unittest.TestCase):
    def test_simulation_collector_requires_connection(self) -> None:
        collector = SimulationCollector()
        with self.assertRaises(RuntimeError):
            collector.collect_window(30)

    def test_simulation_collector_collects_window(self) -> None:
        collector = SimulationCollector()
        connected = collector.connect(
            {
                "source_type": "simulation",
                "target_nf": "UPF",
                "events_per_window": 12,
                "seed": 99,
            }
        )
        self.assertTrue(connected)
        self.assertTrue(collector.is_connected())

        events = collector.collect_window(30)
        self.assertEqual(len(events), 12)
        self.assertTrue(all(event.nf == "UPF" for event in events))

    def test_free5gc_collector_connects_with_injected_health_checker(self) -> None:
        collector = Free5GCCollector(health_checker=lambda url: url.endswith("/health"))
        connected = collector.connect({"base_url": "http://localhost:8080", "health_path": "/health"})
        self.assertTrue(connected)
        self.assertTrue(collector.is_connected())

    def test_free5gc_collector_collects_with_injected_fetcher(self) -> None:
        def fetcher(base_url: str, duration_seconds: int) -> list[dict]:
            self.assertEqual(base_url, "http://localhost:8080")
            self.assertEqual(duration_seconds, 30)
            return [
                {
                    "ts": "2026-03-18T10:00:00+00:00",
                    "nf": "upf",
                    "metric_type": "latency",
                    "value": 15.5,
                    "unit": "ms",
                    "log_type": "INFO",
                    "message": "",
                }
            ]

        collector = Free5GCCollector(health_checker=lambda _url: True, event_fetcher=fetcher)
        self.assertTrue(collector.connect({"base_url": "http://localhost:8080"}))

        events = collector.collect_window(30)
        self.assertGreaterEqual(len(events), 1)
        injected = [event for event in events if event.metric_type == "latency" and event.message == ""]
        self.assertGreaterEqual(len(injected), 1)
        self.assertEqual(injected[0].nf, "UPF")
        self.assertEqual(injected[0].timestamp, "2026-03-18T10:00:00Z")

    def test_free5gc_collector_without_fetcher_uses_runtime_fallback_when_unreachable(self) -> None:
        collector = Free5GCCollector(health_checker=lambda _url: True)
        self.assertTrue(collector.connect({"base_url": "http://localhost:8080"}))
        events = collector.collect_window(30)
        self.assertGreaterEqual(len(events), 1)
        self.assertTrue(all(event.nf in {"AMF", "SMF", "UPF", "NRF"} for event in events))

    def test_free5gc_collector_rejects_invalid_mode(self) -> None:
        collector = Free5GCCollector(health_checker=lambda _url: True)
        with self.assertRaises(ValueError):
            collector.connect({"base_url": "http://localhost:8080", "mode": "invalid"})


if __name__ == "__main__":
    unittest.main()
