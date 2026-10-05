"""Deduplication — the frozen ``DuplicateDetector``, used exactly as-is.

Nothing in this module changes duplicate semantics. It only *arranges the input*
so the frozen detector's own retention rule protects the right data:

    :class:`~device_ai.dataset.duplicates.DuplicateDetector` retains the **first**
    record of any duplicate group and flags the later ones.

Therefore protected records are always presented **first** and new-batch records
second. A new image that duplicates protected data is consequently flagged as the
duplicate, and a protected image can never be flagged against a new one. Records
are namespaced (``protected/<label>/...`` vs ``batch/...``) before the scan so
identical relative paths under different roots cannot collide.

The threshold, the hashing, and the pair semantics come untouched from
:class:`~device_ai.configs.settings.Settings` and the frozen detector; this module
neither reads nor overrides them. Protected trees are opened read-only — no path
beneath them is ever written, moved or deleted, and a duplicate found *within*
protected data is reported for information only, never acted on.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

# Namespaces applied to record identities during the cross-batch scan.
PROTECTED_PREFIX = "protected"
BATCH_PREFIX = "batch"

SKIPPED_NO_PROTECTED_DATA = "SKIPPED_NO_PROTECTED_DATA"
COMPLETED = "COMPLETED"
SKIPPED_EMPTY_BATCH = "SKIPPED_EMPTY_BATCH"


@dataclass(frozen=True, slots=True)
class DedupOutcome:
    """Result of the frozen duplicate scan over protected + new records.

    Attributes:
        status: :data:`COMPLETED`, :data:`SKIPPED_NO_PROTECTED_DATA` or
            :data:`SKIPPED_EMPTY_BATCH`.
        hamming_threshold: The frozen threshold actually used (echoed, not set).
        protected_scanned: Protected records included in the scan.
        batch_scanned: New-batch records included in the scan.
        batch_duplicates: Batch ``relative_path`` values flagged as duplicates
            (these are excluded from the accepted set).
        protected_flagged: Protected paths flagged as duplicates of an *earlier
            protected* record. Reported only; never acted on.
        pairs: Every duplicate relationship found, as primitive mappings.
        detail: Human-readable note about the scan.
    """

    status: str
    hamming_threshold: int
    protected_scanned: int = 0
    batch_scanned: int = 0
    batch_duplicates: tuple[str, ...] = ()
    protected_flagged: tuple[str, ...] = ()
    pairs: tuple[dict[str, object], ...] = field(default_factory=tuple)
    detail: str = ""

    @property
    def num_batch_duplicates(self) -> int:
        """Count of new-batch images flagged as duplicates."""
        return len(self.batch_duplicates)

    def to_dict(self) -> dict[str, object]:
        """Return a primitive-only, JSON-serialisable mapping."""
        return {
            "status": self.status,
            "hamming_threshold": self.hamming_threshold,
            "detector": "device_ai.dataset.duplicates.DuplicateDetector (frozen)",
            "ordering": (
                "protected records scanned first so the frozen retain-first rule "
                "always keeps the protected representative"
            ),
            "protected_scanned": self.protected_scanned,
            "batch_scanned": self.batch_scanned,
            "batch_duplicates": list(self.batch_duplicates),
            "num_batch_duplicates": self.num_batch_duplicates,
            "protected_flagged_information_only": list(self.protected_flagged),
            "pairs": list(self.pairs),
            "detail": self.detail,
        }


def _namespaced(records: list, prefix: str) -> list:
    """Return copies of ``records`` with a namespaced ``relative_path``."""
    from dataclasses import replace

    return [
        replace(record, relative_path=f"{prefix}/{record.relative_path}")
        for record in records
    ]


def run_dedup(
    *,
    batch_images_root: Path,
    protected_roots: tuple[tuple[str, Path], ...],
    settings: object | None = None,
) -> DedupOutcome:
    """Scan the new batch against itself and against protected data.

    Args:
        batch_images_root: Staged images root for the new batch.
        protected_roots: ``(label, path)`` pairs of read-only protected trees.
            Absent roots are skipped and reported, never fabricated.
        settings: Optional injected settings (defaults to ``get_settings()``).

    Returns:
        A :class:`DedupOutcome` naming every new-batch image to drop.
    """
    from ..configs.settings import get_settings
    from ..dataset.duplicates import DuplicateDetector
    from ..dataset.metadata import MetadataGenerator

    active = settings if settings is not None else get_settings()
    generator = MetadataGenerator.from_settings(active)  # type: ignore[arg-type]
    detector = DuplicateDetector.from_settings(active)  # type: ignore[arg-type]
    threshold = int(active.duplicate_hamming_threshold)  # type: ignore[attr-defined]

    batch_records = (
        generator.analyze_directory(batch_images_root)
        if batch_images_root.is_dir()
        else []
    )
    if not batch_records:
        return DedupOutcome(
            status=SKIPPED_EMPTY_BATCH,
            hamming_threshold=threshold,
            detail="no staged images to deduplicate",
        )

    protected_records: list = []
    scanned_labels: list[str] = []
    for label, root in protected_roots:
        if not root.is_dir():
            continue
        records = generator.analyze_directory(root)
        if not records:
            continue
        scanned_labels.append(label)
        protected_records.extend(_namespaced(records, f"{PROTECTED_PREFIX}/{label}"))

    ordered = protected_records + _namespaced(batch_records, BATCH_PREFIX)
    report = detector.detect(ordered)

    batch_duplicates = tuple(
        path[len(BATCH_PREFIX) + 1 :]
        for path in report.duplicate_paths
        if path.startswith(f"{BATCH_PREFIX}/")
    )
    protected_flagged = tuple(
        path for path in report.duplicate_paths if path.startswith(PROTECTED_PREFIX)
    )
    pairs = tuple(
        {
            "source": pair.source,
            "duplicate": pair.duplicate,
            "distance": pair.distance,
            "exact": pair.exact,
        }
        for pair in report.pairs
    )

    if not protected_records:
        return DedupOutcome(
            status=SKIPPED_NO_PROTECTED_DATA,
            hamming_threshold=threshold,
            protected_scanned=0,
            batch_scanned=len(batch_records),
            batch_duplicates=batch_duplicates,
            protected_flagged=protected_flagged,
            pairs=pairs,
            detail=(
                "no protected data present to compare against; the batch was "
                "still deduplicated against itself with the frozen detector"
            ),
        )

    return DedupOutcome(
        status=COMPLETED,
        hamming_threshold=threshold,
        protected_scanned=len(protected_records),
        batch_scanned=len(batch_records),
        batch_duplicates=batch_duplicates,
        protected_flagged=protected_flagged,
        pairs=pairs,
        detail=(
            f"scanned {len(batch_records)} new image(s) against "
            f"{len(protected_records)} protected image(s) from "
            f"{', '.join(scanned_labels)} (read-only, protected records first)"
        ),
    )
