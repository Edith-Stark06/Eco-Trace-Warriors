"""Tests for the recoverability scoring engine (milestone M1.8).

The scoring engine is pure arithmetic over a list of
:class:`~device_ai.recoverability.models.RuleOutcome` s, so these tests feed it
hand-built outcomes and assert the fold: summed/clamped/rounded dimensions, the
most-severe hazard floor, the product-of-factors confidence aggregation and each
branch of the recommended-action decision table.
"""

from device_ai.fusion.models import (
    DeviceContext,
    EvidenceKind,
    FusionAttribute,
    ResolvedAttribute,
)
from device_ai.recoverability.config import RecoverabilityConfig
from device_ai.recoverability.models import (
    HazardLevel,
    RecommendedAction,
    RuleOutcome,
)
from device_ai.recoverability.profiles import profile_for
from device_ai.recoverability.scoring import ScoringEngine

_CONFIG = RecoverabilityConfig()


def _context(*, device_type="laptop", confidence=0.9):
    return DeviceContext(
        eco_id="ET-2026-0000ABCD",
        fingerprint="f" * 64,
        attributes=(
            ResolvedAttribute(
                attribute=FusionAttribute.DEVICE_TYPE,
                value=device_type,
                confidence=confidence,
                sources=(EvidenceKind.DETECTION,),
            ),
        ),
        confidence=confidence,
        evidence=(),
        conflicts=(),
        source_hashes=("a" * 64,),
        engine_version="fusion-test",
    )


def _score(outcomes, *, device_type="laptop", confidence=0.9, config=_CONFIG):
    engine = ScoringEngine(config)
    return engine.score(
        _context(device_type=device_type, confidence=confidence),
        profile_for(device_type),
        outcomes,
        engine_version="1.0.0",
    )


# --- Dimension folding ----------------------------------------------------


def test_dimensions_are_summed_and_rounded():
    outcomes = [
        RuleOutcome(rule="a", reason="a", repairability_delta=0.4),
        RuleOutcome(rule="b", reason="b", repairability_delta=0.25),
    ]
    report = _score(outcomes)
    assert report.repairability == 0.65


def test_dimensions_are_clamped_to_unit_interval():
    over = [RuleOutcome(rule="a", reason="a", reusability_delta=1.5)]
    under = [RuleOutcome(rule="a", reason="a", recyclability_delta=-0.5)]
    assert _score(over).reusability == 1.0
    assert _score(under).recyclability == 0.0


def test_scores_are_rounded_to_six_decimals():
    outcomes = [
        RuleOutcome(rule="a", reason="a", repairability_delta=0.1),
        RuleOutcome(rule="b", reason="b", repairability_delta=0.2),
    ]
    report = _score(outcomes)
    # 0.1 + 0.2 would be 0.30000000000000004 unrounded.
    assert report.repairability == 0.3


# --- Hazard aggregation ---------------------------------------------------


def test_hazard_level_is_the_most_severe_floor():
    outcomes = [
        RuleOutcome(rule="a", reason="a", hazard_floor=HazardLevel.LOW),
        RuleOutcome(rule="b", reason="b", hazard_floor=HazardLevel.HIGH),
        RuleOutcome(rule="c", reason="c", hazard_floor=None),
    ]
    report = _score(outcomes)
    assert report.hazard_level is HazardLevel.HIGH


def test_hazard_level_defaults_to_none_without_floors():
    report = _score([RuleOutcome(rule="a", reason="a")])
    assert report.hazard_level is HazardLevel.NONE


# --- Confidence aggregation ----------------------------------------------


def test_confidence_is_product_of_factors():
    outcomes = [
        RuleOutcome(rule="a", reason="a", confidence_factor=0.8),
        RuleOutcome(rule="b", reason="b", confidence_factor=0.5),
    ]
    report = _score(outcomes, confidence=1.0)
    assert report.confidence == 0.4


def test_confidence_factors_compound():
    # Two independent damping signals reduce confidence more than either alone.
    outcomes = [
        RuleOutcome(rule="a", reason="a", confidence_factor=0.8),
        RuleOutcome(rule="b", reason="b", confidence_factor=0.6),
    ]
    report = _score(outcomes, confidence=0.9)
    assert report.confidence == round(0.9 * 0.8 * 0.6, 6)


# --- Recommended-action decision table -----------------------------------


def test_high_hazard_forces_hazardous_disposal():
    outcomes = [
        RuleOutcome(rule="a", reason="a", reusability_delta=0.99),
        RuleOutcome(rule="b", reason="b", hazard_floor=HazardLevel.HIGH),
    ]
    report = _score(outcomes)
    assert report.recommended_action is RecommendedAction.HAZARDOUS_DISPOSAL


def test_forced_disposal_action_overrides_scores():
    outcomes = [
        RuleOutcome(rule="a", reason="a", reusability_delta=0.99),
        RuleOutcome(
            rule="b",
            reason="b",
            force_action=RecommendedAction.HAZARDOUS_DISPOSAL,
        ),
    ]
    assert _score(outcomes).recommended_action is (RecommendedAction.HAZARDOUS_DISPOSAL)


def test_forced_manual_review_overrides_score_ladder():
    outcomes = [
        RuleOutcome(rule="a", reason="a", reusability_delta=0.99),
        RuleOutcome(rule="b", reason="b", force_action=RecommendedAction.MANUAL_REVIEW),
    ]
    assert _score(outcomes).recommended_action is RecommendedAction.MANUAL_REVIEW


def test_high_hazard_beats_forced_manual_review():
    outcomes = [
        RuleOutcome(rule="a", reason="a", hazard_floor=HazardLevel.HIGH),
        RuleOutcome(rule="b", reason="b", force_action=RecommendedAction.MANUAL_REVIEW),
    ]
    assert _score(outcomes).recommended_action is (RecommendedAction.HAZARDOUS_DISPOSAL)


def test_high_reusability_recommends_refurbish():
    outcomes = [RuleOutcome(rule="a", reason="a", reusability_delta=0.70)]
    assert _score(outcomes).recommended_action is RecommendedAction.REFURBISH


def test_repairable_but_not_reusable_recommends_repair():
    outcomes = [
        RuleOutcome(
            rule="a",
            reason="a",
            reusability_delta=0.10,
            repairability_delta=0.60,
        )
    ]
    assert _score(outcomes).recommended_action is RecommendedAction.REPAIR


def test_only_recyclable_recommends_recycle():
    outcomes = [
        RuleOutcome(
            rule="a",
            reason="a",
            reusability_delta=0.10,
            repairability_delta=0.10,
            recyclability_delta=0.60,
        )
    ]
    assert _score(outcomes).recommended_action is RecommendedAction.RECYCLE


def test_nothing_clears_threshold_falls_through_to_manual_review():
    outcomes = [
        RuleOutcome(
            rule="a",
            reason="a",
            reusability_delta=0.10,
            repairability_delta=0.10,
            recyclability_delta=0.10,
        )
    ]
    assert _score(outcomes).recommended_action is RecommendedAction.MANUAL_REVIEW


def test_refurbish_boundary_is_inclusive():
    outcomes = [
        RuleOutcome(
            rule="a",
            reason="a",
            reusability_delta=_CONFIG.refurbish_min_reusability,
        )
    ]
    assert _score(outcomes).recommended_action is RecommendedAction.REFURBISH


# --- Explanations & provenance -------------------------------------------


def test_reasoning_and_warnings_preserve_rule_order():
    outcomes = [
        RuleOutcome(rule="a", reason="first", warning="w1"),
        RuleOutcome(rule="b", reason="second"),
        RuleOutcome(rule="c", reason="third", warning="w2"),
    ]
    report = _score(outcomes)
    assert report.reasoning == ("first", "second", "third")
    assert report.warnings == ("w1", "w2")


def test_report_carries_context_provenance():
    report = _score([RuleOutcome(rule="a", reason="a")])
    assert report.eco_id == "ET-2026-0000ABCD"
    assert report.device_type == "laptop"
    assert report.engine_version == "1.0.0"


def test_custom_thresholds_change_the_decision():
    lenient = RecoverabilityConfig(refurbish_min_reusability=0.05)
    outcomes = [RuleOutcome(rule="a", reason="a", reusability_delta=0.10)]
    assert _score(outcomes, config=lenient).recommended_action is (
        RecommendedAction.REFURBISH
    )
