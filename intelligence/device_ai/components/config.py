"""Component engine configuration (milestone M1.9).

:class:`ComponentConfig` is the single source of truth for every tunable number
and locator the engine uses — the external profile-library path and the
corroboration/aggregation weights. No threshold is hardcoded in the inference
engine or the profile loader; they all read from a config instance, so behaviour
is adjusted in exactly one place (and, for the operationally-relevant knobs, from
the environment via :meth:`ComponentConfig.from_settings`).

The object is a frozen dataclass with conservative defaults that reproduce the
documented reference behaviour, so ``ComponentConfig()`` is always valid and
every field remains directly overridable in code or tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # Type-only import: the config maps a few fields off Settings
    # but never couples the engine to the settings module at runtime.
    from ..configs.settings import Settings

#: Default profile-library locator, relative to the ``device_ai`` package root.
DEFAULT_PROFILES_PATH = "components/data/components.yaml"


@dataclass(frozen=True, slots=True)
class ComponentConfig:
    """All thresholds, weights and locators the engine reads, with defaults.

    Attributes:
        profiles_path: Locator of the external component-profile library
            (YAML/JSON). Resolved relative to the ``device_ai`` package root
            when not absolute.
        min_presence_confidence: Presence confidence at or below which an
            inferred component is dropped from the report as too unlikely.
        identity_corroboration_bonus: Presence-confidence boost added to a
            component whose ``implied_by`` identity signal is present in the
            fused context (e.g. a serial number corroborating a mainboard).
        hazard_corroboration_bonus: Presence-confidence boost added to a
            hazardous component when the recoverability report already flags a
            non-``NONE`` hazard for the device (the two engines agree).
        unknown_type_confidence_factor: Overall-confidence multiplier applied
            when the device type is not in the catalogue (generic fallback).
        conflict_confidence_factor: Overall-confidence multiplier applied when
            the fused context reported cross-module conflicts.
        recoverability_confidence_weight: Weight in ``[0, 1]`` blending the
            recoverability report's own confidence into the overall confidence
            (``0`` ignores it; ``1`` averages it in fully).
    """

    # --- Profile library locator -----------------------------------------
    profiles_path: str = DEFAULT_PROFILES_PATH

    # --- Component filtering ---------------------------------------------
    min_presence_confidence: float = 0.05

    # --- Presence corroboration weights ----------------------------------
    identity_corroboration_bonus: float = 0.05
    hazard_corroboration_bonus: float = 0.05

    # --- Overall-confidence aggregation factors --------------------------
    unknown_type_confidence_factor: float = 0.50
    conflict_confidence_factor: float = 0.85
    recoverability_confidence_weight: float = 0.50

    def resolved_profiles_path(self, *, package_root: Path) -> Path:
        """Return the absolute profile-library path.

        Relative :attr:`profiles_path` values are resolved against the given
        ``package_root`` (the ``device_ai`` package directory), so the packaged
        catalogue is found regardless of the process working directory.

        Args:
            package_root: The ``device_ai`` package directory.

        Returns:
            The absolute path to the profile-library file.
        """
        candidate = Path(self.profiles_path)
        if candidate.is_absolute():
            return candidate
        return package_root / candidate

    @classmethod
    def from_settings(cls, settings: Settings) -> ComponentConfig:
        """Build a config from application settings.

        Maps the two operationally-tunable, env-driven knobs onto the config;
        every other field keeps its default (still overridable directly in
        code). Keeping the mapping explicit means adding an env knob is a
        one-line, reviewable change.

        Args:
            settings: The application :class:`~device_ai.configs.settings.Settings`.

        Returns:
            A :class:`ComponentConfig` reflecting the env settings.
        """
        return cls(
            profiles_path=settings.component_profiles_path,
            min_presence_confidence=settings.component_min_presence_confidence,
        )
