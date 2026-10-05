"""Fingerprint persistence abstraction (milestone M1.5).

The fingerprinting service depends only on the :class:`FingerprintRepository`
*protocol*, never on a concrete store — so the storage medium (in-memory, a
JSON file tree, a future vector database or blockchain anchor) can change
without touching the domain or API layers (``CLAUDE.md`` → "persistence
abstraction; do not tightly couple to storage").

Two implementations ship with M1.5:

* :class:`InMemoryFingerprintRepository` — process-local dict; the default and
  the one used throughout the test suite.
* :class:`JsonFileFingerprintRepository` — one JSON document per EcoID under a
  configured directory; durable across restarts and human-inspectable.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol, runtime_checkable

from ..exceptions import FingerprintError
from .models import DeviceFingerprint


@runtime_checkable
class FingerprintRepository(Protocol):
    """Storage-agnostic persistence contract for fingerprints.

    Implementations must be safe to call with unknown EcoIDs: :meth:`get`
    returns ``None`` rather than raising when a record is absent.
    """

    def save(self, fingerprint: DeviceFingerprint) -> None:
        """Persist ``fingerprint``, replacing any record with the same EcoID."""
        ...

    def get(self, eco_id: str) -> DeviceFingerprint | None:
        """Return the fingerprint for ``eco_id``, or ``None`` if absent."""
        ...

    def exists(self, eco_id: str) -> bool:
        """Return whether a fingerprint is stored for ``eco_id``."""
        ...

    def list_ids(self) -> list[str]:
        """Return all stored EcoIDs (order is not guaranteed)."""
        ...


class InMemoryFingerprintRepository:
    """Non-durable, process-local fingerprint store backed by a dict.

    Suitable for tests, demos and the default runtime backend. Records are
    lost when the process exits.
    """

    def __init__(self) -> None:
        self._store: dict[str, DeviceFingerprint] = {}

    def save(self, fingerprint: DeviceFingerprint) -> None:
        """Store ``fingerprint`` keyed by its EcoID (last write wins)."""
        self._store[fingerprint.eco_id] = fingerprint

    def get(self, eco_id: str) -> DeviceFingerprint | None:
        """Return the fingerprint for ``eco_id``, or ``None`` if absent."""
        return self._store.get(eco_id)

    def exists(self, eco_id: str) -> bool:
        """Return whether a fingerprint is stored for ``eco_id``."""
        return eco_id in self._store

    def list_ids(self) -> list[str]:
        """Return all stored EcoIDs."""
        return list(self._store)


class JsonFileFingerprintRepository:
    """Durable fingerprint store persisting one JSON file per EcoID.

    Files are written as ``<store_dir>/<eco_id>.json``. The directory is
    created lazily on first write so pointing at a fresh path just works.

    Args:
        store_dir: Directory under which per-EcoID JSON records are kept.
    """

    def __init__(self, store_dir: Path) -> None:
        self._store_dir = store_dir

    @property
    def store_dir(self) -> Path:
        """The directory backing this repository."""
        return self._store_dir

    def _path_for(self, eco_id: str) -> Path:
        """Return the JSON file path for ``eco_id``.

        Raises:
            FingerprintError: If ``eco_id`` contains path separators (which
                could escape the store directory).
        """
        if "/" in eco_id or "\\" in eco_id or eco_id in {"", ".", ".."}:
            raise FingerprintError(
                "Invalid EcoID for persistence.",
                details={"eco_id": eco_id},
            )
        return self._store_dir / f"{eco_id}.json"

    def save(self, fingerprint: DeviceFingerprint) -> None:
        """Write ``fingerprint`` as a JSON document (overwriting if present)."""
        self._store_dir.mkdir(parents=True, exist_ok=True)
        path = self._path_for(fingerprint.eco_id)
        path.write_text(
            json.dumps(fingerprint.to_dict(), indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def get(self, eco_id: str) -> DeviceFingerprint | None:
        """Return the fingerprint for ``eco_id``, or ``None`` if absent."""
        path = self._path_for(eco_id)
        if not path.is_file():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return DeviceFingerprint.from_dict(data)

    def exists(self, eco_id: str) -> bool:
        """Return whether a fingerprint file exists for ``eco_id``."""
        return self._path_for(eco_id).is_file()

    def list_ids(self) -> list[str]:
        """Return the EcoIDs of every stored JSON record."""
        if not self._store_dir.is_dir():
            return []
        return [path.stem for path in self._store_dir.glob("*.json")]
