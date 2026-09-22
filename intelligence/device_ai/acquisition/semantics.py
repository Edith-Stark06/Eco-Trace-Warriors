"""Semantic gate for the ``router`` class — accept only explicit routers.

A source class label clears the gate only when it **explicitly** denotes a
router. Ambiguous or class-distinct labels are rejected with a specific reason:

* ``modem`` / ``gateway`` / ``switch`` / ``access point`` / ``hub`` / ``NAS`` /
  ``repeater`` / ``set-top box`` — a *different* networking device, or a
  combined label (``modem/router``) that does not establish *router* alone;
* ``networking device`` / ``network appliance`` / ``electronics`` /
  ``device`` — too generic;
* anything that does not contain an explicit ``router`` sense — not a router.

A label such as ``wifi-router`` / ``wireless router`` / ``dual-band router`` is
accepted (router noun with benign adjectives). ``modem-router`` /
``access-point-router`` are rejected as ambiguous combinations.

This gate operates on the *label string* only. Whether the source actually
carries bounding boxes (rather than image-classification tags) is a separate
check performed during ingestion — image-classification labels are never
promoted to bbox labels.
"""

from __future__ import annotations

from dataclasses import dataclass

from .licenses import normalize_license_id as _normalize  # shared token normaliser

# Verdicts.
ACCEPTED = "ACCEPTED"
REJECTED = "REJECTED"

# Decision categories (machine-readable).
CATEGORY_EXPLICIT_ROUTER = "explicit-router"
CATEGORY_AMBIGUOUS_COMBINED = "ambiguous-combined"
CATEGORY_DIFFERENT_DEVICE = "different-device"
CATEGORY_TOO_GENERIC = "too-generic"
CATEGORY_NOT_ROUTER = "not-router"

#: Single-word device nouns that are *not* a router (or make a label ambiguous
#: when combined with ``router``).
_OTHER_DEVICE_SINGLE: frozenset[str] = frozenset(
    {
        "modem",
        "gateway",
        "switch",
        "hub",
        "nas",
        "repeater",
        "extender",
        "bridge",
        "stb",
        "television",
        "tv",
        "printer",
        "camera",
        "smartphone",
        "phone",
        "controller",
        "adapter",
        "charger",
        "dongle",
        "ap",
    }
)

#: Multi-word device phrases (checked as normalised substrings).
_OTHER_DEVICE_PHRASES: tuple[str, ...] = (
    "access-point",
    "set-top",
    "set-top-box",
    "network-switch",
    "network-attached-storage",
)

#: Whole-label spellings that are too generic to establish *router*.
_GENERIC_LABELS: frozenset[str] = frozenset(
    {
        "",
        "networking",
        "network",
        "networking-device",
        "network-device",
        "networking-devices",
        "network-appliance",
        "appliance",
        "electronics",
        "electronic",
        "device",
        "devices",
        "equipment",
        "generic",
        "gadget",
        "hardware",
        "other",
        "misc",
        "unknown",
    }
)


@dataclass(frozen=True, slots=True)
class SemanticDecision:
    """Outcome of evaluating one source class label for the router class.

    Attributes:
        verdict: :data:`ACCEPTED` or :data:`REJECTED`.
        raw_label: The label exactly as supplied by the source.
        normalized: The normalised token form used for matching.
        category: Machine-readable category (see ``CATEGORY_*``).
        reason: Exact human/machine reason for the verdict.
    """

    verdict: str
    raw_label: str
    normalized: str
    category: str
    reason: str

    @property
    def accepted(self) -> bool:
        """Whether the label cleared the semantic gate."""
        return self.verdict == ACCEPTED

    def to_dict(self) -> dict[str, object]:
        """Return a primitive-only, JSON-serialisable mapping."""
        return {
            "verdict": self.verdict,
            "raw_label": self.raw_label,
            "normalized": self.normalized,
            "category": self.category,
            "reason": self.reason,
        }


def _names_other_device(normalized: str, tokens: set[str]) -> bool:
    """Whether the label names a class-distinct device (single word or phrase)."""
    if tokens & _OTHER_DEVICE_SINGLE:
        return True
    return any(phrase in normalized for phrase in _OTHER_DEVICE_PHRASES)


def evaluate_source_label(raw_label: str) -> SemanticDecision:
    """Decide whether a source class label explicitly denotes ``router``.

    Args:
        raw_label: The source's class label / category name.

    Returns:
        A :class:`SemanticDecision` (fail closed: anything not clearly a router
        is rejected with a specific reason).
    """
    raw = (raw_label or "").strip()
    normalized = _normalize(raw)
    tokens = set(normalized.split("-")) if normalized else set()

    has_router = "router" in tokens
    other_device = _names_other_device(normalized, tokens)

    if has_router and not other_device:
        return SemanticDecision(
            verdict=ACCEPTED,
            raw_label=raw,
            normalized=normalized,
            category=CATEGORY_EXPLICIT_ROUTER,
            reason="label explicitly denotes 'router' with no class-distinct device term",
        )

    if has_router and other_device:
        return SemanticDecision(
            verdict=REJECTED,
            raw_label=raw,
            normalized=normalized,
            category=CATEGORY_AMBIGUOUS_COMBINED,
            reason=(
                "combined/ambiguous label pairs 'router' with a class-distinct "
                "device (e.g. modem/router, access-point/router); source must "
                "establish 'router' alone"
            ),
        )

    if other_device:
        return SemanticDecision(
            verdict=REJECTED,
            raw_label=raw,
            normalized=normalized,
            category=CATEGORY_DIFFERENT_DEVICE,
            reason=(
                "label denotes a class-distinct networking device "
                "(modem/gateway/switch/access-point/hub/NAS/set-top-box), not a router"
            ),
        )

    if normalized in _GENERIC_LABELS:
        return SemanticDecision(
            verdict=REJECTED,
            raw_label=raw,
            normalized=normalized,
            category=CATEGORY_TOO_GENERIC,
            reason="label is too generic (networking device / electronics) to establish 'router'",
        )

    return SemanticDecision(
        verdict=REJECTED,
        raw_label=raw,
        normalized=normalized,
        category=CATEGORY_NOT_ROUTER,
        reason="label does not explicitly denote 'router'",
    )


# --------------------------------------------------------------------------
# Generalized multi-class gate (P4.3.8)
# --------------------------------------------------------------------------
#
# The router gate above is preserved byte-for-byte (it carries a hand-curated
# list of networking-device synonyms specific to routers). The generalized gate
# below decides any *taxonomy* class using accept/reject token sets derived
# **mechanically from the frozen taxonomy** — never from filenames and never
# from fuzzy inference (spec P4.3.8 §3). For the ``router`` target it delegates
# to :func:`evaluate_source_label` so router behaviour is identical.
#
# P4.3.10 adds one narrow, human-authorized exception: an EXACT-match synonym
# table (:data:`_AUTHORIZED_SOURCE_SYNONYMS`) that lets a specifically approved
# source label denote a class even when its tokens differ (e.g. Open Images
# "Mobile phone" -> smartphone). It is exact-string only, never fuzzy and never
# a general loosening; every non-listed label is judged by the same token gate.

#: Category for a label that explicitly denotes the (non-router) target class.
CATEGORY_EXPLICIT_TARGET = "explicit-target"
#: Category for a label that denotes no taxonomy class at all.
CATEGORY_NOT_TARGET = "not-target"
#: Category for an EXACT, individually human-authorized source-label synonym.
#: This is not fuzzy matching, token similarity, or inference: only a listed
#: ``(class, normalised-label)`` pair clears here, and only for that class.
CATEGORY_AUTHORIZED_SYNONYM = "authorized-synonym"

#: Exact-match authorized source-label synonyms, keyed by taxonomy class name.
#: Each value is a frozenset of NORMALISED source labels (see
#: :func:`normalize_license_id`) that are accepted as denoting that class — and
#: nothing else. Entries are added ONLY with explicit human authorization, are
#: recorded in the acquisition evidence + per-image provenance, and are covered
#: by regression tests. This is deliberately NOT a general synonym mechanism:
#: no token similarity, no fuzzy matching, no broad semantic inference — every
#: label that is not an exact listed string continues through the unchanged
#: token gate below.
#:
#: P4.3.10 (human-authorized): Open Images V7 labels its mobile-phone MID
#: (``/m/050k8``) ``"Mobile phone"``; the frozen EcoTrace taxonomy names the same
#: device class ``smartphone`` (id 1). Only the EXACT label ``"Mobile phone"`` is
#: authorized to denote ``smartphone``.
_AUTHORIZED_SOURCE_SYNONYMS: dict[str, frozenset[str]] = {
    "smartphone": frozenset({"mobile-phone"}),
}


def _label_tokens(name: str) -> frozenset[str]:
    """Return the normalised hyphen-split token set of a class name/label."""
    normalized = _normalize(name)
    return frozenset(normalized.split("-")) if normalized else frozenset()


@dataclass(frozen=True, slots=True)
class TargetSemantics:
    """Accept/reject token sets for one taxonomy target class.

    Attributes:
        class_name: Canonical taxonomy class name (e.g. ``laptop``).
        class_id: The class's frozen taxonomy id.
        target_tokens: Normalised tokens that a label must contain (as a subset)
            to denote the target class.
        other_tokens: Tokens that belong to *other* taxonomy classes (with the
            target's own tokens removed). A label containing any of these names a
            class-distinct device and is rejected.
    """

    class_name: str
    class_id: int
    target_tokens: frozenset[str]
    other_tokens: frozenset[str]


def build_target_semantics(
    class_name: str, *, taxonomy: object | None = None
) -> TargetSemantics:
    """Derive the accept/reject token sets for ``class_name`` from the taxonomy.

    Args:
        class_name: A canonical taxonomy class name.
        taxonomy: Optional pre-loaded taxonomy (defaults to ``load_taxonomy``).

    Returns:
        A :class:`TargetSemantics` profile.

    Raises:
        ValueError: If ``class_name`` is not present in the frozen taxonomy.
    """
    if taxonomy is None:
        from ..dataset.taxonomy import load_taxonomy

        taxonomy = load_taxonomy()

    class_names = tuple(getattr(taxonomy, "class_names", ()))
    if class_name not in class_names:
        raise ValueError(
            f"unknown target class '{class_name}': not in the frozen taxonomy"
        )
    class_id = class_names.index(class_name)

    target_tokens = _label_tokens(class_name)
    other: set[str] = set()
    for other_name in class_names:
        if other_name == class_name:
            continue
        other |= _label_tokens(other_name)
    other -= target_tokens

    return TargetSemantics(
        class_name=class_name,
        class_id=int(class_id),
        target_tokens=target_tokens,
        other_tokens=frozenset(other),
    )


def evaluate_label(raw_label: str, target: TargetSemantics) -> SemanticDecision:
    """Decide whether a source label explicitly denotes ``target``'s class.

    For the ``router`` target this delegates to :func:`evaluate_source_label` so
    the P4.3.7 router behaviour is preserved exactly. For any other taxonomy
    class it applies the mechanically-derived token gate: a label is accepted
    only when it contains every target token and no token belonging to a
    class-distinct taxonomy class (fail closed on ambiguity or generic labels).

    Args:
        raw_label: The source's class label / category name.
        target: The :class:`TargetSemantics` profile for the class being acquired.

    Returns:
        A :class:`SemanticDecision` (fail closed).
    """
    if target.class_name == "router":  # preserve identical P4.3.7 behaviour
        return evaluate_source_label(raw_label)

    raw = (raw_label or "").strip()
    normalized = _normalize(raw)
    tokens = set(normalized.split("-")) if normalized else set()

    # Exact-match authorized synonym (P4.3.10): a specifically human-authorized
    # source label for THIS class, accepted verbatim and nothing near it. Only an
    # exact normalised-string match against the class's authorized set clears
    # here; there is no fuzzy matching or inference. Every other label — including
    # near-misses like "mobile" or "mobile phone case" — falls through to the
    # unchanged token gate below and is judged exactly as before.
    if normalized in _AUTHORIZED_SOURCE_SYNONYMS.get(target.class_name, frozenset()):
        return SemanticDecision(
            verdict=ACCEPTED,
            raw_label=raw,
            normalized=normalized,
            category=CATEGORY_AUTHORIZED_SYNONYM,
            reason=(
                f"authorized exact source-label synonym for '{target.class_name}' "
                "(exact match only; no token similarity, fuzzy matching or inference)"
            ),
        )

    has_target = bool(target.target_tokens) and target.target_tokens <= tokens
    names_other = bool(tokens & target.other_tokens)

    if has_target and not names_other:
        return SemanticDecision(
            verdict=ACCEPTED,
            raw_label=raw,
            normalized=normalized,
            category=CATEGORY_EXPLICIT_TARGET,
            reason=(
                f"label explicitly denotes '{target.class_name}' with no "
                "class-distinct taxonomy term"
            ),
        )
    if has_target and names_other:
        return SemanticDecision(
            verdict=REJECTED,
            raw_label=raw,
            normalized=normalized,
            category=CATEGORY_AMBIGUOUS_COMBINED,
            reason=(
                f"combined/ambiguous label pairs '{target.class_name}' with a "
                "class-distinct taxonomy class; the source must establish "
                f"'{target.class_name}' alone"
            ),
        )
    if names_other:
        return SemanticDecision(
            verdict=REJECTED,
            raw_label=raw,
            normalized=normalized,
            category=CATEGORY_DIFFERENT_DEVICE,
            reason=(
                "label denotes a class-distinct taxonomy device, not "
                f"'{target.class_name}'"
            ),
        )
    if normalized in _GENERIC_LABELS:
        return SemanticDecision(
            verdict=REJECTED,
            raw_label=raw,
            normalized=normalized,
            category=CATEGORY_TOO_GENERIC,
            reason=f"label is too generic to establish '{target.class_name}'",
        )
    return SemanticDecision(
        verdict=REJECTED,
        raw_label=raw,
        normalized=normalized,
        category=CATEGORY_NOT_TARGET,
        reason=f"label does not explicitly denote '{target.class_name}'",
    )
