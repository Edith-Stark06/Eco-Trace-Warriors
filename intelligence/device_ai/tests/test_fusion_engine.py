"""Tests for the FusionEngine (milestone M1.7).

Covers the four required scenarios — **agreement**, **disagreement**, **partial
evidence** and **missing evidence** — plus confidence aggregation (noisy-OR +
support-share damping), conflict detection, determinism and the
identity-anchor/provenance carry-over. The engine is exercised both through the
pure ``fuse`` core (hand-built evidence) and the ``fuse_modules`` convenience
(real module result objects), all in the base environment with no models or I-O.
"""

from datetime import UTC, datetime

from device_ai.fingerprint.models import DeviceFingerprint
from device_ai.fusion.engine import FUSION_ENGINE_VERSION, FusionEngine
from device_ai.fusion.models import (
    Claim,
    Evidence,
    EvidenceKind,
    FusionAttribute,
)
from device_ai.inference.predictor import DetectionResult
from device_ai.ocr.models import (
    ExtractedField,
    FieldSource,
    FieldType,
    OCRExtraction,
)

_CLOCK = datetime(2026, 8, 1, 12, 0, 0, tzinfo=UTC)


def _engine(*, with_clock=False):
    return FusionEngine(clock=(lambda: _CLOCK) if with_clock else None)


def _detection(device_type="Laptop", brand="Dell", confidence=0.9):
    return DetectionResult(
        device_type=device_type, brand=brand, confidence=confidence, detections=[]
    )


def _ocr(fields):
    return OCRExtraction(
        fields=tuple(fields),
        engine_name="ocr",
        engine_version="mock-ocr-m16-1.0.0",
        created_at=_CLOCK,
        source_hashes=("a" * 64,),
    )


def _field(field_type, value, confidence, source=FieldSource.TEXT):
    return ExtractedField(field_type, value, confidence, value, source)


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


# --- Agreement ---------------------------------------------------------------


def test_agreement_raises_confidence_above_either_source():
    """Two modules agreeing on a value combine via noisy-OR (agreement lifts)."""
    evidence = [
        Evidence(
            EvidenceKind.DETECTION,
            "detector",
            "",
            0.8,
            (
                Claim(
                    FusionAttribute.DEVICE_TYPE, "Laptop", 0.8, EvidenceKind.DETECTION
                ),
            ),
        ),
        Evidence(
            EvidenceKind.OCR,
            "ocr",
            "",
            0.8,
            (Claim(FusionAttribute.DEVICE_TYPE, "Laptop", 0.8, EvidenceKind.OCR),),
        ),
    ]
    context = _engine().fuse(evidence)
    resolved = context.get(FusionAttribute.DEVICE_TYPE)
    assert resolved.value == "Laptop"
    assert resolved.agreed is True
    assert resolved.conflicted is False
    # noisy-OR of 0.8, 0.8 = 0.96 (no damping — unanimous)
    assert resolved.confidence == 0.96
    assert resolved.sources == (EvidenceKind.DETECTION, EvidenceKind.OCR)
    assert context.has_conflicts is False


def test_full_module_agreement_via_fuse_modules():
    """Detection + fingerprint + OCR all agreeing yields no conflicts."""
    detection = _detection(device_type="Laptop", brand="Dell")
    fingerprint = _fingerprint(device_type="Laptop", brand="Dell")
    ocr = _ocr(
        [
            _field(FieldType.MANUFACTURER, "Dell", 0.95),
            _field(FieldType.SERIAL_NUMBER, "ABC12345", 0.9),
        ]
    )
    context = _engine().fuse_modules(
        detection=detection, fingerprint=fingerprint, ocr=ocr
    )
    assert context.eco_id == "ET-2026-0000ABCD"
    assert context.fingerprint == "f" * 64
    assert context.device_type == "Laptop"
    assert context.brand == "Dell"
    assert context.serial_number == "ABC12345"
    assert context.has_conflicts is False
    # brand is supported by all three modules
    assert context.get(FusionAttribute.BRAND).sources == (
        EvidenceKind.DETECTION,
        EvidenceKind.FINGERPRINT,
        EvidenceKind.OCR,
    )


# --- Disagreement / conflict -------------------------------------------------


def test_disagreement_records_conflict_and_damps_confidence():
    """Two modules claiming different brands conflict; winner is highest support."""
    evidence = [
        Evidence.from_detection(_detection(brand="Dell", confidence=0.9)),
        Evidence.from_ocr(_ocr([_field(FieldType.MANUFACTURER, "HP", 0.6)])),
    ]
    context = _engine().fuse(evidence)
    brand = context.get(FusionAttribute.BRAND)
    assert brand.value == "Dell"  # 0.9 beats 0.6
    assert brand.conflicted is True
    assert brand.agreed is False
    assert context.has_conflicts is True
    conflict = next(
        c for c in context.conflicts if c.attribute is FusionAttribute.BRAND
    )
    assert conflict.resolved_value == "Dell"
    # claims ordered by descending confidence
    assert [claim.value for claim in conflict.claims] == ["Dell", "HP"]
    # support-share damping pulls the winner below its raw 0.9
    assert brand.confidence < 0.9


def test_device_type_vs_ocr_identity_conflict_is_detected():
    """The spec's example: inconsistent device type across modules is flagged."""
    evidence = [
        Evidence.from_detection(_detection(device_type="Laptop", confidence=0.9)),
        Evidence(
            EvidenceKind.FINGERPRINT,
            "fingerprint",
            "",
            0.5,
            (
                Claim(
                    FusionAttribute.DEVICE_TYPE,
                    "Smartphone",
                    0.5,
                    EvidenceKind.FINGERPRINT,
                ),
            ),
        ),
    ]
    context = _engine().fuse(evidence)
    assert context.device_type == "Laptop"
    assert context.has_conflicts is True
    attributes = [c.attribute for c in context.conflicts]
    assert FusionAttribute.DEVICE_TYPE in attributes


# --- Partial evidence --------------------------------------------------------


def test_partial_evidence_only_ocr():
    """OCR alone still produces a context for the fields it found."""
    context = _engine().fuse_modules(
        ocr=_ocr(
            [
                _field(FieldType.SERIAL_NUMBER, "SN-77", 0.88),
                _field(FieldType.IMEI, "490154203237518", 0.9),
            ]
        )
    )
    assert context.serial_number == "SN-77"
    assert context.imei == "490154203237518"
    assert context.device_type == ""  # nothing claimed it
    assert context.eco_id == ""  # no fingerprint anchor
    assert context.has_conflicts is False


def test_partial_evidence_detection_and_fingerprint_no_ocr():
    """Detection + fingerprint without OCR still fuses type/brand and anchors id."""
    context = _engine().fuse_modules(detection=_detection(), fingerprint=_fingerprint())
    assert context.device_type == "Laptop"
    assert context.brand == "Dell"
    assert context.eco_id == "ET-2026-0000ABCD"
    assert context.model == ""


def test_source_hashes_fall_back_to_fingerprint():
    """When not passed explicitly, source hashes come from the fingerprint."""
    context = _engine().fuse_modules(fingerprint=_fingerprint())
    assert context.source_hashes == ("b" * 64,)


def test_explicit_source_hashes_override_fingerprint():
    context = _engine().fuse_modules(
        fingerprint=_fingerprint(), source_hashes=("c" * 64,)
    )
    assert context.source_hashes == ("c" * 64,)


# --- Missing evidence --------------------------------------------------------


def test_missing_evidence_yields_empty_context():
    """No modules at all → an empty, valid, zero-confidence context."""
    context = _engine().fuse_modules()
    assert context.attributes == ()
    assert context.conflicts == ()
    assert context.evidence == ()
    assert context.confidence == 0.0
    assert context.eco_id == ""
    assert context.fingerprint == ""
    assert context.device_type == ""
    assert context.has_conflicts is False


def test_fuse_empty_evidence_iterable():
    context = _engine().fuse([])
    assert context.attributes == ()
    assert context.confidence == 0.0


# --- Confidence aggregation & normalization ----------------------------------


def test_aggregate_confidence_is_mean_of_resolved_attributes():
    evidence = [
        Evidence.from_detection(_detection(device_type="Laptop", brand="Dell")),
    ]
    context = _engine().fuse(evidence)
    resolved = context.attributes
    expected = round(sum(r.confidence for r in resolved) / len(resolved), 6)
    assert context.confidence == expected


def test_confidence_is_bounded_unit_interval():
    evidence = [
        Evidence(
            EvidenceKind.DETECTION,
            "d",
            "",
            1.0,
            (Claim(FusionAttribute.BRAND, "Dell", 1.0, EvidenceKind.DETECTION),),
        ),
        Evidence(
            EvidenceKind.OCR,
            "o",
            "",
            1.0,
            (Claim(FusionAttribute.BRAND, "Dell", 1.0, EvidenceKind.OCR),),
        ),
    ]
    context = _engine().fuse(evidence)
    assert 0.0 <= context.get(FusionAttribute.BRAND).confidence <= 1.0


def test_attributes_are_in_declaration_order():
    ocr = _ocr(
        [
            _field(FieldType.MAC_ADDRESS, "0F:E1:B9:C5:F1:CD", 0.9),
            _field(FieldType.MANUFACTURER, "Dell", 0.9),
            _field(FieldType.SERIAL_NUMBER, "SN1", 0.9),
        ]
    )
    context = _engine().fuse_modules(detection=_detection(), ocr=ocr)
    order = [resolved.attribute for resolved in context.attributes]
    assert order == sorted(order, key=list(FusionAttribute).index)


# --- Determinism & metadata --------------------------------------------------


def test_fusion_is_deterministic_for_identical_input():
    detection = _detection()
    fingerprint = _fingerprint()
    ocr = _ocr([_field(FieldType.SERIAL_NUMBER, "SN1", 0.9)])
    first = _engine().fuse_modules(
        detection=detection, fingerprint=fingerprint, ocr=ocr
    )
    second = _engine().fuse_modules(
        detection=detection, fingerprint=fingerprint, ocr=ocr
    )
    assert first.to_dict() == second.to_dict()


def test_engine_stamps_version_and_optional_clock():
    with_clock = _engine(with_clock=True).fuse_modules(detection=_detection())
    assert with_clock.engine_version == FUSION_ENGINE_VERSION
    assert with_clock.created_at == _CLOCK
    without_clock = _engine().fuse_modules(detection=_detection())
    assert without_clock.created_at is None


def test_evidence_provenance_is_preserved_on_context():
    context = _engine().fuse_modules(detection=_detection())
    assert len(context.evidence) == 1
    assert context.evidence[0].source is EvidenceKind.DETECTION
