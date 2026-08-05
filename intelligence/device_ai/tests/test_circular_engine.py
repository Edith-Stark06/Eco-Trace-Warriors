"""Tests for the circular decision engine (milestone M2.2).

The engine is deterministic evaluation over a resolved :class:`RuleCatalogue`
and the four upstream inputs, so these tests feed it hand-built reports and a
hand-built catalogue and assert each stage: the projection of the upstream
reports onto the canonical ``[0, 1]`` signals, the precedence-ordered rule match
(lowest precedence wins), the recommendation, the confidence aggregation and the
default fallback. No shipped catalogue, no upstream engines, no models.
"""

import pytest

from device_ai.circular.config import CircularConfig
from device_ai.circular.engine import CircularDecisionEngine
from device_ai.circular.models import DecisionReport, Priority, RecommendedAction
from device_ai.circular.rules import (
    DecisionRule,
    DefaultRule,
    RuleCatalogue,
    RuleCondition,
)
from device_ai.decision.models import DecisionKnowledgeReport
from device_ai.environmental.models import EnvironmentalImpactReport
from device_ai.fusion.models import (
    Conflict,
    DeviceContext,
    EvidenceKind,
    FusionAttribute,
    ResolvedAttribute,
)
from device_ai.recoverability.models import HazardLevel, RecoverabilityReport

_CONFIG = CircularConfig()
_ENGINE = CircularDecisionEngine(_CONFIG)


# --- Hand-built inputs ----------------------------------------------------


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
        confidence=0.9,
        evidence=(),
        conflicts=tuple(conflicts),
        source_hashes=("a" * 64,),
        engine_version="fusion-test",
    )


def _knowledge(
    *,
    device_type="laptop",
    repairability=0.5,
    reusability=0.5,
    recycling=0.5,
    hazard=0.2,
    environmental_priority=0.5,
    material_value=0.5,
    confidence=0.9,
):
    return DecisionKnowledgeReport(
        device_type=device_type,
        repairability_score=repairability,
        reusability_score=reusability,
        recycling_score=recycling,
        hazard_score=hazard,
        environmental_priority=environmental_priority,
        material_value_score=material_value,
        overall_confidence=confidence,
        dimensions=(),
        reasoning=(),
        warnings=(),
    )


def _recoverability(
    *,
    device_type="laptop",
    repairability=0.8,
    reusability=0.8,
    recyclability=0.8,
    hazard=HazardLevel.LOW,
    confidence=0.9,
    action=RecommendedAction.REFURBISH,
):
    return RecoverabilityReport(
        device_type=device_type,
        repairability=repairability,
        reusability=reusability,
        recyclability=recyclability,
        hazard_level=hazard,
        confidence=confidence,
        recommended_action=action,
        reasoning=(),
        warnings=(),
    )


def _environmental(
    *,
    device_type="laptop",
    circularity_index=0.5,
    hazard_reduction_score=0.4,
    confidence=0.9,
):
    return EnvironmentalImpactReport(
        device_type=device_type,
        contributions=(),
        carbon_saved_kg=1.0,
        energy_saved_mj=1.0,
        water_saved_l=1.0,
        landfill_diversion_kg=1.0,
        critical_material_recovery_kg=0.01,
        circularity_index=circularity_index,
        hazard_reduction_score=hazard_reduction_score,
        confidence=confidence,
        reasoning=(),
        warnings=(),
    )


def _condition(signal, operator="gte", threshold=0.5):
    return RuleCondition(signal=signal, operator=operator, threshold=threshold)


def _rule(
    rule_id,
    precedence,
    *conditions,
    action=RecommendedAction.RECYCLE,
    priority=Priority.LOW,
    reason="matched",
    confidence_factor=1.0,
    warning=None,
):
    return DecisionRule(
        rule_id=rule_id,
        precedence=precedence,
        action=action,
        priority=priority,
        reason=reason,
        conditions=tuple(conditions),
        confidence_factor=confidence_factor,
        warning=warning,
    )


def _catalogue(*rules, version="test-1", default=None):
    ordered = tuple(sorted(rules, key=lambda rule: rule.precedence))
    return RuleCatalogue(
        version=version,
        rules=ordered,
        default=default
        or DefaultRule(
            action=RecommendedAction.MANUAL_REVIEW,
            priority=Priority.LOW,
            reason="no rule matched",
        ),
    )


def _evaluate(
    *,
    context=None,
    knowledge=None,
    recoverability=None,
    environmental=None,
    catalogue=None,
):
    return _ENGINE.evaluate(
        context if context is not None else _context(),
        knowledge if knowledge is not None else _knowledge(),
        recoverability if recoverability is not None else _recoverability(),
        environmental if environmental is not None else _environmental(),
        catalogue if catalogue is not None else _catalogue(),
        rules_version="test-1",
        engine_version="engine-test",
    )


# --- Signal projection ----------------------------------------------------


def test_knowledge_scores_pass_through_to_signals():
    # A single-condition rule per signal reads exactly the projected value.
    knowledge = _knowledge(reusability=0.7)
    rule = _rule(
        "reuse",
        1,
        _condition("reusability", "gte", 0.7),
        action=RecommendedAction.REFURBISH,
    )
    report = _evaluate(knowledge=knowledge, catalogue=_catalogue(rule))
    assert report.recommended_action is RecommendedAction.REFURBISH
    # 0.69 would not clear the 0.7 threshold, confirming pass-through fidelity.
    lower = _evaluate(
        knowledge=_knowledge(reusability=0.69), catalogue=_catalogue(rule)
    )
    assert lower.recommended_action is RecommendedAction.MANUAL_REVIEW


@pytest.mark.parametrize(
    "hazard,expected_fires",
    [
        (HazardLevel.NONE, False),
        (HazardLevel.UNKNOWN, False),
        (HazardLevel.LOW, False),
        (HazardLevel.MEDIUM, True),
        (HazardLevel.HIGH, True),
    ],
)
def test_hazard_severity_signal_ordering(hazard, expected_fires):
    # hazard_severity: NONE=0, UNKNOWN=0.25, LOW=0.4, MEDIUM=0.7, HIGH=1.0.
    rule = _rule(
        "haz",
        1,
        _condition("hazard_severity", "gte", 0.7),
        action=RecommendedAction.HAZARDOUS_DISPOSAL,
        priority=Priority.HIGH,
    )
    report = _evaluate(
        recoverability=_recoverability(hazard=hazard, action=RecommendedAction.RECYCLE),
        catalogue=_catalogue(rule),
    )
    fired = report.recommended_action is RecommendedAction.HAZARDOUS_DISPOSAL
    assert fired is expected_fires


def test_upstream_forced_flags_project_to_one():
    review_rule = _rule(
        "review",
        1,
        _condition("upstream_manual_review", "gte", 1.0),
        action=RecommendedAction.MANUAL_REVIEW,
    )
    report = _evaluate(
        recoverability=_recoverability(action=RecommendedAction.MANUAL_REVIEW),
        catalogue=_catalogue(review_rule),
    )
    assert report.winning_rule is not None
    assert report.winning_rule.rule_id == "review"


def test_conflict_flag_projects_from_context():
    conflict = Conflict(
        attribute=FusionAttribute.BRAND, resolved_value="Dell", claims=()
    )
    rule = _rule(
        "conf",
        1,
        _condition("conflict", "gte", 1.0),
        action=RecommendedAction.MANUAL_REVIEW,
    )
    matched = _evaluate(
        context=_context(conflicts=(conflict,)), catalogue=_catalogue(rule)
    )
    assert matched.winning_rule is not None
    clean = _evaluate(context=_context(), catalogue=_catalogue(rule))
    assert clean.winning_rule is None


def test_identity_completeness_is_fraction_of_present_fields():
    # All four identity fields present → identity_completeness == 1.0.
    rule = _rule(
        "identity",
        1,
        _condition("identity_completeness", "gte", 1.0),
        action=RecommendedAction.REFURBISH,
    )
    full = _evaluate(
        context=_context(model="m", serial="s", imei="i", mac="x"),
        catalogue=_catalogue(rule),
    )
    assert full.winning_rule is not None
    # Two of four present → 0.5, below the 1.0 threshold.
    partial = _evaluate(
        context=_context(model="m", serial="s"), catalogue=_catalogue(rule)
    )
    assert partial.winning_rule is None


# --- Precedence & determinism --------------------------------------------


def test_lowest_precedence_matching_rule_wins():
    high_prec = _rule(
        "loser",
        50,
        _condition("recycling", "gte", 0.4),
        action=RecommendedAction.RECYCLE,
    )
    low_prec = _rule(
        "winner",
        10,
        _condition("recycling", "gte", 0.4),
        action=RecommendedAction.REPAIR,
    )
    report = _evaluate(
        knowledge=_knowledge(recycling=0.9),
        catalogue=_catalogue(high_prec, low_prec),
    )
    assert report.recommended_action is RecommendedAction.REPAIR
    assert report.winning_rule.rule_id == "winner"
    # Both fired and are retained; only the winner is flagged won.
    assert report.triggered_count == 2
    won = [r for r in report.triggered_rules if r.won]
    assert len(won) == 1 and won[0].rule_id == "winner"


def test_triggered_rules_are_in_precedence_order():
    a = _rule("a", 10, _condition("recycling", "gte", 0.4))
    b = _rule("b", 20, _condition("recycling", "gte", 0.4))
    c = _rule("c", 30, _condition("recycling", "gte", 0.4))
    report = _evaluate(
        knowledge=_knowledge(recycling=0.9), catalogue=_catalogue(c, a, b)
    )
    assert [r.rule_id for r in report.triggered_rules] == ["a", "b", "c"]


def test_evaluation_is_deterministic():
    context = _context(model="XPS-13", serial="SN123")
    catalogue = _catalogue(
        _rule("r", 10, _condition("recycling", "gte", 0.4)),
    )
    first = _evaluate(context=context, catalogue=catalogue)
    second = _evaluate(context=context, catalogue=catalogue)
    assert first.to_dict() == second.to_dict()


# --- Recommendation coverage: all actions and priorities -----------------


@pytest.mark.parametrize(
    "action",
    [
        RecommendedAction.REFURBISH,
        RecommendedAction.REPAIR,
        RecommendedAction.RECYCLE,
        RecommendedAction.HAZARDOUS_DISPOSAL,
        RecommendedAction.MANUAL_REVIEW,
    ],
)
def test_every_action_can_be_recommended(action):
    rule = _rule("any", 1, _condition("recycling", "gte", 0.4), action=action)
    report = _evaluate(knowledge=_knowledge(recycling=0.9), catalogue=_catalogue(rule))
    assert report.recommended_action is action


@pytest.mark.parametrize("priority", [Priority.HIGH, Priority.MEDIUM, Priority.LOW])
def test_every_priority_can_be_recommended(priority):
    rule = _rule("any", 1, _condition("recycling", "gte", 0.4), priority=priority)
    report = _evaluate(knowledge=_knowledge(recycling=0.9), catalogue=_catalogue(rule))
    assert report.priority is priority


# --- Default fallback -----------------------------------------------------


def test_default_applies_when_no_rule_fires():
    # A rule that cannot match (threshold above any possible signal).
    rule = _rule("never", 1, _condition("recycling", "gt", 1.0))
    default = DefaultRule(
        action=RecommendedAction.MANUAL_REVIEW,
        priority=Priority.LOW,
        reason="fallback reason",
    )
    report = _evaluate(
        knowledge=_knowledge(recycling=0.5),
        catalogue=_catalogue(rule, default=default),
    )
    assert report.recommended_action is RecommendedAction.MANUAL_REVIEW
    assert report.priority is Priority.LOW
    assert report.winning_rule is None
    assert report.triggered_count == 0
    assert any("fallback reason" in reason for reason in report.reasoning)


# --- Confidence aggregation ----------------------------------------------


def test_confidence_is_decision_confidence_when_no_damping():
    rule = _rule("r", 1, _condition("recycling", "gte", 0.4))
    report = _evaluate(
        knowledge=_knowledge(recycling=0.9, confidence=0.8),
        catalogue=_catalogue(rule),
    )
    assert report.confidence == 0.8


def test_confidence_factors_of_fired_rules_compound():
    a = _rule("a", 10, _condition("recycling", "gte", 0.4), confidence_factor=0.5)
    b = _rule("b", 20, _condition("recycling", "gte", 0.4), confidence_factor=0.5)
    report = _evaluate(
        knowledge=_knowledge(recycling=0.9, confidence=0.8),
        catalogue=_catalogue(a, b),
    )
    # 0.8 * 0.5 * 0.5 = 0.2.
    assert report.confidence == 0.2


def test_confidence_does_not_change_action():
    rule = _rule(
        "r",
        1,
        _condition("recycling", "gte", 0.4),
        action=RecommendedAction.RECYCLE,
        confidence_factor=0.1,
    )
    report = _evaluate(knowledge=_knowledge(recycling=0.9), catalogue=_catalogue(rule))
    assert report.recommended_action is RecommendedAction.RECYCLE


# --- Reasoning & warnings -------------------------------------------------


def test_winning_rule_reason_is_in_reasoning():
    rule = _rule(
        "r",
        1,
        _condition("recycling", "gte", 0.4),
        reason="clearly recyclable",
    )
    report = _evaluate(knowledge=_knowledge(recycling=0.9), catalogue=_catalogue(rule))
    assert any("clearly recyclable" in reason for reason in report.reasoning)


def test_rule_warning_is_surfaced():
    rule = _rule(
        "r",
        1,
        _condition("recycling", "gte", 0.4),
        warning="handle with care",
    )
    report = _evaluate(knowledge=_knowledge(recycling=0.9), catalogue=_catalogue(rule))
    assert "handle with care" in report.warnings


def test_assessed_hazard_adds_a_warning():
    rule = _rule("r", 1, _condition("recycling", "gte", 0.4))
    report = _evaluate(
        knowledge=_knowledge(recycling=0.9),
        recoverability=_recoverability(hazard=HazardLevel.MEDIUM),
        catalogue=_catalogue(rule),
    )
    assert any("hazard" in warning.lower() for warning in report.warnings)


def test_low_confidence_adds_a_warning():
    rule = _rule("r", 1, _condition("recycling", "gte", 0.4), confidence_factor=0.1)
    report = _evaluate(
        knowledge=_knowledge(recycling=0.9, confidence=0.3),
        catalogue=_catalogue(rule),
    )
    # 0.3 * 0.1 = 0.03, at or below the default 0.35 floor.
    assert any("low-confidence" in warning.lower() for warning in report.warnings)


def test_overridden_rules_are_noted_in_reasoning():
    winner = _rule("winner", 10, _condition("recycling", "gte", 0.4))
    loser = _rule("loser", 20, _condition("recycling", "gte", 0.4))
    report = _evaluate(
        knowledge=_knowledge(recycling=0.9), catalogue=_catalogue(winner, loser)
    )
    assert any("overridden" in reason.lower() for reason in report.reasoning)


# --- Report shape & provenance -------------------------------------------


def test_report_carries_provenance_and_device_type():
    report = _evaluate(
        knowledge=_knowledge(device_type="laptop"),
        catalogue=_catalogue(_rule("r", 1, _condition("recycling", "gte", 0.4))),
    )
    assert isinstance(report, DecisionReport)
    assert report.device_type == "laptop"
    assert report.eco_id == "ET-2026-0000ABCD"
    assert report.engine_version == "engine-test"
    assert report.rules_version == "test-1"
    assert report.created_at is None


def test_device_type_falls_back_across_inputs():
    # Knowledge has no device type; recoverability does.
    report = _evaluate(
        knowledge=_knowledge(device_type=""),
        recoverability=_recoverability(device_type="crt_monitor"),
        catalogue=_catalogue(_rule("r", 1, _condition("recycling", "gte", 0.4))),
    )
    assert report.device_type == "crt_monitor"
