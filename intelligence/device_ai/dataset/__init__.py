"""Dataset intelligence pipeline (milestone M1.2).

A modular, production-grade toolkit for **dataset engineering** — the stage
that precedes any model training. It provides:

* **Import** — ingest and de-duplicate source images into a managed tree.
* **Metadata** — per-image quality metrics (blur, brightness, resolution,
  corruption) and content/perceptual hashes.
* **Duplicates** — exact (SHA-256) and near-duplicate (aHash/dHash/pHash)
  detection.
* **Annotations** — YOLO label parsing and validation.
* **Splitting** — deterministic train/val/test partitioning.
* **Augmentation** — offline, label-aware image augmentation.
* **Export** — YOLO, COCO and Pascal VOC layouts.
* **Statistics & reporting** — aggregate stats plus JSON/HTML reports.
* **Versioning** — immutable, content-addressed dataset snapshots.

Every component is independently testable and free of HTTP concerns; the
:class:`~device_ai.dataset.service.DatasetService` facade composes them for
the API layer. No model training or inference happens here.
"""

from __future__ import annotations

from .service import DatasetService

__all__ = ["DatasetService"]
