"""EcoTrace Device Passport Verification & Trust Layer (P5.7).

Provides:
- Deterministic canonical JSON serialization of DevicePassport.
- Cryptographic SHA-256 fingerprinting.
- Comprehensive verification suite:
  - Identity facet verification
  - Detection facet verification
  - Lifecycle state machine verification
  - Chronological audit history verification
  - Provenance integrity verification
  - Enrichment consistency verification
- Structured, non-crashing verification results.
- Strictly read-only guarantees (zero database writes, zero event emissions, zero record mutations).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
import hashlib
import json
import math
from typing import Any

from ..inference.class_map import CANONICAL_CLASSES
from .enrichment_models import DeviceEnrichment
from .models import DeviceEvent, DeviceEventType, DeviceRecord, RegistrationState
from .passport import DevicePassport, build_device_passport


def _utc_now() -> datetime:
    return datetime.now(UTC)


class VerificationCheckStatus(str, Enum):
    """Status of an individual verification check."""

    PASS = "PASS"
    WARNING = "WARNING"
    FAIL = "FAIL"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class VerificationStatus(str, Enum):
    """Overall status of a passport verification evaluation."""

    VERIFIED = "VERIFIED"
    WARNING = "WARNING"
    INVALID = "INVALID"


@dataclass(frozen=True, slots=True)
class VerificationCheckDetail:
    """Detailed result for a single verification check."""

    name: str
    status: VerificationCheckStatus
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status.value,
            "message": self.message,
            "details": self.details,
        }


@dataclass(frozen=True, slots=True)
class PassportVerificationResult:
    """Aggregated result of passport integrity, lifecycle, and provenance verification."""

    success: bool
    device_id: str
    verification_status: VerificationStatus
    passport_fingerprint: str
    checks: dict[str, str]
    check_details: list[VerificationCheckDetail]
    warnings: list[str]
    errors: list[str]
    verified_at: str = field(default_factory=lambda: _utc_now().isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "device_id": self.device_id,
            "verification_status": self.verification_status.value,
            "passport_fingerprint": self.passport_fingerprint,
            "checks": self.checks,
            "check_details": [c.to_dict() for c in self.check_details],
            "warnings": self.warnings,
            "errors": self.errors,
            "verified_at": self.verified_at,
        }


def canonicalize_passport(passport: DevicePassport) -> bytes:
    """Produce deterministic, canonical byte representation of a DevicePassport.

    Rules:
    - Encodes all semantic domain facets.
    - Excludes transient generation timestamps (generated_at) to ensure reproducible fingerprinting.
    - Keys are strictly sorted at all hierarchy levels.
    - Compact delimiters (':', ',') with UTF-8 encoding.
    - Enums and floating points serialized deterministically.
    """
    canonical_dict = {
        "device_id": passport.device_id,
        "eco_id": passport.eco_id,
        "identity": {
            "device_id": passport.identity.device_id,
            "eco_id": passport.identity.eco_id,
            "device_type": passport.identity.device_type,
            "class_id": passport.identity.class_id,
            "capture_id": passport.identity.capture_id,
            "registration_timestamp": passport.identity.registration_timestamp,
            "created_at": passport.identity.created_at,
            "updated_at": passport.identity.updated_at,
        },
        "detection": {
            "confidence": round(float(passport.detection.confidence), 4),
            "confidence_state": passport.detection.confidence_state,
            "bounding_box": [int(x) for x in passport.detection.bounding_box],
            "inference_mode": passport.detection.inference_mode,
            "model_version": passport.detection.model_version,
        },
        "brand": {
            "brand": passport.brand.brand,
            "status": passport.brand.status,
            "source": passport.brand.source,
            "confidence": round(float(passport.brand.confidence), 4) if passport.brand.confidence is not None else None,
            "raw_text": passport.brand.raw_text,
        },
        "condition": {
            "condition": passport.condition.condition,
            "status": passport.condition.status,
            "source": passport.condition.source,
            "notes": passport.condition.notes,
        },
        "material": {
            "materials": [
                {
                    "material": m.material,
                    "category": m.category,
                    "mass_g": round(float(m.mass_g), 2),
                    "recoverable": bool(m.recoverable),
                    "hazardous": bool(m.hazardous),
                    "basis": m.basis,
                }
                for m in passport.material.materials
            ],
            "total_mass_g": round(float(passport.material.total_mass_g), 2) if passport.material.total_mass_g is not None else None,
            "source": passport.material.source,
            "version": passport.material.version,
            "notes": passport.material.notes,
        },
        "carbon": {
            "carbon_score": round(float(passport.carbon.carbon_score), 4) if passport.carbon.carbon_score is not None else None,
            "contributing_factors": {
                k: round(float(v), 4) for k, v in sorted(passport.carbon.contributing_factors.items())
            },
            "methodology": passport.carbon.methodology,
            "source": passport.carbon.source,
            "version": passport.carbon.version,
            "notes": passport.carbon.notes,
        },
        "lifecycle": {
            "current_state": passport.lifecycle.current_state,
            "is_confirmed": bool(passport.lifecycle.is_confirmed),
            "is_registered": bool(passport.lifecycle.is_registered),
            "is_enriched": bool(passport.lifecycle.is_enriched),
        },
        "audit": {
            "total_events": int(passport.audit.total_events),
            "events": [
                {
                    "event_id": str(e.get("event_id", "")),
                    "device_id": str(e.get("device_id", "")),
                    "event_type": str(e.get("event_type", "")),
                    "timestamp": str(e.get("timestamp", "")),
                    "capture_id": e.get("capture_id"),
                    "metadata": {k: v for k, v in sorted(e.get("metadata", {}).items())} if isinstance(e.get("metadata"), dict) else {},
                }
                for e in sorted(passport.audit.events, key=lambda x: (str(x.get("timestamp", "")), str(x.get("event_id", ""))))
            ],
        },
    }

    return json.dumps(
        canonical_dict,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")


def fingerprint_passport(passport: DevicePassport) -> str:
    """Compute deterministic SHA-256 hexadecimal fingerprint of a DevicePassport."""
    raw_bytes = canonicalize_passport(passport)
    return hashlib.sha256(raw_bytes).hexdigest().lower()


def _verify_identity_facet(record: DeviceRecord, passport: DevicePassport) -> VerificationCheckDetail:
    """Validate device identity, taxonomy, and identifier coherence."""
    errors = []

    if passport.device_id != record.device_id:
        errors.append(f"Passport device_id '{passport.device_id}' does not match record device_id '{record.device_id}'.")

    if record.class_id < 0 or record.class_id >= len(CANONICAL_CLASSES):
        errors.append(f"Invalid class_id {record.class_id}; outside taxonomy bounds [0..{len(CANONICAL_CLASSES)-1}].")
    else:
        canonical_expected = CANONICAL_CLASSES[record.class_id]
        if record.device_type.lower() != canonical_expected.lower():
            errors.append(f"Device type '{record.device_type}' does not match canonical taxonomy '{canonical_expected}' for class_id {record.class_id}.")

    if passport.identity.class_id != record.class_id:
        errors.append(f"Passport class_id {passport.identity.class_id} differs from record class_id {record.class_id}.")

    if not record.capture_id:
        errors.append("Capture correlation ID is empty or missing.")

    if errors:
        return VerificationCheckDetail(
            name="identity",
            status=VerificationCheckStatus.FAIL,
            message="; ".join(errors),
            details={"errors": errors},
        )

    return VerificationCheckDetail(
        name="identity",
        status=VerificationCheckStatus.PASS,
        message="Device identity and canonical taxonomy verified.",
        details={"device_type": record.device_type, "class_id": record.class_id},
    )


def _verify_detection_facet(record: DeviceRecord, passport: DevicePassport) -> VerificationCheckDetail:
    """Validate computer vision detection values and bounding box boundaries."""
    errors = []

    if not (0.0 <= record.confidence <= 1.0):
        errors.append(f"Confidence score {record.confidence} outside valid range [0.0, 1.0].")

    if round(record.confidence, 4) != round(passport.detection.confidence, 4):
        errors.append(f"Passport confidence {passport.detection.confidence} differs from record confidence {record.confidence}.")

    bbox = record.bounding_box
    if len(bbox) != 4:
        errors.append(f"Bounding box must contain 4 coordinates; found {len(bbox)}.")
    else:
        x1, y1, x2, y2 = bbox
        if x1 > x2 or y1 > y2 or x1 < 0 or y1 < 0:
            errors.append(f"Invalid bounding box coordinates [{x1}, {y1}, {x2}, {y2}].")

    if record.inference_mode not in ("single_model", "ensemble", "mock"):
        errors.append(f"Unrecognized inference mode '{record.inference_mode}'.")

    if not record.model_version:
        errors.append("Model version tag is missing.")

    if errors:
        return VerificationCheckDetail(
            name="detection",
            status=VerificationCheckStatus.FAIL,
            message="; ".join(errors),
            details={"errors": errors},
        )

    return VerificationCheckDetail(
        name="detection",
        status=VerificationCheckStatus.PASS,
        message="Computer vision detection attributes verified.",
        details={"confidence": record.confidence, "bounding_box": list(record.bounding_box)},
    )


def _verify_lifecycle_facet(record: DeviceRecord, passport: DevicePassport) -> VerificationCheckDetail:
    """Validate lifecycle state machine rules and status flags."""
    errors = []
    warnings = []

    state = record.registration_state
    is_conf = state in (RegistrationState.CONFIRMED, RegistrationState.REGISTERED)
    is_reg = state == RegistrationState.REGISTERED
    enrichment_present = "enrichment" in record.metadata or record.carbon_score is not None

    if passport.lifecycle.is_confirmed != is_conf:
        errors.append(f"Passport is_confirmed={passport.lifecycle.is_confirmed} does not match record state '{state.value}'.")

    if passport.lifecycle.is_registered != is_reg:
        errors.append(f"Passport is_registered={passport.lifecycle.is_registered} does not match record state '{state.value}'.")

    # Invariant: DEVICE_ENRICHED is allowed only after registration
    if enrichment_present and state != RegistrationState.REGISTERED:
        errors.append(f"Device has enrichment data but lifecycle state is '{state.value}' (enrichment requires REGISTERED state).")

    if state == RegistrationState.DETECTED:
        warnings.append("Device is in initial DETECTED state; awaiting user confirmation and final registration.")

    if errors:
        return VerificationCheckDetail(
            name="lifecycle",
            status=VerificationCheckStatus.FAIL,
            message="; ".join(errors),
            details={"errors": errors, "warnings": warnings},
        )

    if warnings:
        return VerificationCheckDetail(
            name="lifecycle",
            status=VerificationCheckStatus.WARNING,
            message="; ".join(warnings),
            details={"warnings": warnings},
        )

    return VerificationCheckDetail(
        name="lifecycle",
        status=VerificationCheckStatus.PASS,
        message=f"Lifecycle state '{state.value}' consistent with state machine.",
        details={"state": state.value},
    )


def _verify_audit_history_facet(record: DeviceRecord, events: list[DeviceEvent], passport: DevicePassport) -> VerificationCheckDetail:
    """Validate chronological audit log integrity, device correlation, and transition progression."""
    errors = []
    warnings = []

    if not events:
        errors.append("Audit trail is empty; expected at least initial DEVICE_DETECTED event.")
        return VerificationCheckDetail(
            name="audit_history",
            status=VerificationCheckStatus.FAIL,
            message="; ".join(errors),
            details={"errors": errors},
        )

    # 1. Device ID matching
    for idx, evt in enumerate(events):
        if evt.device_id != record.device_id:
            errors.append(f"Event #{idx} (ID: {evt.event_id}) device_id '{evt.device_id}' does not match record '{record.device_id}'.")

    # 2. Chronological ordering
    for idx in range(len(events) - 1):
        if events[idx].timestamp > events[idx + 1].timestamp:
            errors.append(f"Chronological inversion between event #{idx} ({events[idx].timestamp}) and #{idx+1} ({events[idx+1].timestamp}).")

    # 3. State transition order validation
    # Allowed sequence: DETECTED -> CONFIRMED -> REGISTERED -> ENRICHED
    stage_rank = {
        DeviceEventType.DEVICE_DETECTED: 1,
        DeviceEventType.DEVICE_CONFIRMED: 2,
        DeviceEventType.DEVICE_REGISTERED: 3,
        DeviceEventType.DEVICE_ENRICHED: 4,
    }

    first_event_type = events[0].event_type
    if first_event_type != DeviceEventType.DEVICE_DETECTED:
        errors.append(f"Initial event must be DEVICE_DETECTED; found '{first_event_type.value if isinstance(first_event_type, DeviceEventType) else first_event_type}'.")

    seen_stages: set[DeviceEventType] = set()
    current_highest_rank = 0

    for idx, evt in enumerate(events):
        evt_type = evt.event_type if isinstance(evt.event_type, DeviceEventType) else DeviceEventType(evt.event_type)
        rank = stage_rank.get(evt_type, 0)

        # Regressive transition check (unless idempotent repeat of identical event)
        if rank < current_highest_rank:
            errors.append(f"Illegal backward lifecycle transition at event #{idx}: {evt_type.value} after higher stage.")
        else:
            # Check prerequisites
            if evt_type == DeviceEventType.DEVICE_CONFIRMED and DeviceEventType.DEVICE_DETECTED not in seen_stages:
                errors.append("DEVICE_CONFIRMED occurred without preceding DEVICE_DETECTED.")
            if evt_type == DeviceEventType.DEVICE_REGISTERED and DeviceEventType.DEVICE_CONFIRMED not in seen_stages:
                errors.append("DEVICE_REGISTERED occurred without preceding DEVICE_CONFIRMED.")
            if evt_type == DeviceEventType.DEVICE_ENRICHED and DeviceEventType.DEVICE_REGISTERED not in seen_stages:
                errors.append("DEVICE_ENRICHED occurred without preceding DEVICE_REGISTERED.")

            current_highest_rank = max(current_highest_rank, rank)
            seen_stages.add(evt_type)

    # 4. Invariant: If passport indicates enriched, DEVICE_ENRICHED event must exist
    if passport.lifecycle.is_enriched and DeviceEventType.DEVICE_ENRICHED not in seen_stages:
        errors.append("Device is marked enriched, but no DEVICE_ENRICHED audit event exists in history.")

    if errors:
        return VerificationCheckDetail(
            name="audit_history",
            status=VerificationCheckStatus.FAIL,
            message="; ".join(errors),
            details={"errors": errors},
        )

    if warnings:
        return VerificationCheckDetail(
            name="audit_history",
            status=VerificationCheckStatus.WARNING,
            message="; ".join(warnings),
            details={"warnings": warnings},
        )

    return VerificationCheckDetail(
        name="audit_history",
        status=VerificationCheckStatus.PASS,
        message=f"Audit trail verified: {len(events)} chronological events without sequence violations.",
        details={"total_events": len(events)},
    )


def _verify_provenance_facet(passport: DevicePassport) -> VerificationCheckDetail:
    """Validate that enrichment attributes identify genuine provenance and never fabricate physical data."""
    errors = []
    warnings = []

    # 1. Brand provenance
    brand_facet = passport.brand
    if brand_facet.status == "CONFIRMED":
        if brand_facet.source not in ("ocr", "manual_inspection"):
            errors.append(f"Brand confirmed with invalid source '{brand_facet.source}'; must be 'ocr' or 'manual_inspection'.")
        if not brand_facet.brand:
            errors.append("Brand status is CONFIRMED but brand name is empty.")
    elif brand_facet.status == "UNAVAILABLE":
        if brand_facet.source != "NONE":
            warnings.append(f"Brand unavailable with unexpected source '{brand_facet.source}'.")

    # 2. Condition provenance
    cond_facet = passport.condition
    if cond_facet.source not in ("manual_inspection", "pending_assessment", "NONE", "device_record"):
        errors.append(f"Unrecognized condition source '{cond_facet.source}'. Never infer physical wear from object detector.")

    # 3. Material provenance
    mat_facet = passport.material
    if mat_facet.materials:
        if mat_facet.source not in ("device_profile", "manual_inspection"):
            errors.append(f"Material composition has invalid source '{mat_facet.source}'; expected 'device_profile'.")
        for m in mat_facet.materials:
            if m.basis not in ("device_profile", "nominal_profile", "manual_input"):
                errors.append(f"Material item '{m.material}' has invalid basis '{m.basis}'.")

    # 4. Carbon provenance
    carb_facet = passport.carbon
    if carb_facet.carbon_score is not None:
        if carb_facet.source not in ("estimated_project_model", "device_record"):
            errors.append(f"Carbon burden has invalid source '{carb_facet.source}'. Never treat estimated carbon as measured facts.")
        if carb_facet.methodology not in ("avoided_burden_co2e", "manual_audit", None):
            errors.append(f"Carbon calculation has unrecognized methodology '{carb_facet.methodology}'.")

    if errors:
        return VerificationCheckDetail(
            name="provenance",
            status=VerificationCheckStatus.FAIL,
            message="; ".join(errors),
            details={"errors": errors},
        )

    if warnings:
        return VerificationCheckDetail(
            name="provenance",
            status=VerificationCheckStatus.WARNING,
            message="; ".join(warnings),
            details={"warnings": warnings},
        )

    return VerificationCheckDetail(
        name="provenance",
        status=VerificationCheckStatus.PASS,
        message="Provenance integrity verified across brand, condition, material, and carbon facets.",
        details={},
    )


def _verify_enrichment_consistency_facet(record: DeviceRecord, passport: DevicePassport) -> VerificationCheckDetail:
    """Validate consistency across DeviceRecord, DeviceEnrichment snapshot, and DevicePassport."""
    errors = []
    warnings = []

    enrichment_data = record.metadata.get("enrichment")
    if enrichment_data:
        try:
            enrichment = DeviceEnrichment.from_dict(enrichment_data)
        except Exception:
            enrichment = None
            errors.append("Enrichment metadata exists but failed structural validation.")

        if enrichment is not None:
            # Carbon score matching
            if enrichment.carbon.carbon_score is not None:
                if passport.carbon.carbon_score is None:
                    errors.append("Passport carbon score is None but enrichment snapshot has score.")
                elif not math.isclose(passport.carbon.carbon_score, enrichment.carbon.carbon_score, rel_tol=1e-3):
                    errors.append(f"Passport carbon score {passport.carbon.carbon_score} does not match enrichment score {enrichment.carbon.carbon_score}.")

            # Material mass sum matching
            if passport.material.materials:
                total_computed = sum(m.mass_g for m in passport.material.materials)
                if passport.material.total_mass_g is not None and not math.isclose(passport.material.total_mass_g, total_computed, rel_tol=1e-3):
                    errors.append(f"Material total_mass_g {passport.material.total_mass_g} does not match sum of individual items ({total_computed}).")
    else:
        # Un-enriched record
        if passport.brand.brand is not None:
            errors.append("Passport contains brand name on un-enriched record.")
        if passport.material.materials:
            errors.append("Passport contains material composition items on un-enriched record.")
        warnings.append("Device is not yet enriched with multi-facet intelligence.")

    if errors:
        return VerificationCheckDetail(
            name="enrichment",
            status=VerificationCheckStatus.FAIL,
            message="; ".join(errors),
            details={"errors": errors},
        )

    if warnings:
        return VerificationCheckDetail(
            name="enrichment",
            status=VerificationCheckStatus.WARNING,
            message="; ".join(warnings),
            details={"warnings": warnings},
        )

    return VerificationCheckDetail(
        name="enrichment",
        status=VerificationCheckStatus.PASS,
        message="Enrichment facets are consistent and mathematically sound.",
        details={},
    )


def verify_passport(
    record: DeviceRecord,
    events: list[DeviceEvent],
    passport: DevicePassport | None = None,
) -> PassportVerificationResult:
    """Execute complete deterministic verification of a DevicePassport.

    Strictly read-only: does not modify record or events, and performs zero storage writes.

    Args:
        record: Active domain DeviceRecord.
        events: Chronological list of DeviceEvent audit objects.
        passport: Optional pre-built DevicePassport. If None, built from record and events.

    Returns:
        A :class:`PassportVerificationResult` detailing checks, warnings, and errors.
    """
    if passport is None:
        passport = build_device_passport(record, events)

    fingerprint = fingerprint_passport(passport)

    check_details: list[VerificationCheckDetail] = [
        _verify_identity_facet(record, passport),
        _verify_detection_facet(record, passport),
        _verify_lifecycle_facet(record, passport),
        _verify_audit_history_facet(record, events, passport),
        _verify_provenance_facet(passport),
        _verify_enrichment_consistency_facet(record, passport),
    ]

    checks_map = {c.name: c.status.value for c in check_details}

    errors: list[str] = []
    warnings: list[str] = []

    for c in check_details:
        if c.status == VerificationCheckStatus.FAIL:
            errors.append(f"[{c.name.upper()}] {c.message}")
        elif c.status == VerificationCheckStatus.WARNING:
            warnings.append(f"[{c.name.upper()}] {c.message}")

    if errors:
        overall_status = VerificationStatus.INVALID
    elif warnings:
        overall_status = VerificationStatus.WARNING
    else:
        overall_status = VerificationStatus.VERIFIED

    return PassportVerificationResult(
        success=True,
        device_id=record.device_id,
        verification_status=overall_status,
        passport_fingerprint=fingerprint,
        checks=checks_map,
        check_details=check_details,
        warnings=warnings,
        errors=errors,
    )
