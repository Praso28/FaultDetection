from __future__ import annotations

import os
import sys
from pathlib import Path
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from adapters.free5gc_adapter import Free5GCCollector


@unittest.skipUnless(
    os.getenv("RUN_FREE5GC_INTEGRATION") == "1",
    "Set RUN_FREE5GC_INTEGRATION=1 to run against a live free5GC endpoint",
)
class Free5GCIntegrationTests(unittest.TestCase):
    def test_connect_and_collect_window_live(self) -> None:
        base_url = os.getenv("FREE5GC_BASE_URL", "http://localhost:8080")
        collector = Free5GCCollector()

        connected = collector.connect(
            {
                "base_url": base_url,
                "health_path": os.getenv("FREE5GC_HEALTH_PATH", "/health"),
                "metrics_path": os.getenv("FREE5GC_METRICS_PATH", "/metrics/events"),
                "logs_path": os.getenv("FREE5GC_LOGS_PATH", "/logs/events"),
                "timeout_seconds": int(os.getenv("FREE5GC_TIMEOUT_SECONDS", "2")),
            }
        )

        if not connected:
            self.skipTest("free5GC health check did not pass in this environment")

        events = collector.collect_window(duration_seconds=30)
        self.assertIsInstance(events, list)
        for event in events:
            self.assertIn(event.nf, {"AMF", "SMF", "UPF", "NRF"})


if __name__ == "__main__":
    unittest.main()
