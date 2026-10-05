"""Component Intelligence Engine (milestone M1.9).

Turns the immutable :class:`~device_ai.fusion.models.DeviceContext` produced by
the fusion engine (M1.7) and the
:class:`~device_ai.recoverability.models.RecoverabilityReport` produced by the
recoverability engine (M1.8) into an explainable
:class:`~device_ai.components.models.ComponentReport`: the likely internal
electronic components of the device, each with a presence confidence, plus a
single overall confidence and ordered human-readable reasoning.

The engine is **deterministic and explainable** — no learned models, no material
or carbon estimation, no blockchain or passport — so it runs in the base
environment with zero weights:

* **External profiles** — the component catalogue is stored *outside* the code as
  a versioned YAML/JSON file (``components/data/components.yaml``), loaded and
  validated by :func:`~device_ai.components.profiles.load_library`. This is the
  deliberate M1.9 departure from M1.8's in-code table: the catalogue is data, so
  it is reviewed and extended without a code change.
* **Inference** — :class:`~device_ai.components.inference.ComponentInferenceEngine`
  starts each component at its catalogue prior and adjusts it with explicit,
  bounded corroboration from the fused identity and the recoverability hazard.
* **Service** — :class:`~device_ai.components.service.ComponentService` wires the
  library + inference into :meth:`analyze
  <device_ai.components.service.ComponentService.analyze>`.

The engine is **internal-only**: it exposes no endpoints and does not touch the
frozen ``/predict`` contract. It is imported directly by the orchestrating code.
"""

from __future__ import annotations

from .config import DEFAULT_PROFILES_PATH, ComponentConfig
from .inference import ComponentInferenceEngine
from .models import ComponentCategory, ComponentReport, InferredComponent
from .profiles import (
    ComponentProfile,
    ComponentProfileLibrary,
    ComponentSpec,
    load_library,
)
from .service import COMPONENT_ENGINE_VERSION, ComponentService

__all__ = [
    "COMPONENT_ENGINE_VERSION",
    "DEFAULT_PROFILES_PATH",
    "ComponentCategory",
    "ComponentConfig",
    "ComponentInferenceEngine",
    "ComponentProfile",
    "ComponentProfileLibrary",
    "ComponentReport",
    "ComponentService",
    "ComponentSpec",
    "InferredComponent",
    "load_library",
]
