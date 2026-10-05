"""Content-addressed dataset versioning.

:class:`DatasetVersionManager` records immutable snapshots of a dataset. A
snapshot captures a manifest of ``relative_path`` → ``sha256`` for every
image plus an aggregate ``content_hash`` over that sorted manifest, so two
snapshots are identical iff their image contents are identical.

Versions are persisted as JSON documents under the ``metadata`` sub-folder
(``versions.json``). Version labels are monotonic (``v1``, ``v2``, …).
Timestamps are injected rather than read from the wall clock so snapshots are
reproducible in tests.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import cast

from .hashing import sha256_hash
from .records import DatasetVersion, ImageRecord

# File (under the metadata dir) holding the ordered list of versions.
_VERSIONS_FILE = "versions.json"


def compute_content_hash(manifest: dict[str, str]) -> str:
    """Return an aggregate SHA-256 over a sorted path→hash manifest.

    Args:
        manifest: Mapping of relative path → per-image SHA-256.

    Returns:
        A hex digest identifying the manifest's content.
    """
    payload = "\n".join(f"{path}:{digest}" for path, digest in sorted(manifest.items()))
    return sha256_hash(payload.encode("utf-8"))


def version_to_dict(version: DatasetVersion) -> dict[str, object]:
    """Convert a :class:`DatasetVersion` into a JSON-serialisable dict.

    Args:
        version: The version to serialise.

    Returns:
        A primitive-only mapping.
    """
    return {
        "version": version.version,
        "created_at": version.created_at,
        "image_count": version.image_count,
        "content_hash": version.content_hash,
        "note": version.note,
        "manifest": version.manifest,
    }


def version_from_dict(data: dict[str, object]) -> DatasetVersion:
    """Reconstruct a :class:`DatasetVersion` from a serialised mapping.

    Args:
        data: A mapping previously produced by :func:`version_to_dict`.

    Returns:
        The reconstructed :class:`DatasetVersion`.
    """
    return DatasetVersion(
        version=str(data["version"]),
        created_at=str(data["created_at"]),
        image_count=int(cast(int, data["image_count"])),
        content_hash=str(data["content_hash"]),
        note=str(data.get("note", "")),
        manifest=dict(cast("dict[str, str]", data.get("manifest", {}))),
    )


class DatasetVersionManager:
    """Create and persist immutable dataset snapshots.

    Args:
        metadata_dir: Directory under which ``versions.json`` is stored.
    """

    def __init__(self, metadata_dir: Path) -> None:
        self._metadata_dir = metadata_dir
        self._store = metadata_dir / _VERSIONS_FILE

    def _load(self) -> list[DatasetVersion]:
        """Load persisted versions (empty when none exist)."""
        if not self._store.exists():
            return []
        raw = json.loads(self._store.read_text(encoding="utf-8"))
        return [version_from_dict(item) for item in raw]

    def _save(self, versions: list[DatasetVersion]) -> None:
        """Persist the ordered version list to disk."""
        self._metadata_dir.mkdir(parents=True, exist_ok=True)
        payload = [version_to_dict(version) for version in versions]
        self._store.write_text(
            json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
        )

    def list_versions(self) -> list[DatasetVersion]:
        """Return all recorded versions in creation order.

        Returns:
            The persisted versions (possibly empty).
        """
        return self._load()

    def latest(self) -> DatasetVersion | None:
        """Return the most recent version, or ``None`` when none exist."""
        versions = self._load()
        return versions[-1] if versions else None

    def create_version(
        self,
        records: list[ImageRecord],
        *,
        created_at: datetime,
        note: str = "",
    ) -> DatasetVersion:
        """Record a new immutable snapshot from analysed records.

        The next monotonic label (``v<N+1>``) is assigned automatically.

        Args:
            records: Analysed image records forming the snapshot.
            created_at: Timestamp to embed (injected for reproducibility).
            note: Optional human-readable description.

        Returns:
            The newly created :class:`DatasetVersion`.
        """
        versions = self._load()
        manifest = {record.relative_path: record.hashes.sha256 for record in records}
        version = DatasetVersion(
            version=f"v{len(versions) + 1}",
            created_at=created_at.isoformat(),
            image_count=len(records),
            content_hash=compute_content_hash(manifest),
            note=note,
            manifest=dict(sorted(manifest.items())),
        )
        versions.append(version)
        self._save(versions)
        return version
