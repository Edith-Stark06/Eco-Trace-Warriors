"""Splitting — the frozen ``DatasetSplitter``, run for real.

The split is performed by
:class:`~device_ai.dataset.splitter.DatasetSplitter.from_settings`, so the ratios
``(0.7, 0.2, 0.1)`` and seed ``42`` come from
:class:`~device_ai.configs.settings.Settings` and are never overridden here. This
module adds verification only:

* **deterministic** — the splitter is invoked twice over the same identifiers and
  the two assignments must be identical;
* **disjoint** — no identifier appears in more than one split;
* **complete** — the union of the three splits equals the input set;
* **class presence** — the target class must appear in train *and* val *and* test.
  Presence is read from the staged label files through the frozen annotation
  validator; it is never assumed from a non-empty split.

There is **no minimum image count**. If a split ends up without the target class,
that exact result is reported (``CLASS_ABSENT_FROM_SPLIT``) with the per-split
counts — the seed is not changed, the ratios are not changed, and no threshold is
invented to paper over it.

Scope note: this verifies the **router wave** in isolation. Whole-dataset release
readiness is a separate gate (see the readiness stage), because the protected
P4.3.5/P4.3.6 batches are not merged by this pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

# Statuses (stable, machine-readable).
VERIFIED = "VERIFIED"
BLOCKED_EMPTY = "BLOCKED_EMPTY_INPUT"
CLASS_ABSENT = "CLASS_ABSENT_FROM_SPLIT"
NON_DETERMINISTIC = "NON_DETERMINISTIC"
DEFECTIVE = "DEFECTIVE"


@dataclass(frozen=True, slots=True)
class SplitOutcome:
    """Result of running and verifying the frozen split.

    Attributes:
        status: One of :data:`VERIFIED`, :data:`BLOCKED_EMPTY`,
            :data:`CLASS_ABSENT`, :data:`NON_DETERMINISTIC`, :data:`DEFECTIVE`.
        ratios: The ratios the frozen splitter reported using.
        seed: The seed the frozen splitter reported using.
        counts: Per-split image counts.
        assignments: Per-split identifier lists.
        deterministic: Whether two independent runs matched exactly.
        disjoint: Whether the splits share no identifier.
        complete: Whether the splits cover the whole input.
        class_present: Per-split presence of the target class.
        class_box_counts: Per-split target-class box counts.
        detail: Exact explanation of the outcome.
    """

    status: str
    ratios: tuple[float, float, float] = (0.0, 0.0, 0.0)
    seed: int = 0
    counts: dict[str, int] = field(default_factory=dict)
    assignments: dict[str, list[str]] = field(default_factory=dict)
    deterministic: bool = False
    disjoint: bool = False
    complete: bool = False
    class_present: dict[str, bool] = field(default_factory=dict)
    class_box_counts: dict[str, int] = field(default_factory=dict)
    detail: str = ""

    @property
    def verified(self) -> bool:
        """Whether every split check passed, including per-split class presence."""
        return self.status == VERIFIED

    def to_dict(self) -> dict[str, object]:
        """Return a primitive-only, JSON-serialisable mapping."""
        return {
            "status": self.status,
            "splitter": "device_ai.dataset.splitter.DatasetSplitter (frozen)",
            "ratios": list(self.ratios),
            "seed": self.seed,
            "counts": self.counts,
            "deterministic": self.deterministic,
            "disjoint": self.disjoint,
            "complete": self.complete,
            "class_present": self.class_present,
            "class_box_counts": self.class_box_counts,
            "minimum_per_class": (
                "none - no numerical minimum is defined or applied by this pipeline"
            ),
            "assignments": self.assignments,
            "detail": self.detail,
        }


def _target_boxes(
    identifiers: set[str], *, labels_root: Path, taxonomy_id: int, num_classes: int
) -> int:
    """Count target-class boxes across a split's staged label files."""
    from ..dataset.validator import AnnotationValidator

    validator = AnnotationValidator(num_classes=num_classes)
    total = 0
    for rel in sorted(identifiers):
        label = (labels_root / rel).with_suffix(".txt")
        if not label.exists():
            continue
        boxes, _ = validator.validate_label_file(label, root=labels_root)
        total += sum(1 for box in boxes if box.class_id == taxonomy_id)
    return total


def run_split(
    identifiers: list[str],
    *,
    labels_root: Path,
    taxonomy_id: int,
    num_classes: int,
    settings: object | None = None,
) -> SplitOutcome:
    """Split the accepted identifiers with the frozen splitter and verify it.

    Args:
        identifiers: Accepted staged image paths (relative to the images root).
        labels_root: Staged labels root, read to establish class presence.
        taxonomy_id: The target class id whose presence is verified.
        num_classes: Taxonomy size for the frozen annotation validator.
        settings: Optional injected settings (defaults to ``get_settings()``).

    Returns:
        A :class:`SplitOutcome`. An empty input yields :data:`BLOCKED_EMPTY`
        rather than an exception escaping to the caller.
    """
    from ..configs.settings import get_settings
    from ..dataset.splitter import DatasetSplitter
    from ..exceptions import EmptyDatasetError

    active = settings if settings is not None else get_settings()
    ratios = tuple(float(r) for r in active.split_ratios)  # type: ignore[attr-defined]
    seed = int(active.split_seed)  # type: ignore[attr-defined]

    if not identifiers:
        return SplitOutcome(
            status=BLOCKED_EMPTY,
            ratios=ratios,  # type: ignore[arg-type]
            seed=seed,
            detail=(
                "no accepted images to split; the frozen splitter raises "
                "EmptyDatasetError by design and no split was performed"
            ),
        )

    splitter = DatasetSplitter.from_settings(active)  # type: ignore[arg-type]
    try:
        assignment = splitter.split_identifiers(list(identifiers))
        repeat = DatasetSplitter.from_settings(active).split_identifiers(  # type: ignore[arg-type]
            list(reversed(identifiers))
        )
    except EmptyDatasetError as exc:  # pragma: no cover - guarded above
        return SplitOutcome(
            status=BLOCKED_EMPTY,
            ratios=ratios,  # type: ignore[arg-type]
            seed=seed,
            detail=f"frozen splitter refused an empty dataset: {exc}",
        )

    # Determinism is asserted against a reversed input order too: the frozen
    # splitter sorts before shuffling, so ordering must not affect the result.
    deterministic = (
        assignment.train == repeat.train
        and assignment.val == repeat.val
        and assignment.test == repeat.test
    )

    train, val, test = set(assignment.train), set(assignment.val), set(assignment.test)
    disjoint = not ((train & val) or (train & test) or (val & test))
    complete = (train | val | test) == set(identifiers)

    class_box_counts = {
        name: _target_boxes(
            ids, labels_root=labels_root, taxonomy_id=taxonomy_id, num_classes=num_classes
        )
        for name, ids in (("train", train), ("val", val), ("test", test))
    }
    class_present = {name: count > 0 for name, count in class_box_counts.items()}

    assignments = {
        "train": list(assignment.train),
        "val": list(assignment.val),
        "test": list(assignment.test),
    }
    common = {
        "ratios": assignment.ratios,
        "seed": assignment.seed,
        "counts": assignment.counts,
        "assignments": assignments,
        "deterministic": deterministic,
        "disjoint": disjoint,
        "complete": complete,
        "class_present": class_present,
        "class_box_counts": class_box_counts,
    }

    if not deterministic:
        return SplitOutcome(
            status=NON_DETERMINISTIC,
            detail=(
                "two runs of the frozen splitter over the same identifiers "
                "disagreed; this is a hard defect, not a data shortfall"
            ),
            **common,  # type: ignore[arg-type]
        )
    if not disjoint or not complete:
        return SplitOutcome(
            status=DEFECTIVE,
            detail=(
                f"split defect: disjoint={disjoint}, complete={complete} "
                "(leakage or dropped identifiers)"
            ),
            **common,  # type: ignore[arg-type]
        )

    absent = [name for name, present in class_present.items() if not present]
    if absent:
        return SplitOutcome(
            status=CLASS_ABSENT,
            detail=(
                f"target class absent from: {', '.join(absent)}. Reported exactly "
                "as measured - the seed and ratios were not changed and no minimum "
                "image count was invented. More real images are required."
            ),
            **common,  # type: ignore[arg-type]
        )
    return SplitOutcome(
        status=VERIFIED,
        detail=(
            "frozen 70/20/10 seed-42 split verified: deterministic, disjoint, "
            "complete, target class present in train/val/test"
        ),
        **common,  # type: ignore[arg-type]
    )
