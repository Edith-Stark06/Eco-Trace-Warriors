"""End-to-end tests for the decision service (milestone M2.1).

Exercises :meth:`DecisionService.analyze` against the shipped external knowledge
catalogue across the required scenarios — an identifiable laptop, a hazardous
CRT, an unknown device and a conflicted context — plus determinism, provenance
carry-over, the injected clock and report immutability. The five upstream inputs
are built by actually running the recoverability, component, material and
environmental engines over a hand-built :class:`DeviceContext` (no fusion run, no
models); only the external catalogues are read from disk.

The report is normalized evidence only: every dimension score and the overall
confidence sit in ``[0, 1]`` and no field is a recommended action or a monetary
value — asserted explicitly below.
"""

from datetime import UTC, datetime

import pytest

from device_ai.components import ComponentService
from device_ai.decision import (
    DECISION_ENGINE_VERSION,
    DecisionConfig,
    DecisionKnowledgeReport,
    DecisionService,
)
from device_ai.decision.models import DecisionDimension
from device_ai.environmental import EnvironmentalService
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


def _service(*, with_clock=False, config=None, knowledge=None):
    return DecisionService(
        config=config,
        knowledge=knowledge,
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


def _upstream(context):
    recoverability = RecoverabilityService(clock=None).assess(context)
    components = ComponentService(clock=None).analyze(context, recoverability)
    materials = MaterialService(clock=None).analyze(context, recoverability, components)
    environmental = EnvironmentalService(clock=None).analyze(
        context, recoverability, components, materials
    )
    return recoverability, components, materials, environmental


def _analyze(context, *, with_clock=False, config=None, knowledge=None):
    recoverability, components, materials, environmental = _upstream(context)
    return _service(with_clock=with_clock, config=config, knowledge=knowledge).analyze(
        context, recoverability, components, materials, environmental
    )


# --- Healthy, identifiable device ----------------------------------------


def test_analyze_identifiable_laptop_reports_evidence():
    report = _analyze(_context(model="XPS-13", serial="SN123"))
    assert isinstance(report, DecisionKnowledgeReport)
    assert report.device_type == "laptop"
    assert report.dimension_count == len(DecisionDimension)
    for score in (
        report.repairability_score,
        report.reusability_score,
        report.recycling_score,
        report.hazard_score,
        report.environmental_priority,
        report.material_value_score,
        report.overall_confidence,
    ):
        assert 0.0 <= score <= 1.0


def test_every_dimension_has_evidence_and_a_reason():
    report = _analyze(_context(model="XPS-13", serial="SN123"))
    dimensions = {ev.dimension for ev in report.dimensions}
    assert dimensions == set(DecisionDimension)
    for evidence in report.dimensions:
        assert evidence.reason
        assert 0.0 <= evidence.score <= 1.0


def test_score_for_matches_dimension_evidence():
    report = _analyze(_context(model="XPS-13"))
    assert report.score_for(DecisionDimension.HAZARD) == report.hazard_score


def test_report_is_normalized_evidence_only():
    # The report exposes no recommended-action or monetary field: its public
    # payload keys are all normalized scores, evidence and provenance.
    report = _analyze(_context(model="XPS-13"))
    payload = report.to_dict()
    forbidden = {
        "recommended_action",
        "recommendation",
        "action",
        "price",
        "value_usd",
        "value_inr",
        "cost",
        "currency",
    }
    assert forbidden.isdisjoint(payload)


# --- Hazardous class ------------------------------------------------------


def test_analyze_crt_elevates_hazard_and_warns():
    report = _analyze(_context(device_type="CRT monitor"))
    assert report.device_type == "crt_monitor"
    assert report.hazard_score > 0.0
    assert any("hazard" in w.lower() for w in report.warnings)


# --- Unknown device -------------------------------------------------------


def test_analyze_unknown_device_lowers_confidence():
    unknown = _analyze(_context(device_type="teleporter"))
    known = _analyze(_context(model="XPS-13"))
    assert unknown.device_type == "teleporter"
    # Unknown-type damping upstream keeps the consolidated confidence lower.
    assert unknown.overall_confidence < known.overall_confidence


# --- Conflicted context ---------------------------------------------------


def test_analyze_conflicted_context_damps_confidence():
    clean = _analyze(_context(model="XPS-13"))
    conflict = Conflict(
        attribute=FusionAttribute.BRAND, resolved_value="Dell", claims=()
    )
    conflicted = _analyze(_context(model="XPS-13", conflicts=(conflict,)))
    # The conflict damping is inherited from the upstream confidences.
    assert conflicted.overall_confidence < clean.overall_confidence


# --- Determinism & provenance --------------------------------------------


def test_analyze_is_deterministic_for_identical_input():
    context = _context(model="XPS-13", serial="SN123")
    recoverability, components, materials, environmental = _upstream(context)
    service = _service()
    first = service.analyze(
        context, recoverability, components, materials, environmental
    )
    second = service.analyze(
        context, recoverability, components, materials, environmental
    )
    assert first.to_dict() == second.to_dict()


def test_service_stamps_versions_and_optional_clock():
    with_clock = _analyze(_context(model="XPS-13"), with_clock=True)
    assert with_clock.engine_version == DECISION_ENGINE_VERSION
    assert with_clock.knowledge_version  # catalogue version from the YAML
    assert with_clock.created_at == _CLOCK
    without_clock = _analyze(_context(model="XPS-13"))
    assert without_clock.created_at is None


def test_report_is_json_serializable_shape():
    report = _analyze(_context(model="XPS-13", serial="SN123"), with_clock=True)
    payload = report.to_dict()
    assert payload["device_type"] == "laptop"
    assert isinstance(payload["dimensions"], list)
    assert payload["dimension_count"] == len(payload["dimensions"])
    assert payload["created_at"] == _CLOCK.isoformat()
    assert set(payload) >= {
        "repairability_score",
        "reusability_score",
        "recycling_score",
        "hazard_score",
        "environmental_priority",
        "material_value_score",
        "overall_confidence",
    }
    for dimension in payload["dimensions"]:
        assert set(dimension) == {"dimension", "score", "signals", "reason"}
        for signal in dimension["signals"]:
            assert set(signal) == {"name", "value", "weight"}


def test_report_is_immutable():
    report = _analyze(_context(model="XPS-13"))
    with pytest.raises((AttributeError, TypeError)):
        report.repairability_score = 1.0  # type: ignore[misc]


def test_eco_id_carried_over_from_context():
    report = _analyze(_context(model="XPS-13", eco_id="ET-2026-DEADBEEF"))
    assert report.eco_id == "ET-2026-DEADBEEF"


# --- Injected knowledge & config -----------------------------------------


def test_injected_knowledge_is_used():
    from device_ai.decision.knowledge import KnowledgeBase, Normalization

    knowledge = KnowledgeBase(
        version="knowledge-test-1",
        dimensions={
            DecisionDimension.REPAIRABILITY: {"repairability": 1.0},
            DecisionDimension.REUSABILITY: {"reusability": 1.0},
            DecisionDimension.RECYCLING: {"recyclability": 1.0},
            DecisionDimension.HAZARD: {"hazard_severity": 1.0},
            DecisionDimension.ENVIRONMENTAL_PRIORITY: {"environmental_savings": 1.0},
            DecisionDimension.MATERIAL_VALUE: {"critical_material_presence": 1.0},
        },
        confidence_weights={"materials": 1.0},
        normalization=Normalization(
            carbon_saturation_kg=100.0,
            energy_saturation_mj=1500.0,
            water_saturation_l=1000.0,
            critical_recovery_saturation_kg=0.05,
        ),
    )
    report = _analyze(_context(model="XPS-13"), knowledge=knowledge)
    assert report.knowledge_version == "knowledge-test-1"


def test_custom_config_is_exposed_on_service():
    config = DecisionConfig(min_confidence=0.99)
    service = DecisionService(config=config, clock=None)
    assert service.config.min_confidence == 0.99


def test_service_loads_shipped_catalogue_by_default():
    service = DecisionService(clock=None)
    assert service.knowledge.version
    assert set(service.knowledge.dimensions) == set(DecisionDimension)
