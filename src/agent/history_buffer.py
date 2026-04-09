from __future__ import annotations

from collections import deque

from agent.contracts import StateSnapshot
from rules.fault_catalog import evaluate_rules


class HistoryBuffer:
    def __init__(self, max_windows: int = 10) -> None:
        if max_windows < 1:
            raise ValueError("max_windows must be >= 1")
        self.max_windows = max_windows
        self._snapshots: deque[StateSnapshot] = deque(maxlen=max_windows)

    def append(self, snapshot: StateSnapshot) -> None:
        self._snapshots.append(snapshot)

    def snapshots(self) -> list[StateSnapshot]:
        return list(self._snapshots)

    def get_metric_trend(self, nf: str, metric_name: str, window_count: int = 5) -> list[float]:
        values: list[float] = []
        for snapshot in self._recent(window_count):
            state = snapshot.states.get(nf)
            if state is None:
                continue
            value = getattr(state, metric_name, None)
            if value is None:
                continue
            values.append(float(value))
        return values

    def compute_monotonic_ratio(self, nf: str, metric_name: str, direction: str = "up", window_count: int = 5) -> float:
        trend = self.get_metric_trend(nf=nf, metric_name=metric_name, window_count=window_count)
        if len(trend) < 2:
            return 0.0

        improving = 0
        total = len(trend) - 1
        for idx in range(1, len(trend)):
            prev = trend[idx - 1]
            curr = trend[idx]
            if direction == "up" and curr >= prev:
                improving += 1
            if direction == "down" and curr <= prev:
                improving += 1
        return round(improving / total, 6)

    def is_trending(
        self,
        nf: str,
        metric_name: str,
        direction: str,
        threshold: float = 0.6,
        window_count: int = 5,
    ) -> bool:
        ratio = self.compute_monotonic_ratio(
            nf=nf,
            metric_name=metric_name,
            direction=direction,
            window_count=window_count,
        )
        return ratio >= threshold

    def recent_fault_match_ratio(self, fault_id: str, target_nf: str, window_count: int = 5) -> float:
        recent = self._recent(window_count)
        if not recent:
            return 0.0

        hits = 0
        for snapshot in recent:
            matched = any(
                hypothesis.fault == fault_id and hypothesis.target_nf == target_nf
                for hypothesis in evaluate_rules(snapshot)
            )
            if matched:
                hits += 1
        return round(hits / len(recent), 6)

    def consecutive_fault_matches(self, fault_id: str, target_nf: str, window_count: int = 5) -> int:
        recent = self._recent(window_count)
        count = 0
        for snapshot in reversed(recent):
            matched = any(
                hypothesis.fault == fault_id and hypothesis.target_nf == target_nf
                for hypothesis in evaluate_rules(snapshot)
            )
            if not matched:
                break
            count += 1
        return count

    def _recent(self, window_count: int) -> list[StateSnapshot]:
        if window_count < 1:
            return []
        snapshots = self.snapshots()
        return snapshots[-window_count:]
