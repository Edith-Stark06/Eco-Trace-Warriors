"""Deterministic device-passport builder (milestone M2.3).

Pure composition over the five upstream inputs — a fused
:class:`~device_ai.fusion.models.DeviceContext` (M1.7), the actionable
:class:`~device_ai.circular.models.DecisionReport` (M2.2), the
:class:`~device_ai.materials.models.MaterialReport` (M1.10), the
:class:`~device_ai.environmental.models.EnvironmentalImpactReport` (M1.11) and the
device's :class:`~device_ai.fingerprint.models.DeviceFingerprint` (M1.5). There is
no model and no I/O here, and crucially **no inference**: the builder copies or
plainly summarizes what its inputs already reported and never derives a new score
or recommendation. Given the same inputs it always produces the same
:class:`DevicePassport`, which is what makes the passport an auditable snapshot.

The assembly has four clean stages:

1. **Summarize** each upstream report into its passport section (identity,
   classification, decision, material, environmental, fingerprint), copying
   values verbatim.
2. **Compose confidence** by gathering the four upstream confidences onto one
   axis and taking their plain arithmetic mean — a transparent composition, not a
   new inference.
3. **Identify** the passport with a deterministic, content-addressed id derived
   from the device's stable identity (EcoID, fingerprint, resolved identity) and
   its recommendation, so the same device and reports always yield the same id.
4. **Narrate** by composing the ordered reasoning and warnings from the inputs'
   own reasoning/warnings and a few passport-level notes, then capping them.

The builder derives nothing an operator could not re-derive from the inputs by
hand; it exists to make that composition uniform, deterministic and validated.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..fusion.models import FusionAttribute
from ..utils.hashing import hash_bytes
from .models import (
    Classification,
    ConfidenceSummary,
    DecisionSummary,
    DeviceIdentity,
    DevicePassport,
    EnvironmentalSummary,
    FingerprintSummary,
    MaterialSummary,
    PassportMetadata,
)

if TYPE_CHECKING:
    from datetime import datetime

    from ..circular.models import DecisionReport
    from ..environmental.models import EnvironmentalImpactReport
    from ..fingerprint.models import DeviceFingerprint
    from ..fusion.models import DeviceContext
    from ..materials.models import MaterialReport
    from .config import PassportConfig

# Decimal places the composed overall confidence is rounded to. Matches the
# fusion, recoverability, decision, environmental and circular engines so every
# engine's numbers compare cleanly.
_CONFIDENCE_PRECISION = 6

# Length of the content-addressed passport id's hash suffix (hex characters). A
# 12-character SHA-256 prefix is ample to keep passports distinct while staying
# log-friendly; the human-readable ``ET-PP-`` prefix marks it as a passport id.
_PASSPORT_ID_HASH_LENGTH = 12

#: Human-readable prefix marking a device-passport identifier.
_PASSPORT_ID_PREFIX = "ET-PP-"


def _mean(values: tuple[float, ...]) -> float:
    """Return the arithmetic mean of ``values`` (``0.0`` when empty)."""
    return sum(values) / len(values) if values else 0.0


class PassportBuilder:
    """Compose the five upstream inputs into an immutable device passport."""

    def __init__(self, config: PassportConfig) -> None:
        self._config = config

    @property
    def config(self) -> PassportConfig:
        """Return the configuration this builder assembles with."""
        return self._config

    def build(
        self,
        context: DeviceContext,
        decision: DecisionReport,
        materials: MaterialReport,
        environmental: EnvironmentalImpactReport,
        fingerprint: DeviceFingerprint | None,
        *,
        schema_version: str = "",
        passport_version: str = "",
        engine_version: str = "",
        created_at: datetime | None = None,
    ) -> DevicePassport:
        """Assemble a :class:`DevicePassport` from the upstream reports.

        Args:
            context: The fused device context (identity, classification,
                conflicts, provenance).
            decision: The device's circular :class:`DecisionReport`.
            materials: The device's :class:`MaterialReport`.
            environmental: The device's :class:`EnvironmentalImpactReport`.
            fingerprint: The device's :class:`DeviceFingerprint`, or ``None`` when
                no fingerprint is available (the fingerprint section is then
                empty, still schema-valid).
            schema_version: Schema version stamped onto the passport metadata.
            passport_version: Passport version stamped onto the passport (falls
                back to the config's version when empty).
            engine_version: Passport-builder version stamped onto the metadata.
            created_at: Assembly timestamp stamped onto the metadata, or ``None``.

        Returns:
            The immutable, composed :class:`DevicePassport`.
        """
        identity = self._identity(context)
        classification = self._classification(context)
        decision_summary = self._decision_summary(decision)
        material_summary = self._material_summary(materials)
        environmental_summary = self._environmental_summary(environmental)
        fingerprint_summary = self._fingerprint_summary(fingerprint)
        confidence_summary = self._confidence_summary(
            context, decision, materials, environmental
        )

        version = passport_version or self._config.passport_version
        metadata = self._metadata(
            context=context,
            decision=decision,
            materials=materials,
            environmental=environmental,
            schema_version=schema_version,
            engine_version=engine_version,
            created_at=created_at,
        )
        passport_id = self._passport_id(
            context=context,
            identity=identity,
            decision_summary=decision_summary,
            fingerprint_summary=fingerprint_summary,
        )
        reasoning, warnings = self._narrate(
            classification=classification,
            decision=decision,
            materials=materials,
            environmental=environmental,
            fingerprint_summary=fingerprint_summary,
        )

        return DevicePassport(
            passport_id=passport_id,
            passport_version=version,
            eco_id=context.eco_id,
            device_identity=identity,
            classification=classification,
            decision_summary=decision_summary,
            material_summary=material_summary,
            environmental_summary=environmental_summary,
            fingerprint_summary=fingerprint_summary,
            confidence_summary=confidence_summary,
            metadata=metadata,
            reasoning=reasoning,
            warnings=warnings,
        )

    # -- Section summarizers (verbatim copies of upstream evidence) ----------

    def _identity(self, context: DeviceContext) -> DeviceIdentity:
        """Copy the resolved identity fields from the fused context."""
        return DeviceIdentity(
            brand=context.brand,
            model=context.model,
            serial_number=context.serial_number,
            imei=context.imei,
            mac_address=context.mac_address,
        )

    def _classification(self, context: DeviceContext) -> Classification:
        """Copy the resolved device type and its confidence from fusion."""
        return Classification(
            device_type=context.device_type,
            confidence=context.confidence_of(FusionAttribute.DEVICE_TYPE),
            has_conflicts=context.has_conflicts,
        )

    def _decision_summary(self, decision: DecisionReport) -> DecisionSummary:
        """Summarize the circular decision recommendation."""
        winner = decision.winning_rule
        return DecisionSummary(
            recommended_action=decision.recommended_action.value,
            priority=decision.priority.value,
            confidence=decision.confidence,
            winning_rule_id=winner.rule_id if winner is not None else "",
            triggered_count=decision.triggered_count,
        )

    def _material_summary(self, materials: MaterialReport) -> MaterialSummary:
        """Summarize the material estimate totals."""
        return MaterialSummary(
            material_count=materials.material_count,
            total_mass_g=materials.total_mass_g,
            recoverable_mass_g=materials.recoverable_mass_g,
            hazardous_mass_g=materials.hazardous_mass_g,
            confidence=materials.overall_confidence,
        )

    def _environmental_summary(
        self, environmental: EnvironmentalImpactReport
    ) -> EnvironmentalSummary:
        """Summarize the avoided-burden headline metrics."""
        return EnvironmentalSummary(
            carbon_saved_kg=environmental.carbon_saved_kg,
            energy_saved_mj=environmental.energy_saved_mj,
            water_saved_l=environmental.water_saved_l,
            landfill_diversion_kg=environmental.landfill_diversion_kg,
            critical_material_recovery_kg=environmental.critical_material_recovery_kg,
            circularity_index=environmental.circularity_index,
            hazard_reduction_score=environmental.hazard_reduction_score,
            confidence=environmental.confidence,
        )

    def _fingerprint_summary(
        self, fingerprint: DeviceFingerprint | None
    ) -> FingerprintSummary:
        """Summarize the hash-backed identity anchor and encoder provenance.

        When no fingerprint is available every field is its empty/zero default,
        which is still a schema-valid section (the fingerprint block is optional
        evidence, not a required identity).
        """
        if fingerprint is None:
            return FingerprintSummary(
                fingerprint="",
                dimension=0,
                encoder_name="",
                encoder_version="",
                metric="",
            )
        return FingerprintSummary(
            fingerprint=fingerprint.fingerprint,
            dimension=fingerprint.dimension,
            encoder_name=fingerprint.encoder_name,
            encoder_version=fingerprint.encoder_version,
            metric=fingerprint.metric,
        )

    def _confidence_summary(
        self,
        context: DeviceContext,
        decision: DecisionReport,
        materials: MaterialReport,
        environmental: EnvironmentalImpactReport,
    ) -> ConfidenceSummary:
        """Gather the four upstream confidences and take their plain mean.

        The mean is a transparent composition of values the inputs already
        reported — the passport derives no confidence of its own.
        """
        identity_confidence = context.confidence
        decision_confidence = decision.confidence
        material_confidence = materials.overall_confidence
        environmental_confidence = environmental.confidence
        overall = round(
            _mean(
                (
                    identity_confidence,
                    decision_confidence,
                    material_confidence,
                    environmental_confidence,
                )
            ),
            _CONFIDENCE_PRECISION,
        )
        return ConfidenceSummary(
            identity_confidence=identity_confidence,
            decision_confidence=decision_confidence,
            material_confidence=material_confidence,
            environmental_confidence=environmental_confidence,
            overall=overall,
        )

    # -- Provenance & identity -----------------------------------------------

    def _metadata(
        self,
        *,
        context: DeviceContext,
        decision: DecisionReport,
        materials: MaterialReport,
        environmental: EnvironmentalImpactReport,
        schema_version: str,
        engine_version: str,
        created_at: datetime | None,
    ) -> PassportMetadata:
        """Gather the provenance of every source engine onto the metadata block."""
        return PassportMetadata(
            passport_engine_version=engine_version,
            schema_version=schema_version,
            fusion_engine_version=context.engine_version,
            decision_engine_version=decision.engine_version,
            decision_rules_version=decision.rules_version,
            material_engine_version=materials.engine_version,
            material_profile_version=materials.profile_version,
            environmental_engine_version=environmental.engine_version,
            environmental_factors_version=environmental.factors_version,
            source_image_count=len(context.source_hashes),
            created_at=created_at,
        )

    def _passport_id(
        self,
        *,
        context: DeviceContext,
        identity: DeviceIdentity,
        decision_summary: DecisionSummary,
        fingerprint_summary: FingerprintSummary,
    ) -> str:
        """Return a deterministic, content-addressed passport identifier.

        The id is a stable hash of the device's identifying evidence — its
        EcoID, hash-backed fingerprint, resolved identity fields and recommended
        action — so the same device and reports always yield the same id, and two
        materially different devices practically never collide. The id carries no
        timestamp, so it is a pure function of the device evidence (a passport
        rebuilt later for the same device keeps its id).
        """
        parts = (
            context.eco_id,
            fingerprint_summary.fingerprint,
            context.device_type,
            identity.brand,
            identity.model,
            identity.serial_number,
            identity.imei,
            identity.mac_address,
            decision_summary.recommended_action,
        )
        canonical = "\x1f".join(parts).encode("utf-8")
        digest = hash_bytes(canonical)[:_PASSPORT_ID_HASH_LENGTH]
        return f"{_PASSPORT_ID_PREFIX}{digest.upper()}"

    # -- Narrative composition -----------------------------------------------

    def _narrate(
        self,
        *,
        classification: Classification,
        decision: DecisionReport,
        materials: MaterialReport,
        environmental: EnvironmentalImpactReport,
        fingerprint_summary: FingerprintSummary,
    ) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """Compose the ordered reasoning and warnings from the inputs.

        Reasoning leads with a passport-level summary line, then carries over the
        circular decision's own reasoning (the report that actually recommends an
        action). Warnings are the union of the decision, material and
        environmental warnings, de-duplicated in order, plus a passport-level note
        when identity evidence is thin. Both are capped by the config so the
        document stays bounded.
        """
        reasoning: list[str] = []
        device = classification.device_type or "unknown device"
        reasoning.append(
            f"Passport composed for {device}: recommended "
            f"'{decision.recommended_action.value}' at {decision.priority.value} "
            f"priority from the upstream circular decision."
        )
        reasoning.extend(decision.reasoning)

        warnings: list[str] = []
        seen: set[str] = set()
        for warning in (
            *decision.warnings,
            *materials.warnings,
            *environmental.warnings,
        ):
            if warning not in seen:
                seen.add(warning)
                warnings.append(warning)
        if not fingerprint_summary.fingerprint:
            warnings.append(
                "No device fingerprint was available; the passport carries no "
                "hash-backed identity anchor."
            )

        return (
            tuple(reasoning[: self._config.max_reasoning]),
            tuple(warnings[: self._config.max_warnings]),
        )
