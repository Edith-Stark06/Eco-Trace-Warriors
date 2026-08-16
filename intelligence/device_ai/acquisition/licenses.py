"""License gate — fail closed, never infer.

A source may be *accepted* only when an **explicit** license string is present
and that license belongs to the documented permissive allowlist (permits both
ML training and redistribution). Every other outcome is:

* ``REJECTED`` — an explicit but incompatible license (non-commercial,
  no-derivatives, proprietary/all-rights-reserved), or
* ``UNVERIFIED`` — no license string at all, or an unrecognised one.

The gate **never guesses**: an unknown or missing license is *never* upgraded
to permissive. Every decision carries the exact machine-readable reason.

The allowlist mirrors ``docs/ai/device_detection_sources.md §6`` and the
P4.3.7 research package: CC-BY, CC0, CC-BY-SA, Apache-2.0, public domain, and
team-owned (first-party) images.
"""

from __future__ import annotations

from dataclasses import dataclass

# Verdicts (stable, machine-readable).
ACCEPTED = "ACCEPTED"
REJECTED = "REJECTED"
UNVERIFIED = "UNVERIFIED"

#: Canonical permissive families. A normalised license id must reduce to one of
#: these to be accepted. All of these permit ML training *and* redistribution
#: (team-owned = first-party, license-clean by construction).
PERMISSIVE_FAMILIES: frozenset[str] = frozenset(
    {"cc0", "cc-by", "cc-by-sa", "apache-2.0", "public-domain", "team-owned"}
)

#: Hyphen-tokens (or whole-string aliases) that force an explicit REJECT even in
#: the presence of an otherwise-permissive family (e.g. ``cc-by-nc-4.0``).
_REJECT_TOKENS: frozenset[str] = frozenset(
    {"nc", "noncommercial", "nd", "noderivs", "noderivatives"}
)

#: Whole-string reject aliases (proprietary / all-rights-reserved family).
_REJECT_ALIASES: frozenset[str] = frozenset(
    {
        "proprietary",
        "all-rights-reserved",
        "copyright",
        "copyrighted",
        "arr",
        "unlicensed",
    }
)


@dataclass(frozen=True, slots=True)
class LicenseDecision:
    """Outcome of evaluating one source's license.

    Attributes:
        verdict: One of :data:`ACCEPTED`, :data:`REJECTED`, :data:`UNVERIFIED`.
        raw: The exact license string supplied (empty when none was found).
        normalized_id: Normalised license identifier (family key when accepted).
        license_url: Supporting license URL, if any (recorded, never required to
            infer a license from a hosting page).
        permits_training: Whether the license permits ML training.
        permits_redistribution: Whether the license permits redistribution.
        reason: Exact machine-readable reason for the verdict.
    """

    verdict: str
    raw: str
    normalized_id: str
    license_url: str
    permits_training: bool
    permits_redistribution: bool
    reason: str

    @property
    def accepted(self) -> bool:
        """Whether the license cleared the gate."""
        return self.verdict == ACCEPTED

    def to_dict(self) -> dict[str, object]:
        """Return a primitive-only, JSON-serialisable mapping."""
        return {
            "verdict": self.verdict,
            "raw": self.raw,
            "normalized_id": self.normalized_id,
            "license_url": self.license_url,
            "permits_training": self.permits_training,
            "permits_redistribution": self.permits_redistribution,
            "reason": self.reason,
        }


def normalize_license_id(raw: str) -> str:
    """Reduce a free-form license string to a canonical hyphenated token form.

    Lower-cases, trims, drops the words ``license``/``licence``, and collapses
    spaces/underscores/dots to single hyphens. This is *syntactic* only — it
    never maps an unknown string onto a known family.

    Args:
        raw: The license string as supplied by the source.

    Returns:
        A normalised token string (may be empty).
    """
    text = (raw or "").strip().lower()
    for noise in ("license", "licence", "version", "the "):
        text = text.replace(noise, " ")
    # Unify separators to single hyphens.
    for sep in (" ", "_", ".", "/", ":", ","):
        text = text.replace(sep, "-")
    while "--" in text:
        text = text.replace("--", "-")
    return text.strip("-")


def _reduce_to_family(normalized: str) -> str | None:
    """Map a normalised id to a permissive family key, or ``None``.

    Only *recognised* permissive spellings reduce to a family; everything else
    returns ``None`` (kept unverified, never inferred).
    """
    tokens = normalized.split("-")
    token_set = set(tokens)

    # Public domain / CC0.
    if normalized in {"cc0", "cc0-1-0"} or "cc0" in token_set:
        return "cc0"
    if normalized in {"public-domain", "publicdomain", "pd", "pdm", "pd-mark"}:
        return "public-domain"
    if "public" in token_set and "domain" in token_set:
        return "public-domain"

    # Team-owned / first-party.
    if normalized in {
        "team-owned",
        "teamowned",
        "first-party",
        "firstparty",
        "self-collected",
        "selfcollected",
        "own",
        "own-work",
    }:
        return "team-owned"

    # Apache.
    if "apache" in token_set:
        # Apache-2.0 is the only version we admit.
        if "2" in token_set or "2-0" in normalized or normalized.endswith("2"):
            return "apache-2.0"
        return "apache-2.0" if normalized == "apache" else None

    # Creative Commons Attribution family (BY / BY-SA), never NC/ND.
    if "cc" in token_set and "by" in token_set:
        if "sa" in token_set:
            return "cc-by-sa"
        return "cc-by"

    return None


def evaluate_license(raw_license: str, *, license_url: str = "") -> LicenseDecision:
    """Evaluate a source license against the permissive allowlist (fail closed).

    Args:
        raw_license: The license string exactly as supplied by the source
            (empty/whitespace means *no license found*).
        license_url: Optional supporting license URL (recorded for provenance;
            a URL alone never establishes a license).

    Returns:
        A :class:`LicenseDecision` with an exact reason.
    """
    raw = (raw_license or "").strip()
    url = (license_url or "").strip()

    if not raw:
        return LicenseDecision(
            verdict=UNVERIFIED,
            raw="",
            normalized_id="",
            license_url=url,
            permits_training=False,
            permits_redistribution=False,
            reason="no license metadata found; unclear => exclude (never inferred)",
        )

    normalized = normalize_license_id(raw)
    tokens = set(normalized.split("-"))

    # Explicit rejects take precedence over any permissive family match so that
    # e.g. ``cc-by-nc-4.0`` is REJECTED, not accepted as ``cc-by``.
    if tokens & _REJECT_TOKENS:
        return LicenseDecision(
            verdict=REJECTED,
            raw=raw,
            normalized_id=normalized,
            license_url=url,
            permits_training=False,
            permits_redistribution=False,
            reason=(
                "license carries a non-commercial / no-derivatives restriction "
                "incompatible with ML training + redistribution"
            ),
        )
    if normalized in _REJECT_ALIASES or tokens & _REJECT_ALIASES:
        return LicenseDecision(
            verdict=REJECTED,
            raw=raw,
            normalized_id=normalized,
            license_url=url,
            permits_training=False,
            permits_redistribution=False,
            reason="proprietary / all-rights-reserved: redistribution not permitted",
        )

    family = _reduce_to_family(normalized)
    if family in PERMISSIVE_FAMILIES:
        return LicenseDecision(
            verdict=ACCEPTED,
            raw=raw,
            normalized_id=family,
            license_url=url,
            permits_training=True,
            permits_redistribution=True,
            reason=f"explicit permissive license recognised ({family})",
        )

    return LicenseDecision(
        verdict=UNVERIFIED,
        raw=raw,
        normalized_id=normalized,
        license_url=url,
        permits_training=False,
        permits_redistribution=False,
        reason=(
            "license string not on the permissive allowlist and not inferable; "
            "unclear => exclude"
        ),
    )
