"""Persistence layer abstraction for EcoTrace Device records (P5.2).

Follows the repository pattern established in ``device_ai.fingerprint.repository``.
Decouples domain models and API handlers from concrete storage engines.

Provides:
- :class:`DeviceRepository`: Storage-agnostic Protocol interface.
- :class:`InMemoryDeviceRepository`: Fast, thread-safe in-memory store for testing and runtime default.
- :class:`JsonFileDeviceRepository`: Durable JSON filesystem store.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol, runtime_checkable

from .models import DeviceRecord


@runtime_checkable
class DeviceRepository(Protocol):
    """Storage-agnostic persistence contract for DeviceRecord entities."""

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


class InMemoryDeviceRepository:
    """Non-durable, thread-safe in-memory repository backed by a dictionary."""

    def __init__(self) -> None:
        self._records: dict[str, DeviceRecord] = {}

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
            return True
        return False

    def count(self) -> int:
        """Total number of stored devices."""
        return len(self._records)


class JsonFileDeviceRepository:
    """Durable JSON repository persisting one document per device under a directory."""

    def __init__(self, store_dir: Path) -> None:
        self._store_dir = Path(store_dir)

    @property
    def store_dir(self) -> Path:
        """Root storage directory."""
        return self._store_dir

    def _path_for(self, device_id: str) -> Path:
        """Return file path for a device ID."""
        # Sanitize filename
        safe_id = "".join(c for c in device_id if c.isalnum() or c in ("-", "_"))
        return self._store_dir / f"{safe_id}.json"

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
        """Delete JSON record file."""
        path = self._path_for(device_id)
        if path.is_file():
            path.unlink()
            return True
        return False

    def count(self) -> int:
        """Count JSON records in storage directory."""
        if not self._store_dir.is_dir():
            return 0
        return len(list(self._store_dir.glob("*.json")))
