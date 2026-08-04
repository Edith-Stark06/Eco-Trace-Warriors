"""Model registry and artifact layout for the training platform (M1.3).

This package provides the two persistence-facing collaborators of the training
lifecycle:

* :class:`~device_ai.training.registry.artifact_manager.ArtifactManager` —
  resolves and creates the ``checkpoints`` / ``exports`` / ``reports`` tree
  under ``ARTIFACT_DIR`` (mirroring the dataset layout).
* :class:`~device_ai.training.registry.model_registry.ModelRegistry` — a
  JSON-backed catalogue of ``ModelRecord`` provenance entries for every
  produced artifact.

Both are pure filesystem/JSON collaborators; neither trains or loads a model.
"""

from __future__ import annotations

from .artifact_manager import ArtifactManager
from .model_registry import (
    ModelRecord,
    ModelRegistry,
    record_from_dict,
    record_to_dict,
)

__all__ = [
    "ArtifactManager",
    "ModelRecord",
    "ModelRegistry",
    "record_from_dict",
    "record_to_dict",
]
