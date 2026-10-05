"""Environmental intelligence service (milestone M1.11).

The thin, injectable façade over the environmental engine: it owns the loaded
conversion-factor catalogue and the inference engine, and stamps provenance
(engine/catalogue versions and an optional timestamp) onto every
:class:`~device_ai.environmental.models.EnvironmentalImpactReport`.

Like the material service it mirrors, every collaborator is constructor-injected
with a sensible default, so production wires nothing while tests can inject a
hand-built library, a fixed clock or a custom config. The catalogue is loaded
exactly once, at construction, and held immutably.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from .config import EnvironmentalConfig
from .factors import FactorLibrary, load_library
from .inference import EnvironmentalInferenceEngine

if TYPE_CHECKING:
    from ..components.models import ComponentReport
    from ..fusion.models import DeviceContext
    from ..materials.models import MaterialReport
    from ..recoverability.models import RecoverabilityReport
    from .models import EnvironmentalImpactReport

#: Version tag stamped onto every produced :class:`EnvironmentalImpactReport`.
ENVIRONMENTAL_ENGINE_VERSION = "1.0.0"

#: The ``device_ai`` package root, used to resolve a relative catalogue path.
_PACKAGE_ROOT = Path(__file__).resolve().parent.parent


def _utc_now() -> datetime:
    """Return the current UTC time (isolated for easy test overriding)."""
    return datetime.now(UTC)


class EnvironmentalService:
    """Estimates the avoided environmental burden of recovering a device."""

    def __init__(
        self,
        *,
        config: EnvironmentalConfig | None = None,
        library: FactorLibrary | None = None,
        inference_engine: EnvironmentalInferenceEngine | None = None,
        clock: Callable[[], datetime] | None = _utc_now,
        engine_version: str = ENVIRONMENTAL_ENGINE_VERSION,
    ) -> None:
        self._config = config if config is not None else EnvironmentalConfig()
        self._library = (
            library
            if library is not None
            else load_library(
                self._config.resolved_factors_path(package_root=_PACKAGE_ROOT)
            )
        )
        self._inference = (
            inference_engine
            if inference_engine is not None
            else EnvironmentalInferenceEngine(self._config)
        )
        self._clock = clock
        self._engine_version = engine_version

    @property
    def config(self) -> EnvironmentalConfig:
        """Return the configuration this service analyzes with."""
        return self._config

    @property
    def library(self) -> FactorLibrary:
        """Return the loaded conversion-factor library."""
        return self._library

    def analyze(
        self,
        context: DeviceContext,
        recoverability: RecoverabilityReport,
        components: ComponentReport,
        materials: MaterialReport,
    ) -> EnvironmentalImpactReport:
        """Estimate the environmental impact of recovering a device.

        Runs the inference engine over the fused context, its recoverability
        report, its component inventory and its material breakdown against the
        loaded conversion-factor catalogue, and stamps provenance. The inference
        reads only the reports' aggregate quantities (masses, scores, hazard,
        confidences) — never any raw image or model.

        Args:
            context: The fused :class:`~device_ai.fusion.models.DeviceContext`.
            recoverability: The device's
                :class:`~device_ai.recoverability.models.RecoverabilityReport`.
            components: The device's
                :class:`~device_ai.components.models.ComponentReport`.
            materials: The device's
                :class:`~device_ai.materials.models.MaterialReport`.

        Returns:
            The normalized, immutable :class:`EnvironmentalImpactReport`.
        """
        created_at = self._clock() if self._clock is not None else None
        return self._inference.infer(
            context,
            recoverability,
            components,
            materials,
            self._library,
            factors_version=self._library.version,
            engine_version=self._engine_version,
            created_at=created_at,
        )
