"""Experiment tracking for the training platform (M1.3).

Exposes the tracking protocol and its light-weight default backends:

* :class:`~device_ai.training.experiments.tracker.ExperimentTracker` /
  ``RunHandle`` — the protocol trainers program against.
* :class:`~device_ai.training.experiments.tracker.JsonExperimentTracker` —
  default backend writing JSON run directories under ``MLRUNS_DIR``.
* :class:`~device_ai.training.experiments.tracker.NullTracker` — disables
  tracking.
* :func:`~device_ai.training.experiments.tracker.build_tracker` — selects a
  backend from settings, falling back from MLflow to JSON when the optional
  MLflow dependency is absent.
"""

from __future__ import annotations

from .mlflow import mlflow_available
from .tracker import (
    ExperimentTracker,
    JsonExperimentTracker,
    NullTracker,
    RunHandle,
    build_tracker,
)

__all__ = [
    "ExperimentTracker",
    "JsonExperimentTracker",
    "NullTracker",
    "RunHandle",
    "build_tracker",
    "mlflow_available",
]
