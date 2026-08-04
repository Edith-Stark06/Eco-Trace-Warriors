"""Configuration for the material intelligence engine (milestone M1.10).

Mirrors the component engine's config: a small, frozen, slotted value object
holding the profile-library locator and the handful of tunable weights the
inference engine folds in. Two fields are env-driven (via
:meth:`MaterialConfig.from_settings`); the rest keep code-level defaults that are
still overridable directly in a constructed config.

Keeping the engine's numeric behaviour in one immutable object (rather than
scattered literals) is what makes the material estimate reproducible and easy to
reason about — every weight that shapes a report is named and defaulted here.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..configs.settings import Settings

#: Default profile-library locator, relative to the ``device_ai`` package root.
DEFAULT_PROFILES_PATH = "materials/data/materials.yaml"


@dataclass(frozen=True, slots=True)
class MaterialConfig:
    """Tunable configuration for the material intelligence engine.

    Attributes:
        profiles_path: Locator of the external material-profile library,
            resolved relative to the ``device_ai`` package root when not
            absolute.
        min_material_confidence: Confidence at or below which a recovered
            material is dropped from the report as too unlikely to be worth
            listing.
        unknown_type_confidence_factor: Multiplicative factor applied to the
            overall confidence when the device type is not in the catalogue and
            the conservative unknown fallback profile is used.
        conflict_confidence_factor: Multiplicative factor applied to the overall
            confidence when the fused context reported conflicting evidence.
        recoverability_confidence_weight: Weight in ``[0, 1]`` given to the
            recoverability report's own confidence when blending it with the
            fused device confidence (the device confidence gets the complement).
    """

    # --- Profile library locator -----------------------------------------
    profiles_path: str = DEFAULT_PROFILES_PATH

    # --- Material filtering ----------------------------------------------
    min_material_confidence: float = 0.05

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
    def from_settings(cls, settings: Settings) -> MaterialConfig:
        """Build a config from application settings.

        Maps the two operationally-tunable, env-driven knobs onto the config;
        every other field keeps its default (still overridable directly in
        code). Keeping the mapping explicit means adding an env knob is a
        one-line, reviewable change.

        Args:
            settings: The application :class:`~device_ai.configs.settings.Settings`.

        Returns:
            A :class:`MaterialConfig` reflecting the env settings.
        """
        return cls(
            profiles_path=settings.material_profiles_path,
            min_material_confidence=settings.material_min_confidence,
        )
