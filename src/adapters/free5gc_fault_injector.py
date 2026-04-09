from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable


DEFAULT_NF_BY_FAULT = {
    "F1": "SMF",
    "F2": "UPF",
    "F3": "UPF",
    "F4": "AMF",
    "F5": "NRF",
}

ACTIVE_FAULT_STATE_PATH = Path("/tmp/ai5g_active_fault.json")


@dataclass(frozen=True)
class FaultInjectionResult:
    fault_id: str
    target_nf: str
    intensity: float
    duration_s: int
    applied: bool
    dry_run: bool
    started_at: str
    commands: tuple[str, ...]
    rollback_commands: tuple[str, ...]
    detail: str


class Free5GCFaultInjector:
    def __init__(
        self,
        *,
        mode: str = "TEST",
        dry_run: bool = True,
        command_runner: Callable[[str], int] | None = None,
        sleep_fn: Callable[[float], None] | None = None,
        free5gc_root: str = "/home/vboxuser/free5gc",
        command_timeout_seconds: int = 10,
    ) -> None:
        normalized_mode = mode.upper().strip()
        if normalized_mode not in {"LIVE", "TEST"}:
            raise ValueError("mode must be LIVE or TEST")
        if command_timeout_seconds <= 0:
            raise ValueError("command_timeout_seconds must be > 0")

        self.mode = normalized_mode
        self.dry_run = dry_run
        self.free5gc_root = free5gc_root
        self.command_timeout_seconds = command_timeout_seconds
        self._command_runner = command_runner or self._default_command_runner
        self._sleep = sleep_fn or time.sleep

    def inject(
        self,
        fault_id: str,
        target_nf: str | None = None,
        intensity: float = 1.0,
        duration_s: int = 120,
        auto_rollback: bool = False,
    ) -> FaultInjectionResult:
        if self.mode != "TEST":
            raise PermissionError("fault injection is disabled unless mode=TEST")

        normalized_fault = fault_id.upper()
        if normalized_fault not in DEFAULT_NF_BY_FAULT:
            raise ValueError(f"Unsupported fault_id '{fault_id}'")

        nf = (target_nf or DEFAULT_NF_BY_FAULT[normalized_fault]).upper()
        commands, rollback_commands = self._commands_for_fault(
            fault_id=normalized_fault,
            target_nf=nf,
            intensity=intensity,
        )

        started_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        expires_at = (
            (datetime.now(timezone.utc) + timedelta(seconds=max(1, duration_s)))
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )
        applied = True
        detail = "injection_applied"

        if not self.dry_run:
            for command in commands:
                rc = self._command_runner(command)
                if rc != 0 and "|| true" not in command:
                    applied = False
                    detail = f"command_failed:{command}"
                    break

            if applied and auto_rollback and duration_s > 0:
                self._sleep(duration_s)
                self.rollback(
                    FaultInjectionResult(
                        fault_id=normalized_fault,
                        target_nf=nf,
                        intensity=intensity,
                        duration_s=duration_s,
                        applied=applied,
                        dry_run=self.dry_run,
                        started_at=started_at,
                        commands=commands,
                        rollback_commands=rollback_commands,
                        detail=detail,
                    )
                )

        if applied:
            self._write_active_fault_state(
                fault_id=normalized_fault,
                target_nf=nf,
                intensity=float(intensity),
                duration_s=duration_s,
                started_at=started_at,
                expires_at=expires_at,
                dry_run=self.dry_run,
            )

        return FaultInjectionResult(
            fault_id=normalized_fault,
            target_nf=nf,
            intensity=intensity,
            duration_s=duration_s,
            applied=applied,
            dry_run=self.dry_run,
            started_at=started_at,
            commands=commands,
            rollback_commands=rollback_commands,
            detail=detail,
        )

    def rollback(self, result: FaultInjectionResult) -> bool:
        if self.dry_run:
            self._clear_active_fault_state()
            return True

        for command in result.rollback_commands:
            rc = self._command_runner(command)
            if rc != 0:
                return False
        self._clear_active_fault_state()
        return True

    def _commands_for_fault(self, fault_id: str, target_nf: str, intensity: float) -> tuple[tuple[str, ...], tuple[str, ...]]:
        if fault_id == "F1":
            command = f"pkill -f '/free5gc/.*/smf' || true"
            rollback = (
                f"cd {self.free5gc_root} && ./bin/smf -c ./config/smfcfg.yaml -l ./log/injector_smf.log >/dev/null 2>&1 &",
            )
            return ((command,), rollback)

        if fault_id in {"F2", "F3"}:
            delay_ms = int((40 if fault_id == "F2" else 25) * max(0.1, intensity))
            loss_pct = round((2.0 if fault_id == "F2" else 5.0) * max(0.1, intensity), 2)
            command = f"sudo tc qdisc replace dev lo root netem delay {delay_ms}ms loss {loss_pct}%"
            rollback = ("sudo tc qdisc del dev lo root || true",)
            return ((command,), rollback)

        if fault_id == "F4":
            burst_count = max(50, int(200 * max(0.1, intensity)))
            command = (
                "for i in $(seq 1 "
                f"{burst_count}"
                "); do curl -s -m 1 http://127.0.0.18:8000/ >/dev/null || true; done"
            )
            rollback: tuple[str, ...] = ()
            return ((command,), rollback)

        if fault_id == "F5":
            command = (
                "echo 'time=\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\" level=\"error\" "
                "msg=\"Unrecognized parameter injected\" NF=\"NRF\"' "
                f">> {self.free5gc_root}/log/injector_fault.log"
            )
            rollback = ("true",)
            return ((command,), rollback)

        raise ValueError(f"Unsupported fault_id '{fault_id}'")

    def _default_command_runner(self, command: str) -> int:
        try:
            completed = subprocess.run(
                command,
                shell=True,
                check=False,
                timeout=self.command_timeout_seconds,
            )
            return int(completed.returncode)
        except subprocess.TimeoutExpired:
            return 124

    def _write_active_fault_state(
        self,
        *,
        fault_id: str,
        target_nf: str,
        intensity: float,
        duration_s: int,
        started_at: str,
        expires_at: str,
        dry_run: bool,
    ) -> None:
        payload = {
            "fault_id": fault_id,
            "target_nf": target_nf,
            "intensity": intensity,
            "duration_s": duration_s,
            "started_at": started_at,
            "expires_at": expires_at,
            "dry_run": dry_run,
        }
        ACTIVE_FAULT_STATE_PATH.write_text(json.dumps(payload), encoding="utf-8")

    def _clear_active_fault_state(self) -> None:
        if ACTIVE_FAULT_STATE_PATH.exists():
            ACTIVE_FAULT_STATE_PATH.unlink(missing_ok=True)
