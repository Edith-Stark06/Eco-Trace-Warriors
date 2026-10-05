"""Material intelligence service (milestone M1.10).

The thin, injectable façade over the material engine: it owns the loaded
catalogue and the inference engine, resolves the device-type profile and stamps
provenance (engine/catalogue versions and an optional timestamp) onto every
:class:`~device_ai.materials.models.MaterialReport`.

Like the component service it mirrors, every collaborator is constructor-injected
with a sensible default, so production wires nothing while tests can inject a
hand-built library, a fixed clock or a custom config. The catalogue is loaded
exactly once, at construction, and held immutably.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from .config import MaterialConfig
from .inference import MaterialInferenceEngine
from .profiles import MaterialProfileLibrary, load_library

if TYPE_CHECKING:
    from ..components.models import ComponentReport
    from ..fusion.models import DeviceContext
    from ..recoverability.models import RecoverabilityReport
    from .models import MaterialReport

#: Version tag stamped onto every produced :class:`MaterialReport`.
MATERIAL_ENGINE_VERSION = "1.0.0"

#: The ``device_ai`` package root, used to resolve a relative catalogue path.
_PACKAGE_ROOT = Path(__file__).resolve().parent.parent


def _utc_now() -> datetime:
    """Return the current UTC time (isolated for easy test overriding)."""
    return datetime.now(UTC)


class MaterialService:
    """Infers the recoverable-material breakdown of a fused, assessed device."""

    def __init__(
        self,
        *,
        config: MaterialConfig | None = None,
        library: MaterialProfileLibrary | None = None,
        inference_engine: MaterialInferenceEngine | None = None,
        clock: Callable[[], datetime] | None = _utc_now,
        engine_version: str = MATERIAL_ENGINE_VERSION,
    ) -> None:
        self._config = config if config is not None else MaterialConfig()
        self._library = (
            library
            if library is not None
            else load_library(
                self._config.resolved_profiles_path(package_root=_PACKAGE_ROOT)
            )
        )
        self._inference = (
            inference_engine
            if inference_engine is not None
            else MaterialInferenceEngine(self._config)
        )
        self._clock = clock
        self._engine_version = engine_version

    @property
    def config(self) -> MaterialConfig:
        """Return the configuration this service analyzes with."""
        return self._config

    @property
    def library(self) -> MaterialProfileLibrary:
        """Return the loaded material-profile library."""
        return self._library

    def analyze(
        self,
        context: DeviceContext,
        recoverability: RecoverabilityReport,
        components: ComponentReport,
    ) -> MaterialReport:
        """Estimate the recoverable materials of a fused, assessed device.

        Resolves the device-type material profile from the external catalogue,
        runs the inference engine over the context, its recoverability report and
        its component inventory, and stamps provenance. The inference reads only
        the context's confidence and conflict flag, the recoverability
        confidence/hazard and the component inventory — never any raw image or
        model.

        Args:
            context: The fused :class:`~device_ai.fusion.models.DeviceContext`.
            recoverability: The device's
                :class:`~device_ai.recoverability.models.RecoverabilityReport`.
            components: The device's
                :class:`~device_ai.components.models.ComponentReport`.

        Returns:
            The normalized, immutable :class:`MaterialReport`.
        """
        profile = self._library.profile_for(context.device_type)
        created_at = self._clock() if self._clock is not None else None
        return self._inference.infer(
            context,
            recoverability,
            components,
            profile,
            profile_version=self._library.version,
            engine_version=self._engine_version,
            created_at=created_at,
        )
