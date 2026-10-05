"""Enriched dataset release manifest (Sprint P4.1.2, PART 5).

A :class:`~device_ai.dataset.records.DatasetVersion` captures the immutable core
of a snapshot: label, timestamp, image count, content hash and per-image
manifest. A *release manifest* wraps that version with everything a training run
or an auditor needs alongside it — image statistics, annotation statistics,
taxonomy version, and the train/val/test split assignment — into one
JSON-serialisable document.

This module is pure composition: it takes already-computed value objects
(produced by the existing statistics, annotation-statistics, versioning and
splitter modules) and assembles the release document. It performs no I/O and
computes no metrics itself, so it neither duplicates nor modifies any existing
pipeline behaviour.
"""

from __future__ import annotations

from dataclasses import dataclass

from .annotation_statistics import AnnotationStatistics, annotation_statistics_to_dict
from .records import DatasetStatistics, DatasetVersion, SplitAssignment
from .statistics import statistics_to_dict
from .versioning import version_to_dict


@dataclass(frozen=True, slots=True)
class DatasetRelease:
    """A complete, auditable dataset release.

    Attributes:
        version: The immutable content-addressed snapshot.
        image_statistics: Aggregate image statistics for the snapshot.
        annotation_statistics: Annotation-derived statistics (class
            distribution, bounding boxes, completeness).
        split: The train/val/test split assignment for this release, or
            ``None`` when the release is not yet split.
        taxonomy_version: Version of the class taxonomy the release targets.
    """

    version: DatasetVersion
    image_statistics: DatasetStatistics
    annotation_statistics: AnnotationStatistics
    split: SplitAssignment | None
    taxonomy_version: str


def _split_to_dict(split: SplitAssignment | None) -> dict[str, object] | None:
    """Convert a :class:`SplitAssignment` into a JSON-serialisable dict."""
    if split is None:
        return None
    return {
        "ratios": {
            "train": split.ratios[0],
            "val": split.ratios[1],
            "test": split.ratios[2],
        },
        "seed": split.seed,
        "counts": split.counts,
        "assignments": {
            "train": list(split.train),
            "val": list(split.val),
            "test": list(split.test),
        },
    }


def build_release(
    *,
    version: DatasetVersion,
    image_statistics: DatasetStatistics,
    annotation_statistics: AnnotationStatistics,
    split: SplitAssignment | None = None,
) -> DatasetRelease:
    """Assemble a :class:`DatasetRelease` from its component value objects.

    The taxonomy version is taken from the annotation statistics, which sourced
    it from the single canonical taxonomy — so a release always agrees with the
    class list its statistics were computed against.

    Args:
        version: The immutable snapshot.
        image_statistics: Aggregate image statistics.
        annotation_statistics: Annotation-derived statistics.
        split: Optional train/val/test split assignment.

    Returns:
        The assembled :class:`DatasetRelease`.
    """
    return DatasetRelease(
        version=version,
        image_statistics=image_statistics,
        annotation_statistics=annotation_statistics,
        split=split,
        taxonomy_version=annotation_statistics.taxonomy_version,
    )


def release_to_dict(release: DatasetRelease) -> dict[str, object]:
    """Convert a :class:`DatasetRelease` into a JSON-serialisable dict.

    The resulting document is the enriched manifest required by PART 5: it
    carries metadata (version + timestamp + checksums), image statistics,
    annotation statistics, taxonomy version and split information in one place.

    Args:
        release: The dataset release.

    Returns:
        A primitive-only mapping.
    """
    return {
        "taxonomy_version": release.taxonomy_version,
        "version": version_to_dict(release.version),
        "checksums": {
            "content_hash": release.version.content_hash,
            "manifest": release.version.manifest,
        },
        "image_statistics": statistics_to_dict(release.image_statistics),
        "annotation_statistics": annotation_statistics_to_dict(
            release.annotation_statistics
        ),
        "split": _split_to_dict(release.split),
    }
