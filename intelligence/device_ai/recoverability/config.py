"""Recoverability engine configuration (milestone M1.8).

:class:`RecoverabilityConfig` is the single source of truth for every tunable
number the engine uses — the decision thresholds *and* the rule weights. No
threshold is hardcoded in the rules or the scoring engine; they all read from a
config instance, so behaviour is adjusted in exactly one place (and, for the
operationally-relevant thresholds, from the environment via
:meth:`RecoverabilityConfig.from_settings`).

The object is a frozen dataclass with conservative defaults that reproduce the
documented reference behaviour, so ``RecoverabilityConfig()`` is always valid
and every field remains directly overridable in code or tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # Type-only import: the config maps a few fields off Settings
    # but never couples the engine to the settings module at runtime.
    from ..configs.settings import Settings


@dataclass(frozen=True, slots=True)
class RecoverabilityConfig:
    """All thresholds and rule weights the engine reads, with defaults.

    Attributes:
        refurbish_min_reusability: Reusability at or above which a (non-hazard,
            confident) device is recommended for refurbishment.
        repair_min_repairability: Repairability at or above which such a device
            is recommended for repair (when refurbishment does not apply).
        recycle_min_recyclability: Recyclability at or above which such a device
            is recommended for recycling (when repair does not apply).
        low_confidence_threshold: Aggregate confidence below which the engine
            forces a manual review.
        identity_repair_bonus: Repairability added when a specific model/serial
            makes the unit and its parts identifiable.
        identity_reuse_bonus: Reusability added when identity completeness makes
            the unit trackable and wipeable.
        missing_identity_reuse_penalty: Reusability removed when no identifying
            field (model/serial/imei) is present at all.
        battery_recyclability_penalty: Recyclability removed when a battery must
            be separated before material recovery.
        battery_hazard_floor_enabled: Whether a detected battery raises the
            hazard floor to at least ``MEDIUM``.
        conflict_confidence_factor: Confidence multiplier applied when fusion
            reported cross-module conflicts.
        low_confidence_factor: Confidence multiplier applied when the context's
            own confidence is below ``low_confidence_threshold``.
        unknown_device_confidence_factor: Confidence multiplier applied when the
            device type is unrecognized.
    """

    # --- Recommended-action decision thresholds --------------------------
    refurbish_min_reusability: float = 0.65
    repair_min_repairability: float = 0.55
    recycle_min_recyclability: float = 0.45
    low_confidence_threshold: float = 0.50

    # --- Identity-completeness rule weights ------------------------------
    identity_repair_bonus: float = 0.10
    identity_reuse_bonus: float = 0.10
    missing_identity_reuse_penalty: float = 0.15

    # --- Hazard rule weights ---------------------------------------------
    battery_recyclability_penalty: float = 0.10
    battery_hazard_floor_enabled: bool = True

    # --- Confidence-aggregation factors ----------------------------------
    conflict_confidence_factor: float = 0.80
    low_confidence_factor: float = 0.60
    unknown_device_confidence_factor: float = 0.70

    @classmethod
    def from_settings(cls, settings: Settings) -> RecoverabilityConfig:
        """Build a config from application settings.

        Maps the four operationally-tunable, env-driven thresholds onto the
        config; every other field keeps its default (still overridable directly
        in code). Keeping the mapping explicit means adding an env knob is a
        one-line, reviewable change.

        Args:
            settings: The application :class:`~device_ai.configs.settings.Settings`.

        Returns:
            A :class:`RecoverabilityConfig` reflecting the env thresholds.
        """
        return cls(
            refurbish_min_reusability=settings.recoverability_refurbish_min_reusability,
            repair_min_repairability=settings.recoverability_repair_min_repairability,
            recycle_min_recyclability=settings.recoverability_recycle_min_recyclability,
            low_confidence_threshold=settings.recoverability_low_confidence_threshold,
        )
