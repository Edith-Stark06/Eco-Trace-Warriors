"""Material inference engine (milestone M1.10).

Deterministic arithmetic over a resolved :class:`MaterialProfile`, a fused
:class:`~device_ai.fusion.models.DeviceContext`, its
:class:`~device_ai.recoverability.models.RecoverabilityReport` and its
:class:`~device_ai.components.models.ComponentReport`. There is no model and no
I/O here — given the same inputs the engine always produces the same
:class:`MaterialReport`, which is what makes the material estimate auditable.

The fold has two independent axes (per the design):

* **Mass** is the catalogue nominal (``mass_g``), never scaled by confidence.
* **Confidence** is derived separately: the overall inventory confidence blends
  the fused device confidence with the recoverability confidence and is damped
  for an unrecognized device type and for fusion conflicts (identical to the
  component engine); each material's own confidence is that overall confidence
  scaled by how strongly its *source components* are present in the consumed
  component report.

A material is listed only when at least one of its source components is present
(unconditional structural materials are always present) and its resulting
confidence clears the configured floor.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..recoverability.models import HazardLevel

if TYPE_CHECKING:
    from datetime import datetime

    from ..components.models import ComponentReport
    from ..fusion.models import DeviceContext
    from ..recoverability.models import RecoverabilityReport
    from .config import MaterialConfig
    from .profiles import MaterialProfile, MaterialSpec

from .models import MaterialReport, RecoveredMaterial

# Decimal places every emitted confidence is rounded to. Matches the fusion,
# recoverability and component engines so all engines' numbers compare cleanly.
_SCORE_PRECISION = 6

# Decimal places every emitted mass (grams) is rounded to. Masses are physical
# quantities, not probabilities, so they are rounded but never clamped to [0, 1].
_MASS_PRECISION = 3


def _clamp_round(value: float) -> float:
    """Clamp ``value`` to ``[0, 1]`` and round to the score precision."""
    return round(max(0.0, min(1.0, value)), _SCORE_PRECISION)


def _round_mass(value: float) -> float:
    """Round a mass in grams to the mass precision (never clamped)."""
    return round(value, _MASS_PRECISION)


class MaterialInferenceEngine:
    """Infers the recoverable-material breakdown for a fused, assessed device."""

    def __init__(self, config: MaterialConfig) -> None:
        self._config = config

    @property
    def config(self) -> MaterialConfig:
        """Return the configuration this engine infers with."""
        return self._config

    def infer(
        self,
        context: DeviceContext,
        recoverability: RecoverabilityReport,
        components: ComponentReport,
        profile: MaterialProfile,
        *,
        profile_version: str = "",
        engine_version: str = "",
        created_at: datetime | None = None,
    ) -> MaterialReport:
        """Infer the material breakdown for a device.

        Args:
            context: The fused device context (confidence + conflicts + eco_id).
            recoverability: The device's recoverability report (its own
                confidence feeds the overall blend).
            components: The device's component report (its inventory conditions
                which materials are present and how confident each is).
            profile: The resolved material profile for the device type.
            profile_version: Catalogue version stamped onto the report.
            engine_version: Engine version stamped onto the report.
            created_at: Timestamp stamped onto the report, or ``None``.

        Returns:
            The normalized, immutable :class:`MaterialReport`.
        """
        presence_by_category = self._presence_by_category(components)
        overall = self._overall_confidence(
            context=context,
            recoverability=recoverability,
            profile=profile,
        )

        materials: list[RecoveredMaterial] = []
        for spec in profile.materials:
            recovered = self._infer_one(
                spec,
                presence_by_category=presence_by_category,
                overall_confidence=overall,
            )
            if recovered is not None:
                materials.append(recovered)

        total_mass = _round_mass(sum(material.mass_g for material in materials))
        recoverable_mass = _round_mass(
            sum(material.mass_g for material in materials if material.recoverable)
        )
        hazardous_mass = _round_mass(
            sum(material.mass_g for material in materials if material.hazardous)
        )

        reasoning, warnings = self._explain(
            context=context,
            recoverability=recoverability,
            profile=profile,
            kept=len(materials),
        )

        return MaterialReport(
            device_type=profile.device_type,
            materials=tuple(materials),
            total_mass_g=total_mass,
            recoverable_mass_g=recoverable_mass,
            hazardous_mass_g=hazardous_mass,
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
        spec: MaterialSpec,
        *,
        presence_by_category: dict[str, float],
        overall_confidence: float,
    ) -> RecoveredMaterial | None:
        """Estimate one material, or drop it.

        Returns ``None`` when no source component is present (for a conditional
        material) or the resulting confidence is at or below the configured
        floor.
        """
        config = self._config

        if spec.source_components:
            matched = {
                source: presence_by_category[source]
                for source in spec.source_components
                if source in presence_by_category
            }
            if not matched:
                return None
            source_presence = max(matched.values())
            present_sources = tuple(
                source for source in spec.source_components if source in matched
            )
            reason = (
                f"Derived from present component(s) "
                f"{', '.join(present_sources)} "
                f"(strongest presence {source_presence:.0%}); confidence scaled "
                f"by the overall estimate confidence {overall_confidence:.0%}."
            )
        else:
            source_presence = 1.0
            present_sources = ()
            reason = (
                "Structural material assumed present regardless of the component "
                f"inventory; confidence is the overall estimate confidence "
                f"{overall_confidence:.0%}."
            )

        confidence = _clamp_round(source_presence * overall_confidence)
        if confidence <= config.min_material_confidence:
            return None

        return RecoveredMaterial(
            name=spec.name,
            category=spec.category,
            mass_g=_round_mass(spec.mass_g),
            confidence=confidence,
            recoverable=spec.recoverable,
            hazardous=spec.hazardous,
            source_components=present_sources,
            reason=reason,
        )

    @staticmethod
    def _presence_by_category(components: ComponentReport) -> dict[str, float]:
        """Return the strongest presence confidence per component category.

        A device may list several components in the same category; the material
        that draws on that category is conditioned by the most-present of them.
        """
        presence: dict[str, float] = {}
        for component in components.components:
            key = component.category.value
            current = presence.get(key)
            if current is None or component.presence_confidence > current:
                presence[key] = component.presence_confidence
        return presence

    def _overall_confidence(
        self,
        *,
        context: DeviceContext,
        recoverability: RecoverabilityReport,
        profile: MaterialProfile,
    ) -> float:
        """Blend and damp the inputs into a single overall confidence.

        The fused device confidence is blended with the recoverability report's
        own confidence (weighted by
        :attr:`MaterialConfig.recoverability_confidence_weight`), then damped by
        a multiplicative factor for an unrecognized device type and for fusion
        conflicts. Independent damping signals therefore compound — mirroring the
        component engine so the two reports' confidences are comparable.
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
        profile: MaterialProfile,
        kept: int,
    ) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """Build the ordered report-level reasoning and warnings."""
        reasoning: list[str] = []
        warnings: list[str] = []

        if profile.known:
            reasoning.append(
                f"Material profile for '{profile.device_type}' lists "
                f"{len(profile.materials)} candidate material(s); {kept} were "
                "supported by the component inventory and cleared the confidence "
                "floor."
            )
        else:
            reasoning.append(
                f"'{profile.device_type}' is not in the material catalogue; only "
                f"{kept} generic material(s) were estimated at low confidence."
            )
            warnings.append(
                "Unrecognized device type; the material breakdown is generic and "
                "should be confirmed manually."
            )

        reasoning.append(
            "Estimated masses are catalogue nominal values; each material's "
            "confidence is the strongest presence of its source components "
            "scaled by the overall estimate confidence."
        )

        reasoning.append(
            "Recoverability assessment "
            f"(action '{recoverability.recommended_action.value}', hazard "
            f"'{recoverability.hazard_level.value}', confidence "
            f"{recoverability.confidence:.2f}) was blended into the overall "
            "confidence."
        )

        if recoverability.hazard_level not in (HazardLevel.NONE, HazardLevel.UNKNOWN):
            warnings.append(
                "Device carries an assessed hazard; hazardous materials must be "
                "handled through a dedicated stream."
            )

        if context.has_conflicts:
            warnings.append(
                "Fusion reported conflicting evidence; material estimate "
                "confidence is reduced."
            )

        if kept == 0:
            warnings.append(
                "No materials could be estimated from the component inventory; "
                "the breakdown is empty."
            )

        return tuple(reasoning), tuple(warnings)
