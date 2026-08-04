"""Material Intelligence Engine (milestone M1.10).

An internal-only, deterministic engine that turns a fused
:class:`~device_ai.fusion.models.DeviceContext`, its
:class:`~device_ai.recoverability.models.RecoverabilityReport` and its
:class:`~device_ai.components.models.ComponentReport` into an explainable
:class:`MaterialReport`: the recoverable and hazardous materials the device is
made of, each with an estimated mass and confidence, plus recoverable/hazardous
weight totals and ordered reasoning/warnings.

The engine mirrors the M1.9 component engine: its material knowledge lives in an
external, versioned YAML/JSON catalogue (loaded by a strict validating loader),
its numeric behaviour lives in an immutable config, and its service is fully
injectable. There is no HTTP surface — orchestrating code consumes the
:class:`MaterialReport` directly.
"""

from __future__ import annotations

from .config import DEFAULT_PROFILES_PATH, MaterialConfig
from .inference import MaterialInferenceEngine
from .models import MaterialCategory, MaterialReport, RecoveredMaterial
from .profiles import (
    MaterialProfile,
    MaterialProfileLibrary,
    MaterialSpec,
    load_library,
)
from .service import MATERIAL_ENGINE_VERSION, MaterialService

__all__ = [
    "DEFAULT_PROFILES_PATH",
    "MATERIAL_ENGINE_VERSION",
    "MaterialCategory",
    "MaterialConfig",
    "MaterialInferenceEngine",
    "MaterialProfile",
    "MaterialProfileLibrary",
    "MaterialReport",
    "MaterialService",
    "MaterialSpec",
    "RecoveredMaterial",
    "load_library",
]
