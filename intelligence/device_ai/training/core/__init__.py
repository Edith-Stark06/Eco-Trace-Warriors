"""Core training lifecycle for the platform (milestone M1.3).

This package is the reusable, model-agnostic heart of the training ecosystem:

* :mod:`~device_ai.training.core.trainer` — :class:`BaseTrainer`, the abstract
  training lifecycle (seed → epoch loop → callbacks → checkpoint → register),
  plus its :class:`TrainingHistory` result.
* :mod:`~device_ai.training.core.metrics` — pure-NumPy classification metrics
  and a :class:`MetricTracker`.
* :mod:`~device_ai.training.core.callbacks` — :class:`Callback` base and the
  :class:`EarlyStopping` / :class:`ModelCheckpoint` / :class:`LoggingCallback`
  implementations.
* :mod:`~device_ai.training.core.registry` — :class:`TrainerRegistry`, the
  name → trainer-class decorator registry.
* :mod:`~device_ai.training.core.exporter` — import-guarded PyTorch / TorchScript
  / ONNX exporters returning :class:`ExportRecord` outcomes.
* :mod:`~device_ai.training.core.evaluator` — :class:`Evaluator` producing
  JSON + self-contained HTML evaluation reports.

No concrete trainer is implemented here (M1.3 builds the ecosystem, not models).
"""

from __future__ import annotations

from .callbacks import (
    Callback,
    CallbackList,
    EarlyStopping,
    LoggingCallback,
    ModelCheckpoint,
    TrainerState,
)
from .evaluator import Evaluator, build_evaluation_document
from .exporter import (
    ExportPlan,
    ExportRecord,
    ModelExporter,
    OnnxExporter,
    PyTorchExporter,
    SkippedExport,
    TorchScriptExporter,
    export_model,
    get_exporter,
)
from .metrics import (
    MetricTracker,
    accuracy,
    classification_metrics,
    confusion_matrix,
    f1_score,
    mean_average_precision,
    precision_recall_f1,
    precision_score,
    recall_score,
)
from .registry import TrainerRegistry, default_registry
from .trainer import BaseTrainer, EpochResult, TrainingHistory

__all__ = [
    "BaseTrainer",
    "Callback",
    "CallbackList",
    "EarlyStopping",
    "Evaluator",
    "EpochResult",
    "ExportPlan",
    "ExportRecord",
    "LoggingCallback",
    "MetricTracker",
    "ModelCheckpoint",
    "ModelExporter",
    "OnnxExporter",
    "PyTorchExporter",
    "SkippedExport",
    "TorchScriptExporter",
    "TrainerRegistry",
    "TrainerState",
    "TrainingHistory",
    "accuracy",
    "build_evaluation_document",
    "classification_metrics",
    "confusion_matrix",
    "default_registry",
    "export_model",
    "f1_score",
    "get_exporter",
    "mean_average_precision",
    "precision_recall_f1",
    "precision_score",
    "recall_score",
]
