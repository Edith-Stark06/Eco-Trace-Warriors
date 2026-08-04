"""End-to-end tests for the material service (milestone M1.10).

Exercises :meth:`MaterialService.analyze` against the shipped external catalogue
across the required scenarios — an identifiable laptop, a hazardous CRT, an
unknown device and a conflicted context — plus determinism, provenance
carry-over, the injected clock and report immutability. The upstream inputs are
built by actually running the recoverability and component engines over a
hand-built :class:`DeviceContext` (no fusion run, no models); only the external
catalogues are read from disk.
"""

from datetime import UTC, datetime

import pytest

from device_ai.components import ComponentService
from device_ai.fusion.models import (
    Conflict,
    DeviceContext,
    EvidenceKind,
    FusionAttribute,
    ResolvedAttribute,
)
from device_ai.materials import (
    MATERIAL_ENGINE_VERSION,
    MaterialConfig,
    MaterialReport,
    MaterialService,
)
from device_ai.recoverability import RecoverabilityService

_CLOCK = datetime(2026, 8, 1, 12, 0, 0, tzinfo=UTC)


def _service(*, with_clock=False, config=None):
    return MaterialService(
        config=config,
        clock=(lambda: _CLOCK) if with_clock else None,
    )


def _resolved(attribute, value, confidence=0.9):
    return ResolvedAttribute(
        attribute=attribute,
        value=value,
        confidence=confidence,
        sources=(EvidenceKind.DETECTION,),
    )


def _context(
    *,
    device_type="laptop",
    model="",
    serial="",
    imei="",
    mac="",
    confidence=0.9,
    conflicts=(),
    eco_id="ET-2026-0000ABCD",
):
    attributes = [_resolved(FusionAttribute.DEVICE_TYPE, device_type)]
    if model:
        attributes.append(_resolved(FusionAttribute.MODEL, model))
    if serial:
        attributes.append(_resolved(FusionAttribute.SERIAL_NUMBER, serial))
    if imei:
        attributes.append(_resolved(FusionAttribute.IMEI, imei))
    if mac:
        attributes.append(_resolved(FusionAttribute.MAC_ADDRESS, mac))
    return DeviceContext(
        eco_id=eco_id,
        fingerprint="f" * 64,
        attributes=tuple(attributes),
        confidence=confidence,
        evidence=(),
        conflicts=tuple(conflicts),
        source_hashes=("a" * 64,),
        engine_version="fusion-test",
    )


def _analyze(context, *, with_clock=False, config=None):
    recoverability = RecoverabilityService(clock=None).assess(context)
    components = ComponentService(clock=None).analyze(context, recoverability)
    return _service(with_clock=with_clock, config=config).analyze(
        context, recoverability, components
    )


# --- Healthy, identifiable device ----------------------------------------


def test_analyze_identifiable_laptop_lists_materials_and_weights():
    report = _analyze(_context(model="XPS-13", serial="SN123", mac="00:1A:2B:3C:4D:5E"))
    assert isinstance(report, MaterialReport)
    assert report.device_type == "laptop"
    assert report.material_count > 0
    assert report.total_mass_g > 0.0
    assert report.recoverable_mass_g > 0.0
    # Every listed material's confidence is capped by the overall estimate.
    for material in report.materials:
        assert material.confidence <= report.overall_confidence


def test_analyze_laptop_flags_hazardous_weight():
    report = _analyze(_context(model="XPS-13", serial="SN123"))
    assert report.hazardous_materials  # laptop battery cells are hazardous
    assert report.hazardous_mass_g > 0.0


# --- Hazardous class ------------------------------------------------------


def test_analyze_crt_surfaces_hazardous_leaded_glass():
    report = _analyze(_context(device_type="CRT monitor"))
    assert report.device_type == "crt_monitor"
    assert report.hazardous_mass_g > 0.0
    assert any(material.hazardous for material in report.materials)
    assert any("glass" in material.name.lower() for material in report.materials)


# --- Unknown device -------------------------------------------------------


def test_analyze_unknown_device_uses_generic_fallback_and_warns():
    report = _analyze(_context(device_type="teleporter"))
    assert report.device_type == "teleporter"
    assert report.materials  # generic structural materials inferred
    assert any("Unrecognized" in w for w in report.warnings)
    # Unknown-type damping keeps the estimate well below a known device's.
    known = _analyze(_context(model="XPS-13"))
    assert report.overall_confidence < known.overall_confidence


# --- Conflicted context ---------------------------------------------------


def test_analyze_conflicted_context_damps_confidence_and_warns():
    clean = _analyze(_context(model="XPS-13"))
    conflict = Conflict(
        attribute=FusionAttribute.BRAND, resolved_value="Dell", claims=()
    )
    conflicted = _analyze(_context(model="XPS-13", conflicts=(conflict,)))
    assert conflicted.overall_confidence < clean.overall_confidence
    assert any("conflict" in w.lower() for w in conflicted.warnings)


# --- Determinism & provenance --------------------------------------------


def test_analyze_is_deterministic_for_identical_input():
    context = _context(model="XPS-13", serial="SN123")
    recoverability = RecoverabilityService(clock=None).assess(context)
    components = ComponentService(clock=None).analyze(context, recoverability)
    service = _service()
    first = service.analyze(context, recoverability, components)
    second = service.analyze(context, recoverability, components)
    assert first.to_dict() == second.to_dict()


def test_service_stamps_versions_and_optional_clock():
    with_clock = _analyze(_context(model="XPS-13"), with_clock=True)
    assert with_clock.engine_version == MATERIAL_ENGINE_VERSION
    assert with_clock.profile_version  # catalogue version from the YAML
    assert with_clock.created_at == _CLOCK
    without_clock = _analyze(_context(model="XPS-13"))
    assert without_clock.created_at is None


def test_report_is_json_serializable_shape():
    report = _analyze(_context(model="XPS-13", serial="SN123"), with_clock=True)
    payload = report.to_dict()
    assert payload["device_type"] == "laptop"
    assert isinstance(payload["materials"], list)
    assert payload["material_count"] == len(payload["materials"])
    assert payload["created_at"] == _CLOCK.isoformat()
    for material in payload["materials"]:
        assert set(material) == {
            "name",
            "category",
            "mass_g",
            "confidence",
            "recoverable",
            "hazardous",
            "source_components",
            "reason",
        }


def test_report_is_immutable():
    report = _analyze(_context(model="XPS-13"))
    with pytest.raises((AttributeError, TypeError)):
        report.overall_confidence = 1.0  # type: ignore[misc]


def test_eco_id_carried_over_from_context():
    report = _analyze(_context(model="XPS-13", eco_id="ET-2026-DEADBEEF"))
    assert report.eco_id == "ET-2026-DEADBEEF"


# --- Injected library & config -------------------------------------------


def test_injected_library_is_used():
    from device_ai.materials.models import MaterialCategory
    from device_ai.materials.profiles import (
        MaterialProfile,
        MaterialProfileLibrary,
        MaterialSpec,
    )

    library = MaterialProfileLibrary(
        version="test-1",
        profiles={
            "laptop": MaterialProfile(
                device_type="laptop",
                materials=(
                    MaterialSpec(
                        name="Only material",
                        category=MaterialCategory.OTHER,
                        mass_g=42.0,
                    ),
                ),
            )
        },
        aliases={},
        unknown=MaterialProfile(
            device_type="",
            materials=(
                MaterialSpec(
                    name="Generic",
                    category=MaterialCategory.OTHER,
                    mass_g=10.0,
                ),
            ),
            known=False,
        ),
    )
    service = MaterialService(library=library, clock=None)
    context = _context(model="XPS-13")
    recoverability = RecoverabilityService(clock=None).assess(context)
    components = ComponentService(clock=None).analyze(context, recoverability)
    report = service.analyze(context, recoverability, components)
    assert report.profile_version == "test-1"
    assert [material.name for material in report.materials] == ["Only material"]


def test_custom_config_is_exposed_on_service():
    config = MaterialConfig(min_material_confidence=0.99)
    service = MaterialService(config=config, clock=None)
    assert service.config.min_material_confidence == 0.99
