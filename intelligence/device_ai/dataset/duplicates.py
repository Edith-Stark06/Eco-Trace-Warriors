"""Duplicate and near-duplicate detection.

Given analysed :class:`~device_ai.dataset.records.ImageRecord` objects, the
:class:`DuplicateDetector` finds:

* **Exact duplicates** — identical SHA-256 (byte-for-byte).
* **Near-duplicates** — perceptual hashes (aHash/dHash/pHash) within a
  configurable Hamming distance.

The first image (in sorted path order) of any duplicate group is retained as
the representative; the rest are reported for removal. The comparison is a
straightforward O(n²) scan, which is appropriate for the moderate dataset
sizes handled by this service and keeps the logic transparent and testable.
"""

from __future__ import annotations

from ..configs.settings import Settings
from .hashing import hamming_distance
from .records import DuplicatePair, DuplicateReport, ImageRecord


class DuplicateDetector:
    """Detect exact and near-duplicate images among analysed records.

    Args:
        hamming_threshold: Maximum perceptual-hash Hamming distance for two
            images to be treated as near-duplicates.
    """

    def __init__(self, hamming_threshold: int) -> None:
        self._threshold = hamming_threshold

    @classmethod
    def from_settings(cls, settings: Settings) -> DuplicateDetector:
        """Build a detector from application settings.

        Args:
            settings: The active settings supplying the threshold.

        Returns:
            A configured :class:`DuplicateDetector`.
        """
        return cls(settings.duplicate_hamming_threshold)

    def _min_distance(self, a: ImageRecord, b: ImageRecord) -> int:
        """Return the smallest Hamming distance across the perceptual hashes.

        Using the minimum across aHash/dHash/pHash makes detection sensitive
        to any single strong perceptual match. Corrupted records (empty
        hashes) never match perceptually.

        Args:
            a: First record.
            b: Second record.

        Returns:
            The minimum bitwise distance, or a large sentinel when either
            record lacks perceptual hashes.
        """
        pairs = (
            (a.hashes.phash, b.hashes.phash),
            (a.hashes.dhash, b.hashes.dhash),
            (a.hashes.ahash, b.hashes.ahash),
        )
        distances = [
            hamming_distance(x, y) for x, y in pairs if x and y and len(x) == len(y)
        ]
        return min(distances) if distances else 64

    def detect(self, records: list[ImageRecord]) -> DuplicateReport:
        """Find duplicate relationships within ``records``.

        Args:
            records: Analysed image records (any order; scanned as given).

        Returns:
            A :class:`DuplicateReport` listing every duplicate pair and the
            unique set of paths recommended for removal.
        """
        pairs: list[DuplicatePair] = []
        duplicate_paths: set[str] = set()
        seen_sha: dict[str, str] = {}

        for index, record in enumerate(records):
            # Exact duplicate: same content hash as an earlier image.
            sha = record.hashes.sha256
            if sha in seen_sha:
                source = seen_sha[sha]
                pairs.append(
                    DuplicatePair(
                        source=source,
                        duplicate=record.relative_path,
                        distance=0,
                        exact=True,
                    )
                )
                duplicate_paths.add(record.relative_path)
                continue
            seen_sha[sha] = record.relative_path

            # Near-duplicate: compare against every earlier, still-unique image.
            for prior in records[:index]:
                if prior.relative_path in duplicate_paths:
                    continue
                if prior.hashes.sha256 == sha:
                    continue
                distance = self._min_distance(record, prior)
                if distance <= self._threshold:
                    pairs.append(
                        DuplicatePair(
                            source=prior.relative_path,
                            duplicate=record.relative_path,
                            distance=distance,
                            exact=False,
                        )
                    )
                    duplicate_paths.add(record.relative_path)
                    break

        return DuplicateReport(
            pairs=tuple(pairs),
            duplicate_paths=tuple(sorted(duplicate_paths)),
            total_images=len(records),
        )
