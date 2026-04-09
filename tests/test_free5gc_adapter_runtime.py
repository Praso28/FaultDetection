from __future__ import annotations

import sys
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from adapters.free5gc_adapter import (
    Free5GCCollector,
    _parse_free5gc_log_events,
    _parse_netem_qdisc,
)


class Free5GCAdapterRuntimeTests(unittest.TestCase):
    def test_parse_netem_qdisc(self) -> None:
        parsed = _parse_netem_qdisc("qdisc netem 8001: root refcnt 2 limit 1000 delay 48ms loss 2.4%")
        self.assertIsNotNone(parsed)
        delay_ms, loss_pct = parsed
        self.assertEqual(delay_ms, 48.0)
        self.assertEqual(loss_pct, 2.4)

    def test_parse_free5gc_log_events(self) -> None:
        with TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "free5gc.log"
            log_path.write_text(
                "\n".join(
                    [
                        'time="2026-03-18T16:49:25+05:30" level="error" msg="Failed to listen: address already in use" NF="AMF"',
                        'time="2026-03-18T16:49:26+05:30" level="info" msg="Server started" NF="SMF"',
                    ]
                ),
                encoding="utf-8",
            )

            events = _parse_free5gc_log_events(
                duration_seconds=10_000_000,
                log_file_path=str(log_path),
                max_log_lines=100,
            )

            self.assertGreaterEqual(len(events), 2)
            self.assertEqual(events[0].nf, "AMF")
            self.assertIn(events[0].metric_type, {"connection_refused", "session_rate"})

    def test_collector_fallback_generates_events_from_log(self) -> None:
        with TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "free5gc.log"
            log_path.write_text(
                'time="2026-03-18T16:49:25+05:30" level="error" msg="connection refused" NF="SMF"\n',
                encoding="utf-8",
            )

            collector = Free5GCCollector(health_checker=lambda _url: True)
            self.assertTrue(
                collector.connect(
                    {
                        "base_url": "http://127.0.0.10:8000",
                        "health_path": "/",
                        "metrics_path": "/missing-metrics",
                        "logs_path": "/missing-logs",
                        "timeout_seconds": 1,
                        "log_file_path": str(log_path),
                        "max_log_lines": 100,
                    }
                )
            )

            events = collector.collect_window(30)
            self.assertGreaterEqual(len(events), 1)
            self.assertTrue(any(event.nf in {"AMF", "SMF", "UPF", "NRF"} for event in events))
            self.assertTrue(any(event.metric_type in {"cpu", "connection_refused", "latency", "packet_loss"} for event in events))


if __name__ == "__main__":
    unittest.main()
