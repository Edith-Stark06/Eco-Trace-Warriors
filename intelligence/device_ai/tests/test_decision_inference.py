"""Tests for the decision inference engine (milestone M2.1).

The inference engine is deterministic arithmetic over a resolved
:class:`KnowledgeBase` and the five upstream reports, so these tests feed it a
small hand-built knowledge base and hand-built reports and assert the fold: the
projection of upstream reports onto the eleven canonical ``[0, 1]`` signals, the
per-dimension weighted mean, the environmental saturation, the separate
confidence blend (with its floor), and the reasoning/warnings. No shipped
catalogue, no images, no models.

Every dimension score and the overall confidence are normalized ``[0, 1]``
measures — the engine emits normalized evidence only, never a recommended action
or a monetary value; several tests assert exactly that invariant.
"""

import pytest

from device_ai.components.models import ComponentReport
from device_ai.decision.config import DecisionConfig
from device_ai.decision.inference import DecisionInferenceEngine
from device_ai.decision.knowledge import KnowledgeBase, Normalization
from device_ai.decision.models import DecisionDimension
from device_ai.environmental.models import EnvironmentalImpactReport
from device_ai.fusion.models import (
    DeviceContext,
    EvidenceKind,
    FusionAttribute,
    ResolvedAttribute,
)
from device_ai.materials.models import (
    MaterialCategory,
    MaterialReport,
    RecoveredMaterial,
)
from device_ai.recoverability.models import (
    HazardLevel,
    RecommendedAction,
    RecoverabilityReport,
)

_CONFIG = DecisionConfig()

# A saturation block chosen so the hand-built physical amounts saturate to
# round numbers: 50 kg / 100 = 0.5, 750 MJ / 1500 = 0.5, 500 L / 1000 = 0.5,
# 0.025 kg / 0.05 = 0.5.
_NORMALIZATION = Normalization(
    carbon_saturation_kg=100.0,
    energy_saturation_mj=1500.0,
    water_saturation_l=1000.0,
    critical_recovery_saturation_kg=0.05,
)


def _knowledge(
    *,
    dimensions=None,
    confidence=None,
    version="test-knowledge-1",
) -> KnowledgeBase:
    return KnowledgeBase(
        version=version,
        dimensions=(
            dimensions
            if dimensions is not None
            else {
                DecisionDimension.REPAIRABILITY: {"repairability": 1.0},
                DecisionDimension.REUSABILITY: {"reusability": 1.0},
                DecisionDimension.RECYCLING: {"recyclability": 1.0},
                DecisionDimension.HAZARD: {"hazard_severity": 1.0},
                DecisionDimension.ENVIRONMENTAL_PRIORITY: {
                    "environmental_savings": 1.0
                },
                DecisionDimension.MATERIAL_VALUE: {"critical_material_presence": 1.0},
            }
        ),
        confidence_weights=(
            confidence
            if confidence is not None
            else {
                "recoverability": 0.2,
                "components": 0.15,
                "materials": 0.25,
                "environmental": 0.25,
                "fusion": 0.15,
            }
        ),
        normalization=_NORMALIZATION,
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
        conflicts=(),
        source_hashes=("a" * 64,),
        engine_version="fusion-test",
    )


def _recoverability(
    *,
    repairability=0.8,
    reusability=0.8,
    recyclability=0.8,
    hazard=HazardLevel.LOW,
    confidence=0.9,
):
    return RecoverabilityReport(
        device_type="laptop",
        repairability=repairability,
        reusability=reusability,
        recyclability=recyclability,
        hazard_level=hazard,
        confidence=confidence,
        recommended_action=RecommendedAction.RECYCLE,
        reasoning=(),
        warnings=(),
    )


def _components(*, overall_confidence=0.9):
    return ComponentReport(
        device_type="laptop",
        components=(),
        overall_confidence=overall_confidence,
        reasoning=(),
        warnings=(),
    )


def _material(
    *,
    name="Steel",
    category=MaterialCategory.FERROUS_METAL,
    mass_g=1000.0,
    confidence=0.9,
    recoverable=True,
    hazardous=False,
):
    return RecoveredMaterial(
        name=name,
        category=category,
        mass_g=mass_g,
        confidence=confidence,
        recoverable=recoverable,
        hazardous=hazardous,
        source_components=(),
        reason="",
    )


def _materials(*materials, device_type="laptop", overall_confidence=0.9):
    recoverable_mass = sum(m.mass_g for m in materials if m.recoverable)
    hazardous_mass = sum(m.mass_g for m in materials if m.hazardous)
    return MaterialReport(
        device_type=device_type,
        materials=tuple(materials),
        total_mass_g=round(sum(m.mass_g for m in materials), 3),
        recoverable_mass_g=round(recoverable_mass, 3),
        hazardous_mass_g=round(hazardous_mass, 3),
        overall_confidence=overall_confidence,
        reasoning=(),
        warnings=(),
    )


def _environmental(
    *,
    carbon_saved_kg=50.0,
    energy_saved_mj=750.0,
    water_saved_l=500.0,
    critical_material_recovery_kg=0.025,
    circularity_index=0.5,
    hazard_reduction_score=0.4,
    confidence=0.9,
):
    return EnvironmentalImpactReport(
        device_type="laptop",
        contributions=(),
        carbon_saved_kg=carbon_saved_kg,
        energy_saved_mj=energy_saved_mj,
        water_saved_l=water_saved_l,
        landfill_diversion_kg=1.0,
        critical_material_recovery_kg=critical_material_recovery_kg,
        circularity_index=circularity_index,
        hazard_reduction_score=hazard_reduction_score,
        confidence=confidence,
        reasoning=(),
        warnings=(),
    )


def _infer(
    *,
    context=None,
    recoverability=None,
    components=None,
    materials=None,
    environmental=None,
    knowledge=None,
    config=_CONFIG,
):
    engine = DecisionInferenceEngine(config)
    return engine.infer(
        context if context is not None else _context(),
        recoverability if recoverability is not None else _recoverability(),
        components if components is not None else _components(),
        materials if materials is not None else _materials(_material()),
        environmental if environmental is not None else _environmental(),
        knowledge if knowledge is not None else _knowledge(),
        knowledge_version="test-knowledge-1",
        engine_version="engine-test",
    )


# --- Signal projection: pass-through scores ------------------------------


def test_repairability_dimension_passes_through_recoverability_score():
    report = _infer(recoverability=_recoverability(repairability=0.6))
    # Repairability dimension weights repairability 1.0 plus a hand-built
    # single-signal map → the score is exactly the upstream repairability.
    assert report.repairability_score == 0.6


def test_reusability_and_recycling_pass_through_their_scores():
    report = _infer(recoverability=_recoverability(reusability=0.7, recyclability=0.3))
    assert report.reusability_score == 0.7
    assert report.recycling_score == 0.3


# --- Signal projection: hazard severity ordering -------------------------


@pytest.mark.parametrize(
    "hazard,expected",
    [
        (HazardLevel.NONE, 0.0),
        (HazardLevel.UNKNOWN, 0.25),
        (HazardLevel.LOW, 0.4),
        (HazardLevel.MEDIUM, 0.7),
        (HazardLevel.HIGH, 1.0),
    ],
)
def test_hazard_dimension_maps_severity(hazard, expected):
    report = _infer(recoverability=_recoverability(hazard=hazard))
    assert report.hazard_score == expected


# --- Signal projection: environmental saturation -------------------------


def test_environmental_savings_is_mean_of_saturated_axes():
    # carbon 50/100=0.5, energy 750/1500=0.5, water 500/1000=0.5 → mean 0.5.
    report = _infer(
        knowledge=_knowledge(
            dimensions={
                DecisionDimension.REPAIRABILITY: {"repairability": 1.0},
                DecisionDimension.REUSABILITY: {"reusability": 1.0},
                DecisionDimension.RECYCLING: {"recyclability": 1.0},
                DecisionDimension.HAZARD: {"hazard_severity": 1.0},
                DecisionDimension.ENVIRONMENTAL_PRIORITY: {
                    "environmental_savings": 1.0
                },
                DecisionDimension.MATERIAL_VALUE: {"environmental_savings": 1.0},
            }
        )
    )
    assert report.environmental_priority == 0.5


def test_physical_amounts_saturate_at_the_ceiling():
    # Amounts far above the ceilings clamp to 1.0, not beyond.
    report = _infer(
        environmental=_environmental(
            carbon_saved_kg=10_000.0,
            energy_saved_mj=10_000_000.0,
            water_saved_l=10_000_000.0,
        ),
        knowledge=_knowledge(
            dimensions={
                DecisionDimension.REPAIRABILITY: {"repairability": 1.0},
                DecisionDimension.REUSABILITY: {"reusability": 1.0},
                DecisionDimension.RECYCLING: {"recyclability": 1.0},
                DecisionDimension.HAZARD: {"hazard_severity": 1.0},
                DecisionDimension.ENVIRONMENTAL_PRIORITY: {
                    "environmental_savings": 1.0
                },
                DecisionDimension.MATERIAL_VALUE: {"critical_material_presence": 1.0},
            }
        ),
    )
    assert report.environmental_priority == 1.0


def test_critical_material_presence_saturates():
    # 0.025 kg / 0.05 ceiling = 0.5.
    report = _infer(
        environmental=_environmental(critical_material_recovery_kg=0.025),
        knowledge=_knowledge(
            dimensions={
                DecisionDimension.REPAIRABILITY: {"repairability": 1.0},
                DecisionDimension.REUSABILITY: {"reusability": 1.0},
                DecisionDimension.RECYCLING: {"recyclability": 1.0},
                DecisionDimension.HAZARD: {"hazard_severity": 1.0},
                DecisionDimension.ENVIRONMENTAL_PRIORITY: {"circularity_index": 1.0},
                DecisionDimension.MATERIAL_VALUE: {"critical_material_presence": 1.0},
            }
        ),
    )
    assert report.material_value_score == 0.5


# --- Signal projection: mass fractions -----------------------------------


def test_recycling_blends_recoverable_mass_fraction():
    # recyclability 0.4 (weight 0.5) + recoverable fraction 0.8 (weight 0.5)
    # → (0.2 + 0.4) / 1.0 = 0.6.
    knowledge = _knowledge(
        dimensions={
            DecisionDimension.REPAIRABILITY: {"repairability": 1.0},
            DecisionDimension.REUSABILITY: {"reusability": 1.0},
            DecisionDimension.RECYCLING: {
                "recyclability": 0.5,
                "recoverable_mass_fraction": 0.5,
            },
            DecisionDimension.HAZARD: {"hazard_severity": 1.0},
            DecisionDimension.ENVIRONMENTAL_PRIORITY: {"environmental_savings": 1.0},
            DecisionDimension.MATERIAL_VALUE: {"critical_material_presence": 1.0},
        }
    )
    report = _infer(
        recoverability=_recoverability(recyclability=0.4),
        materials=_materials(
            _material(name="Steel", mass_g=800.0, recoverable=True),
            _material(name="Resin", mass_g=200.0, recoverable=False),
        ),
        knowledge=knowledge,
    )
    assert report.recycling_score == 0.6


def test_hazardous_mass_fraction_is_zero_when_total_mass_zero():
    # An empty material report must not divide by zero; the fraction is 0.
    knowledge = _knowledge(
        dimensions={
            DecisionDimension.REPAIRABILITY: {"repairability": 1.0},
            DecisionDimension.REUSABILITY: {"reusability": 1.0},
            DecisionDimension.RECYCLING: {"recyclability": 1.0},
            DecisionDimension.HAZARD: {"hazardous_mass_fraction": 1.0},
            DecisionDimension.ENVIRONMENTAL_PRIORITY: {"environmental_savings": 1.0},
            DecisionDimension.MATERIAL_VALUE: {"critical_material_presence": 1.0},
        }
    )
    report = _infer(materials=_materials(device_type="laptop"), knowledge=knowledge)
    assert report.hazard_score == 0.0


# --- Signal projection: identity completeness ----------------------------


def test_identity_completeness_counts_present_attributes():
    # Two of four identity attributes present → 0.5.
    knowledge = _knowledge(
        dimensions={
            DecisionDimension.REPAIRABILITY: {"identity_completeness": 1.0},
            DecisionDimension.REUSABILITY: {"reusability": 1.0},
            DecisionDimension.RECYCLING: {"recyclability": 1.0},
            DecisionDimension.HAZARD: {"hazard_severity": 1.0},
            DecisionDimension.ENVIRONMENTAL_PRIORITY: {"environmental_savings": 1.0},
            DecisionDimension.MATERIAL_VALUE: {"critical_material_presence": 1.0},
        }
    )
    report = _infer(
        context=_context(model="XPS-13", serial="SN123"), knowledge=knowledge
    )
    assert report.repairability_score == 0.5


def test_full_identity_scores_one():
    knowledge = _knowledge(
        dimensions={
            DecisionDimension.REPAIRABILITY: {"identity_completeness": 1.0},
            DecisionDimension.REUSABILITY: {"reusability": 1.0},
            DecisionDimension.RECYCLING: {"recyclability": 1.0},
            DecisionDimension.HAZARD: {"hazard_severity": 1.0},
            DecisionDimension.ENVIRONMENTAL_PRIORITY: {"environmental_savings": 1.0},
            DecisionDimension.MATERIAL_VALUE: {"critical_material_presence": 1.0},
        }
    )
    report = _infer(
        context=_context(model="M", serial="S", imei="I", mac="AA"),
        knowledge=knowledge,
    )
    assert report.repairability_score == 1.0


# --- Weighted-mean blend --------------------------------------------------


def test_dimension_is_weighted_mean_of_its_signals():
    # repairability 0.9 (weight 0.75) + identity 0.5 (weight 0.25)
    # → (0.675 + 0.125) / 1.0 = 0.8.
    knowledge = _knowledge(
        dimensions={
            DecisionDimension.REPAIRABILITY: {
                "repairability": 0.75,
                "identity_completeness": 0.25,
            },
            DecisionDimension.REUSABILITY: {"reusability": 1.0},
            DecisionDimension.RECYCLING: {"recyclability": 1.0},
            DecisionDimension.HAZARD: {"hazard_severity": 1.0},
            DecisionDimension.ENVIRONMENTAL_PRIORITY: {"environmental_savings": 1.0},
            DecisionDimension.MATERIAL_VALUE: {"critical_material_presence": 1.0},
        }
    )
    report = _infer(
        context=_context(model="XPS-13", serial="SN123"),
        recoverability=_recoverability(repairability=0.9),
        knowledge=knowledge,
    )
    assert report.repairability_score == 0.8


def test_evidence_breakdown_records_every_signal():
    report = _infer(
        context=_context(model="XPS-13", serial="SN123"),
        knowledge=_knowledge(
            dimensions={
                DecisionDimension.REPAIRABILITY: {
                    "repairability": 0.75,
                    "identity_completeness": 0.25,
                },
                DecisionDimension.REUSABILITY: {"reusability": 1.0},
                DecisionDimension.RECYCLING: {"recyclability": 1.0},
                DecisionDimension.HAZARD: {"hazard_severity": 1.0},
                DecisionDimension.ENVIRONMENTAL_PRIORITY: {
                    "environmental_savings": 1.0
                },
                DecisionDimension.MATERIAL_VALUE: {"critical_material_presence": 1.0},
            }
        ),
    )
    assert report.dimension_count == len(DecisionDimension)
    by_dim = {ev.dimension: ev for ev in report.dimensions}
    repair = by_dim[DecisionDimension.REPAIRABILITY]
    names = {signal.name for signal in repair.signals}
    assert names == {"repairability", "identity_completeness"}
    assert repair.reason


def test_all_scores_are_within_unit_interval():
    report = _infer()
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


# --- Overall confidence (separate axis) ----------------------------------


def test_confidence_blends_all_five_sources():
    # All five at 0.8 with any weights → weighted mean 0.8.
    report = _infer(
        context=_context(confidence=0.8),
        recoverability=_recoverability(confidence=0.8),
        components=_components(overall_confidence=0.8),
        materials=_materials(_material(), overall_confidence=0.8),
        environmental=_environmental(confidence=0.8),
    )
    assert report.overall_confidence == 0.8


def test_confidence_drops_sources_at_or_below_floor():
    # Materials confidence at the floor (0.05) is dropped; the blend uses only
    # the remaining sources, so a near-zero source does not anchor the result.
    config = DecisionConfig(min_confidence=0.05)
    knowledge = _knowledge(
        confidence={"materials": 0.5, "fusion": 0.5},
    )
    report = _infer(
        context=_context(confidence=0.9),
        materials=_materials(_material(), overall_confidence=0.05),
        knowledge=knowledge,
        config=config,
    )
    # materials dropped → only fusion (0.9) remains → 0.9.
    assert report.overall_confidence == 0.9


def test_confidence_is_zero_when_every_source_below_floor():
    config = DecisionConfig(min_confidence=0.5)
    report = _infer(
        context=_context(confidence=0.1),
        recoverability=_recoverability(confidence=0.1),
        components=_components(overall_confidence=0.1),
        materials=_materials(_material(), overall_confidence=0.1),
        environmental=_environmental(confidence=0.1),
        config=config,
    )
    assert report.overall_confidence == 0.0


def test_confidence_never_scales_a_dimension_score():
    # Halving every upstream confidence leaves the dimension scores untouched.
    strong = _infer(
        context=_context(confidence=0.9),
        recoverability=_recoverability(confidence=0.9),
        components=_components(overall_confidence=0.9),
        materials=_materials(_material(), overall_confidence=0.9),
        environmental=_environmental(confidence=0.9),
    )
    weak = _infer(
        context=_context(confidence=0.2),
        recoverability=_recoverability(confidence=0.2),
        components=_components(overall_confidence=0.2),
        materials=_materials(_material(), overall_confidence=0.2),
        environmental=_environmental(confidence=0.2),
    )
    assert strong.repairability_score == weak.repairability_score
    assert weak.overall_confidence < strong.overall_confidence


# --- Reasoning & warnings -------------------------------------------------


def test_reasoning_is_populated_and_normalized_only():
    report = _infer()
    assert report.reasoning
    joined = " ".join(report.reasoning).lower()
    assert "normalized evidence only" in joined
    assert "does not itself recommend" in joined


def test_hazard_present_warns():
    report = _infer(recoverability=_recoverability(hazard=HazardLevel.HIGH))
    assert any("hazard" in w.lower() for w in report.warnings)


def test_unknown_hazard_does_not_warn():
    # UNKNOWN is "needs review", not an asserted hazard — no hazard warning.
    report = _infer(recoverability=_recoverability(hazard=HazardLevel.UNKNOWN))
    assert not any("carries an assessed hazard" in w.lower() for w in report.warnings)


def test_empty_material_report_warns():
    report = _infer(materials=_materials(device_type="laptop"))
    assert any("material breakdown is empty" in w.lower() for w in report.warnings)


def test_unresolved_device_type_warns():
    report = _infer(
        context=_context(device_type=""),
        materials=_materials(_material(), device_type=""),
    )
    assert any("device type is unresolved" in w.lower() for w in report.warnings)


def test_low_environmental_confidence_warns():
    config = DecisionConfig(min_confidence=0.5)
    report = _infer(
        environmental=_environmental(confidence=0.1),
        config=config,
    )
    assert any("environmental confidence" in w.lower() for w in report.warnings)


# --- Device type resolution ----------------------------------------------


def test_device_type_prefers_material_then_context():
    report = _infer(
        context=_context(device_type="laptop"),
        materials=_materials(_material(), device_type="tablet"),
    )
    assert report.device_type == "tablet"


def test_device_type_falls_back_to_context():
    report = _infer(
        context=_context(device_type="laptop"),
        materials=_materials(_material(), device_type=""),
    )
    assert report.device_type == "laptop"


# --- Provenance & determinism --------------------------------------------


def test_eco_id_and_versions_are_stamped():
    report = _infer(context=_context(eco_id="ET-2026-DEADBEEF"))
    assert report.eco_id == "ET-2026-DEADBEEF"
    assert report.engine_version == "engine-test"
    assert report.knowledge_version == "test-knowledge-1"


def test_inference_is_deterministic():
    engine = DecisionInferenceEngine(_CONFIG)
    args = (
        _context(model="XPS-13"),
        _recoverability(),
        _components(),
        _materials(_material(mass_g=1234.0)),
        _environmental(),
        _knowledge(),
    )
    first = engine.infer(*args)
    second = engine.infer(*args)
    assert first.to_dict() == second.to_dict()
