"""P4.3.8 — multi-class acquisition foundation tests.

These tests cover the generalization of the P4.3.7 router-only acquisition
framework to a configurable, taxonomy-validated target class. They are additive:
the historical ``test_acquisition_p437.py`` suite continues to assert the exact
router behaviour, which must remain green (spec P4.3.8 §5, §8.12).

Every id/name here is resolved from the frozen taxonomy at runtime — nothing is
hardcoded beyond the well-known anchors (laptop=0, smartphone=1, router=11).
"""

from __future__ import annotations

import pytest

from device_ai.acquisition.config import AcquisitionConfig, TargetClass
from device_ai.acquisition.promotion import (
    REJECTED,
    UNKNOWN,
    VERIFIED,
    evaluate_promotion,
)
from device_ai.acquisition.provenance_model import AcquisitionProvenanceRecord
from device_ai.acquisition.semantics import (
    CATEGORY_DIFFERENT_DEVICE,
    CATEGORY_EXPLICIT_TARGET,
    build_target_semantics,
    evaluate_label,
    evaluate_source_label,
)
from device_ai.dataset.taxonomy import load_taxonomy

TAX = load_taxonomy()


def _target(name: str):
    """Build a target-semantics profile against the frozen taxonomy."""
    return build_target_semantics(name, taxonomy=TAX)


def _record(**overrides) -> AcquisitionProvenanceRecord:
    """A fully production-eligible laptop provenance record, overridable."""
    base = {
        "relative_path": "laptop_00000_x.jpg",
        "original_filename": "x.jpg",
        "source_dataset": "Open Images V7",
        "source_identifier": "images/x.jpg",
        "source_class": "Laptop",
        "taxonomy_class": "laptop",
        "taxonomy_id": 0,
        "license_id": "cc-by",
        "license_raw": "CC-BY-4.0",
        "license_url": "https://creativecommons.org/licenses/by/4.0/",
        "checksum_sha256": "a" * 64,
        "import_timestamp": "2026-01-01T00:00:00Z",
        "publisher": "",
        "source_url": "",
        "source_version": "v7",
        "image_width": 640,
        "image_height": 480,
        "object_count": 1,
    }
    base.update(overrides)
    return AcquisitionProvenanceRecord(**base)


# --------------------------------------------------------------------------
# §8.1–8.3 — target class labels are accepted
# --------------------------------------------------------------------------
def test_1_laptop_target_accepts_laptop_label():
    decision = evaluate_label("laptop", _target("laptop"))
    assert decision.accepted
    assert decision.category == CATEGORY_EXPLICIT_TARGET


def test_2_smartphone_target_accepts_smartphone_label():
    decision = evaluate_label("smartphone", _target("smartphone"))
    assert decision.accepted
    assert decision.category == CATEGORY_EXPLICIT_TARGET


def test_3_router_target_accepts_router_label():
    decision = evaluate_label("router", _target("router"))
    assert decision.accepted
    # The router path must be byte-identical to the frozen P4.3.7 gate.
    assert decision.to_dict() == evaluate_source_label("router").to_dict()


# --------------------------------------------------------------------------
# §8.4–8.5 — other semantic classes are rejected
# --------------------------------------------------------------------------
def test_4_laptop_target_rejects_smartphone_label():
    decision = evaluate_label("smartphone", _target("laptop"))
    assert not decision.accepted
    assert decision.category == CATEGORY_DIFFERENT_DEVICE


def test_5_smartphone_target_rejects_laptop_label():
    decision = evaluate_label("laptop", _target("smartphone"))
    assert not decision.accepted
    assert decision.category == CATEGORY_DIFFERENT_DEVICE


# --------------------------------------------------------------------------
# §8.6–8.7 — invalid targets fail cleanly
# --------------------------------------------------------------------------
def test_6_invalid_class_id_rejected():
    with pytest.raises(ValueError):
        TargetClass.resolve(class_id=99, taxonomy=TAX)
    with pytest.raises(ValueError):
        TargetClass.resolve(class_id=-1, taxonomy=TAX)


def test_7_invalid_class_name_rejected():
    with pytest.raises(ValueError):
        TargetClass.resolve(name="banana", taxonomy=TAX)
    with pytest.raises(ValueError):
        build_target_semantics("banana", taxonomy=TAX)


# --------------------------------------------------------------------------
# §8.8 — a missing license prevents promotion
# --------------------------------------------------------------------------
def test_8_missing_license_prevents_promotion():
    decision = evaluate_promotion(
        _record(license_id="", license_raw="", license_url="")
    )
    assert not decision.production_eligible
    assert decision.status == UNKNOWN
    # An explicitly incompatible license is a hard REJECT, not merely UNKNOWN.
    proprietary = evaluate_promotion(
        _record(license_id="", license_raw="All Rights Reserved")
    )
    assert not proprietary.production_eligible
    assert proprietary.status == REJECTED


# --------------------------------------------------------------------------
# §8.9 — insufficient provenance prevents promotion
# --------------------------------------------------------------------------
def test_9_missing_provenance_prevents_promotion():
    # License is acceptable, but the object count / dimensions are unrecorded.
    assert not evaluate_promotion(_record(object_count=0)).production_eligible
    assert evaluate_promotion(_record(object_count=0)).status == UNKNOWN
    assert not evaluate_promotion(
        _record(image_width=0, image_height=0)
    ).production_eligible
    assert not evaluate_promotion(_record(source_identifier="")).production_eligible
    # Control: a complete, permissively-licensed record IS production-eligible.
    full = evaluate_promotion(_record())
    assert full.production_eligible
    assert full.status == VERIFIED


# --------------------------------------------------------------------------
# §8.10 — target class is validated against the frozen taxonomy
# --------------------------------------------------------------------------
def test_10_target_class_validates_against_taxonomy():
    assert TargetClass.resolve(name="laptop", taxonomy=TAX) == TargetClass("laptop", 0)
    assert TargetClass.resolve(class_id=11, taxonomy=TAX).name == "router"
    # A consistent name+id pair resolves; an inconsistent pair is rejected.
    assert TargetClass.resolve(name="laptop", class_id=0, taxonomy=TAX).class_id == 0
    with pytest.raises(ValueError):
        TargetClass.resolve(name="laptop", class_id=1, taxonomy=TAX)
    # ``parse`` accepts either a name or a stringified id.
    assert TargetClass.parse("router", taxonomy=TAX).class_id == 11
    assert TargetClass.parse("0", taxonomy=TAX).name == "laptop"


# --------------------------------------------------------------------------
# §8.11 — the protected tree is never targeted by a new-class layout
# --------------------------------------------------------------------------
def test_11_protected_tree_unchanged_for_new_target(tmp_path):
    router = AcquisitionConfig.default(root=tmp_path)
    laptop = AcquisitionConfig.for_target(
        TargetClass.resolve(name="laptop", taxonomy=TAX), root=tmp_path
    )

    # Protected roots are preserved verbatim and remain non-empty.
    assert laptop.protected_roots == router.protected_roots
    assert laptop.protected_roots

    # No writable output path of the new-class layout lies within a protected root.
    writable = [
        laptop.staging_root,
        laptop.evidence_dir,
        laptop.report_path,
        laptop.json_report_path,
        laptop.work_dir,
    ]
    for _label, protected in laptop.protected_roots:
        for path in writable:
            assert path != protected
            assert protected not in path.parents

    # Router via for_target is byte-identical to the P4.3.7 default layout.
    router_via_target = AcquisitionConfig.for_target(
        TargetClass.resolve(name="router", taxonomy=TAX), root=tmp_path
    )
    assert router_via_target == router


# --------------------------------------------------------------------------
# §8.12 — router semantics remain identical through the generalized entrypoint
# --------------------------------------------------------------------------
def test_12_router_semantics_preserved_through_generalized_gate():
    router = _target("router")
    labels = [
        "router",
        "wifi router",
        "wireless-router",
        "dual band router",
        "modem",
        "modem/router",
        "access point",
        "access-point-router",
        "networking device",
        "",
        "laptop",
        "switch",
    ]
    for label in labels:
        assert evaluate_label(label, router).to_dict() == evaluate_source_label(
            label
        ).to_dict()

    # Spot-check the exact categories the P4.3.7 suite depends on.
    assert evaluate_source_label("router").category == "explicit-router"
    assert evaluate_source_label("modem/router").category == "ambiguous-combined"
    assert evaluate_source_label("modem").category == "different-device"
    assert evaluate_source_label("").category == "too-generic"
    assert evaluate_source_label("laptop").category == "not-router"
