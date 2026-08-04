"""AI training & MLOps platform for the Device Intelligence Engine (M1.3).

This package provides the reusable training *ecosystem* that every future
model (YOLO detector, CLIP encoder, OCR, condition classifier, material
estimator, carbon intelligence) plugs into. It contains **no** model
implementations of its own; instead it offers:

* :mod:`device_ai.training.config` — typed run configuration + loaders.
* :mod:`device_ai.training.core` — abstract trainer, evaluator, exporter,
  metrics, callbacks and the trainer registry.
* :mod:`device_ai.training.experiments` — pluggable experiment trackers.
* :mod:`device_ai.training.registry` — the JSON-backed model registry and
  artifact manager.
* :mod:`device_ai.training.utils` — small, dependency-injected helpers
  (git metadata, RNG seeding, timing, environment capture).

Heavy third-party libraries (PyTorch, ONNX, Hydra, MLflow) are optional and
accessed behind import guards so the full platform — and its test suite —
runs in the lightweight base environment.
"""

from __future__ import annotations

from device_ai.training.config import (
    OptimizerConfig,
    RunConfig,
    TrainingConfig,
    load_config,
)

__all__ = [
    "OptimizerConfig",
    "RunConfig",
    "TrainingConfig",
    "load_config",
]
