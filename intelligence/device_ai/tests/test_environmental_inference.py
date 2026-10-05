"""Tests for the environmental inference engine (milestone M1.11).

The inference engine is deterministic arithmetic over a resolved
:class:`FactorLibrary` and the four upstream reports, so these tests feed it a
small hand-built factor library and hand-built reports and assert the fold:
mass→savings conversion, per-category aggregation, the confidence floor, the
landfill/critical-recovery quantities, the circularity and hazard-reduction
indices, the separate confidence blend and the reasoning/warnings. No shipped
catalogue, no images, no models.
"""

import pytest

from device_ai.components.models import ComponentReport
from device_ai.environmental.config import EnvironmentalConfig
from device_ai.environmental.factors import FactorLibrary, MaterialFactor
from device_ai.environmental.inference import EnvironmentalInferenceEngine
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

_CONFIG = EnvironmentalConfig()


def _library():
    return FactorLibrary(
        version="test-factors-1",
        factors={
            MaterialCategory.FERROUS_METAL: MaterialFactor(
                category=MaterialCategory.FERROUS_METAL,
                carbon_kg_per_kg=2.0,
                energy_mj_per_kg=20.0,
                water_l_per_kg=10.0,
            ),
            MaterialCategory.PRECIOUS_METAL: MaterialFactor(
                category=MaterialCategory.PRECIOUS_METAL,
                carbon_kg_per_kg=1000.0,
                energy_mj_per_kg=15000.0,
                water_l_per_kg=1000.0,
                critical=True,
            ),
        },
        default=MaterialFactor(
            category=MaterialCategory.OTHER,
            carbon_kg_per_kg=1.0,
            energy_mj_per_kg=10.0,
            water_l_per_kg=10.0,
        ),
    )


def _context(*, eco_id="ET-2026-0000ABCD"):
    return DeviceContext(
        eco_id=eco_id,
        fingerprint="f" * 64,
        attributes=(
            ResolvedAttribute(
                attribute=FusionAttribute.DEVICE_TYPE,
                value="laptop",
                confidence=0.9,
                sources=(EvidenceKind.DETECTION,),
            ),
        ),
        confidence=0.9,
        evidence=(),
        conflicts=(),
        source_hashes=("a" * 64,),
        engine_version="fusion-test",
    )


def _recoverability(*, recyclability=0.8, hazard=HazardLevel.LOW, confidence=0.9):
    return RecoverabilityReport(
        device_type="laptop",
        repairability=0.8,
        reusability=0.8,
        recyclability=recyclability,
        hazard_level=hazard,
        confidence=confidence,
        recommended_action=RecommendedAction.RECYCLE,
        reasoning=(),
        warnings=(),
    )


def _components():
    return ComponentReport(
        device_type="laptop",
        components=(),
        overall_confidence=0.9,
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


def _materials(
    *materials,
    device_type="laptop",
    overall_confidence=0.9,
):
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


def _infer(materials, *, recoverability=None, config=_CONFIG, library=None):
    engine = EnvironmentalInferenceEngine(config)
    return engine.infer(
        _context(),
        recoverability if recoverability is not None else _recoverability(),
        _components(),
        materials,
        library if library is not None else _library(),
    )


# --- Resource-savings conversion -----------------------------------------


def test_carbon_energy_water_are_mass_times_factor():
    # 1000 g = 1 kg of ferrous metal at 2.0/20.0/10.0 per kg.
    report = _infer(_materials(_material(mass_g=1000.0)))
    assert report.carbon_saved_kg == 2.0
    assert report.energy_saved_mj == 20.0
    assert report.water_saved_l == 10.0


def test_savings_scale_linearly_with_mass():
    report = _infer(_materials(_material(mass_g=2500.0)))
    assert report.carbon_saved_kg == 5.0  # 2.5 kg * 2.0
    assert report.energy_saved_mj == 50.0


def test_metrics_are_not_clamped_to_unit_interval():
    # A precious-metal recovery yields a carbon figure far above 1.0 — physical
    # metrics must never be clamped like a probability.
    report = _infer(
        _materials(
            _material(name="Gold", category=MaterialCategory.PRECIOUS_METAL, mass_g=5.0)
        )
    )
    assert report.carbon_saved_kg == 5.0  # 0.005 kg * 1000


# --- Per-category aggregation --------------------------------------------


def test_same_category_materials_are_aggregated():
    report = _infer(
        _materials(
            _material(name="Chassis", mass_g=600.0),
            _material(name="Screws", mass_g=400.0),
        )
    )
    assert report.contribution_count == 1
    assert report.contributions[0].recovered_mass_g == 1000.0
    assert report.carbon_saved_kg == 2.0


def test_distinct_categories_produce_distinct_contributions():
    report = _infer(
        _materials(
            _material(name="Steel", category=MaterialCategory.FERROUS_METAL),
            _material(
                name="Gold", category=MaterialCategory.PRECIOUS_METAL, mass_g=10.0
            ),
        )
    )
    assert report.contribution_count == 2
    categories = {c.category for c in report.contributions}
    assert categories == {
        MaterialCategory.FERROUS_METAL,
        MaterialCategory.PRECIOUS_METAL,
    }


def test_unknown_category_falls_back_to_default_factor():
    report = _infer(
        _materials(_material(category=MaterialCategory.PLASTIC, mass_g=1000.0))
    )
    # PLASTIC is absent from the test library → default 1.0/kg.
    assert report.carbon_saved_kg == 1.0


# --- Filtering ------------------------------------------------------------


def test_non_recoverable_materials_do_not_contribute():
    report = _infer(
        _materials(
            _material(name="Steel", mass_g=1000.0, recoverable=True),
            _material(
                name="Lead",
                category=MaterialCategory.HAZARDOUS,
                mass_g=500.0,
                recoverable=False,
            ),
        )
    )
    assert report.contribution_count == 1
    assert report.carbon_saved_kg == 2.0


def test_materials_at_or_below_floor_are_ignored():
    config = EnvironmentalConfig(min_material_confidence=0.5)
    report = _infer(
        _materials(
            _material(name="Keep", mass_g=1000.0, confidence=0.9),
            _material(name="Drop", mass_g=1000.0, confidence=0.4),
        ),
        config=config,
    )
    # Both are ferrous; only the confident one counts → 1 kg not 2 kg.
    assert report.contributions[0].recovered_mass_g == 1000.0
    assert report.carbon_saved_kg == 2.0


# --- Landfill diversion & critical recovery ------------------------------


def test_landfill_diversion_is_recoverable_mass_in_kg():
    report = _infer(
        _materials(
            _material(name="Steel", mass_g=1500.0, recoverable=True),
            _material(name="Sludge", mass_g=500.0, recoverable=False),
        )
    )
    assert report.landfill_diversion_kg == 1.5


def test_critical_material_recovery_sums_only_critical_categories():
    report = _infer(
        _materials(
            _material(
                name="Steel", category=MaterialCategory.FERROUS_METAL, mass_g=900.0
            ),
            _material(
                name="Gold", category=MaterialCategory.PRECIOUS_METAL, mass_g=100.0
            ),
        )
    )
    # Only the 100 g of precious metal is critical → 0.1 kg.
    assert report.critical_material_recovery_kg == 0.1


# --- Circularity index ----------------------------------------------------


def test_circularity_blends_mass_fraction_and_recyclability():
    # recoverable 800 / total 1000 = 0.8 mass fraction; recyclability 0.6;
    # weight 0.5 → 0.7.
    report = _infer(
        _materials(
            _material(name="Steel", mass_g=800.0, recoverable=True),
            _material(name="Resin", mass_g=200.0, recoverable=False),
        ),
        recoverability=_recoverability(recyclability=0.6),
    )
    assert report.circularity_index == 0.7


def test_circularity_is_zero_for_zero_mass():
    report = _infer(
        _materials(device_type="laptop"),
        recoverability=_recoverability(recyclability=0.0),
    )
    assert report.circularity_index == 0.0


# --- Hazard-reduction score ----------------------------------------------


def test_no_hazard_yields_zero_reduction():
    report = _infer(
        _materials(_material(mass_g=1000.0)),
        recoverability=_recoverability(hazard=HazardLevel.NONE),
    )
    assert report.hazard_reduction_score == 0.0


def test_higher_hazard_yields_higher_reduction():
    low = _infer(
        _materials(
            _material(name="Steel", mass_g=900.0),
            _material(
                name="Cell",
                category=MaterialCategory.BATTERY_MATERIAL,
                mass_g=100.0,
                hazardous=True,
            ),
        ),
        recoverability=_recoverability(hazard=HazardLevel.LOW),
    )
    high = _infer(
        _materials(
            _material(name="Steel", mass_g=900.0),
            _material(
                name="Cell",
                category=MaterialCategory.BATTERY_MATERIAL,
                mass_g=100.0,
                hazardous=True,
            ),
        ),
        recoverability=_recoverability(hazard=HazardLevel.HIGH),
    )
    assert high.hazard_reduction_score > low.hazard_reduction_score


# --- Confidence (separate axis) ------------------------------------------


def test_confidence_blends_material_and_recoverability():
    # material overall 0.8, recoverability 0.4, weight 0.5 → 0.6.
    report = _infer(
        _materials(_material(mass_g=1000.0), overall_confidence=0.8),
        recoverability=_recoverability(confidence=0.4),
    )
    assert report.confidence == 0.6


def test_confidence_does_not_scale_metrics():
    # Halving both upstream confidences leaves the physical metrics untouched.
    strong = _infer(
        _materials(_material(mass_g=1000.0), overall_confidence=0.9),
        recoverability=_recoverability(confidence=0.9),
    )
    weak = _infer(
        _materials(_material(mass_g=1000.0), overall_confidence=0.2),
        recoverability=_recoverability(confidence=0.2),
    )
    assert strong.carbon_saved_kg == weak.carbon_saved_kg == 2.0
    assert weak.confidence < strong.confidence


# --- Reasoning & warnings -------------------------------------------------


def test_empty_material_report_warns():
    report = _infer(_materials(device_type="laptop"))
    assert report.contributions == ()
    assert any("empty" in w.lower() for w in report.warnings)


def test_all_below_floor_warns():
    config = EnvironmentalConfig(min_material_confidence=0.95)
    report = _infer(
        _materials(_material(mass_g=1000.0, confidence=0.9)),
        config=config,
    )
    assert report.contributions == ()
    assert any("confidence floor" in w.lower() for w in report.warnings)


def test_hazard_present_warns():
    report = _infer(
        _materials(_material(mass_g=1000.0)),
        recoverability=_recoverability(hazard=HazardLevel.HIGH),
    )
    assert any("hazard" in w.lower() for w in report.warnings)


def test_unresolved_device_type_warns():
    report = _infer(_materials(_material(mass_g=1000.0), device_type=""))
    assert any("device type" in w.lower() for w in report.warnings)


def test_reasoning_is_populated():
    report = _infer(_materials(_material(mass_g=1000.0)))
    assert report.reasoning
    assert any(
        "avoided" in r.lower() or "burden" in r.lower() for r in report.reasoning
    )


# --- Determinism ----------------------------------------------------------


def test_inference_is_deterministic():
    engine = EnvironmentalInferenceEngine(_CONFIG)
    materials = _materials(_material(mass_g=1234.0))
    args = (_context(), _recoverability(), _components(), materials, _library())
    first = engine.infer(*args)
    second = engine.infer(*args)
    assert first.to_dict() == second.to_dict()


@pytest.mark.parametrize("hazard", list(HazardLevel))
def test_all_hazard_levels_are_handled(hazard):
    report = _infer(
        _materials(_material(mass_g=1000.0)),
        recoverability=_recoverability(hazard=hazard),
    )
    assert 0.0 <= report.hazard_reduction_score <= 1.0
