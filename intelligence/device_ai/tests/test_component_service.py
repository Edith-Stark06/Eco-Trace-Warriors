"""End-to-end tests for the component service (milestone M1.9).

Exercises :meth:`ComponentService.analyze` against the shipped external
catalogue across the required scenarios — an identifiable laptop, a hazardous
CRT, an unknown device and a conflicted context — plus determinism, provenance
carry-over, the injected clock and report immutability. Inputs are hand-built
(no fusion run, no models); only the external catalogue is read from disk.
"""

from datetime import UTC, datetime

import pytest

from device_ai.components import (
    COMPONENT_ENGINE_VERSION,
    ComponentConfig,
    ComponentReport,
    ComponentService,
)
from device_ai.fusion.models import (
    Conflict,
    DeviceContext,
    EvidenceKind,
    FusionAttribute,
    ResolvedAttribute,
)
from device_ai.recoverability import RecoverabilityService

_CLOCK = datetime(2026, 8, 1, 12, 0, 0, tzinfo=UTC)


def _service(*, with_clock=False, config=None):
    return ComponentService(
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
    return _service(with_clock=with_clock, config=config).analyze(
        context, recoverability
    )


# --- Healthy, identifiable device ----------------------------------------


def test_analyze_identifiable_laptop_lists_expected_components():
    report = _analyze(_context(model="XPS-13", serial="SN123", mac="00:1A:2B:3C:4D:5E"))
    assert isinstance(report, ComponentReport)
    assert report.device_type == "laptop"
    assert report.component_count > 0
    names = {component.name for component in report.components}
    assert any("battery" in name.lower() for name in names)
    assert any("board" in name.lower() for name in names)


def test_analyze_flags_hazardous_and_recoverable_partitions():
    report = _analyze(_context(model="XPS-13", serial="SN123"))
    assert report.hazardous_components  # laptop battery is hazardous
    assert report.recoverable_components


# --- Hazardous class ------------------------------------------------------


def test_analyze_crt_lists_hazardous_tube():
    report = _analyze(_context(device_type="CRT monitor"))
    assert report.device_type == "crt_monitor"
    assert any(component.hazardous for component in report.components)


# --- Unknown device -------------------------------------------------------


def test_analyze_unknown_device_uses_generic_fallback_and_warns():
    report = _analyze(_context(device_type="teleporter"))
    assert report.device_type == "teleporter"
    assert report.components  # generic components inferred
    assert any("Unrecognized" in w for w in report.warnings)


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
    service = _service()
    first = service.analyze(context, recoverability)
    second = service.analyze(context, recoverability)
    assert first.to_dict() == second.to_dict()


def test_service_stamps_versions_and_optional_clock():
    with_clock = _analyze(_context(model="XPS-13"), with_clock=True)
    assert with_clock.engine_version == COMPONENT_ENGINE_VERSION
    assert with_clock.profile_version  # catalogue version from the YAML
    assert with_clock.created_at == _CLOCK
    without_clock = _analyze(_context(model="XPS-13"))
    assert without_clock.created_at is None


def test_report_is_json_serializable_shape():
    report = _analyze(_context(model="XPS-13", serial="SN123"), with_clock=True)
    payload = report.to_dict()
    assert payload["device_type"] == "laptop"
    assert isinstance(payload["components"], list)
    assert payload["component_count"] == len(payload["components"])
    assert payload["created_at"] == _CLOCK.isoformat()
    for component in payload["components"]:
        assert set(component) == {
            "name",
            "category",
            "presence_confidence",
            "hazardous",
            "recoverable",
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
    from device_ai.components.models import ComponentCategory
    from device_ai.components.profiles import (
        ComponentProfile,
        ComponentProfileLibrary,
        ComponentSpec,
    )

    library = ComponentProfileLibrary(
        version="test-1",
        profiles={
            "laptop": ComponentProfile(
                device_type="laptop",
                components=(
                    ComponentSpec(
                        name="Only part",
                        category=ComponentCategory.OTHER,
                        base_likelihood=0.9,
                    ),
                ),
            )
        },
        aliases={},
        unknown=ComponentProfile(
            device_type="",
            components=(
                ComponentSpec(
                    name="Generic",
                    category=ComponentCategory.OTHER,
                    base_likelihood=0.5,
                ),
            ),
            known=False,
        ),
    )
    service = ComponentService(library=library, clock=None)
    context = _context(model="XPS-13")
    recoverability = RecoverabilityService(clock=None).assess(context)
    report = service.analyze(context, recoverability)
    assert report.profile_version == "test-1"
    assert [component.name for component in report.components] == ["Only part"]


def test_custom_config_is_exposed_on_service():
    config = ComponentConfig(min_presence_confidence=0.99)
    service = ComponentService(config=config, clock=None)
    assert service.config.min_presence_confidence == 0.99
