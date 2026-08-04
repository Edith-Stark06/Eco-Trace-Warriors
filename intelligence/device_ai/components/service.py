"""Component service: orchestration facade for the engine (milestone M1.9).

:class:`ComponentService` is the single collaborator downstream code depends on
to infer a device's internal components. It wires together the injected
configuration, the externally-loaded component-profile library and the inference
engine into the one operation the engine exposes:

* :meth:`analyze` — resolve the component profile for a fused
  :class:`~device_ai.fusion.models.DeviceContext`, run the inference engine over
  the context and its
  :class:`~device_ai.recoverability.models.RecoverabilityReport`, and stamp
  provenance, yielding an immutable
  :class:`~device_ai.components.models.ComponentReport`.

The component **catalogue is external data** (YAML/JSON), loaded once at service
construction via :func:`~device_ai.components.profiles.load_library` and then
held immutably — so the engine reads its knowledge from a reviewable file, not
from code, while remaining a pure, deterministic function of its inputs at call
time. Every collaborator (config, library, inference engine, clock) is injected,
so the whole engine is exercised deterministically in tests with a hand-built
context and report — no fusion run, no models. Like the fusion and recoverability
engines it builds on, the service is **internal-only**: it exposes no HTTP
surface and does not touch the frozen ``/predict`` contract.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from .config import ComponentConfig
from .inference import ComponentInferenceEngine
from .models import ComponentReport
from .profiles import ComponentProfileLibrary, load_library

if TYPE_CHECKING:  # Type-only imports keep the component core free of a hard
    # runtime coupling to the layers it consumes (both are passed in).
    from ..fusion.models import DeviceContext
    from ..recoverability.models import RecoverabilityReport

#: Version tag stamped onto every produced :class:`ComponentReport`.
COMPONENT_ENGINE_VERSION = "1.0.0"

#: The ``device_ai`` package root, used to resolve a relative catalogue path.
_PACKAGE_ROOT = Path(__file__).resolve().parent.parent


def _utc_now() -> datetime:
    """Return the current UTC time (isolated for easy test overriding)."""
    return datetime.now(UTC)


class ComponentService:
    """High-level orchestration of the component inference.

    Args:
        config: The engine configuration (locator + weights). Defaults to the
            reference :class:`ComponentConfig`.
        library: A pre-loaded component-profile library. Defaults to loading the
            external catalogue named by ``config.profiles_path`` (resolved
            against the package root) exactly once at construction.
        inference_engine: The inference engine. Defaults to a
            :class:`ComponentInferenceEngine` bound to ``config``.
        clock: Callable returning the current time; injected for reproducible
            timestamps in tests. Pass ``None`` to omit ``created_at`` entirely
            (keeping the report a pure function of its inputs).
        engine_version: Version tag stamped onto every produced report.

    Raises:
        ComponentProfileError: If no ``library`` is supplied and the external
            catalogue cannot be loaded or is invalid.
    """

    def __init__(
        self,
        *,
        config: ComponentConfig | None = None,
        library: ComponentProfileLibrary | None = None,
        inference_engine: ComponentInferenceEngine | None = None,
        clock: Callable[[], datetime] | None = _utc_now,
        engine_version: str = COMPONENT_ENGINE_VERSION,
    ) -> None:
        self._config = config if config is not None else ComponentConfig()
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
            else ComponentInferenceEngine(self._config)
        )
        self._clock = clock
        self._engine_version = engine_version

    @property
    def config(self) -> ComponentConfig:
        """Return the configuration this service analyzes with."""
        return self._config

    @property
    def library(self) -> ComponentProfileLibrary:
        """Return the loaded component-profile library."""
        return self._library

    def analyze(
        self,
        context: DeviceContext,
        recoverability: RecoverabilityReport,
    ) -> ComponentReport:
        """Infer the internal components of a fused, assessed device.

        Resolves the device-type component profile from the external catalogue,
        runs the inference engine over the context and its recoverability report,
        and stamps provenance. The inference reads only the context's identity
        signals and conflict flag, plus the recoverability hazard and confidence
        — never any raw image or model.

        Args:
            context: The fused :class:`~device_ai.fusion.models.DeviceContext`.
            recoverability: The device's
                :class:`~device_ai.recoverability.models.RecoverabilityReport`.

        Returns:
            The normalized, immutable :class:`ComponentReport`.
        """
        profile = self._library.profile_for(context.device_type)
        created_at = self._clock() if self._clock is not None else None
        return self._inference.infer(
            context,
            recoverability,
            profile,
            profile_version=self._library.version,
            engine_version=self._engine_version,
            created_at=created_at,
        )
