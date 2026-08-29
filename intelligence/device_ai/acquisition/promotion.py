"""Production-eligibility (promotion) gate for acquired images (P4.3.8).

An image staged by :mod:`device_ai.acquisition.ingest` carries a full
:class:`~device_ai.acquisition.provenance_model.AcquisitionProvenanceRecord`.
Before any staged image may be *promoted* to a production-eligible dataset it
must clear two independent requirements, evaluated here and **never inferred**:

* **License (spec §6)** — the recorded license must be an explicit permissive
  license (re-checked from the record's raw string via
  :func:`device_ai.acquisition.licenses.evaluate_license`). No recorded license,
  or an unverified one, yields :data:`UNKNOWN`; an incompatible/proprietary
  license yields :data:`REJECTED`.
* **Provenance (spec §7)** — the record must carry sufficient attribution:
  every mandatory field of
  :func:`device_ai.acquisition.provenance_model.is_complete` *plus* measured
  image dimensions and a non-zero object count.

This module owns no policy of its own beyond composing those two frozen checks,
so promotion decisions stay auditable and consistent with the acquisition gates.
"""

from __future__ import annotations

from dataclasses import dataclass

from .licenses import ACCEPTED as LICENSE_ACCEPTED
from .licenses import REJECTED as LICENSE_REJECTED
from .licenses import evaluate_license
from .provenance_model import AcquisitionProvenanceRecord, is_complete

# Promotion verdicts (three-valued, fail closed).
VERIFIED = "VERIFIED"
UNKNOWN = "UNKNOWN"
REJECTED = "REJECTED"


@dataclass(frozen=True, slots=True)
class PromotionDecision:
    """Outcome of evaluating one provenance record for production eligibility.

    Attributes:
        status: :data:`VERIFIED`, :data:`UNKNOWN`, or :data:`REJECTED`.
        production_eligible: ``True`` only when ``status == VERIFIED``.
        license_verdict: The underlying license verdict (from ``evaluate_license``).
        reasons: Ordered, machine-readable reasons supporting the status.
    """

    status: str
    production_eligible: bool
    license_verdict: str
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        """Return a primitive-only, JSON-serialisable mapping."""
        return {
            "status": self.status,
            "production_eligible": self.production_eligible,
            "license_verdict": self.license_verdict,
            "reasons": list(self.reasons),
        }


def _provenance_gaps(record: AcquisitionProvenanceRecord) -> list[str]:
    """Return the list of missing/insufficient provenance fields (spec §7)."""
    gaps: list[str] = []
    if not is_complete(record):
        gaps.append(
            "mandatory provenance incomplete (checksum / filename / source / "
            "source class / source identifier / taxonomy id / license id / "
            "import timestamp)"
        )
    if record.image_width <= 0 or record.image_height <= 0:
        gaps.append("image dimensions not recorded")
    if record.object_count <= 0:
        gaps.append("object count not recorded")
    return gaps


def evaluate_promotion(record: AcquisitionProvenanceRecord) -> PromotionDecision:
    """Decide whether one provenance record is production-eligible.

    Args:
        record: The acquisition provenance record for a staged image.

    Returns:
        A :class:`PromotionDecision`. ``VERIFIED`` (and only then eligible) when
        the license is an explicit permissive license *and* provenance is
        sufficient; ``REJECTED`` when the license is incompatible; ``UNKNOWN``
        otherwise (missing/unverified license or insufficient provenance) — never
        inferred, always fail closed.
    """
    license_decision = evaluate_license(
        record.license_raw, license_url=record.license_url
    )

    # An incompatible/proprietary license is a hard rejection.
    if license_decision.verdict == LICENSE_REJECTED:
        return PromotionDecision(
            status=REJECTED,
            production_eligible=False,
            license_verdict=license_decision.verdict,
            reasons=(f"license: {license_decision.reason}",),
        )

    # A missing or unverified license cannot become production-eligible (§6).
    if license_decision.verdict != LICENSE_ACCEPTED or not record.license_id:
        return PromotionDecision(
            status=UNKNOWN,
            production_eligible=False,
            license_verdict=license_decision.verdict,
            reasons=(
                f"license: {license_decision.reason}",
                "no recorded/accepted license => not production-eligible",
            ),
        )

    # License is acceptable; provenance must also be sufficient (§7).
    gaps = _provenance_gaps(record)
    if gaps:
        return PromotionDecision(
            status=UNKNOWN,
            production_eligible=False,
            license_verdict=license_decision.verdict,
            reasons=tuple(f"provenance: {gap}" for gap in gaps),
        )

    return PromotionDecision(
        status=VERIFIED,
        production_eligible=True,
        license_verdict=license_decision.verdict,
        reasons=(
            f"license: {license_decision.reason}",
            "provenance: all mandatory fields present with dimensions and object count",
        ),
    )
