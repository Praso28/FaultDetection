from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from agent.collector import Collector
from agent.confidence import CalibrationParams
from agent.executor import Executor
from agent.history_buffer import HistoryBuffer
from agent.incident_manager import IncidentManager
from agent.main import run_control_cycle_from_collector
from adapters.free5gc_fault_injector import Free5GCFaultInjector


@dataclass(frozen=True)
class Scenario:
    name: str
    fault_id: str
    target_nf: str
    duration_s: int
    expected_mode: str
    expected_action: str


@dataclass(frozen=True)
class ScenarioResult:
    name: str
    fault_id: str
    target_nf: str
    expected_mode: str
    expected_action: str
    actual_mode: str
    actual_action: str
    passed: bool
    detail: str


def load_scenarios(file_path: str | Path) -> list[Scenario]:
    path = Path(file_path)
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("Scenario file must contain a top-level list")

    scenarios: list[Scenario] = []
    for row in payload:
        if not isinstance(row, dict):
            raise ValueError("Each scenario entry must be an object")
        scenarios.append(
            Scenario(
                name=str(row["name"]),
                fault_id=str(row["fault_id"]).upper(),
                target_nf=str(row["target_nf"]).upper(),
                duration_s=int(row.get("duration_s", 120)),
                expected_mode=str(row["expected_mode"]).upper(),
                expected_action=str(row["expected_action"]),
            )
        )
    return scenarios


def run_scenarios(
    scenarios: list[Scenario],
    injector: Free5GCFaultInjector,
    collector: Collector,
    baseline,
    executor: Executor,
    *,
    calibration: CalibrationParams = CalibrationParams(),
    history: HistoryBuffer | None = None,
    incident_mgr: IncidentManager | None = None,
) -> list[ScenarioResult]:
    results: list[ScenarioResult] = []

    for scenario in scenarios:
        scenario_history = history or HistoryBuffer(max_windows=20)
        scenario_incident_mgr = incident_mgr or IncidentManager()

        injection_result = injector.inject(
            fault_id=scenario.fault_id,
            target_nf=scenario.target_nf,
            duration_s=scenario.duration_s,
            auto_rollback=False,
        )

        outcome = run_control_cycle_from_collector(
            collector=collector,
            baseline=baseline,
            executor=executor,
            calibration=calibration,
            incident_mgr=scenario_incident_mgr,
            history=scenario_history,
            window_seconds=30,
        )

        mode_ok = outcome.mode.upper() == scenario.expected_mode
        action_ok = outcome.action == scenario.expected_action
        passed = mode_ok and action_ok

        injector.rollback(injection_result)

        results.append(
            ScenarioResult(
                name=scenario.name,
                fault_id=scenario.fault_id,
                target_nf=scenario.target_nf,
                expected_mode=scenario.expected_mode,
                expected_action=scenario.expected_action,
                actual_mode=outcome.mode,
                actual_action=outcome.action,
                passed=passed,
                detail="scenario_passed" if passed else "scenario_expectation_mismatch",
            )
        )

    return results
