"""Real device-detection trainer for the platform (milestone M1.4).

This package plugs the first *real* trainer into the M1.3 training platform: an
Ultralytics YOLO detector. It **reuses** the platform end to end rather than
re-implementing any of it —

* :class:`~device_ai.training.detector.yolo_trainer.YOLOTrainer` overrides
  :meth:`~device_ai.training.core.trainer.BaseTrainer.fit` to delegate the epoch
  loop (resume, early-stopping, checkpointing, MLflow logging) to Ultralytics,
  while reusing the platform's :class:`ArtifactManager`, :class:`ModelRegistry`,
  :class:`ExperimentTracker` and :class:`ExportRecord` for provenance.
* :class:`~device_ai.training.detector.evaluation.DetectionEvaluator` adapts an
  Ultralytics ``model.val()`` result onto the shared
  :func:`~device_ai.training.core.evaluator.build_evaluation_document` and
  :class:`~device_ai.training.core.evaluator.Evaluator`, producing the same
  JSON + HTML reports (mAP / precision / recall / F1 / confusion matrix).

Importing this package registers the trainer under the key ``"yolo"`` on
:data:`~device_ai.training.core.registry.default_registry`, so a run config with
``trainer: yolo`` resolves to :class:`YOLOTrainer`. The training CLI imports this
package before resolving a trainer so the registration is always in effect.
"""

from __future__ import annotations

from .evaluation import (
    DetectionEvaluator,
    extract_confusion,
    extract_metrics,
    names_to_list,
)
from .yolo_trainer import YOLOTrainer

__all__ = [
    "DetectionEvaluator",
    "YOLOTrainer",
    "extract_confusion",
    "extract_metrics",
    "names_to_list",
]
