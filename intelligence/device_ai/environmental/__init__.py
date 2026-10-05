"""Environmental Intelligence Engine (milestone M1.11).

An internal-only, deterministic engine that turns a fused
:class:`~device_ai.fusion.models.DeviceContext`, its
:class:`~device_ai.recoverability.models.RecoverabilityReport`, its
:class:`~device_ai.components.models.ComponentReport` and its
:class:`~device_ai.materials.models.MaterialReport` into an explainable
:class:`EnvironmentalImpactReport`: the avoided environmental burden of
recovering the device (carbon, energy and water saved, landfill diverted,
critical materials recovered) plus a circularity index and a hazard-reduction
score, with confidence kept on a wholly separate axis.

The engine mirrors the M1.10 material engine: its conversion-factor knowledge
lives in an external, versioned YAML/JSON catalogue (loaded by a strict
validating loader), its numeric behaviour lives in an immutable config, and its
service is fully injectable. There is no HTTP surface — orchestrating code
consumes the :class:`EnvironmentalImpactReport` directly.
"""

from __future__ import annotations

from .config import DEFAULT_FACTORS_PATH, EnvironmentalConfig
from .factors import FactorLibrary, MaterialFactor, load_library
from .inference import EnvironmentalInferenceEngine
from .models import EnvironmentalImpactReport, MaterialContribution
from .service import ENVIRONMENTAL_ENGINE_VERSION, EnvironmentalService

__all__ = [
    "DEFAULT_FACTORS_PATH",
    "ENVIRONMENTAL_ENGINE_VERSION",
    "EnvironmentalConfig",
    "EnvironmentalImpactReport",
    "EnvironmentalInferenceEngine",
    "EnvironmentalService",
    "FactorLibrary",
    "MaterialContribution",
    "MaterialFactor",
    "load_library",
]
