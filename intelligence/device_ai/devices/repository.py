"""Persistence layer abstraction for EcoTrace Device records (P5.2).

Follows the repository pattern established in ``device_ai.fingerprint.repository``.
Decouples domain models and API handlers from concrete storage engines.

Provides:
- :class:`DeviceRepository`: Storage-agnostic Protocol interface.
- :class:`InMemoryDeviceRepository`: Fast, thread-safe in-memory store for testing and runtime default.
- :class:`JsonFileDeviceRepository`: Durable JSON filesystem store.
"""

from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path
from typing import Protocol, runtime_checkable

from .models import DeviceEvent, DeviceRecord


@runtime_checkable
class DeviceRepository(Protocol):
    """Storage-agnostic persistence contract for DeviceRecord entities and audit events."""

    def save(self, device: DeviceRecord) -> None:
        """Persist ``device``, replacing any existing record with the same device_id."""
        ...

    def get(self, device_id: str) -> DeviceRecord | None:
        """Return the record for ``device_id``, or ``None`` if not found."""
        ...

    def exists(self, device_id: str) -> bool:
        """Return whether a record exists for ``device_id``."""
        ...

    def find_by_capture_id(self, capture_id: str) -> list[DeviceRecord]:
        """Return all device records originated from ``capture_id``."""
        ...

    def list_all(self, limit: int = 100, offset: int = 0) -> list[DeviceRecord]:
        """Return paginated device records."""
        ...

    def delete(self, device_id: str) -> bool:
        """Delete record for ``device_id``, returning True if deleted."""
        ...

    def count(self) -> int:
        """Return the total number of stored device records."""
        ...

    def append_event(self, event: DeviceEvent) -> None:
        """Append an immutable lifecycle audit event."""
        ...

    def list_events(self, device_id: str) -> list[DeviceEvent]:
        """Return all audit events for a device in chronological order (oldest -> newest)."""
        ...

    def get_latest_event(self, device_id: str) -> DeviceEvent | None:
        """Return the most recent audit event for a device, or None."""
        ...

    def count_events(self, device_id: str | None = None) -> int:
        """Count events for a specific device or across all devices."""
        ...


class InMemoryDeviceRepository:
    """Non-durable, thread-safe in-memory repository backed by dictionaries."""

    def __init__(self) -> None:
        self._records: dict[str, DeviceRecord] = {}
        self._events: dict[str, list[DeviceEvent]] = defaultdict(list)

    def save(self, device: DeviceRecord) -> None:
        """Store or update ``device``."""
        self._records[device.device_id] = device

    def get(self, device_id: str) -> DeviceRecord | None:
        """Retrieve record by device ID."""
        return self._records.get(device_id)

    def exists(self, device_id: str) -> bool:
        """Check presence of device ID."""
        return device_id in self._records

    def find_by_capture_id(self, capture_id: str) -> list[DeviceRecord]:
        """Find all devices originating from a specific capture/session ID."""
        return [
            rec for rec in self._records.values() if rec.capture_id == capture_id
        ]

    def list_all(self, limit: int = 100, offset: int = 0) -> list[DeviceRecord]:
        """List all stored devices with pagination."""
        records = list(self._records.values())
        return records[offset : offset + limit]

    def delete(self, device_id: str) -> bool:
        """Delete a record by device ID."""
        if device_id in self._records:
            del self._records[device_id]
            self._events.pop(device_id, None)
            return True
        return False

    def count(self) -> int:
        """Total number of stored devices."""
        return len(self._records)

    def append_event(self, event: DeviceEvent) -> None:
        """Append an event to the in-memory event log."""
        self._events[event.device_id].append(event)

    def list_events(self, device_id: str) -> list[DeviceEvent]:
        """List events sorted chronologically."""
        events = list(self._events.get(device_id, []))
        return sorted(events, key=lambda e: e.timestamp)

    def get_latest_event(self, device_id: str) -> DeviceEvent | None:
        """Return the most recent event for device_id."""
        events = self.list_events(device_id)
        return events[-1] if events else None

    def count_events(self, device_id: str | None = None) -> int:
        """Count events in memory."""
        if device_id is not None:
            return len(self._events.get(device_id, []))
        return sum(len(evts) for evts in self._events.values())


class JsonFileDeviceRepository:
    """Durable JSON repository persisting device records and event streams under a directory."""

    def __init__(self, store_dir: Path) -> None:
        self._store_dir = Path(store_dir)
        self._events_dir = self._store_dir / "events"

    @property
    def store_dir(self) -> Path:
        """Root storage directory."""
        return self._store_dir

    def _path_for(self, device_id: str) -> Path:
        """Return file path for a device ID."""
        safe_id = "".join(c for c in device_id if c.isalnum() or c in ("-", "_"))
        return self._store_dir / f"{safe_id}.json"

    def _events_path_for(self, device_id: str) -> Path:
        """Return JSONL file path for a device ID's event stream."""
        safe_id = "".join(c for c in device_id if c.isalnum() or c in ("-", "_"))
        return self._events_dir / f"{safe_id}.events.jsonl"

    def save(self, device: DeviceRecord) -> None:
        """Write device record as JSON document."""
        self._store_dir.mkdir(parents=True, exist_ok=True)
        path = self._path_for(device.device_id)
        path.write_text(json.dumps(device.to_dict(), indent=2), encoding="utf-8")

    def get(self, device_id: str) -> DeviceRecord | None:
        """Read and deserialize JSON record."""
        path = self._path_for(device_id)
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return DeviceRecord.from_dict(data)
        except Exception:
            return None

    def exists(self, device_id: str) -> bool:
        """Check if JSON record exists."""
        return self._path_for(device_id).is_file()

    def find_by_capture_id(self, capture_id: str) -> list[DeviceRecord]:
        """Scan directory and return all devices matching capture_id."""
        if not self._store_dir.is_dir():
            return []
        matches: list[DeviceRecord] = []
        for path in self._store_dir.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if data.get("capture_id") == capture_id:
                    matches.append(DeviceRecord.from_dict(data))
            except Exception:
                continue
        return matches

    def list_all(self, limit: int = 100, offset: int = 0) -> list[DeviceRecord]:
        """List paginated records from filesystem."""
        if not self._store_dir.is_dir():
            return []
        all_records: list[DeviceRecord] = []
        for path in sorted(self._store_dir.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                all_records.append(DeviceRecord.from_dict(data))
            except Exception:
                continue
        return all_records[offset : offset + limit]

    def delete(self, device_id: str) -> bool:
        """Delete JSON record file and corresponding event log."""
        deleted = False
        path = self._path_for(device_id)
        if path.is_file():
            path.unlink()
            deleted = True
        events_path = self._events_path_for(device_id)
        if events_path.is_file():
            events_path.unlink()
        return deleted

    def count(self) -> int:
        """Count JSON records in storage directory."""
        if not self._store_dir.is_dir():
            return 0
        return len(list(self._store_dir.glob("*.json")))

    def append_event(self, event: DeviceEvent) -> None:
        """Append an event to the JSONL event log for the device."""
        self._events_dir.mkdir(parents=True, exist_ok=True)
        path = self._events_path_for(event.device_id)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event.to_dict()) + "\n")

    def list_events(self, device_id: str) -> list[DeviceEvent]:
        """Read all events from the device's JSONL stream."""
        path = self._events_path_for(device_id)
        if not path.is_file():
            return []
        events: list[DeviceEvent] = []
        try:
            with path.open("r", encoding="utf-8") as f:
                for line in f:
                    line_str = line.strip()
                    if line_str:
                        events.append(DeviceEvent.from_dict(json.loads(line_str)))
        except Exception:
            return []
        return sorted(events, key=lambda e: e.timestamp)

    def get_latest_event(self, device_id: str) -> DeviceEvent | None:
        """Return the most recent event for device_id."""
        events = self.list_events(device_id)
        return events[-1] if events else None

    def count_events(self, device_id: str | None = None) -> int:
        """Count events in JSON storage."""
        if device_id is not None:
            return len(self.list_events(device_id))
        total = 0
        if self._events_dir.is_dir():
            for path in self._events_dir.glob("*.events.jsonl"):
                try:
                    with path.open("r", encoding="utf-8") as f:
                        total += sum(1 for line in f if line.strip())
                except Exception:
                    continue
        return total
