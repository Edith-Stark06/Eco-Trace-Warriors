"""Automated single-class dataset acquisition (Sprint P4.3.7).

A production-grade, offline-capable pipeline that acquires bounding-box
detection data for a single taxonomy class (initially ``router``, id 11) and
runs it through the *existing, frozen* dataset-intelligence gates without
modifying any of them:

    discover -> license gate -> semantic gate -> acquire/ingest ->
    provenance -> Gate A (image validation) -> Gate B (annotation validation)
    -> frozen deduplication -> automated QA -> deterministic split ->
    readiness audit -> report.

Design principles honoured here:

* **Never fabricate.** No image, label, count, license, or provenance value is
  ever invented. When no real source is available the pipeline reports
  ``BLOCKED_NO_SOURCE`` and stops.
* **Fail closed.** License and semantic gates reject on any ambiguity; remote
  adapters raise :class:`~device_ai.acquisition.adapters.base.AdapterUnavailable`
  when credentials or network are missing rather than guessing.
* **Frozen components are reused, never modified.** Deduplication threshold,
  hashing, split ratios/seed and the readiness gates are imported and called
  as-is.

The heavy dataset components (Pillow/numpy/pydantic-backed) are imported
*lazily* inside the pipeline stage methods, so the gate/adapter/format modules
stay import-light and independently unit-testable.
"""

from __future__ import annotations

from .config import (
    EXPECTED_CLASS_ID,
    EXPECTED_NUM_CLASSES,
    EXPECTED_SPLIT_RATIOS,
    EXPECTED_SPLIT_SEED,
    EXPECTED_TAXONOMY_VERSION,
    TARGET_CLASS_NAME,
    AcquisitionConfig,
    TargetClass,
)
from .gates import SourceVerdict, verify_source
from .pipeline import (
    MODE_AUTO,
    MODE_OFFLINE,
    MODE_ONLINE,
    LocalSourceSpec,
    RunResult,
    run_pipeline,
)
from .preflight import PreflightResult, run_preflight
from .promotion import PromotionDecision, evaluate_promotion
from .semantics import (
    TargetSemantics,
    build_target_semantics,
    evaluate_label,
    evaluate_source_label,
)

__all__ = [
    "AcquisitionConfig",
    "TargetClass",
    "TARGET_CLASS_NAME",
    "EXPECTED_CLASS_ID",
    "EXPECTED_NUM_CLASSES",
    "EXPECTED_TAXONOMY_VERSION",
    "EXPECTED_SPLIT_RATIOS",
    "EXPECTED_SPLIT_SEED",
    "PreflightResult",
    "run_preflight",
    "SourceVerdict",
    "verify_source",
    "TargetSemantics",
    "build_target_semantics",
    "evaluate_label",
    "evaluate_source_label",
    "PromotionDecision",
    "evaluate_promotion",
    "LocalSourceSpec",
    "RunResult",
    "run_pipeline",
    "MODE_AUTO",
    "MODE_ONLINE",
    "MODE_OFFLINE",
]
