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

Sprint P4.1.2 adds four additive, composition-only collaborators for the
dataset-collection and annotation pipeline (they reuse the modules above and
modify none of them):

* **Provenance** (:mod:`~device_ai.dataset.provenance`) — source/license/
  contributor/date/checksum attribution layered over import.
* **Image validation** (:mod:`~device_ai.dataset.image_validation`) —
  structural image checks (extensions, resolution, aspect ratio, duplicate
  filenames/hashes).
* **Annotation statistics** (:mod:`~device_ai.dataset.annotation_statistics`) —
  class distribution, bounding-box geometry and annotation completeness.
* **Release** (:mod:`~device_ai.dataset.release`) — an enriched, auditable
  dataset release manifest composing a version with statistics, taxonomy
  version and split information.
"""

from __future__ import annotations

from .annotation_statistics import (
    AnnotationStatistics,
    AnnotationStatisticsCalculator,
    annotation_statistics_to_dict,
)
from .image_validation import (
    ImageValidationReport,
    ImageValidator,
    image_validation_to_dict,
)
from .provenance import (
    ProvenanceCollector,
    ProvenanceManifest,
    ProvenanceRecord,
    manifest_to_dict,
    provenance_to_dict,
)
from .release import DatasetRelease, build_release, release_to_dict
from .service import DatasetService
from .taxonomy import DeviceTaxonomy, load_taxonomy

__all__ = [
    "DatasetService",
    # Provenance (PART 1)
    "ProvenanceCollector",
    "ProvenanceManifest",
    "ProvenanceRecord",
    "provenance_to_dict",
    "manifest_to_dict",
    # Image validation (PART 2)
    "ImageValidator",
    "ImageValidationReport",
    "image_validation_to_dict",
    # Taxonomy + annotation statistics (PART 4)
    "DeviceTaxonomy",
    "load_taxonomy",
    "AnnotationStatistics",
    "AnnotationStatisticsCalculator",
    "annotation_statistics_to_dict",
    # Release manifest (PART 5)
    "DatasetRelease",
    "build_release",
    "release_to_dict",
]
