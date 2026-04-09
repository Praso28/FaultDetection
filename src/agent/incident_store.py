from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any


class IncidentStore:
    def __init__(self, db_path: str | Path) -> None:
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("", encoding="utf-8")

    def save(self, incident: Any) -> dict[str, Any]:
        record = self._normalize_record(incident)
        records = self._read_all_records()

        found = False
        for idx, existing in enumerate(records):
            if existing.get("incident_id") == record["incident_id"]:
                records[idx] = record
                found = True
                break

        if not found:
            records.append(record)

        self._write_all_records(records)
        return record

    def load(self, incident_id: str) -> dict[str, Any] | None:
        for record in self._read_all_records():
            if record.get("incident_id") == incident_id:
                return record
        return None

    def query(self, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        filters = filters or {}
        records = self._read_all_records()
        if not filters:
            return records

        result: list[dict[str, Any]] = []
        for record in records:
            include = True
            for key, value in filters.items():
                if record.get(key) != value:
                    include = False
                    break
            if include:
                result.append(record)
        return result

    def bulk_export(self, start_ts: str | None = None, end_ts: str | None = None) -> list[dict[str, Any]]:
        records = self._read_all_records()
        if start_ts is None and end_ts is None:
            return records

        result: list[dict[str, Any]] = []
        for record in records:
            created_at = str(record.get("created_at", ""))
            if start_ts is not None and created_at < start_ts:
                continue
            if end_ts is not None and created_at > end_ts:
                continue
            result.append(record)
        return result

    def _read_all_records(self) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                records.append(json.loads(line))
        return records

    def _write_all_records(self, records: list[dict[str, Any]]) -> None:
        with self.path.open("w", encoding="utf-8") as f:
            for record in records:
                f.write(json.dumps(record, separators=(",", ":"), ensure_ascii=False))
                f.write("\n")

    def _normalize_record(self, incident: Any) -> dict[str, Any]:
        if isinstance(incident, dict):
            record = dict(incident)
        elif is_dataclass(incident):
            record = asdict(incident)
        elif hasattr(incident, "to_dict"):
            record = dict(incident.to_dict())
        else:
            raise ValueError("incident must be a dict, dataclass, or expose to_dict()")

        if "incident_id" not in record:
            raise ValueError("incident record must include incident_id")
        return record
