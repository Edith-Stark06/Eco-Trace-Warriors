"""Multi-modal device intelligence fusion engine (milestone M1.7).

Merges the outputs of the independent AI modules — **detection**,
**fingerprint** and **OCR** — into a single, normalized, **immutable**
:class:`~device_ai.fusion.models.DeviceContext` that downstream AI modules
(recoverability, material, carbon, passport) consume instead of reaching back
into each module individually.

The engine builds directly on the existing module contracts and reuses their
frozen result value objects — it duplicates none of their logic:

* **Evidence** — :class:`~device_ai.fusion.models.Evidence` is what each module
  contributes; its builders (``from_detection`` / ``from_fingerprint`` /
  ``from_ocr`` / ``from_ocr_identity``) map a module's native fields onto the
  shared :class:`~device_ai.fusion.models.FusionAttribute` space.
* **Fusion** — :class:`~device_ai.fusion.engine.FusionEngine` aggregates
  heterogeneous evidence with a noisy-OR (agreement raises confidence),
  detects cross-module :class:`~device_ai.fusion.models.Conflict` s, and
  normalizes everything into the ``DeviceContext``.

The engine is **internal-only**: it exposes no endpoints and does not touch the
frozen ``/predict`` contract. It is imported directly by the orchestrating code.
"""

from __future__ import annotations

from .engine import FUSION_ENGINE_VERSION, FusionEngine
from .models import (
    Claim,
    Conflict,
    DeviceContext,
    Evidence,
    EvidenceKind,
    FusionAttribute,
    ResolvedAttribute,
)

__all__ = [
    "FUSION_ENGINE_VERSION",
    "Claim",
    "Conflict",
    "DeviceContext",
    "Evidence",
    "EvidenceKind",
    "FusionAttribute",
    "FusionEngine",
    "ResolvedAttribute",
]
