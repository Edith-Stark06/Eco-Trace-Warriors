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
