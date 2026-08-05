"""End-to-end tests for the circular decision service (milestone M2.2).

Exercises :meth:`CircularService.decide` against the shipped external rule
catalogue across the required scenarios — an identifiable laptop, a hazardous
CRT, an unknown device and a conflicted context — plus determinism, provenance
carry-over, the injected clock, report immutability and injected config/catalogue.
The four upstream inputs are built by actually running the recoverability,
component, material, environmental and decision-knowledge engines over a
hand-built :class:`DeviceContext` (no fusion run, no models); only the external
catalogues are read from disk.

The report is the first in the pipeline that carries a real recommendation: an
action and a priority. Its aggregated confidence stays in ``[0, 1]`` and it never
exposes a monetary field — asserted explicitly below.
"""

from datetime import UTC, datetime

import pytest

from device_ai.circular import (
    CIRCULAR_ENGINE_VERSION,
    CircularConfig,
    CircularService,
    DecisionReport,
    Priority,
    RecommendedAction,
)
from device_ai.components import ComponentService
from device_ai.decision import DecisionService
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


def _service(*, with_clock=False, config=None, catalogue=None):
    return CircularService(
        config=config,
        catalogue=catalogue,
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
    """Run the real upstream engines and return the four circular inputs."""
    recoverability = RecoverabilityService(clock=None).assess(context)
    components = ComponentService(clock=None).analyze(context, recoverability)
    materials = MaterialService(clock=None).analyze(context, recoverability, components)
    environmental = EnvironmentalService(clock=None).analyze(
        context, recoverability, components, materials
    )
    knowledge = DecisionService(clock=None).analyze(
        context, recoverability, components, materials, environmental
    )
    return knowledge, recoverability, environmental


def _decide(context, *, with_clock=False, config=None, catalogue=None):
    knowledge, recoverability, environmental = _upstream(context)
    return _service(with_clock=with_clock, config=config, catalogue=catalogue).decide(
        context, knowledge, recoverability, environmental
    )


# --- Healthy, identifiable device ----------------------------------------


def test_decide_identifiable_laptop_recommends_an_action():
    report = _decide(_context(model="XPS-13", serial="SN123"))
    assert isinstance(report, DecisionReport)
    assert report.device_type == "laptop"
    assert isinstance(report.recommended_action, RecommendedAction)
    assert isinstance(report.priority, Priority)
    assert 0.0 <= report.confidence <= 1.0
    # A recommendation must be backed by either a winning rule or the fallback.
    assert report.winning_rule is not None or report.triggered_count == 0


def test_report_exposes_no_monetary_field():
    report = _decide(_context(model="XPS-13"))
    payload = report.to_dict()
    forbidden = {
        "price",
        "value_usd",
        "value_inr",
        "cost",
        "currency",
        "market_value",
    }
    assert forbidden.isdisjoint(payload)


# --- Hazardous class ------------------------------------------------------


def test_decide_crt_routes_to_hazardous_disposal():
    report = _decide(_context(device_type="CRT monitor"))
    assert report.device_type == "crt_monitor"
    assert report.recommended_action is RecommendedAction.HAZARDOUS_DISPOSAL
    assert report.priority is Priority.HIGH
    assert any("hazard" in warning.lower() for warning in report.warnings)


# --- Unknown device -------------------------------------------------------


def test_decide_unknown_device_routes_to_manual_review():
    report = _decide(_context(device_type="teleporter"))
    assert report.device_type == "teleporter"
    # The recoverability engine forces manual review for an unknown type, which
    # the circular engine honours ahead of any recovery pathway.
    assert report.recommended_action is RecommendedAction.MANUAL_REVIEW
    assert any(
        "manual review" in warning.lower() or "human" in warning.lower()
        for warning in report.warnings
    )


# --- Conflicted context ---------------------------------------------------


def test_decide_conflicted_context_damps_confidence():
    clean = _decide(_context(model="XPS-13"))
    conflict = Conflict(
        attribute=FusionAttribute.BRAND, resolved_value="Dell", claims=()
    )
    conflicted = _decide(_context(model="XPS-13", conflicts=(conflict,)))
    # The conflict damping is inherited from the upstream consolidated confidence.
    assert conflicted.confidence < clean.confidence


# --- Determinism & provenance --------------------------------------------


def test_decide_is_deterministic_for_identical_input():
    context = _context(model="XPS-13", serial="SN123")
    knowledge, recoverability, environmental = _upstream(context)
    service = _service()
    first = service.decide(context, knowledge, recoverability, environmental)
    second = service.decide(context, knowledge, recoverability, environmental)
    assert first.to_dict() == second.to_dict()


def test_service_stamps_versions_and_optional_clock():
    with_clock = _decide(_context(model="XPS-13"), with_clock=True)
    assert with_clock.engine_version == CIRCULAR_ENGINE_VERSION
    assert with_clock.rules_version  # catalogue version from the YAML
    assert with_clock.created_at == _CLOCK
    without_clock = _decide(_context(model="XPS-13"))
    assert without_clock.created_at is None


def test_report_is_json_serializable_shape():
    report = _decide(_context(model="XPS-13", serial="SN123"), with_clock=True)
    payload = report.to_dict()
    assert payload["device_type"] == "laptop"
    assert isinstance(payload["triggered_rules"], list)
    assert payload["triggered_count"] == len(payload["triggered_rules"])
    assert payload["created_at"] == _CLOCK.isoformat()
    assert set(payload) >= {
        "recommended_action",
        "priority",
        "confidence",
        "triggered_rules",
        "reasoning",
        "warnings",
        "engine_version",
        "rules_version",
    }
    for rule in payload["triggered_rules"]:
        assert set(rule) == {
            "rule_id",
            "action",
            "priority",
            "precedence",
            "reason",
            "won",
        }


def test_report_is_immutable():
    report = _decide(_context(model="XPS-13"))
    with pytest.raises((AttributeError, TypeError)):
        report.confidence = 1.0  # type: ignore[misc]


def test_eco_id_carried_over_from_context():
    report = _decide(_context(model="XPS-13", eco_id="ET-2026-DEADBEEF"))
    assert report.eco_id == "ET-2026-DEADBEEF"


def test_at_most_one_winning_rule():
    report = _decide(_context(device_type="CRT monitor"))
    won = [rule for rule in report.triggered_rules if rule.won]
    assert len(won) <= 1
    if won:
        assert report.winning_rule is not None
        assert report.winning_rule.rule_id == won[0].rule_id


# --- Injected config & catalogue -----------------------------------------


def test_custom_config_is_exposed_on_service():
    config = CircularConfig(min_confidence=0.99)
    service = CircularService(config=config, clock=None)
    assert service.config.min_confidence == 0.99


def test_service_loads_shipped_catalogue_by_default():
    service = CircularService(clock=None)
    assert service.catalogue.version
    assert service.catalogue.rules


def test_injected_catalogue_is_used():
    from device_ai.circular.rules import (
        DecisionRule,
        DefaultRule,
        RuleCatalogue,
        RuleCondition,
    )

    catalogue = RuleCatalogue(
        version="injected-1",
        rules=(
            DecisionRule(
                rule_id="always_recycle",
                precedence=1,
                action=RecommendedAction.RECYCLE,
                priority=Priority.LOW,
                reason="test rule always recycles a recyclable device",
                conditions=(RuleCondition("recycling", "gte", 0.0),),
            ),
        ),
        default=DefaultRule(
            action=RecommendedAction.MANUAL_REVIEW,
            priority=Priority.LOW,
            reason="fallback",
        ),
    )
    report = _decide(_context(model="XPS-13"), catalogue=catalogue)
    assert report.rules_version == "injected-1"
    assert report.recommended_action is RecommendedAction.RECYCLE
    assert report.winning_rule is not None
    assert report.winning_rule.rule_id == "always_recycle"


def test_config_from_settings_maps_env_knobs():
    from device_ai.configs.settings import Settings

    settings = Settings(
        circular_rules_path="custom/rules.yaml",
        circular_min_confidence=0.2,
    )
    config = CircularConfig.from_settings(settings)
    assert config.rules_path == "custom/rules.yaml"
    assert config.min_confidence == 0.2
