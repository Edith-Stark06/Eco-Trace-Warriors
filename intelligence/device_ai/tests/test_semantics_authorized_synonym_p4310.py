"""P4.3.10 — regression tests for the ONE human-authorized exact-match synonym.

The user explicitly authorized a single narrow semantic mapping:

    Open Images "Mobile phone"  ->  EcoTrace ``smartphone`` (class 1)

...for the EXACT source label ``"Mobile phone"`` only — no generic synonyms, no
fuzzy matching, no token similarity, no broad semantic inference. These tests
pin that contract down and prove the surrounding gate is otherwise untouched:

* ``"Mobile phone"`` -> ``smartphone`` = ACCEPT (category ``authorized-synonym``);
* unrelated / near-miss labels remain REJECTED (exact-string only);
* the mapping is scoped to ``smartphone`` — it does not leak to other classes;
* the existing router semantics remain byte-identical to the frozen P4.3.7 gate;
* all other existing taxonomy mappings remain unchanged.

Every id/name is resolved from the frozen taxonomy at runtime (spec convention
shared with ``test_acquisition_p438.py``).
"""

from __future__ import annotations

from device_ai.acquisition.semantics import (
    ACCEPTED,
    CATEGORY_AUTHORIZED_SYNONYM,
    CATEGORY_DIFFERENT_DEVICE,
    CATEGORY_EXPLICIT_TARGET,
    REJECTED,
    build_target_semantics,
    evaluate_label,
    evaluate_source_label,
)
from device_ai.dataset.taxonomy import load_taxonomy

TAX = load_taxonomy()

#: The 8 other Open Images V7 display labels that already clear the frozen token
#: gate for their EcoTrace class WITHOUT any synonym (probe_semantics.py). These
#: must keep accepting exactly as before — the synonym table adds smartphone and
#: touches nothing else.
_OTHER_OI_MAPPINGS = (
    ("tablet", "Tablet computer"),
    ("monitor", "Computer monitor"),
    ("printer", "Printer"),
    ("television", "Television"),
    ("keyboard", "Computer keyboard"),
    ("mouse", "Computer mouse"),
    ("camera", "Camera"),
    ("headphones", "Headphones"),
)


def _target(name: str):
    """Build a target-semantics profile against the frozen taxonomy."""
    return build_target_semantics(name, taxonomy=TAX)


# --------------------------------------------------------------------------
# (1) "Mobile phone" -> smartphone = ACCEPT, via the authorized-synonym path
# --------------------------------------------------------------------------
def test_mobile_phone_maps_to_smartphone_accept():
    decision = evaluate_label("Mobile phone", _target("smartphone"))
    assert decision.accepted
    assert decision.verdict == ACCEPTED
    assert decision.category == CATEGORY_AUTHORIZED_SYNONYM
    # The authoritative taxonomy name is preserved (never renamed to the source).
    assert _target("smartphone").class_name == "smartphone"
    assert _target("smartphone").class_id == 1


def test_authorized_synonym_is_exact_string_only():
    """Only the exact label clears — the normalisation is case/space tolerant
    (``normalize`` lowercases + hyphenates) but the match is otherwise exact."""
    tgt = _target("smartphone")
    # Exact label, tolerant only of case/whitespace normalisation.
    for spelling in ("Mobile phone", "mobile phone", "MOBILE PHONE", " Mobile  phone "):
        assert evaluate_label(spelling, tgt).category == CATEGORY_AUTHORIZED_SYNONYM


# --------------------------------------------------------------------------
# (2) Unrelated / near-miss labels remain REJECTED (no fuzzy, no similarity)
# --------------------------------------------------------------------------
def test_unrelated_and_near_miss_labels_remain_rejected():
    tgt = _target("smartphone")
    for label in (
        "phone",
        "mobile",
        "cell phone",
        "cellphone",
        "Mobile phone case",  # superset of the authorized tokens -> still REJECT
        "Landline phone",
        "Telephone",
        "smart phone",  # NB: two words is NOT the exact authorized string
        "iphone",
        "handset",
    ):
        decision = evaluate_label(label, tgt)
        assert not decision.accepted, f"{label!r} must stay REJECTED"
        assert decision.verdict == REJECTED
        # Crucially, NONE of these are the authorized synonym.
        assert decision.category != CATEGORY_AUTHORIZED_SYNONYM


def test_literal_smartphone_label_still_uses_the_normal_token_gate():
    """The synonym must not hijack the ordinary path: the canonical taxonomy
    label still accepts as an EXPLICIT target, not as an authorized synonym."""
    decision = evaluate_label("smartphone", _target("smartphone"))
    assert decision.accepted
    assert decision.category == CATEGORY_EXPLICIT_TARGET


# --------------------------------------------------------------------------
# (3) The mapping is scoped to smartphone — it does not leak to other classes
# --------------------------------------------------------------------------
def test_mobile_phone_rejected_for_non_smartphone_targets():
    for other in ("tablet", "laptop", "television", "camera", "router"):
        decision = evaluate_label("Mobile phone", _target(other))
        assert not decision.accepted, f"Mobile phone must be REJECTED for {other!r}"
        assert decision.category != CATEGORY_AUTHORIZED_SYNONYM


# --------------------------------------------------------------------------
# (4a) Router semantics remain byte-identical to the frozen P4.3.7 gate
# --------------------------------------------------------------------------
def test_router_semantics_unchanged_by_synonym():
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
        "Mobile phone",  # the new synonym must NOT reach the router path
        "mobile phone",
    ]
    for label in labels:
        assert (
            evaluate_label(label, router).to_dict()
            == evaluate_source_label(label).to_dict()
        )
    # "Mobile phone" is a different-device for router (it names "phone"),
    # proving the smartphone synonym is scoped and does not leak here.
    assert evaluate_source_label("Mobile phone").category == CATEGORY_DIFFERENT_DEVICE
    # Spot-check the exact categories the P4.3.7 suite depends on.
    assert evaluate_source_label("router").category == "explicit-router"
    assert evaluate_source_label("modem/router").category == "ambiguous-combined"
    assert evaluate_source_label("modem").category == "different-device"
    assert evaluate_source_label("").category == "too-generic"


# --------------------------------------------------------------------------
# (4b) All other existing taxonomy mappings remain unchanged
# --------------------------------------------------------------------------
def test_other_oi_mappings_still_accept_their_class():
    for class_name, oi_label in _OTHER_OI_MAPPINGS:
        decision = evaluate_label(oi_label, _target(class_name))
        assert decision.accepted, f"{oi_label!r} must still ACCEPT for {class_name!r}"
        # These clear the ordinary token gate, NOT the synonym table.
        assert decision.category == CATEGORY_EXPLICIT_TARGET


def test_cross_class_rejections_still_hold():
    # A concrete taxonomy label denoting a *different* class stays a hard reject.
    assert evaluate_label("laptop", _target("smartphone")).category == (
        CATEGORY_DIFFERENT_DEVICE
    )
    assert evaluate_label("smartphone", _target("laptop")).category == (
        CATEGORY_DIFFERENT_DEVICE
    )
    # And the other OI labels do NOT accept for smartphone.
    for _class_name, oi_label in _OTHER_OI_MAPPINGS:
        assert not evaluate_label(oi_label, _target("smartphone")).accepted
