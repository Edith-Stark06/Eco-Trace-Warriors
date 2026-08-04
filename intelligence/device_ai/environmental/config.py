"""Configuration for the environmental intelligence engine (milestone M1.11).

Mirrors the material engine's config: a small, frozen, slotted value object
holding the conversion-factor catalogue locator and the handful of tunable
weights the inference engine folds in. Two fields are env-driven (via
:meth:`EnvironmentalConfig.from_settings`); the rest keep code-level defaults
that are still overridable directly in a constructed config.

Keeping the engine's numeric behaviour in one immutable object (rather than
scattered literals) is what makes the environmental estimate reproducible and
easy to reason about — every weight that shapes a report is named and defaulted
here.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..configs.settings import Settings

#: Default factor-catalogue locator, relative to the ``device_ai`` package root.
DEFAULT_FACTORS_PATH = "environmental/data/factors.yaml"


@dataclass(frozen=True, slots=True)
class EnvironmentalConfig:
    """Tunable configuration for the environmental intelligence engine.

    Attributes:
        factors_path: Locator of the external conversion-factor catalogue,
            resolved relative to the ``device_ai`` package root when not
            absolute.
        min_material_confidence: Confidence at or below which a recovered
            material is ignored when aggregating the resource-savings metrics —
            it is too unlikely to be worth counting toward the avoided burden.
        recoverability_confidence_weight: Weight in ``[0, 1]`` given to the
            recoverability report's own confidence when blending it with the
            material report's overall confidence (the material confidence gets
            the complement). No separate unknown-type or conflict damping is
            applied here: the consumed :attr:`MaterialReport.overall_confidence`
            already folds in device-type familiarity and fusion conflicts, so
            re-damping would double-count the same signals.
        circularity_recyclability_weight: Weight in ``[0, 1]`` the circularity
            index gives to the recoverability recyclability score; the
            complement weights the recoverable mass fraction.
        hazard_diversion_weight: Weight in ``[0, 1]`` the hazard-reduction score
            gives to the hazardous mass fraction diverted; the complement weights
            the assessed hazard severity.
    """

    # --- Factor catalogue locator ----------------------------------------
    factors_path: str = DEFAULT_FACTORS_PATH

    # --- Material filtering ----------------------------------------------
    min_material_confidence: float = 0.05

    # --- Overall-confidence aggregation -----------------------------------
    recoverability_confidence_weight: float = 0.50

    # --- Index composition weights ---------------------------------------
    circularity_recyclability_weight: float = 0.50
    hazard_diversion_weight: float = 0.50

    def resolved_factors_path(self, *, package_root: Path) -> Path:
        """Return the absolute conversion-factor catalogue path.

        Relative :attr:`factors_path` values are resolved against the given
        ``package_root`` (the ``device_ai`` package directory), so the packaged
        catalogue is found regardless of the process working directory.

        Args:
            package_root: The ``device_ai`` package directory.

        Returns:
            The absolute path to the conversion-factor catalogue file.
        """
        candidate = Path(self.factors_path)
        if candidate.is_absolute():
            return candidate
        return package_root / candidate

    @classmethod
    def from_settings(cls, settings: Settings) -> EnvironmentalConfig:
        """Build a config from application settings.

        Maps the two operationally-tunable, env-driven knobs onto the config;
        every other field keeps its default (still overridable directly in
        code). Keeping the mapping explicit means adding an env knob is a
        one-line, reviewable change.

        Args:
            settings: The application :class:`~device_ai.configs.settings.Settings`.

        Returns:
            An :class:`EnvironmentalConfig` reflecting the env settings.
        """
        return cls(
            factors_path=settings.environmental_factors_path,
            min_material_confidence=settings.environmental_min_confidence,
        )
