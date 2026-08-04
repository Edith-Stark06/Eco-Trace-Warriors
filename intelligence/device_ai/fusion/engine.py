"""Multi-modal fusion engine (milestone M1.7).

:class:`FusionEngine` is the single collaborator downstream AI modules depend on
to obtain a unified view of a device. It merges the outputs of the independent
modules — **detection**, **fingerprint** and **OCR** — into one normalized,
immutable :class:`~device_ai.fusion.models.DeviceContext`.

The engine is deliberately small and pure:

* **Ingest** — each module result is turned into :class:`Evidence` via the
  builders on the model (the engine never reaches into a module's internals).
* **Aggregate** — for every shared :class:`FusionAttribute` the competing claims
  are combined with a **noisy-OR** so independent agreement *raises* confidence,
  then damped by a *support share* so cross-module disagreement *lowers* it.
* **Detect conflicts** — any attribute with two or more distinct claimed values
  yields a :class:`Conflict` recording the competing claims and the resolved
  value.
* **Normalize** — the winning value per attribute, the aggregate confidence, the
  identity anchor (EcoID + fingerprint) and provenance are assembled into an
  immutable ``DeviceContext``.

Everything (engine version, clock) is injected, so the whole engine is exercised
deterministically in tests with hand-built evidence — no models, no I-O.

The engine is **internal-only**: it exposes no HTTP surface and does not touch
the frozen ``/predict`` contract. It is a library the orchestrating code (and
future milestones) import directly.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from datetime import datetime
from typing import TYPE_CHECKING

from .models import (
    Claim,
    Conflict,
    DeviceContext,
    Evidence,
    EvidenceKind,
    FusionAttribute,
    ResolvedAttribute,
)

if TYPE_CHECKING:  # Type-only imports: the engine fuses these results but never
    # couples to the modules at runtime (builders import lazily when invoked).
    from ..fingerprint.models import DeviceFingerprint
    from ..inference.predictor import DetectionResult
    from ..ocr.models import OCRExtraction

#: Version tag stamped onto every produced :class:`DeviceContext`.
FUSION_ENGINE_VERSION = "1.0.0"

#: Decimal places aggregated confidences are rounded to. Matches the fingerprint
#: precision so values are stable against floating-point noise and compare
#: cleanly in tests and serialized output.
_CONFIDENCE_PRECISION = 6

#: Deterministic tie-break ordering for modules (declaration order of the enum).
_SOURCE_ORDER: dict[EvidenceKind, int] = {
    kind: index for index, kind in enumerate(EvidenceKind)
}


def _noisy_or(confidences: Sequence[float]) -> float:
    """Combine independent confidences so agreement raises the total.

    Uses the noisy-OR ``1 - Π(1 - cᵢ)``: two modules each 0.8-confident in the
    same value yield ``0.96`` — more than either alone — while a single claim is
    returned unchanged. Inputs are clamped to ``[0, 1]`` defensively.

    Args:
        confidences: The per-claim confidences supporting one value.

    Returns:
        The combined confidence in ``[0, 1]``.
    """
    product = 1.0
    for confidence in confidences:
        product *= 1.0 - max(0.0, min(1.0, confidence))
    return 1.0 - product


def _clamp_round(value: float) -> float:
    """Clamp ``value`` to ``[0, 1]`` and round to the confidence precision."""
    return round(max(0.0, min(1.0, value)), _CONFIDENCE_PRECISION)


class FusionEngine:
    """Merge module evidence into a normalized, immutable device context.

    Args:
        engine_version: Version tag stamped onto every produced context.
        clock: Optional callable returning the current time; when omitted the
            produced context carries ``created_at=None`` (kept optional so the
            engine is a pure function of its inputs unless a clock is supplied).
    """

    def __init__(
        self,
        *,
        engine_version: str = FUSION_ENGINE_VERSION,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._engine_version = engine_version
        self._clock = clock

    def fuse(
        self,
        evidence: Iterable[Evidence],
        *,
        eco_id: str = "",
        fingerprint: str = "",
        source_hashes: Sequence[str] = (),
    ) -> DeviceContext:
        """Fuse pre-built evidence into a :class:`DeviceContext`.

        This is the pure core: callers that already hold :class:`Evidence`
        (e.g. tests, or a future module producing evidence directly) use it
        without touching any AI module. The convenience :meth:`fuse_modules`
        builds the evidence for the common detection/fingerprint/OCR case.

        Args:
            evidence: The per-module contributions to merge. Empty evidence
                yields an empty context (no attributes, zero confidence).
            eco_id: Public EcoID for the unified device (usually the
                fingerprint's).
            fingerprint: Hash-backed fingerprint identifier.
            source_hashes: Provenance hashes of the source images.

        Returns:
            The normalized, immutable :class:`DeviceContext`.
        """
        evidence = tuple(evidence)
        resolved, conflicts = self._resolve_attributes(evidence)
        if resolved:
            confidence = _clamp_round(
                sum(item.confidence for item in resolved) / len(resolved)
            )
        else:
            confidence = 0.0
        created_at = self._clock() if self._clock is not None else None
        return DeviceContext(
            eco_id=eco_id,
            fingerprint=fingerprint,
            attributes=resolved,
            confidence=confidence,
            evidence=evidence,
            conflicts=conflicts,
            source_hashes=tuple(source_hashes),
            engine_version=self._engine_version,
            created_at=created_at,
        )

    def fuse_modules(
        self,
        *,
        detection: DetectionResult | None = None,
        fingerprint: DeviceFingerprint | None = None,
        ocr: OCRExtraction | None = None,
        source_hashes: Sequence[str] = (),
    ) -> DeviceContext:
        """Build evidence from raw module results and fuse them.

        A thin convenience over :meth:`fuse` covering the common case: pass any
        combination of a ``DetectionResult``, a ``DeviceFingerprint`` and an
        ``OCRExtraction``; each present module contributes evidence, and the
        fingerprint (when given) supplies the identity anchor and source hashes.
        Any module may be ``None`` — the engine simply fuses whatever is present
        (partial and missing evidence are first-class).

        Args:
            detection: Optional
                :class:`~device_ai.inference.predictor.DetectionResult`.
            fingerprint: Optional
                :class:`~device_ai.fingerprint.models.DeviceFingerprint`.
            ocr: Optional :class:`~device_ai.ocr.models.OCRExtraction`.
            source_hashes: Provenance hashes; when omitted and a fingerprint is
                supplied, the fingerprint's own source hashes are used.

        Returns:
            The normalized, immutable :class:`DeviceContext`.
        """
        evidence: list[Evidence] = []
        if detection is not None:
            evidence.append(Evidence.from_detection(detection))
        if fingerprint is not None:
            evidence.append(Evidence.from_fingerprint(fingerprint))
        if ocr is not None:
            evidence.append(Evidence.from_ocr(ocr))

        eco_id = fingerprint.eco_id if fingerprint is not None else ""
        fingerprint_hash = fingerprint.fingerprint if fingerprint is not None else ""
        hashes: Sequence[str] = source_hashes
        if not hashes and fingerprint is not None:
            hashes = fingerprint.source_hashes
        return self.fuse(
            evidence,
            eco_id=eco_id,
            fingerprint=fingerprint_hash,
            source_hashes=hashes,
        )

    def _resolve_attributes(
        self,
        evidence: Sequence[Evidence],
    ) -> tuple[tuple[ResolvedAttribute, ...], tuple[Conflict, ...]]:
        """Resolve every attribute across the evidence into value + confidence.

        For each attribute the claims are grouped by normalized value; the
        winning group is the one with the highest **combined** (noisy-OR)
        confidence, ties broken by claim count then module order for
        determinism. The winner's confidence is scaled by its *support share*
        (its combined confidence over the sum across all groups) so a lone
        dissenting module damps confidence and a unanimous one does not.

        Args:
            evidence: The per-module contributions.

        Returns:
            A ``(resolved_attributes, conflicts)`` pair, each in
            :class:`FusionAttribute` declaration order.
        """
        resolved: list[ResolvedAttribute] = []
        conflicts: list[Conflict] = []
        for attribute in FusionAttribute:
            claims = [
                claim
                for item in evidence
                for claim in item.claims
                if claim.attribute is attribute
            ]
            if not claims:
                continue
            groups = self._group_by_value(claims)
            winner_key, winner_claims = self._select_winner(groups)
            combined = {
                key: _noisy_or([claim.confidence for claim in group])
                for key, group in groups.items()
            }
            total = sum(combined.values())
            support_share = combined[winner_key] / total if total > 0 else 1.0
            conflicted = len(groups) > 1
            confidence = _clamp_round(combined[winner_key] * support_share)
            sources = tuple(
                sorted(
                    {claim.source for claim in winner_claims},
                    key=lambda source: _SOURCE_ORDER[source],
                )
            )
            winning_value = max(winner_claims, key=lambda claim: claim.confidence).value
            resolved.append(
                ResolvedAttribute(
                    attribute=attribute,
                    value=winning_value,
                    confidence=confidence,
                    sources=sources,
                    conflicted=conflicted,
                )
            )
            if conflicted:
                conflicts.append(
                    Conflict(
                        attribute=attribute,
                        resolved_value=winning_value,
                        claims=tuple(
                            sorted(
                                claims,
                                key=lambda claim: (
                                    -claim.confidence,
                                    _SOURCE_ORDER[claim.source],
                                ),
                            )
                        ),
                    )
                )
        return tuple(resolved), tuple(conflicts)

    @staticmethod
    def _group_by_value(claims: Sequence[Claim]) -> dict[str, list[Claim]]:
        """Group claims by their normalized comparison key (insertion-ordered)."""
        groups: dict[str, list[Claim]] = {}
        for claim in claims:
            groups.setdefault(claim.key, []).append(claim)
        return groups

    @staticmethod
    def _select_winner(
        groups: dict[str, list[Claim]],
    ) -> tuple[str, list[Claim]]:
        """Return the ``(key, claims)`` of the highest-support value group.

        Ranked by combined (noisy-OR) confidence, then by number of supporting
        claims, then by module order of the strongest claim — a total, stable
        ordering so identical evidence always resolves identically.
        """

        def rank(item: tuple[str, list[Claim]]) -> tuple[float, int, int]:
            _key, claims = item
            combined = _noisy_or([claim.confidence for claim in claims])
            best_source = min(_SOURCE_ORDER[claim.source] for claim in claims)
            return (combined, len(claims), -best_source)

        winner_key, winner_claims = max(groups.items(), key=rank)
        return winner_key, winner_claims
