"""Inference layer: pluggable model interfaces and the prediction pipeline."""

from __future__ import annotations

from .class_map import CANONICAL_CLASSES, CLASS_NAME_TO_ID, NUM_CLASSES
from .ensemble_detector import EnsembleDetector
from .wbf import box_iou, weighted_box_fusion
from .yolo_detector import YOLODetector

__all__ = [
    "CANONICAL_CLASSES",
    "CLASS_NAME_TO_ID",
    "NUM_CLASSES",
    "EnsembleDetector",
    "YOLODetector",
    "box_iou",
    "weighted_box_fusion",
]
