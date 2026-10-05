"""Tests for the fusion domain models and evidence builders (milestone M1.7).

These exercise the value objects and the per-module ``Evidence`` builders in
isolation (no engine): attribute mapping, unknown/placeholder rejection,
per-field confidence, the identity projection fallback, and serialization.
"""

from datetime import UTC, datetime

import pytest

from device_ai.fingerprint.models import DeviceFingerprint
from device_ai.fusion.models import (
    Claim,
    Conflict,
    DeviceContext,
    Evidence,
    EvidenceKind,
    FusionAttribute,
    ResolvedAttribute,
)
from device_ai.inference.predictor import DetectionResult
from device_ai.ocr.models import (
    ExtractedField,
    FieldSource,
    FieldType,
    OCRExtraction,
    OCRIdentity,
)

_CLOCK = datetime(2026, 8, 1, 12, 0, 0, tzinfo=UTC)


def _detection(device_type="Laptop", brand="Dell", confidence=0.9):
    return DetectionResult(
        device_type=device_type,
        brand=brand,
        confidence=confidence,
        detections=[],
    )


def _ocr_extraction(fields):
    return OCRExtraction(
        fields=tuple(fields),
        engine_name="ocr",
        engine_version="mock-ocr-m16-1.0.0",
        created_at=_CLOCK,
        source_hashes=("a" * 64,),
    )


def _field(field_type, value, confidence, source=FieldSource.TEXT):
    return ExtractedField(
        field_type=field_type,
        value=value,
        confidence=confidence,
        raw_text=value,
        source=source,
    )


def _fingerprint(**overrides):
    base = {
        "eco_id": "ET-2026-0000ABCD",
        "fingerprint": "f" * 64,
        "embedding": (0.5, 0.5, 0.5, 0.5),
        "dimension": 4,
        "encoder_name": "clip",
        "encoder_version": "mock-clip-1.0.0",
        "metric": "cosine",
        "created_at": _CLOCK,
        "source_hashes": ("b" * 64,),
        "device_type": "Laptop",
        "brand": "Dell",
        "identity": {},
    }
    base.update(overrides)
    return DeviceFingerprint(**base)


# --- FusionAttribute / Claim -------------------------------------------------


def test_fusion_attribute_values_are_in_declaration_order():
    assert FusionAttribute.values() == [
        "device_type",
        "brand",
        "model",
        "serial_number",
        "imei",
        "mac_address",
    ]


def test_claim_key_normalizes_case_and_whitespace():
    left = Claim(FusionAttribute.BRAND, "  Dell ", 0.9, EvidenceKind.DETECTION)
    right = Claim(FusionAttribute.BRAND, "dell", 0.8, EvidenceKind.OCR)
    assert left.key == right.key == "dell"


def test_claim_to_dict_shape():
    claim = Claim(FusionAttribute.DEVICE_TYPE, "Laptop", 0.9, EvidenceKind.DETECTION)
    assert claim.to_dict() == {
        "attribute": "device_type",
        "value": "Laptop",
        "confidence": 0.9,
        "source": "detection",
    }


# --- Evidence.from_detection -------------------------------------------------


def test_from_detection_maps_device_type_and_brand():
    evidence = Evidence.from_detection(_detection())
    assert evidence.source is EvidenceKind.DETECTION
    assert {claim.attribute for claim in evidence.claims} == {
        FusionAttribute.DEVICE_TYPE,
        FusionAttribute.BRAND,
    }
    assert evidence.claim_for(FusionAttribute.DEVICE_TYPE).confidence == 0.9


def test_from_detection_drops_unknown_brand_placeholder():
    evidence = Evidence.from_detection(_detection(brand="Unknown"))
    assert evidence.claim_for(FusionAttribute.BRAND) is None
    assert evidence.claim_for(FusionAttribute.DEVICE_TYPE) is not None


def test_from_detection_drops_empty_device_type():
    evidence = Evidence.from_detection(_detection(device_type="", brand=""))
    assert evidence.claims == ()


# --- Evidence.from_ocr -------------------------------------------------------


def test_from_ocr_maps_identity_fields_with_per_field_confidence():
    extraction = _ocr_extraction(
        [
            _field(FieldType.MANUFACTURER, "Dell", 0.95),
            _field(FieldType.MODEL, "XPS 15", 0.80),
            _field(FieldType.SERIAL_NUMBER, "ABC12345", 0.92),
        ]
    )
    evidence = Evidence.from_ocr(extraction)
    assert evidence.claim_for(FusionAttribute.BRAND).value == "Dell"
    assert evidence.claim_for(FusionAttribute.BRAND).confidence == 0.95
    assert evidence.claim_for(FusionAttribute.MODEL).confidence == 0.80
    assert evidence.claim_for(FusionAttribute.SERIAL_NUMBER).value == "ABC12345"


def test_from_ocr_ignores_barcode_and_qr_field_types():
    extraction = _ocr_extraction(
        [
            _field(FieldType.QR_CODE, "SN123", 0.99, FieldSource.QR),
            _field(FieldType.BARCODE, "490154203237518", 0.99, FieldSource.BARCODE),
        ]
    )
    evidence = Evidence.from_ocr(extraction)
    assert evidence.claims == ()
    assert evidence.confidence == 0.0


# --- Evidence.from_ocr_identity ----------------------------------------------


def test_from_ocr_identity_maps_present_fields_at_shared_confidence():
    identity = OCRIdentity(manufacturer="Dell", model="XPS 15", serial_number="X1")
    evidence = Evidence.from_ocr_identity(identity, confidence=0.7)
    assert evidence.claim_for(FusionAttribute.BRAND).value == "Dell"
    assert all(claim.confidence == 0.7 for claim in evidence.claims)
    assert evidence.claim_for(FusionAttribute.IMEI) is None


def test_from_ocr_identity_empty_yields_no_claims():
    evidence = Evidence.from_ocr_identity(OCRIdentity())
    assert evidence.claims == ()
    assert evidence.confidence == 0.0


# --- Evidence.from_fingerprint ----------------------------------------------


def test_from_fingerprint_surfaces_provenance_at_fixed_low_confidence():
    evidence = Evidence.from_fingerprint(_fingerprint())
    device_claim = evidence.claim_for(FusionAttribute.DEVICE_TYPE)
    assert device_claim.value == "Laptop"
    assert device_claim.confidence == 0.5
    assert device_claim.source is EvidenceKind.FINGERPRINT


def test_from_fingerprint_merges_identity_without_duplicating_brand():
    fingerprint = _fingerprint(
        brand="Dell",
        identity={"manufacturer": "HP", "serial_number": "SN9"},
    )
    evidence = Evidence.from_fingerprint(fingerprint)
    brand_claims = [
        claim for claim in evidence.claims if claim.attribute is FusionAttribute.BRAND
    ]
    # The explicit ``brand`` wins; the identity ``manufacturer`` does not add a
    # second, duplicate brand claim.
    assert len(brand_claims) == 1
    assert brand_claims[0].value == "Dell"
    assert evidence.claim_for(FusionAttribute.SERIAL_NUMBER).value == "SN9"


def test_from_fingerprint_without_provenance_has_no_claims():
    fingerprint = _fingerprint(device_type="", brand="", identity={})
    evidence = Evidence.from_fingerprint(fingerprint)
    assert evidence.claims == ()
    assert evidence.confidence == 1.0


# --- ResolvedAttribute / Conflict / DeviceContext ----------------------------


def test_resolved_attribute_agreed_and_to_dict():
    resolved = ResolvedAttribute(
        attribute=FusionAttribute.DEVICE_TYPE,
        value="Laptop",
        confidence=0.95,
        sources=(EvidenceKind.DETECTION, EvidenceKind.FINGERPRINT),
    )
    assert resolved.agreed is True
    assert resolved.to_dict()["sources"] == ["detection", "fingerprint"]
    assert resolved.to_dict()["agreed"] is True


def test_resolved_attribute_conflicted_is_not_agreed():
    resolved = ResolvedAttribute(
        attribute=FusionAttribute.BRAND,
        value="Dell",
        confidence=0.5,
        sources=(EvidenceKind.DETECTION,),
        conflicted=True,
    )
    assert resolved.agreed is False


def test_conflict_sources_and_to_dict():
    claims = (
        Claim(FusionAttribute.BRAND, "Dell", 0.9, EvidenceKind.DETECTION),
        Claim(FusionAttribute.BRAND, "HP", 0.8, EvidenceKind.OCR),
    )
    conflict = Conflict(FusionAttribute.BRAND, "Dell", claims)
    assert conflict.sources == (EvidenceKind.DETECTION, EvidenceKind.OCR)
    payload = conflict.to_dict()
    assert payload["attribute"] == "brand"
    assert payload["resolved_value"] == "Dell"
    assert len(payload["claims"]) == 2


def test_device_context_accessors_and_to_dict():
    context = DeviceContext(
        eco_id="ET-2026-0000ABCD",
        fingerprint="f" * 64,
        attributes=(
            ResolvedAttribute(
                FusionAttribute.DEVICE_TYPE, "Laptop", 0.9, (EvidenceKind.DETECTION,)
            ),
            ResolvedAttribute(FusionAttribute.BRAND, "Dell", 0.8, (EvidenceKind.OCR,)),
        ),
        confidence=0.85,
        evidence=(),
        conflicts=(),
        source_hashes=("a" * 64,),
        engine_version="1.0.0",
        created_at=_CLOCK,
    )
    assert context.device_type == "Laptop"
    assert context.brand == "Dell"
    assert context.model == ""
    assert context.confidence_of(FusionAttribute.DEVICE_TYPE) == 0.9
    assert context.confidence_of(FusionAttribute.IMEI) == 0.0
    assert context.has_conflicts is False
    payload = context.to_dict()
    assert payload["device_type"] == "Laptop"
    assert payload["created_at"] == _CLOCK.isoformat()
    assert payload["source_hashes"] == ["a" * 64]


def test_device_context_is_immutable():
    context = DeviceContext(
        eco_id="",
        fingerprint="",
        attributes=(),
        confidence=0.0,
        evidence=(),
        conflicts=(),
        source_hashes=(),
        engine_version="1.0.0",
    )
    with pytest.raises((AttributeError, TypeError)):
        context.confidence = 1.0  # type: ignore[misc]
