"""Tests for the enriched dataset release manifest (P4.1.2, PART 5)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from PIL import Image

from device_ai.configs.settings import Settings
from device_ai.dataset.annotation_statistics import AnnotationStatisticsCalculator
from device_ai.dataset.duplicates import DuplicateDetector
from device_ai.dataset.metadata import MetadataGenerator
from device_ai.dataset.release import build_release, release_to_dict
from device_ai.dataset.splitter import DatasetSplitter
from device_ai.dataset.statistics import StatisticsCalculator
from device_ai.dataset.taxonomy import load_taxonomy
from device_ai.dataset.versioning import DatasetVersionManager


def _build_dataset(tmp_path: Path, count: int = 6) -> tuple[Path, Path, Path]:
    images = tmp_path / "images"
    labels = tmp_path / "labels"
    meta = tmp_path / "metadata"
    images.mkdir(parents=True)
    labels.mkdir(parents=True)
    meta.mkdir(parents=True)
    for i in range(count):
        Image.new("RGB", (128, 128), (40 + i * 10, 60, 80)).save(
            images / f"laptop_field_{i:06d}.jpg"
        )
        (labels / f"laptop_field_{i:06d}.txt").write_text("0 0.5 0.5 0.4 0.4\n")
    return images, labels, meta


def _assemble(tmp_path: Path):
    images, labels, meta = _build_dataset(tmp_path)
    settings = Settings()
    records = MetadataGenerator.from_settings(settings).analyze_directory(images)
    duplicates = DuplicateDetector.from_settings(settings).detect(records)
    stats = StatisticsCalculator().compute(records, duplicates=duplicates)
    ann = AnnotationStatisticsCalculator(load_taxonomy()).compute(
        images_root=images, labels_root=labels
    )
    split = DatasetSplitter.from_settings(settings).split_records(records)
    version = DatasetVersionManager(meta).create_version(
        records, created_at=datetime(2026, 1, 1, tzinfo=UTC), note="release-test"
    )
    return build_release(
        version=version,
        image_statistics=stats,
        annotation_statistics=ann,
        split=split,
    )


def test_release_taxonomy_version_matches_annotations(tmp_path: Path):
    """The release taxonomy version agrees with its annotation statistics."""
    release = _assemble(tmp_path)
    assert release.taxonomy_version == "1.0.0"
    assert release.annotation_statistics.taxonomy_version == "1.0.0"


def test_release_to_dict_has_all_part5_sections(tmp_path: Path):
    """The manifest carries metadata, statistics, taxonomy, checksums, split."""
    payload = release_to_dict(_assemble(tmp_path))
    assert set(payload) >= {
        "taxonomy_version",
        "version",
        "checksums",
        "image_statistics",
        "annotation_statistics",
        "split",
    }
    # Metadata + timestamp live in the version block.
    assert payload["version"]["created_at"] == "2026-01-01T00:00:00+00:00"
    assert payload["version"]["note"] == "release-test"
    # Checksums expose the content hash and per-image manifest.
    assert payload["checksums"]["content_hash"]
    assert len(payload["checksums"]["manifest"]) == 6


def test_release_split_information_is_recorded(tmp_path: Path):
    """Split ratios, seed and per-split counts are embedded in the manifest."""
    payload = release_to_dict(_assemble(tmp_path))
    split = payload["split"]
    assert split is not None
    assert split["seed"] == 42
    total = sum(split["counts"].values())
    assert total == 6
    assert set(split["assignments"]) == {"train", "val", "test"}


def test_release_without_split_is_allowed(tmp_path: Path):
    """A release may omit the split (null split section)."""
    images, labels, meta = _build_dataset(tmp_path)
    settings = Settings()
    records = MetadataGenerator.from_settings(settings).analyze_directory(images)
    stats = StatisticsCalculator().compute(records)
    ann = AnnotationStatisticsCalculator(load_taxonomy()).compute(
        images_root=images, labels_root=labels
    )
    version = DatasetVersionManager(meta).create_version(
        records, created_at=datetime(2026, 1, 1, tzinfo=UTC)
    )
    release = build_release(
        version=version, image_statistics=stats, annotation_statistics=ann
    )
    payload = release_to_dict(release)
    assert payload["split"] is None
