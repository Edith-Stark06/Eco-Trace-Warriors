"""Tests for the material inference engine (milestone M1.10).

The inference engine is deterministic arithmetic over a resolved
:class:`MaterialProfile`, a fused :class:`DeviceContext`, a
:class:`RecoverabilityReport` and a :class:`ComponentReport`, so these tests feed
it a small hand-built profile and hand-built inputs and assert the fold: nominal
mass passthrough, source-component gating, presence→confidence linkage, the
min-confidence floor, the overall blend/damping and the mass totals. No shipped
catalogue, no images, no models.
"""

from device_ai.components.models import (
    ComponentCategory,
    ComponentReport,
    InferredComponent,
)
from device_ai.fusion.models import (
    Conflict,
    DeviceContext,
    EvidenceKind,
    FusionAttribute,
    ResolvedAttribute,
)
from device_ai.materials.config import MaterialConfig
from device_ai.materials.inference import MaterialInferenceEngine
from device_ai.materials.models import MaterialCategory
from device_ai.materials.profiles import MaterialProfile, MaterialSpec
from device_ai.recoverability.models import (
    HazardLevel,
    RecommendedAction,
    RecoverabilityReport,
)

_CONFIG = MaterialConfig()


def _context(*, device_type="laptop", confidence=0.9, conflicts=()):
    attributes = [
        ResolvedAttribute(
            attribute=FusionAttribute.DEVICE_TYPE,
            value=device_type,
            confidence=confidence,
            sources=(EvidenceKind.DETECTION,),
        )
    ]
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


def _recoverability(*, hazard=HazardLevel.LOW, confidence=0.9):
    return RecoverabilityReport(
        device_type="laptop",
        repairability=0.8,
        reusability=0.8,
        recyclability=0.8,
        hazard_level=hazard,
        confidence=confidence,
        recommended_action=RecommendedAction.REFURBISH,
        reasoning=(),
        warnings=(),
    )


def _component(category, presence=0.9):
    return InferredComponent(
        name=f"{category.value} part",
        category=category,
        presence_confidence=presence,
        hazardous=False,
        recoverable=True,
        reason="",
    )


def _components(*components):
    return ComponentReport(
        device_type="laptop",
        components=tuple(components),
        overall_confidence=0.9,
        reasoning=(),
        warnings=(),
    )


def _profile(*specs, device_type="laptop", known=True):
    return MaterialProfile(device_type=device_type, materials=specs, known=known)


def _spec(name="Mat", category=MaterialCategory.OTHER, mass_g=100.0, **kw):
    return MaterialSpec(name=name, category=category, mass_g=mass_g, **kw)


def _infer(profile, context, recoverability, components, config=_CONFIG):
    engine = MaterialInferenceEngine(config)
    return engine.infer(context, recoverability, components, profile)


# --- Nominal mass ---------------------------------------------------------


def test_mass_is_nominal_not_scaled_by_confidence():
    report = _infer(
        _profile(_spec(mass_g=200.0, source_components=("battery",))),
        _context(confidence=0.5),
        _recoverability(confidence=0.5),
        _components(_component(ComponentCategory.BATTERY, presence=0.5)),
    )
    # mass stays the catalogue nominal even though confidence is well below 1.
    assert report.materials[0].mass_g == 200.0
    assert report.materials[0].confidence < 1.0


# --- Source-component gating ---------------------------------------------


def test_material_dropped_when_no_source_component_present():
    report = _infer(
        _profile(_spec(source_components=("storage",))),
        _context(),
        _recoverability(),
        _components(_component(ComponentCategory.BATTERY)),  # no storage
    )
    assert report.materials == ()


def test_unconditional_material_is_always_present():
    report = _infer(
        _profile(_spec(source_components=())),  # structural
        _context(),
        _recoverability(),
        _components(),  # empty inventory
    )
    assert len(report.materials) == 1
    assert report.materials[0].source_components == ()


def test_strongest_source_presence_drives_confidence():
    profile = _profile(_spec(source_components=("battery", "storage")))
    weak = _infer(
        profile,
        _context(),
        _recoverability(),
        _components(_component(ComponentCategory.STORAGE, presence=0.4)),
    )
    strong = _infer(
        profile,
        _context(),
        _recoverability(),
        _components(
            _component(ComponentCategory.STORAGE, presence=0.4),
            _component(ComponentCategory.BATTERY, presence=0.95),
        ),
    )
    assert strong.materials[0].confidence > weak.materials[0].confidence


# --- Min-confidence floor -------------------------------------------------


def test_materials_at_or_below_floor_are_dropped():
    config = MaterialConfig(min_material_confidence=0.5)
    report = _infer(
        _profile(
            _spec(name="Keep", source_components=("battery",)),
            _spec(name="Drop", source_components=("storage",)),
        ),
        _context(confidence=0.9),
        _recoverability(confidence=0.9),
        _components(
            _component(ComponentCategory.BATTERY, presence=0.9),
            _component(ComponentCategory.STORAGE, presence=0.4),  # 0.4*0.9=0.36
        ),
        config=config,
    )
    names = [material.name for material in report.materials]
    assert names == ["Keep"]


# --- Overall confidence ---------------------------------------------------


def test_overall_confidence_blends_recoverability():
    # weight 0.5 blends context 0.8 with recoverability 0.4 → 0.6.
    report = _infer(
        _profile(_spec()),
        _context(confidence=0.8),
        _recoverability(hazard=HazardLevel.NONE, confidence=0.4),
        _components(),
    )
    assert report.overall_confidence == 0.6


def test_unknown_device_type_damps_overall_confidence():
    known = _infer(
        _profile(_spec(), known=True),
        _context(confidence=0.9),
        _recoverability(confidence=0.9),
        _components(),
    )
    unknown = _infer(
        _profile(_spec(), known=False, device_type="ghost"),
        _context(device_type="ghost", confidence=0.9),
        _recoverability(confidence=0.9),
        _components(),
    )
    assert unknown.overall_confidence < known.overall_confidence


def test_conflicts_damp_overall_confidence():
    conflict = Conflict(
        attribute=FusionAttribute.BRAND, resolved_value="Dell", claims=()
    )
    clean = _infer(
        _profile(_spec()),
        _context(confidence=0.9),
        _recoverability(confidence=0.9),
        _components(),
    )
    conflicted = _infer(
        _profile(_spec()),
        _context(confidence=0.9, conflicts=(conflict,)),
        _recoverability(confidence=0.9),
        _components(),
    )
    assert conflicted.overall_confidence < clean.overall_confidence


# --- Mass totals ----------------------------------------------------------


def test_mass_totals_split_recoverable_and_hazardous():
    report = _infer(
        _profile(
            _spec(name="Steel", mass_g=100.0, recoverable=True, hazardous=False),
            _spec(name="Lead", mass_g=20.0, recoverable=False, hazardous=True),
            _spec(name="Copper", mass_g=30.0, recoverable=True, hazardous=False),
        ),
        _context(),
        _recoverability(),
        _components(),
    )
    assert report.total_mass_g == 150.0
    assert report.recoverable_mass_g == 130.0
    assert report.hazardous_mass_g == 20.0


# --- Reasoning & warnings -------------------------------------------------


def test_unknown_device_type_warns():
    report = _infer(
        _profile(_spec(), known=False, device_type="ghost"),
        _context(device_type="ghost"),
        _recoverability(hazard=HazardLevel.NONE),
        _components(),
    )
    assert any("Unrecognized" in w for w in report.warnings)


def test_conflict_warns():
    conflict = Conflict(
        attribute=FusionAttribute.BRAND, resolved_value="Dell", claims=()
    )
    report = _infer(
        _profile(_spec()),
        _context(conflicts=(conflict,)),
        _recoverability(hazard=HazardLevel.NONE),
        _components(),
    )
    assert any("conflict" in w.lower() for w in report.warnings)


def test_hazard_present_warns():
    report = _infer(
        _profile(_spec()),
        _context(),
        _recoverability(hazard=HazardLevel.HIGH),
        _components(),
    )
    assert any("hazard" in w.lower() for w in report.warnings)


def test_empty_breakdown_warns():
    report = _infer(
        _profile(_spec(source_components=("storage",))),
        _context(),
        _recoverability(hazard=HazardLevel.NONE),
        _components(_component(ComponentCategory.BATTERY)),  # no storage
    )
    assert report.materials == ()
    assert any("empty" in w.lower() for w in report.warnings)


def test_reasoning_is_populated_and_ordered():
    report = _infer(
        _profile(_spec(source_components=("battery",))),
        _context(),
        _recoverability(hazard=HazardLevel.NONE),
        _components(_component(ComponentCategory.BATTERY)),
    )
    assert report.reasoning
    assert any("profile" in r.lower() for r in report.reasoning)
