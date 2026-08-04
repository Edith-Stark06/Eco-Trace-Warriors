"""End-to-end tests for the environmental service (milestone M1.11).

Exercises :meth:`EnvironmentalService.analyze` against the shipped external
factor catalogue across the required scenarios — an identifiable laptop, a
hazardous CRT, an unknown device and a conflicted context — plus determinism,
provenance carry-over, the injected clock and report immutability. The upstream
inputs are built by actually running the recoverability, component and material
engines over a hand-built :class:`DeviceContext` (no fusion run, no models); only
the external catalogues are read from disk.
"""

from datetime import UTC, datetime

import pytest

from device_ai.components import ComponentService
from device_ai.environmental import (
    ENVIRONMENTAL_ENGINE_VERSION,
    EnvironmentalConfig,
    EnvironmentalImpactReport,
    EnvironmentalService,
)
from device_ai.fusion.models import (
    Conflict,
    DeviceContext,
    EvidenceKind,
    FusionAttribute,
    ResolvedAttribute,
)
from device_ai.materials import MaterialService
from device_ai.recoverability import RecoverabilityService

_CLOCK = datetime(2026, 8, 1, 12, 0, 0, tzinfo=UTC)


def _service(*, with_clock=False, config=None):
    return EnvironmentalService(
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
    confidence=0.9,
    conflicts=(),
    eco_id="ET-2026-0000ABCD",
):
    attributes = [_resolved(FusionAttribute.DEVICE_TYPE, device_type)]
    if model:
        attributes.append(_resolved(FusionAttribute.MODEL, model))
    if serial:
        attributes.append(_resolved(FusionAttribute.SERIAL_NUMBER, serial))
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
    materials = MaterialService(clock=None).analyze(context, recoverability, components)
    return _service(with_clock=with_clock, config=config).analyze(
        context, recoverability, components, materials
    )


# --- Healthy, identifiable device ----------------------------------------


def test_analyze_identifiable_laptop_reports_savings():
    report = _analyze(_context(model="XPS-13", serial="SN123"))
    assert isinstance(report, EnvironmentalImpactReport)
    assert report.device_type == "laptop"
    assert report.contribution_count > 0
    assert report.carbon_saved_kg > 0.0
    assert report.energy_saved_mj > 0.0
    assert report.water_saved_l > 0.0
    assert report.landfill_diversion_kg > 0.0
    assert 0.0 <= report.circularity_index <= 1.0
    assert 0.0 <= report.confidence <= 1.0


def test_analyze_laptop_recovers_critical_material():
    # A laptop's boards carry precious/critical metals, so critical recovery
    # should be positive.
    report = _analyze(_context(model="XPS-13", serial="SN123"))
    assert report.critical_material_recovery_kg > 0.0
    assert report.critical_contributions


# --- Hazardous class ------------------------------------------------------


def test_analyze_crt_surfaces_hazard_reduction():
    report = _analyze(_context(device_type="CRT monitor"))
    assert report.device_type == "crt_monitor"
    assert report.hazard_reduction_score > 0.0
    assert any("hazard" in w.lower() for w in report.warnings)


# --- Unknown device -------------------------------------------------------


def test_analyze_unknown_device_still_estimates_and_warns():
    report = _analyze(_context(device_type="teleporter"))
    assert report.device_type == "teleporter"
    # Generic structural materials still yield some savings.
    assert report.carbon_saved_kg >= 0.0
    known = _analyze(_context(model="XPS-13"))
    # Unknown-type damping upstream keeps the estimate's confidence lower.
    assert report.confidence < known.confidence


# --- Conflicted context ---------------------------------------------------


def test_analyze_conflicted_context_damps_confidence():
    clean = _analyze(_context(model="XPS-13"))
    conflict = Conflict(
        attribute=FusionAttribute.BRAND, resolved_value="Dell", claims=()
    )
    conflicted = _analyze(_context(model="XPS-13", conflicts=(conflict,)))
    # The conflict damping is inherited from the upstream material confidence.
    assert conflicted.confidence < clean.confidence
    # The physical savings are unchanged by the confidence damping.
    assert conflicted.carbon_saved_kg == clean.carbon_saved_kg


# --- Determinism & provenance --------------------------------------------


def test_analyze_is_deterministic_for_identical_input():
    context = _context(model="XPS-13", serial="SN123")
    recoverability = RecoverabilityService(clock=None).assess(context)
    components = ComponentService(clock=None).analyze(context, recoverability)
    materials = MaterialService(clock=None).analyze(context, recoverability, components)
    service = _service()
    first = service.analyze(context, recoverability, components, materials)
    second = service.analyze(context, recoverability, components, materials)
    assert first.to_dict() == second.to_dict()


def test_service_stamps_versions_and_optional_clock():
    with_clock = _analyze(_context(model="XPS-13"), with_clock=True)
    assert with_clock.engine_version == ENVIRONMENTAL_ENGINE_VERSION
    assert with_clock.factors_version  # catalogue version from the YAML
    assert with_clock.created_at == _CLOCK
    without_clock = _analyze(_context(model="XPS-13"))
    assert without_clock.created_at is None


def test_report_is_json_serializable_shape():
    report = _analyze(_context(model="XPS-13", serial="SN123"), with_clock=True)
    payload = report.to_dict()
    assert payload["device_type"] == "laptop"
    assert isinstance(payload["contributions"], list)
    assert payload["contribution_count"] == len(payload["contributions"])
    assert payload["created_at"] == _CLOCK.isoformat()
    assert set(payload) >= {
        "carbon_saved_kg",
        "energy_saved_mj",
        "water_saved_l",
        "landfill_diversion_kg",
        "critical_material_recovery_kg",
        "circularity_index",
        "hazard_reduction_score",
        "confidence",
    }
    for contribution in payload["contributions"]:
        assert set(contribution) == {
            "category",
            "recovered_mass_g",
            "carbon_saved_kg",
            "energy_saved_mj",
            "water_saved_l",
            "critical",
            "reason",
        }


def test_report_is_immutable():
    report = _analyze(_context(model="XPS-13"))
    with pytest.raises((AttributeError, TypeError)):
        report.carbon_saved_kg = 1.0  # type: ignore[misc]


def test_eco_id_carried_over_from_context():
    report = _analyze(_context(model="XPS-13", eco_id="ET-2026-DEADBEEF"))
    assert report.eco_id == "ET-2026-DEADBEEF"


# --- Injected library & config -------------------------------------------


def test_injected_library_is_used():
    from device_ai.environmental.factors import FactorLibrary, MaterialFactor
    from device_ai.materials.models import MaterialCategory

    library = FactorLibrary(
        version="factors-test-1",
        factors={
            MaterialCategory.FERROUS_METAL: MaterialFactor(
                category=MaterialCategory.FERROUS_METAL,
                carbon_kg_per_kg=2.0,
                energy_mj_per_kg=20.0,
                water_l_per_kg=10.0,
            )
        },
        default=MaterialFactor(
            category=MaterialCategory.OTHER,
            carbon_kg_per_kg=1.0,
            energy_mj_per_kg=10.0,
            water_l_per_kg=10.0,
        ),
    )
    service = EnvironmentalService(library=library, clock=None)
    context = _context(model="XPS-13")
    recoverability = RecoverabilityService(clock=None).assess(context)
    components = ComponentService(clock=None).analyze(context, recoverability)
    materials = MaterialService(clock=None).analyze(context, recoverability, components)
    report = service.analyze(context, recoverability, components, materials)
    assert report.factors_version == "factors-test-1"


def test_custom_config_is_exposed_on_service():
    config = EnvironmentalConfig(min_material_confidence=0.99)
    service = EnvironmentalService(config=config, clock=None)
    assert service.config.min_material_confidence == 0.99
