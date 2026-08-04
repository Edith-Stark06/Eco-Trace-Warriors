"""Deterministic train/validation/test splitting.

:class:`DatasetSplitter` partitions image identifiers into train/val/test
subsets using a seeded shuffle, so the same inputs and seed always yield the
same split (reproducibility is a milestone requirement). Ratios are validated
to be non-negative and to sum to 1.0.

The splitter operates on ``relative_path`` strings — it performs no I/O — so
it is fast, pure and easy to test. Persisting the split to disk is the
responsibility of the dataset service.
"""

from __future__ import annotations

import numpy as np

from ..configs.settings import Settings
from ..exceptions import EmptyDatasetError, InvalidSplitError
from .records import ImageRecord, SplitAssignment


class DatasetSplitter:
    """Partition image identifiers into train/val/test subsets.

    Args:
        ratios: The ``(train, val, test)`` proportions; must sum to 1.0.
        seed: RNG seed for the deterministic shuffle.
    """

    def __init__(
        self,
        ratios: tuple[float, float, float],
        *,
        seed: int,
    ) -> None:
        self._validate_ratios(ratios)
        self._ratios = ratios
        self._seed = seed

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        *,
        ratios: tuple[float, float, float] | None = None,
        seed: int | None = None,
    ) -> DatasetSplitter:
        """Build a splitter from settings with optional overrides.

        Args:
            settings: The active settings supplying defaults.
            ratios: Optional ratio override.
            seed: Optional seed override.

        Returns:
            A configured :class:`DatasetSplitter`.
        """
        return cls(
            ratios or settings.split_ratios,
            seed=seed if seed is not None else settings.split_seed,
        )

    @staticmethod
    def _validate_ratios(ratios: tuple[float, float, float]) -> None:
        """Raise :class:`InvalidSplitError` when ratios are invalid."""
        if len(ratios) != 3:
            raise InvalidSplitError("split ratios must have exactly three parts")
        if any(part < 0.0 for part in ratios):
            raise InvalidSplitError("split ratios must be non-negative")
        if abs(sum(ratios) - 1.0) > 1e-6:
            raise InvalidSplitError(f"split ratios must sum to 1.0 (got {sum(ratios)})")

    def split_identifiers(self, identifiers: list[str]) -> SplitAssignment:
        """Partition identifier strings into train/val/test subsets.

        Args:
            identifiers: Stable image identifiers (e.g. relative paths).

        Returns:
            The :class:`SplitAssignment`.

        Raises:
            EmptyDatasetError: If ``identifiers`` is empty.
        """
        if not identifiers:
            raise EmptyDatasetError("cannot split an empty dataset")

        # Sort first so the shuffle is independent of input ordering, then
        # shuffle with a seeded RNG for reproducibility.
        ordered = sorted(identifiers)
        rng = np.random.default_rng(self._seed)
        permutation = rng.permutation(len(ordered))
        shuffled = [ordered[int(i)] for i in permutation]

        total = len(shuffled)
        train_end = int(total * self._ratios[0])
        val_end = train_end + int(total * self._ratios[1])

        train = shuffled[:train_end]
        val = shuffled[train_end:val_end]
        test = shuffled[val_end:]

        return SplitAssignment(
            train=tuple(sorted(train)),
            val=tuple(sorted(val)),
            test=tuple(sorted(test)),
            ratios=self._ratios,
            seed=self._seed,
        )

    def split_records(self, records: list[ImageRecord]) -> SplitAssignment:
        """Partition analysed records by their relative paths.

        Args:
            records: Analysed image records.

        Returns:
            The :class:`SplitAssignment`.
        """
        return self.split_identifiers([record.relative_path for record in records])


def split_to_dict(assignment: SplitAssignment) -> dict[str, object]:
    """Convert a :class:`SplitAssignment` into a JSON-serialisable dict.

    Args:
        assignment: The split to serialise.

    Returns:
        A primitive-only mapping.
    """
    return {
        "ratios": list(assignment.ratios),
        "seed": assignment.seed,
        "counts": assignment.counts,
        "train": list(assignment.train),
        "val": list(assignment.val),
        "test": list(assignment.test),
    }
