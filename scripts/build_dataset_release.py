"""Build a Dataset v1.0 release manifest (Sprint P4.2.2, PART 4).

This CLI assembles an auditable, deterministic dataset release by composing the
**frozen** P4.1.2 pipeline end to end — it adds no metrics of its own:

* :class:`~device_ai.dataset.metadata.MetadataGenerator` +
  :class:`~device_ai.dataset.statistics.StatisticsCalculator` -> image stats;
* :class:`~device_ai.dataset.annotation_statistics.AnnotationStatisticsCalculator`
  -> annotation stats (class distribution, boxes, completeness);
* :func:`~device_ai.dataset.versioning.compute_content_hash` -> the immutable
  content hash over the sorted per-image SHA-256 manifest;
* :func:`~device_ai.dataset.release.build_release` /
  :func:`~device_ai.dataset.release.release_to_dict` -> the release document.

The output ``dataset_manifest.json`` carries the version + release timestamp,
checksums (content hash + per-image manifest), image statistics, annotation
statistics and the taxonomy version. It is **deterministic**: same images +
labels + ``--version`` + ``--created-at`` produce byte-identical output. The
release timestamp is injected (not read from the wall clock) so releases are
reproducible; the content hash is derived from image bytes and never depends on
run time.

The builder computes the version snapshot in memory and does **not** persist a
version into the managed dataset tree, so it never mutates the frozen pipeline's
state.

Exit codes:
    0: release manifest built.
    2: usage error (missing directories).

Examples:
    python scripts/build_dataset_release.py \
        --images-root datasets/raw --labels-root datasets/labels \
        --out datasets/exports/dataset_manifest.json
    python scripts/build_dataset_release.py \
        --images-root datasets/raw --labels-root datasets/labels \
        --version v1.0 --created-at 2026-08-07T00:00:00+00:00 \
        --note "Dataset v1.0 release candidate"
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from device_ai.configs.settings import get_settings
from device_ai.dataset.annotation_statistics import AnnotationStatisticsCalculator
from device_ai.dataset.layout import list_image_paths
from device_ai.dataset.metadata import MetadataGenerator
from device_ai.dataset.records import DatasetVersion
from device_ai.dataset.release import build_release, release_to_dict
from device_ai.dataset.statistics import StatisticsCalculator
from device_ai.dataset.taxonomy import load_taxonomy
from device_ai.dataset.versioning import compute_content_hash

# Deterministic default release label and timestamp (override via CLI).
_DEFAULT_VERSION = "v1.0"
_DEFAULT_CREATED_AT = "2026-08-07T00:00:00+00:00"


def _build_version(
    *, images_root: Path, version: str, created_at: str, note: str
) -> DatasetVersion:
    """Build an in-memory, content-addressed :class:`DatasetVersion`.

    Mirrors :meth:`DatasetVersionManager.create_version` (same manifest and
    :func:`compute_content_hash`) but assigns the caller's version label and
    performs **no disk persistence**, keeping the builder deterministic and
    side-effect free.

    Args:
        images_root: Directory containing the dataset images.
        version: The release version label.
        created_at: ISO-8601 timestamp to embed.
        note: Optional human-readable description.

    Returns:
        The assembled :class:`DatasetVersion`.
    """
    settings = get_settings()
    generator = MetadataGenerator.from_settings(settings)
    records = generator.analyze_directory(images_root)
    manifest = {record.relative_path: record.hashes.sha256 for record in records}
    return DatasetVersion(
        version=version,
        created_at=created_at,
        image_count=len(records),
        content_hash=compute_content_hash(manifest),
        note=note,
        manifest=dict(sorted(manifest.items())),
    )


def build_manifest(
    *,
    images_root: Path,
    labels_root: Path,
    version: str,
    created_at: str,
    note: str,
) -> dict[str, object]:
    """Assemble the full release manifest document.

    Args:
        images_root: Directory containing the dataset images.
        labels_root: Directory containing the YOLO ``.txt`` labels.
        version: The release version label.
        created_at: ISO-8601 release timestamp.
        note: Optional human-readable description.

    Returns:
        A JSON-serialisable release manifest.
    """
    settings = get_settings()
    taxonomy = load_taxonomy()

    generator = MetadataGenerator.from_settings(settings)
    records = generator.analyze_directory(images_root)
    image_stats = StatisticsCalculator().compute(records)

    annotation_stats = AnnotationStatisticsCalculator(taxonomy).compute(
        images_root=images_root, labels_root=labels_root
    )

    dataset_version = _build_version(
        images_root=images_root,
        version=version,
        created_at=created_at,
        note=note,
    )

    release = build_release(
        version=dataset_version,
        image_statistics=image_stats,
        annotation_statistics=annotation_stats,
    )
    manifest = release_to_dict(release)

    # An explicit, compact annotation summary alongside the full statistics,
    # so auditors can read release health at a glance.
    manifest["annotation_summary"] = {
        "total_boxes": annotation_stats.total_boxes,
        "total_labelled_images": annotation_stats.total_labelled_images,
        "annotation_completeness": annotation_stats.annotation_completeness,
        "missing_classes": list(annotation_stats.missing_classes),
        "images_without_labels": len(annotation_stats.images_without_labels),
        "orphan_labels": len(annotation_stats.orphan_labels),
    }
    return manifest


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Build a deterministic Dataset v1.0 release manifest.",
    )
    parser.add_argument(
        "--images-root",
        required=True,
        type=Path,
        help="Directory containing the dataset images.",
    )
    parser.add_argument(
        "--labels-root",
        required=True,
        type=Path,
        help="Directory containing the YOLO .txt label files.",
    )
    parser.add_argument(
        "--version",
        default=_DEFAULT_VERSION,
        help=f"Release version label (default {_DEFAULT_VERSION}).",
    )
    parser.add_argument(
        "--created-at",
        default=_DEFAULT_CREATED_AT,
        help=(
            "ISO-8601 release timestamp, injected for reproducibility "
            f"(default {_DEFAULT_CREATED_AT})."
        ),
    )
    parser.add_argument(
        "--note",
        default="",
        help="Optional human-readable release note.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Path to write dataset_manifest.json (also printed to stdout).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point for the release builder.

    Args:
        argv: Optional argument vector (defaults to ``sys.argv``).

    Returns:
        A process exit code (0 success, 2 usage error).
    """
    args = _parse_args(argv)
    if not args.images_root.is_dir():
        print(f"error: images root not found: {args.images_root}", file=sys.stderr)
        return 2
    if not args.labels_root.is_dir():
        print(f"error: labels root not found: {args.labels_root}", file=sys.stderr)
        return 2
    try:
        datetime.fromisoformat(args.created_at)
    except ValueError:
        print(
            f"error: --created-at is not a valid ISO-8601 timestamp: "
            f"{args.created_at}",
            file=sys.stderr,
        )
        return 2

    # Touch the discovery helper so an empty image root is reported explicitly
    # rather than silently producing a zero-image release.
    if not list_image_paths(args.images_root):
        print(f"error: no images found under: {args.images_root}", file=sys.stderr)
        return 2

    manifest = build_manifest(
        images_root=args.images_root,
        labels_root=args.labels_root,
        version=args.version,
        created_at=args.created_at,
        note=args.note,
    )
    text = json.dumps(manifest, indent=2, sort_keys=True)
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
