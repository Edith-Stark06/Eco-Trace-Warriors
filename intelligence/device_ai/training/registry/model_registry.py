"""JSON-backed model registry for the training platform (milestone M1.3).

:class:`ModelRegistry` records an immutable :class:`ModelRecord` for every model
a trainer produces. A record captures the full provenance of an artifact — model
name and version, the dataset version it was trained on, a timestamp, the Git
commit, the achieved metrics, the framework, the available export formats and
the on-disk artifact location — so any produced model can be traced back to the
exact code and data that created it.

Records are persisted as a single JSON document (``model_registry.json``) under
the artifact root. Timestamps and Git commits are *injected* by the caller
rather than read from the wall clock / subprocess here, keeping the registry a
pure, reproducible store (mirroring :class:`DatasetVersionManager`).

Nothing here trains or loads a model; it only records metadata about produced
artifacts.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from ...exceptions import ModelNotFoundError, ModelRegistryError

#: File (under the artifact root) holding the ordered list of model records.
_REGISTRY_FILE = "model_registry.json"


@dataclass(frozen=True, slots=True)
class ModelRecord:
    """Immutable provenance record for one produced model artifact.

    Attributes:
        name: Logical model name (registry key, e.g. ``"device-detector"``).
        version: Semantic version tag of this artifact (e.g. ``"1.0.0"``).
        dataset_version: Dataset snapshot label the model was trained on.
        created_at: ISO-8601 UTC timestamp of registration.
        git_commit: Short Git commit hash of the training code (or
            ``"unknown"``).
        framework: Training framework identifier (e.g. ``"mock"``, ``"torch"``).
        metrics: Achieved evaluation metrics (metric name → value).
        export_formats: Export formats available for this artifact (e.g.
            ``("pytorch", "onnx")``).
        artifact_location: POSIX path of the produced artifact (checkpoint).
        tags: Free-form string metadata copied from the run configuration.
    """

    name: str
    version: str
    dataset_version: str
    created_at: str
    git_commit: str
    framework: str
    metrics: dict[str, float] = field(default_factory=dict)
    export_formats: tuple[str, ...] = ()
    artifact_location: str = ""
    tags: dict[str, str] = field(default_factory=dict)

    @property
    def key(self) -> str:
        """The ``name:version`` identity used to look the record up."""
        return f"{self.name}:{self.version}"


def record_to_dict(record: ModelRecord) -> dict[str, Any]:
    """Convert a :class:`ModelRecord` into a JSON-serialisable mapping.

    Args:
        record: The record to serialise.

    Returns:
        A primitive-only mapping.
    """
    return {
        "name": record.name,
        "version": record.version,
        "dataset_version": record.dataset_version,
        "created_at": record.created_at,
        "git_commit": record.git_commit,
        "framework": record.framework,
        "metrics": dict(record.metrics),
        "export_formats": list(record.export_formats),
        "artifact_location": record.artifact_location,
        "tags": dict(record.tags),
    }


def record_from_dict(data: dict[str, Any]) -> ModelRecord:
    """Reconstruct a :class:`ModelRecord` from a serialised mapping.

    Args:
        data: A mapping previously produced by :func:`record_to_dict`.

    Returns:
        The reconstructed :class:`ModelRecord`.
    """
    return ModelRecord(
        name=str(data["name"]),
        version=str(data["version"]),
        dataset_version=str(data.get("dataset_version", "")),
        created_at=str(data.get("created_at", "")),
        git_commit=str(data.get("git_commit", "unknown")),
        framework=str(data.get("framework", "")),
        metrics=dict(cast("dict[str, float]", data.get("metrics", {}))),
        export_formats=tuple(data.get("export_formats", ())),
        artifact_location=str(data.get("artifact_location", "")),
        tags=dict(cast("dict[str, str]", data.get("tags", {}))),
    )


class ModelRegistry:
    """Create, persist and query immutable model provenance records.

    The registry is a thin JSON store: newest registrations are appended, and
    lookups resolve either an explicit ``name:version`` or the latest version of
    a name. It performs no training and holds no model weights.

    Args:
        registry_path: Path of the JSON document backing the registry.
    """

    def __init__(self, registry_path: Path) -> None:
        self._path = registry_path

    @classmethod
    def from_settings(cls, settings: Any) -> ModelRegistry:
        """Build a registry rooted at ``settings.artifact_dir``.

        Args:
            settings: Application settings supplying ``artifact_dir``.

        Returns:
            A :class:`ModelRegistry` backed by
            ``<artifact_dir>/model_registry.json``.
        """
        return cls(Path(settings.artifact_dir) / _REGISTRY_FILE)

    def _load(self) -> list[ModelRecord]:
        """Load persisted records (empty when the store does not yet exist)."""
        if not self._path.exists():
            return []
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ModelRegistryError(
                f"Failed to read model registry '{self._path}': {exc}",
                details={"path": str(self._path)},
            ) from exc
        if not isinstance(raw, list):
            raise ModelRegistryError(
                f"Model registry root must be a list: {self._path}",
                details={"path": str(self._path)},
            )
        return [record_from_dict(item) for item in raw]

    def _save(self, records: list[ModelRecord]) -> None:
        """Persist the ordered record list to disk (creating parents)."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = [record_to_dict(record) for record in records]
        self._path.write_text(
            json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
        )

    def register(self, record: ModelRecord) -> ModelRecord:
        """Append a new provenance record to the registry.

        Args:
            record: The fully-populated record to store.

        Returns:
            The registered record (unchanged), for chaining.
        """
        records = self._load()
        records.append(record)
        self._save(records)
        return record

    def list_models(self) -> list[ModelRecord]:
        """Return every recorded model in registration order.

        Returns:
            The persisted records (possibly empty).
        """
        return self._load()

    def versions(self, name: str) -> list[ModelRecord]:
        """Return all records for a model name in registration order.

        Args:
            name: Logical model name.

        Returns:
            The matching records (possibly empty).
        """
        return [record for record in self._load() if record.name == name]

    def latest(self, name: str) -> ModelRecord | None:
        """Return the most recently registered record for ``name``.

        Args:
            name: Logical model name.

        Returns:
            The newest matching record, or ``None`` when none exist.
        """
        matches = self.versions(name)
        return matches[-1] if matches else None

    def get(self, name: str, version: str) -> ModelRecord:
        """Return the record for an exact ``name`` / ``version`` pair.

        Args:
            name: Logical model name.
            version: Exact artifact version.

        Returns:
            The matching :class:`ModelRecord`.

        Raises:
            ModelNotFoundError: If no record matches.
        """
        for record in self._load():
            if record.name == name and record.version == version:
                return record
        raise ModelNotFoundError(
            f"No model registered as '{name}:{version}'.",
            details={"name": name, "version": version},
        )

    def resolve(self, name: str, version: str = "latest") -> ModelRecord:
        """Return a record by name and version, resolving ``"latest"``.

        Args:
            name: Logical model name.
            version: Exact version, or ``"latest"`` for the newest record.

        Returns:
            The resolved :class:`ModelRecord`.

        Raises:
            ModelNotFoundError: If the name (or exact version) is unknown.
        """
        if version == "latest":
            record = self.latest(name)
            if record is None:
                raise ModelNotFoundError(
                    f"No versions registered for model '{name}'.",
                    details={"name": name},
                )
            return record
        return self.get(name, version)
