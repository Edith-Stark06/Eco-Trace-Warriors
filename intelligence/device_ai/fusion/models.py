"""Fusion domain models (milestone M1.7).

The multi-modal fusion engine merges the outputs of the independent AI modules
(detection, fingerprint, OCR) into a single, normalized, immutable
:class:`DeviceContext`. The value objects here are the vocabulary that makes
that merge possible:

* :class:`FusionAttribute` — the shared attribute space every module maps its
  native fields onto (so a detector ``brand`` and an OCR ``manufacturer`` become
  comparable claims about the same thing).
* :class:`Claim` — one module's assertion of a value for one attribute, with the
  confidence behind it.
* :class:`Evidence` — everything one AI module contributes: its identity, an
  overall confidence and the set of claims it makes. Each module has a builder
  (``Evidence.from_detection`` / ``from_fingerprint`` / ``from_ocr`` /
  ``from_ocr_identity``) so the engine never reaches into a module's internals.
* :class:`Conflict` — a disagreement between modules on one attribute, carrying
  the competing claims and the value fusion resolved to.
* :class:`ResolvedAttribute` — the fused value of one attribute plus its
  aggregated confidence and the modules that support it.
* :class:`DeviceContext` — the normalized, immutable unified device produced by
  the engine and consumed by downstream AI modules.

Every object is a frozen, slotted dataclass with no HTTP/I-O concerns, so the
whole engine is deterministic and independently testable — mirroring the
fingerprint and OCR domain layers it builds on.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # Type-only imports keep the fusion core free of a hard
    # runtime coupling to the modules it fuses (results are passed in, and the
    # builders below import lazily only when actually invoked).
    from ..fingerprint.models import DeviceFingerprint
    from ..inference.predictor import DetectionResult
    from ..ocr.models import OCRExtraction, OCRIdentity


# Values a module may emit that mean "nothing was determined" and must never
# become a claim (they would otherwise manufacture spurious conflicts).
_UNKNOWN_VALUES: frozenset[str] = frozenset({"", "unknown", "n/a", "none"})

# Confidence assigned to the device_type/brand provenance a fingerprint carries.
# A fingerprint is a deterministic identity anchor, not a classifier, so its
# copied provenance corroborates other evidence only at a modest, fixed weight.
_FINGERPRINT_PROVENANCE_CONFIDENCE = 0.50

# Confidence assigned to OCR identity fields when only the confidence-less
# :class:`OCRIdentity` projection is available (the richer ``from_ocr`` builder
# uses each field's own confidence instead).
_OCR_IDENTITY_DEFAULT_CONFIDENCE = 0.80


def _is_meaningful(value: str) -> bool:
    """Return whether ``value`` is a real claim (not empty/unknown sentinel)."""
    return value.strip().casefold() not in _UNKNOWN_VALUES


def _mean(values: Sequence[float]) -> float:
    """Return the arithmetic mean of ``values`` (``0.0`` when empty)."""
    return sum(values) / len(values) if values else 0.0


class FusionAttribute(str, Enum):
    """The shared attribute space every module maps its native fields onto.

    A ``str`` enum so members serialize to their wire value directly and can be
    constructed from a settings/API string (e.g. ``"device_type"``).
    """

    DEVICE_TYPE = "device_type"
    BRAND = "brand"
    MODEL = "model"
    SERIAL_NUMBER = "serial_number"
    IMEI = "imei"
    MAC_ADDRESS = "mac_address"

    @classmethod
    def values(cls) -> list[str]:
        """Return the wire values of every attribute, in declaration order."""
        return [member.value for member in cls]


class EvidenceKind(str, Enum):
    """Which AI module a piece of :class:`Evidence` came from."""

    DETECTION = "detection"
    FINGERPRINT = "fingerprint"
    OCR = "ocr"


@dataclass(frozen=True, slots=True)
class Claim:
    """One module's assertion of a value for a single attribute.

    Attributes:
        attribute: The attribute this claim is about.
        value: The claimed value, exactly as the module reported it.
        confidence: The module's confidence in the value, in ``[0, 1]``.
        source: The module that made the claim.
    """

    attribute: FusionAttribute
    value: str
    confidence: float
    source: EvidenceKind

    @property
    def key(self) -> str:
        """Return the normalized comparison key for the claimed value.

        Case- and whitespace-insensitive, so ``"Dell"`` and ``" dell "`` are the
        same claim while ``"Dell"`` and ``"HP"`` conflict.
        """
        return " ".join(self.value.split()).casefold()

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation of the claim."""
        return {
            "attribute": self.attribute.value,
            "value": self.value,
            "confidence": self.confidence,
            "source": self.source.value,
        }


@dataclass(frozen=True, slots=True)
class Evidence:
    """Everything one AI module contributes to the fusion.

    Attributes:
        source: Which module produced this evidence.
        module_name: The module's machine-readable name (e.g. ``"detector"``).
        module_version: The module/artifact version.
        confidence: An overall confidence summarizing the module's claims.
        claims: The attribute claims the module makes (may be empty when the
            module contributes only an identity anchor, e.g. a fingerprint with
            no provenance).
    """

    source: EvidenceKind
    module_name: str
    module_version: str
    confidence: float
    claims: tuple[Claim, ...] = ()

    def claim_for(self, attribute: FusionAttribute) -> Claim | None:
        """Return this module's claim for ``attribute``, or ``None``."""
        for claim in self.claims:
            if claim.attribute is attribute:
                return claim
        return None

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation of the evidence."""
        return {
            "source": self.source.value,
            "module_name": self.module_name,
            "module_version": self.module_version,
            "confidence": self.confidence,
            "claims": [claim.to_dict() for claim in self.claims],
        }

    # -- Builders: one per module, so the engine never touches internals -----

    @classmethod
    def from_detection(cls, result: DetectionResult) -> Evidence:
        """Build detection evidence (device type + brand) from a result.

        Both the device type and the brand share the detector's reported
        confidence in the dominant detection. Placeholder brands (``"Unknown"``)
        are dropped rather than claimed.

        Args:
            result: The detector's aggregated output.

        Returns:
            The detection :class:`Evidence`.
        """
        claims: list[Claim] = []
        if _is_meaningful(result.device_type):
            claims.append(
                Claim(
                    FusionAttribute.DEVICE_TYPE,
                    result.device_type,
                    result.confidence,
                    EvidenceKind.DETECTION,
                )
            )
        if _is_meaningful(result.brand):
            claims.append(
                Claim(
                    FusionAttribute.BRAND,
                    result.brand,
                    result.confidence,
                    EvidenceKind.DETECTION,
                )
            )
        return cls(
            source=EvidenceKind.DETECTION,
            module_name="detector",
            module_version="",
            confidence=result.confidence,
            claims=tuple(claims),
        )

    @classmethod
    def from_ocr(cls, extraction: OCRExtraction) -> Evidence:
        """Build OCR evidence from a full extraction (per-field confidences).

        Each extracted identity field is mapped onto its fusion attribute using
        the field's own confidence, so a high-confidence serial and a
        low-confidence model contribute at their true weights. Non-identity
        fields (QR/barcode payloads) are ignored — they are provenance, not
        device attributes.

        Args:
            extraction: The OCR engine's structured extraction.

        Returns:
            The OCR :class:`Evidence`.
        """
        from ..ocr.models import FieldType

        mapping = {
            FieldType.MANUFACTURER: FusionAttribute.BRAND,
            FieldType.MODEL: FusionAttribute.MODEL,
            FieldType.SERIAL_NUMBER: FusionAttribute.SERIAL_NUMBER,
            FieldType.IMEI: FusionAttribute.IMEI,
            FieldType.MAC_ADDRESS: FusionAttribute.MAC_ADDRESS,
        }
        claims: list[Claim] = []
        for extracted in extraction.fields:
            attribute = mapping.get(extracted.field_type)
            if attribute is None or not _is_meaningful(extracted.value):
                continue
            claims.append(
                Claim(
                    attribute,
                    extracted.value,
                    extracted.confidence,
                    EvidenceKind.OCR,
                )
            )
        return cls(
            source=EvidenceKind.OCR,
            module_name=extraction.engine_name,
            module_version=extraction.engine_version,
            confidence=_mean([claim.confidence for claim in claims]),
            claims=tuple(claims),
        )

    @classmethod
    def from_ocr_identity(
        cls,
        identity: OCRIdentity,
        *,
        confidence: float = _OCR_IDENTITY_DEFAULT_CONFIDENCE,
        module_name: str = "ocr",
        module_version: str = "",
    ) -> Evidence:
        """Build OCR evidence from the confidence-less identity projection.

        A fallback for callers that only hold an :class:`OCRIdentity` (e.g. the
        one a fingerprint already carries): every present field is claimed at a
        single shared ``confidence``.

        Args:
            identity: The OCR identity projection.
            confidence: Confidence assigned to each present field.
            module_name: Name recorded on the evidence.
            module_version: Version recorded on the evidence.

        Returns:
            The OCR :class:`Evidence`.
        """
        attribute_by_key = {
            "manufacturer": FusionAttribute.BRAND,
            "model": FusionAttribute.MODEL,
            "serial_number": FusionAttribute.SERIAL_NUMBER,
            "imei": FusionAttribute.IMEI,
            "mac_address": FusionAttribute.MAC_ADDRESS,
        }
        claims = [
            Claim(attribute_by_key[key], value, confidence, EvidenceKind.OCR)
            for key, value in identity.non_empty().items()
            if key in attribute_by_key and _is_meaningful(value)
        ]
        return cls(
            source=EvidenceKind.OCR,
            module_name=module_name,
            module_version=module_version,
            confidence=confidence if claims else 0.0,
            claims=tuple(claims),
        )

    @classmethod
    def from_fingerprint(cls, fingerprint: DeviceFingerprint) -> Evidence:
        """Build fingerprint evidence from a stored/generated fingerprint.

        A fingerprint is primarily an identity anchor (its ``eco_id`` and
        hash-backed ``fingerprint`` are read by the engine directly). Any
        device type / brand provenance it copied from detection, and any
        OCR-derived identity fields it carries, are surfaced as low-weight
        corroborating claims so they can agree with — or flag a conflict
        against — fresh module evidence without dominating it.

        Args:
            fingerprint: The device fingerprint.

        Returns:
            The fingerprint :class:`Evidence`.
        """
        conf = _FINGERPRINT_PROVENANCE_CONFIDENCE
        claims: list[Claim] = []
        if _is_meaningful(fingerprint.device_type):
            claims.append(
                Claim(
                    FusionAttribute.DEVICE_TYPE,
                    fingerprint.device_type,
                    conf,
                    EvidenceKind.FINGERPRINT,
                )
            )
        if _is_meaningful(fingerprint.brand):
            claims.append(
                Claim(
                    FusionAttribute.BRAND,
                    fingerprint.brand,
                    conf,
                    EvidenceKind.FINGERPRINT,
                )
            )
        identity_map = {
            "manufacturer": FusionAttribute.BRAND,
            "model": FusionAttribute.MODEL,
            "serial_number": FusionAttribute.SERIAL_NUMBER,
            "imei": FusionAttribute.IMEI,
            "mac_address": FusionAttribute.MAC_ADDRESS,
        }
        claimed = {claim.attribute for claim in claims}
        for key, value in fingerprint.identity.items():
            attribute = identity_map.get(key)
            if attribute is None or attribute in claimed or not _is_meaningful(value):
                continue
            claims.append(Claim(attribute, value, conf, EvidenceKind.FINGERPRINT))
            claimed.add(attribute)
        return cls(
            source=EvidenceKind.FINGERPRINT,
            module_name="fingerprint",
            module_version=fingerprint.encoder_version,
            confidence=_mean([claim.confidence for claim in claims]) if claims else 1.0,
            claims=tuple(claims),
        )


@dataclass(frozen=True, slots=True)
class ResolvedAttribute:
    """The fused value of one attribute across all evidence.

    Attributes:
        attribute: Which attribute this is.
        value: The winning value fusion resolved to.
        confidence: Aggregated confidence in ``[0, 1]`` (raised by agreement,
            damped by disagreement).
        sources: The modules whose claims supported the winning value.
        conflicted: Whether at least one module claimed a different value.
    """

    attribute: FusionAttribute
    value: str
    confidence: float
    sources: tuple[EvidenceKind, ...]
    conflicted: bool = False

    @property
    def agreed(self) -> bool:
        """Whether two or more modules independently supported this value."""
        return len(self.sources) > 1 and not self.conflicted

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation of the resolved attribute."""
        return {
            "attribute": self.attribute.value,
            "value": self.value,
            "confidence": self.confidence,
            "sources": [source.value for source in self.sources],
            "conflicted": self.conflicted,
            "agreed": self.agreed,
        }


@dataclass(frozen=True, slots=True)
class Conflict:
    """A disagreement between modules on a single attribute.

    Attributes:
        attribute: The attribute the modules disagree on.
        resolved_value: The value fusion selected (the highest-support claim).
        claims: Every competing claim (at least two distinct values), ordered by
            descending confidence.
    """

    attribute: FusionAttribute
    resolved_value: str
    claims: tuple[Claim, ...]

    @property
    def sources(self) -> tuple[EvidenceKind, ...]:
        """Return the modules involved in the conflict, in claim order."""
        return tuple(claim.source for claim in self.claims)

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation of the conflict."""
        return {
            "attribute": self.attribute.value,
            "resolved_value": self.resolved_value,
            "claims": [claim.to_dict() for claim in self.claims],
        }


@dataclass(frozen=True, slots=True)
class DeviceContext:
    """The normalized, immutable unified device produced by the engine.

    Downstream AI modules (recoverability, material, carbon, passport) consume
    this instead of reaching back into detection/fingerprint/OCR individually.

    Attributes:
        eco_id: Public EcoID carried over from the fingerprint (empty when no
            fingerprint evidence was fused).
        fingerprint: Hash-backed fingerprint identifier (empty when absent).
        attributes: The resolved attributes, in :class:`FusionAttribute` order.
        confidence: Aggregate confidence across the resolved attributes.
        evidence: The raw per-module contributions (provenance).
        conflicts: Detected cross-module disagreements (empty on full agreement).
        source_hashes: SHA-256 content hashes of the source images (provenance).
        engine_version: Version of the fusion engine that produced the context.
        created_at: UTC timestamp the context was produced (``None`` when the
            engine was constructed without a clock).
    """

    eco_id: str
    fingerprint: str
    attributes: tuple[ResolvedAttribute, ...]
    confidence: float
    evidence: tuple[Evidence, ...]
    conflicts: tuple[Conflict, ...]
    source_hashes: tuple[str, ...]
    engine_version: str
    created_at: datetime | None = None

    def get(self, attribute: FusionAttribute) -> ResolvedAttribute | None:
        """Return the resolved attribute of ``attribute``, or ``None``."""
        for resolved in self.attributes:
            if resolved.attribute is attribute:
                return resolved
        return None

    def value_of(self, attribute: FusionAttribute) -> str:
        """Return the resolved value of ``attribute``, or ``""`` when absent."""
        found = self.get(attribute)
        return found.value if found is not None else ""

    def confidence_of(self, attribute: FusionAttribute) -> float:
        """Return the resolved confidence of ``attribute``, or ``0.0``."""
        found = self.get(attribute)
        return found.confidence if found is not None else 0.0

    @property
    def device_type(self) -> str:
        """Resolved device type (empty when unknown)."""
        return self.value_of(FusionAttribute.DEVICE_TYPE)

    @property
    def brand(self) -> str:
        """Resolved brand/manufacturer (empty when unknown)."""
        return self.value_of(FusionAttribute.BRAND)

    @property
    def model(self) -> str:
        """Resolved model identifier (empty when unknown)."""
        return self.value_of(FusionAttribute.MODEL)

    @property
    def serial_number(self) -> str:
        """Resolved serial number (empty when unknown)."""
        return self.value_of(FusionAttribute.SERIAL_NUMBER)

    @property
    def imei(self) -> str:
        """Resolved IMEI (empty when unknown)."""
        return self.value_of(FusionAttribute.IMEI)

    @property
    def mac_address(self) -> str:
        """Resolved MAC address (empty when unknown)."""
        return self.value_of(FusionAttribute.MAC_ADDRESS)

    @property
    def has_conflicts(self) -> bool:
        """Whether the engine detected any cross-module disagreement."""
        return bool(self.conflicts)

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation of the device context.

        Returns:
            A plain ``dict`` with a flat identity block (for convenient
            consumption), the resolved attributes, conflicts, evidence
            provenance and an ISO-8601 ``created_at`` (or ``None``).
        """
        return {
            "eco_id": self.eco_id,
            "fingerprint": self.fingerprint,
            "device_type": self.device_type,
            "brand": self.brand,
            "model": self.model,
            "serial_number": self.serial_number,
            "imei": self.imei,
            "mac_address": self.mac_address,
            "confidence": self.confidence,
            "attributes": [resolved.to_dict() for resolved in self.attributes],
            "conflicts": [conflict.to_dict() for conflict in self.conflicts],
            "evidence": [item.to_dict() for item in self.evidence],
            "source_hashes": list(self.source_hashes),
            "engine_version": self.engine_version,
            "created_at": (
                self.created_at.isoformat() if self.created_at is not None else None
            ),
        }
