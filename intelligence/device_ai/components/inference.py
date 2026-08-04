"""Component inference engine (milestone M1.9).

:class:`ComponentInferenceEngine` is the deterministic core that turns a fused
:class:`~device_ai.fusion.models.DeviceContext`, its
:class:`~device_ai.recoverability.models.RecoverabilityReport` and the resolved
:class:`~device_ai.components.profiles.ComponentProfile` into a normalized
:class:`~device_ai.components.models.ComponentReport`.

It does **no learned inference** — every number is a catalogue prior adjusted by
explicit, documented corroboration rules, so the output is fully predictable and
self-explaining:

* **Presence confidence** — each component starts at its catalogue
  ``base_likelihood`` (a prior), then gains a small, bounded bonus when the fused
  identity corroborates it (a declared ``implied_by`` signal is present) and when
  a hazardous part agrees with a non-``NONE`` recoverability hazard. The result
  is clamped to ``[0, 1]`` and rounded; components below the configured floor are
  dropped.
* **Overall confidence** — the fused device confidence blended with the
  recoverability report's confidence, then damped for an unrecognized device type
  and for fusion conflicts.
* **Reasoning & warnings** — ordered, human-readable lines describing the profile
  used, the identity corroboration applied and the recoverability blend, plus
  operator warnings for unknown types and conflicts.

All numeric outputs are clamped to ``[0, 1]`` and rounded to six decimals,
matching the fusion and recoverability engines' precision so the three engines'
numbers compose cleanly.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from ..recoverability.models import HazardLevel
from .config import ComponentConfig
from .models import ComponentReport, InferredComponent

if TYPE_CHECKING:  # Type-only imports keep the component core free of a hard
    # runtime coupling to the layers it consumes (both are passed in).
    from ..fusion.models import DeviceContext
    from ..recoverability.models import RecoverabilityReport
    from .profiles import ComponentProfile, ComponentSpec

# Decimal places every emitted score is rounded to. Matches the fusion and
# recoverability engines so all three engines' numbers compare cleanly.
_SCORE_PRECISION = 6

# Human-readable labels for the identity signals a component may be implied by.
_SIGNAL_LABELS: dict[str, str] = {
    "model": "model",
    "serial_number": "serial number",
    "imei": "IMEI",
    "mac_address": "MAC address",
}


def _clamp_round(value: float) -> float:
    """Clamp ``value`` to ``[0, 1]`` and round to the score precision."""
    return round(max(0.0, min(1.0, value)), _SCORE_PRECISION)


class ComponentInferenceEngine:
    """Infer a device's likely internal components, deterministically.

    Args:
        config: The engine configuration whose weights drive corroboration and
            confidence aggregation.
    """

    def __init__(self, config: ComponentConfig) -> None:
        self._config = config

    @property
    def config(self) -> ComponentConfig:
        """Return the configuration this engine infers with."""
        return self._config

    def infer(
        self,
        context: DeviceContext,
        recoverability: RecoverabilityReport,
        profile: ComponentProfile,
        *,
        profile_version: str = "",
        engine_version: str = "",
        created_at: datetime | None = None,
    ) -> ComponentReport:
        """Infer the component inventory for a device.

        Args:
            context: The fused device context (identity signals + conflicts).
            recoverability: The device's recoverability report (hazard + its own
                confidence feed the inference).
            profile: The resolved component profile for the device type.
            profile_version: Catalogue version stamped onto the report.
            engine_version: Engine version stamped onto the report.
            created_at: Timestamp stamped onto the report, or ``None``.

        Returns:
            The normalized, immutable :class:`ComponentReport`.
        """
        present_signals = self._present_signals(context)
        hazard_present = recoverability.hazard_level not in (
            HazardLevel.NONE,
            HazardLevel.UNKNOWN,
        )

        components: list[InferredComponent] = []
        for spec in profile.components:
            inferred = self._infer_one(
                spec,
                present_signals=present_signals,
                hazard_present=hazard_present,
                device_type=profile.device_type,
            )
            if inferred is not None:
                components.append(inferred)

        overall = self._overall_confidence(
            context=context,
            recoverability=recoverability,
            profile=profile,
        )
        reasoning, warnings = self._explain(
            context=context,
            recoverability=recoverability,
            profile=profile,
            present_signals=present_signals,
            kept=len(components),
        )

        return ComponentReport(
            device_type=profile.device_type,
            components=tuple(components),
            overall_confidence=overall,
            reasoning=reasoning,
            warnings=warnings,
            eco_id=context.eco_id,
            engine_version=engine_version,
            profile_version=profile_version,
            created_at=created_at,
        )

    def _infer_one(
        self,
        spec: ComponentSpec,
        *,
        present_signals: frozenset[str],
        hazard_present: bool,
        device_type: str,
    ) -> InferredComponent | None:
        """Infer one component's presence confidence, or drop it.

        Returns ``None`` when the resulting presence confidence is at or below
        the configured floor.
        """
        config = self._config
        confidence = spec.base_likelihood
        reason_parts = [
            f"Catalogue prior {spec.base_likelihood:.0%} for a "
            f"'{device_type}' device."
        ]

        matched = [
            _SIGNAL_LABELS[signal]
            for signal in spec.implied_by
            if signal in present_signals
        ]
        if matched:
            confidence += config.identity_corroboration_bonus
            reason_parts.append(
                "Corroborated by the device's "
                + ", ".join(matched)
                + f" (+{config.identity_corroboration_bonus:.0%})."
            )

        if spec.hazardous and hazard_present:
            confidence += config.hazard_corroboration_bonus
            reason_parts.append(
                "Hazardous part consistent with the assessed device hazard "
                f"(+{config.hazard_corroboration_bonus:.0%})."
            )

        presence = _clamp_round(confidence)
        if presence <= config.min_presence_confidence:
            return None

        return InferredComponent(
            name=spec.name,
            category=spec.category,
            presence_confidence=presence,
            hazardous=spec.hazardous,
            recoverable=spec.recoverable,
            reason=" ".join(reason_parts),
        )

    @staticmethod
    def _present_signals(context: DeviceContext) -> frozenset[str]:
        """Return the identity signals present in the fused context."""
        candidates = {
            "model": context.model,
            "serial_number": context.serial_number,
            "imei": context.imei,
            "mac_address": context.mac_address,
        }
        return frozenset(name for name, value in candidates.items() if value)

    def _overall_confidence(
        self,
        *,
        context: DeviceContext,
        recoverability: RecoverabilityReport,
        profile: ComponentProfile,
    ) -> float:
        """Blend and damp the inputs into a single overall confidence.

        The fused device confidence is blended with the recoverability report's
        own confidence (weighted by
        :attr:`ComponentConfig.recoverability_confidence_weight`), then damped by
        a multiplicative factor for an unrecognized device type and for fusion
        conflicts. Independent damping signals therefore compound.
        """
        config = self._config
        weight = config.recoverability_confidence_weight
        blended = (
            context.confidence * (1.0 - weight) + recoverability.confidence * weight
        )
        if not profile.known:
            blended *= config.unknown_type_confidence_factor
        if context.has_conflicts:
            blended *= config.conflict_confidence_factor
        return _clamp_round(blended)

    def _explain(
        self,
        *,
        context: DeviceContext,
        recoverability: RecoverabilityReport,
        profile: ComponentProfile,
        present_signals: frozenset[str],
        kept: int,
    ) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """Build the ordered report-level reasoning and warnings."""
        reasoning: list[str] = []
        warnings: list[str] = []

        if profile.known:
            reasoning.append(
                f"Component profile for '{profile.device_type}' lists "
                f"{len(profile.components)} candidate component(s); {kept} met "
                "the presence-confidence floor."
            )
        else:
            reasoning.append(
                f"'{profile.device_type}' is not in the component catalogue; "
                f"only {kept} generic component(s) were inferred at low "
                "confidence."
            )
            warnings.append(
                "Unrecognized device type; the component inventory is generic "
                "and should be confirmed manually."
            )

        if present_signals:
            labels = ", ".join(
                _SIGNAL_LABELS[signal]
                for signal in ("model", "serial_number", "imei", "mac_address")
                if signal in present_signals
            )
            reasoning.append(
                f"Identity signals present ({labels}) corroborated the "
                "components they imply."
            )
        else:
            reasoning.append(
                "No identity signals (model, serial number, IMEI, MAC) were "
                "available to corroborate specific components."
            )

        reasoning.append(
            "Recoverability assessment "
            f"(action '{recoverability.recommended_action.value}', hazard "
            f"'{recoverability.hazard_level.value}', confidence "
            f"{recoverability.confidence:.2f}) was blended into the overall "
            "confidence."
        )

        if context.has_conflicts:
            warnings.append(
                "Fusion reported conflicting evidence; component inference "
                "confidence is reduced."
            )

        return tuple(reasoning), tuple(warnings)
