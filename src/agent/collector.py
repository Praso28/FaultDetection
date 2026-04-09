from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from agent.contracts import Event
from simulation.metrics_gen import generate_normal


@dataclass(frozen=True)
class CollectorConfig:
    source_type: str
    target_nf: str = "UPF"
    events_per_window: int = 30
    seed: int = 42


def _base_window_ts(seed_offset: int) -> str:
    base = datetime(2026, 3, 18, 10, 0, 0, tzinfo=timezone.utc)
    ts = base.replace(second=(seed_offset % 60))
    return ts.isoformat().replace("+00:00", "Z")


class Collector(ABC):
    @abstractmethod
    def connect(self, config: dict) -> bool:
        raise NotImplementedError

    @abstractmethod
    def is_connected(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def collect_window(self, duration_seconds: int = 30) -> list[Event]:
        raise NotImplementedError

    @abstractmethod
    def close(self) -> None:
        raise NotImplementedError


class SimulationCollector(Collector):
    def __init__(self, supplier: Callable[[str, int, int], list[Event]] | None = None) -> None:
        self._connected = False
        self._config = CollectorConfig(source_type="simulation")
        self._window_idx = 0
        self._supplier = supplier or (lambda nf, seed, count: generate_normal(nf=nf, seed=seed, count=count))

    def connect(self, config: dict) -> bool:
        source_type = str(config.get("source_type", "simulation"))
        target_nf = str(config.get("target_nf", "UPF"))
        events_per_window = int(config.get("events_per_window", 30))
        seed = int(config.get("seed", 42))
        self._config = CollectorConfig(
            source_type=source_type,
            target_nf=target_nf,
            events_per_window=events_per_window,
            seed=seed,
        )
        self._connected = True
        self._window_idx = 0
        return True

    def is_connected(self) -> bool:
        return self._connected

    def collect_window(self, duration_seconds: int = 30) -> list[Event]:
        if not self._connected:
            raise RuntimeError("collector is not connected")
        self._window_idx += 1
        window_seed = self._config.seed + self._window_idx
        events = self._supplier(self._config.target_nf, window_seed, self._config.events_per_window)
        if len(events) <= self._config.events_per_window:
            return events
        return events[: self._config.events_per_window]

    def close(self) -> None:
        self._connected = False
