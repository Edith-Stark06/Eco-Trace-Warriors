"""Device-passport domain models (milestone M2.3).

The Device Passport Core is an **assembler**, not an inference engine. It takes
the reports the upstream engines already produced — a fused
:class:`~device_ai.fusion.models.DeviceContext` (M1.7), the actionable
:class:`~device_ai.circular.models.DecisionReport` (M2.2), the
:class:`~device_ai.materials.models.MaterialReport` (M1.10), the
:class:`~device_ai.environmental.models.EnvironmentalImpactReport` (M1.11) and the
device's :class:`~device_ai.fingerprint.models.DeviceFingerprint` (M1.5) — and
**composes** them into a single, immutable :class:`DevicePassport` document. It
derives no new scores and recommends no action; every value it carries is copied
(or plainly summarized) from an upstream report, so the passport is a faithful,
auditable snapshot rather than a re-interpretation.

The value objects here are the vocabulary of that snapshot. Each is a small,
frozen, slotted section with its own ``to_dict`` so the passport serializes
deterministically section by section:

* :class:`DeviceIdentity` — the resolved identity fields (brand, model, serial,
  IMEI, MAC) copied from the fused context.
* :class:`Classification` — the resolved device type and the confidence fusion
  had in it.
* :class:`DecisionSummary` — the recommended action, priority, confidence and the
  winning rule from the circular decision report.
* :class:`MaterialSummary` — the material counts and mass totals from the
  material report.
* :class:`EnvironmentalSummary` — the headline avoided-burden metrics from the
  environmental report.
* :class:`FingerprintSummary` — the hash-backed identity anchor and its encoder
  provenance from the fingerprint.
* :class:`ConfidenceSummary` — the upstream confidences gathered onto one axis,
  plus their plain arithmetic mean (a transparent composition, **not** a new
  inference).
* :class:`PassportMetadata` — the provenance of every source engine (versions and
  catalogue versions), the source-image count and the assembly timestamp.
* :class:`DevicePassport` — the thirteen-field document that composes all of the
  above with the passport id/version, EcoID and the ordered reasoning/warnings.

Every object is a frozen, slotted dataclass with no HTTP/I-O concerns, so the
whole assembler is deterministic and independently testable — mirroring the
fusion, recoverability, material, environmental and decision domain layers it
composes.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime

__all__ = [
    "Classification",
    "ConfidenceSummary",
    "DecisionSummary",
    "DeviceIdentity",
    "DevicePassport",
    "EnvironmentalSummary",
    "FingerprintSummary",
    "MaterialSummary",
    "PassportMetadata",
]


@dataclass(frozen=True, slots=True)
class DeviceIdentity:
    """The resolved identity fields of the device, copied from fusion.

    Attributes:
        brand: Resolved brand/manufacturer (empty when unknown).
        model: Resolved model identifier (empty when unknown).
        serial_number: Resolved serial number (empty when unknown).
        imei: Resolved IMEI (empty when unknown).
        mac_address: Resolved MAC address (empty when unknown).
    """

    brand: str
    model: str
    serial_number: str
    imei: str
    mac_address: str

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation of the identity block."""
        return {
            "brand": self.brand,
            "model": self.model,
            "serial_number": self.serial_number,
            "imei": self.imei,
            "mac_address": self.mac_address,
        }


@dataclass(frozen=True, slots=True)
class Classification:
    """The resolved device classification, copied from fusion.

    Attributes:
        device_type: The resolved device type (empty when fusion could not
            determine it).
        confidence: Fusion's confidence ``[0, 1]`` in the resolved device type.
        has_conflicts: Whether fusion detected any cross-module disagreement.
    """

    device_type: str
    confidence: float
    has_conflicts: bool

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation of the classification."""
        return {
            "device_type": self.device_type,
            "confidence": self.confidence,
            "has_conflicts": self.has_conflicts,
        }


@dataclass(frozen=True, slots=True)
class DecisionSummary:
    """The circular decision recommendation, summarized for the passport.

    Attributes:
        recommended_action: The advised end-of-life disposition (wire value).
        priority: The triage priority of acting on the recommendation.
        confidence: Aggregated confidence ``[0, 1]`` in the recommendation.
        winning_rule_id: Identifier of the rule that determined the
            recommendation, or empty when only the catalogue fallback applied.
        triggered_count: Number of rules that matched the consolidated evidence.
    """

    recommended_action: str
    priority: str
    confidence: float
    winning_rule_id: str
    triggered_count: int

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation of the decision summary."""
        return {
            "recommended_action": self.recommended_action,
            "priority": self.priority,
            "confidence": self.confidence,
            "winning_rule_id": self.winning_rule_id,
            "triggered_count": self.triggered_count,
        }


@dataclass(frozen=True, slots=True)
class MaterialSummary:
    """The material estimate totals, summarized for the passport.

    Attributes:
        material_count: Number of recovered materials in the estimate.
        total_mass_g: Estimated total mass of every listed material (grams).
        recoverable_mass_g: Estimated mass flagged recoverable (grams).
        hazardous_mass_g: Estimated mass flagged hazardous (grams).
        confidence: Aggregated confidence ``[0, 1]`` in the material estimate.
    """

    material_count: int
    total_mass_g: float
    recoverable_mass_g: float
    hazardous_mass_g: float
    confidence: float

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation of the material summary."""
        return {
            "material_count": self.material_count,
            "total_mass_g": self.total_mass_g,
            "recoverable_mass_g": self.recoverable_mass_g,
            "hazardous_mass_g": self.hazardous_mass_g,
            "confidence": self.confidence,
        }


@dataclass(frozen=True, slots=True)
class EnvironmentalSummary:
    """The avoided-burden headline metrics, summarized for the passport.

    Attributes:
        carbon_saved_kg: Total carbon avoided (kg CO₂e).
        energy_saved_mj: Total primary energy avoided (megajoules).
        water_saved_l: Total freshwater avoided (litres).
        landfill_diversion_kg: Recoverable mass diverted from landfill (kg).
        critical_material_recovery_kg: Recovered critical-category mass (kg).
        circularity_index: Normalized ``[0, 1]`` circularity index.
        hazard_reduction_score: Normalized ``[0, 1]`` hazard-reduction score.
        confidence: Aggregated confidence ``[0, 1]`` in the estimate.
    """

    carbon_saved_kg: float
    energy_saved_mj: float
    water_saved_l: float
    landfill_diversion_kg: float
    critical_material_recovery_kg: float
    circularity_index: float
    hazard_reduction_score: float
    confidence: float

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation of the environmental summary."""
        return {
            "carbon_saved_kg": self.carbon_saved_kg,
            "energy_saved_mj": self.energy_saved_mj,
            "water_saved_l": self.water_saved_l,
            "landfill_diversion_kg": self.landfill_diversion_kg,
            "critical_material_recovery_kg": self.critical_material_recovery_kg,
            "circularity_index": self.circularity_index,
            "hazard_reduction_score": self.hazard_reduction_score,
            "confidence": self.confidence,
        }


@dataclass(frozen=True, slots=True)
class FingerprintSummary:
    """The hash-backed identity anchor and its encoder provenance.

    Attributes:
        fingerprint: Hash-backed identifier (SHA-256 hex of the normalized
            embedding); empty when no fingerprint was available.
        dimension: Length of the embedding the fingerprint was derived from.
        encoder_name: Name of the encoder that produced the embedding.
        encoder_version: Version of that encoder.
        metric: Default similarity metric recorded for the fingerprint.
    """

    fingerprint: str
    dimension: int
    encoder_name: str
    encoder_version: str
    metric: str

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation of the fingerprint summary."""
        return {
            "fingerprint": self.fingerprint,
            "dimension": self.dimension,
            "encoder_name": self.encoder_name,
            "encoder_version": self.encoder_version,
            "metric": self.metric,
        }


@dataclass(frozen=True, slots=True)
class ConfidenceSummary:
    """The upstream confidences gathered onto one axis.

    Every value here is copied verbatim from an upstream report; :attr:`overall`
    is their plain arithmetic mean — a transparent composition, **not** a new
    inference. The passport derives no confidence of its own; it only collects
    and averages what its inputs already reported.

    Attributes:
        identity_confidence: Fusion's aggregate confidence in the resolved
            identity.
        decision_confidence: The circular decision report's confidence.
        material_confidence: The material report's overall confidence.
        environmental_confidence: The environmental report's confidence.
        overall: The arithmetic mean of the four upstream confidences (rounded).
    """

    identity_confidence: float
    decision_confidence: float
    material_confidence: float
    environmental_confidence: float
    overall: float

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation of the confidence summary."""
        return {
            "identity_confidence": self.identity_confidence,
            "decision_confidence": self.decision_confidence,
            "material_confidence": self.material_confidence,
            "environmental_confidence": self.environmental_confidence,
            "overall": self.overall,
        }


@dataclass(frozen=True, slots=True)
class PassportMetadata:
    """Provenance of every source engine that fed the passport.

    Attributes:
        passport_engine_version: Version of the passport builder that assembled
            this document.
        schema_version: Version of the external schema the passport was
            assembled and validated under.
        fusion_engine_version: Version of the fusion engine that produced the
            device context.
        decision_engine_version: Version of the circular decision engine.
        decision_rules_version: Version of the circular rule catalogue used.
        material_engine_version: Version of the material engine.
        material_profile_version: Version of the material profile library used.
        environmental_engine_version: Version of the environmental engine.
        environmental_factors_version: Version of the conversion-factor
            catalogue used.
        source_image_count: Number of source images the fused context recorded.
        created_at: UTC timestamp the passport was assembled (``None`` when the
            service was constructed without a clock), as an ISO-8601 string.
    """

    passport_engine_version: str
    schema_version: str
    fusion_engine_version: str
    decision_engine_version: str
    decision_rules_version: str
    material_engine_version: str
    material_profile_version: str
    environmental_engine_version: str
    environmental_factors_version: str
    source_image_count: int
    created_at: datetime | None = None

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation of the metadata block."""
        return {
            "passport_engine_version": self.passport_engine_version,
            "schema_version": self.schema_version,
            "fusion_engine_version": self.fusion_engine_version,
            "decision_engine_version": self.decision_engine_version,
            "decision_rules_version": self.decision_rules_version,
            "material_engine_version": self.material_engine_version,
            "material_profile_version": self.material_profile_version,
            "environmental_engine_version": self.environmental_engine_version,
            "environmental_factors_version": self.environmental_factors_version,
            "source_image_count": self.source_image_count,
            "created_at": (
                self.created_at.isoformat() if self.created_at is not None else None
            ),
        }


@dataclass(frozen=True, slots=True)
class DevicePassport:
    """The immutable device passport composed from the upstream reports.

    Produced by the :class:`~device_ai.passport.service.PassportService` from the
    fused context and its downstream reports. It is a **composition** of existing
    evidence — a single, self-describing document an operator (or a later
    blockchain/QR/reporting layer, out of scope here) can consume — not a new
    inference. Its thirteen fields are exactly the sections the external schema
    requires.

    Attributes:
        passport_id: Deterministic content-addressed identifier
            (``ET-PP-XXXXXXXXXXXX``) derived from the device's stable identity and
            recommendation; the same device and reports always yield the same id.
        passport_version: Semantic version of the passport structure.
        eco_id: Public EcoID carried over from the device context (empty when the
            context had no fingerprint).
        device_identity: The resolved identity fields.
        classification: The resolved device type and its confidence.
        decision_summary: The circular decision recommendation summary.
        material_summary: The material estimate totals.
        environmental_summary: The avoided-burden headline metrics.
        fingerprint_summary: The hash-backed identity anchor and encoder
            provenance.
        confidence_summary: The gathered upstream confidences and their mean.
        metadata: The provenance of every source engine and the timestamp.
        reasoning: Ordered, human-readable reasons composed from the inputs.
        warnings: Ordered operator-facing cautions composed from the inputs.
    """

    passport_id: str
    passport_version: str
    eco_id: str
    device_identity: DeviceIdentity
    classification: Classification
    decision_summary: DecisionSummary
    material_summary: MaterialSummary
    environmental_summary: EnvironmentalSummary
    fingerprint_summary: FingerprintSummary
    confidence_summary: ConfidenceSummary
    metadata: PassportMetadata
    reasoning: tuple[str, ...]
    warnings: tuple[str, ...]

    @property
    def reasoning_count(self) -> int:
        """Return the number of composed reasoning entries."""
        return len(self.reasoning)

    @property
    def warning_count(self) -> int:
        """Return the number of composed warnings."""
        return len(self.warnings)

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation of the passport.

        The keys are emitted in a fixed, logical order (the thirteen schema
        sections), so the mapping is a deterministic function of the inputs.

        Returns:
            A plain ``dict`` with the passport id/version, EcoID, every nested
            section as its own mapping and the ordered reasoning/warnings.
        """
        return {
            "passport_id": self.passport_id,
            "passport_version": self.passport_version,
            "eco_id": self.eco_id,
            "device_identity": self.device_identity.to_dict(),
            "classification": self.classification.to_dict(),
            "decision_summary": self.decision_summary.to_dict(),
            "material_summary": self.material_summary.to_dict(),
            "environmental_summary": self.environmental_summary.to_dict(),
            "fingerprint_summary": self.fingerprint_summary.to_dict(),
            "confidence_summary": self.confidence_summary.to_dict(),
            "metadata": self.metadata.to_dict(),
            "reasoning": list(self.reasoning),
            "warnings": list(self.warnings),
        }

    def to_json(self, *, indent: int | None = None) -> str:
        """Return a deterministic JSON serialization of the passport.

        Serialization is canonical: keys are sorted, non-ASCII is preserved and
        separators are fixed, so the same passport always serializes to the exact
        same bytes (suitable for hashing, diffing or a future anchor). Because
        :meth:`to_dict` is itself a pure function of the inputs, the only source
        of variation is the optional ``created_at`` timestamp in the metadata.

        Args:
            indent: When given, pretty-print with this indent (still canonical);
                when ``None`` (the default), emit the most compact canonical form.

        Returns:
            The canonical JSON string.
        """
        separators = (",", ":") if indent is None else (",", ": ")
        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=separators,
            indent=indent,
        )
