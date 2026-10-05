"""Tests for the recoverability rule engine (milestone M1.8).

Each rule is exercised in isolation against a hand-built
:class:`~device_ai.fusion.models.DeviceContext`, asserting exactly the outcome
it should emit (score deltas, hazard floor, confidence factor, forced action,
warning) and that it stays silent when its trigger is absent. The rule engine's
ordered concatenation is checked separately.
"""

from device_ai.fusion.models import (
    DeviceContext,
    EvidenceKind,
    FusionAttribute,
    ResolvedAttribute,
)
from device_ai.recoverability.config import RecoverabilityConfig
from device_ai.recoverability.models import HazardLevel, RecommendedAction
from device_ai.recoverability.profiles import profile_for
from device_ai.recoverability.rules import (
    DEFAULT_RULES,
    BaselineProfileRule,
    BatteryHazardRule,
    ConflictPenaltyRule,
    HighHazardDisposalRule,
    IdentityCompletenessRule,
    LowConfidenceRule,
    RuleEngine,
    UnknownDeviceRule,
)

_CONFIG = RecoverabilityConfig()


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
    confidence=0.9,
    conflicts=(),
):
    attributes = [_resolved(FusionAttribute.DEVICE_TYPE, device_type)]
    if model:
        attributes.append(_resolved(FusionAttribute.MODEL, model))
    if serial:
        attributes.append(_resolved(FusionAttribute.SERIAL_NUMBER, serial))
    if imei:
        attributes.append(_resolved(FusionAttribute.IMEI, imei))
    return DeviceContext(
        eco_id="ET-2026-0000ABCD",
        fingerprint="f" * 64,
        attributes=tuple(attributes),
        confidence=confidence,
        evidence=(),
        conflicts=tuple(conflicts),
        source_hashes=("a" * 64,),
        engine_version="fusion-test",
    )


# --- BaselineProfileRule --------------------------------------------------


def test_baseline_rule_seeds_scores_and_hazard_from_profile():
    profile = profile_for("laptop")
    outcomes = BaselineProfileRule().evaluate(_context(), profile, _CONFIG)
    assert len(outcomes) == 1
    outcome = outcomes[0]
    assert outcome.repairability_delta == profile.repairability
    assert outcome.reusability_delta == profile.reusability
    assert outcome.recyclability_delta == profile.recyclability
    assert outcome.hazard_floor is profile.hazard
    assert outcome.reason


# --- IdentityCompletenessRule --------------------------------------------


def test_identity_rule_rewards_present_identity():
    context = _context(model="XPS-13", serial="SN123")
    outcomes = IdentityCompletenessRule().evaluate(
        context, profile_for("laptop"), _CONFIG
    )
    assert len(outcomes) == 1
    assert outcomes[0].reusability_delta == _CONFIG.identity_reuse_bonus
    assert outcomes[0].repairability_delta == _CONFIG.identity_repair_bonus
    assert outcomes[0].warning is None


def test_identity_rule_penalizes_and_warns_when_absent():
    outcomes = IdentityCompletenessRule().evaluate(
        _context(), profile_for("laptop"), _CONFIG
    )
    assert len(outcomes) == 1
    assert outcomes[0].reusability_delta == -_CONFIG.missing_identity_reuse_penalty
    assert outcomes[0].warning is not None


# --- BatteryHazardRule ----------------------------------------------------


def test_battery_rule_escalates_hazard_and_penalizes_recycling():
    outcomes = BatteryHazardRule().evaluate(_context(), profile_for("laptop"), _CONFIG)
    assert len(outcomes) == 1
    assert outcomes[0].hazard_floor is HazardLevel.MEDIUM
    assert outcomes[0].recyclability_delta == -_CONFIG.battery_recyclability_penalty


def test_battery_rule_silent_without_battery():
    outcomes = BatteryHazardRule().evaluate(
        _context(device_type="desktop"), profile_for("desktop"), _CONFIG
    )
    assert outcomes == []


def test_battery_hazard_floor_can_be_disabled():
    config = RecoverabilityConfig(battery_hazard_floor_enabled=False)
    outcomes = BatteryHazardRule().evaluate(_context(), profile_for("laptop"), config)
    assert outcomes[0].hazard_floor is None
    assert outcomes[0].recyclability_delta == -config.battery_recyclability_penalty


# --- HighHazardDisposalRule ----------------------------------------------


def test_high_hazard_rule_forces_disposal_for_crt():
    outcomes = HighHazardDisposalRule().evaluate(
        _context(device_type="crt_monitor"), profile_for("crt_monitor"), _CONFIG
    )
    assert len(outcomes) == 1
    assert outcomes[0].hazard_floor is HazardLevel.HIGH
    assert outcomes[0].force_action is RecommendedAction.HAZARDOUS_DISPOSAL


def test_high_hazard_rule_silent_for_low_hazard_device():
    outcomes = HighHazardDisposalRule().evaluate(
        _context(), profile_for("laptop"), _CONFIG
    )
    assert outcomes == []


# --- ConflictPenaltyRule --------------------------------------------------


def test_conflict_rule_damps_confidence_and_warns():
    context = _context(conflicts=("brand",))
    outcomes = ConflictPenaltyRule().evaluate(context, profile_for("laptop"), _CONFIG)
    assert len(outcomes) == 1
    assert outcomes[0].confidence_factor == _CONFIG.conflict_confidence_factor
    assert outcomes[0].warning is not None


def test_conflict_rule_silent_without_conflicts():
    outcomes = ConflictPenaltyRule().evaluate(
        _context(), profile_for("laptop"), _CONFIG
    )
    assert outcomes == []


# --- LowConfidenceRule ----------------------------------------------------


def test_low_confidence_rule_forces_review():
    context = _context(confidence=0.20)
    outcomes = LowConfidenceRule().evaluate(context, profile_for("laptop"), _CONFIG)
    assert len(outcomes) == 1
    assert outcomes[0].force_action is RecommendedAction.MANUAL_REVIEW
    assert outcomes[0].confidence_factor == _CONFIG.low_confidence_factor
    assert outcomes[0].warning is not None


def test_low_confidence_rule_silent_when_confident():
    outcomes = LowConfidenceRule().evaluate(
        _context(confidence=0.90), profile_for("laptop"), _CONFIG
    )
    assert outcomes == []


def test_low_confidence_threshold_boundary_is_inclusive_pass():
    # At exactly the threshold the rule must NOT fire (>= passes).
    context = _context(confidence=_CONFIG.low_confidence_threshold)
    outcomes = LowConfidenceRule().evaluate(context, profile_for("laptop"), _CONFIG)
    assert outcomes == []


# --- UnknownDeviceRule ----------------------------------------------------


def test_unknown_device_rule_forces_review():
    context = _context(device_type="mystery gadget")
    outcomes = UnknownDeviceRule().evaluate(
        context, profile_for("mystery gadget"), _CONFIG
    )
    assert len(outcomes) == 1
    assert outcomes[0].force_action is RecommendedAction.MANUAL_REVIEW
    assert outcomes[0].warning is not None


def test_unknown_device_rule_silent_for_known_device():
    outcomes = UnknownDeviceRule().evaluate(_context(), profile_for("laptop"), _CONFIG)
    assert outcomes == []


# --- RuleEngine -----------------------------------------------------------


def test_rule_engine_runs_all_rules_in_order():
    engine = RuleEngine()
    assert len(engine.rules) == len(DEFAULT_RULES)
    outcomes = engine.run(_context(model="XPS-13"), profile_for("laptop"), _CONFIG)
    # First outcome is always the baseline seed.
    assert outcomes[0].rule == "baseline_profile"
    rule_names = [o.rule for o in outcomes]
    assert "identity_completeness" in rule_names
    assert "battery_hazard" in rule_names


def test_rule_engine_accepts_a_custom_rule_set():
    engine = RuleEngine(rules=(BaselineProfileRule(),))
    outcomes = engine.run(_context(), profile_for("laptop"), _CONFIG)
    assert [o.rule for o in outcomes] == ["baseline_profile"]


def test_rule_engine_is_deterministic():
    engine = RuleEngine()
    context = _context(model="XPS-13", conflicts=("brand",))
    first = engine.run(context, profile_for("laptop"), _CONFIG)
    second = engine.run(context, profile_for("laptop"), _CONFIG)
    assert [o.to_dict() for o in first] == [o.to_dict() for o in second]
