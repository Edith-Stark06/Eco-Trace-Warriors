"""Tests for the split-aware YOLO data manifest builder (P4.1.3, PART 2).

These exercise the connection from a P4.1.2 ``DatasetRelease`` to the trainer's
``data.yaml`` — honoring the release split, degrading gracefully when no split
is present, and sourcing class names from the canonical taxonomy — all in the
base environment (no torch/Ultralytics).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from PIL import Image

from device_ai.configs.settings import Settings
from device_ai.dataset.annotation_statistics import AnnotationStatisticsCalculator
from device_ai.dataset.metadata import MetadataGenerator
from device_ai.dataset.release import DatasetRelease, build_release
from device_ai.dataset.splitter import DatasetSplitter
from device_ai.dataset.statistics import StatisticsCalculator
from device_ai.dataset.taxonomy import load_taxonomy
from device_ai.dataset.versioning import DatasetVersionManager
from device_ai.training.detector.data_manifest import build_training_manifest


def _assemble_release(tmp_path: Path, *, with_split: bool, count: int = 6) -> tuple[
    DatasetRelease, Path
]:
    """Build a small release plus a YOLO export dir with an images/ folder."""
    images = tmp_path / "src_images"
    labels = tmp_path / "src_labels"
    meta = tmp_path / "meta"
    images.mkdir(parents=True)
    labels.mkdir(parents=True)
    meta.mkdir(parents=True)
    for i in range(count):
        Image.new("RGB", (128, 128), (40 + i * 10, 60, 80)).save(
            images / f"laptop_field_{i:06d}.jpg"
        )
        (labels / f"laptop_field_{i:06d}.txt").write_text("0 0.5 0.5 0.4 0.4\n")

    settings = Settings()
    records = MetadataGenerator.from_settings(settings).analyze_directory(images)
    stats = StatisticsCalculator().compute(records)
    ann = AnnotationStatisticsCalculator(load_taxonomy()).compute(
        images_root=images, labels_root=labels
    )
    split = (
        DatasetSplitter.from_settings(settings).split_records(records)
        if with_split
        else None
    )
    version = DatasetVersionManager(meta).create_version(
        records, created_at=datetime(2026, 1, 1, tzinfo=UTC)
    )
    release = build_release(
        version=version,
        image_statistics=stats,
        annotation_statistics=ann,
        split=split,
    )

    # A YOLO export dir with the images/ subfolder the manifest anchors to.
    export_root = tmp_path / "export"
    (export_root / "images").mkdir(parents=True)
    for i in range(count):
        (export_root / "images" / f"laptop_field_{i:06d}.jpg").write_bytes(b"x")
    return release, export_root


def test_split_aware_manifest_writes_lists_and_yaml(tmp_path: Path) -> None:
    """With a split, train/val/test lists + a data.yaml referencing them exist."""
    release, export_root = _assemble_release(tmp_path, with_split=True)

    data_yaml = build_training_manifest(release, export_root=export_root)

    assert data_yaml == export_root / "data.yaml"
    assert (export_root / "train.txt").exists()
    assert (export_root / "val.txt").exists()
    assert (export_root / "test.txt").exists()

    text = data_yaml.read_text(encoding="utf-8")
    assert "train: train.txt" in text
    assert "val: val.txt" in text
    assert "test: test.txt" in text
    # Split leakage is avoided: train and val lists are disjoint.
    train_lines = {
        line
        for line in (export_root / "train.txt").read_text().splitlines()
        if line
    }
    val_lines = {
        line for line in (export_root / "val.txt").read_text().splitlines() if line
    }
    assert train_lines.isdisjoint(val_lines)


def test_manifest_counts_match_split_assignment(tmp_path: Path) -> None:
    """Each list holds exactly the images the split assigned."""
    release, export_root = _assemble_release(tmp_path, with_split=True)
    assert release.split is not None

    build_training_manifest(release, export_root=export_root)

    def _count(name: str) -> int:
        return len(
            [
                line
                for line in (export_root / name).read_text().splitlines()
                if line.strip()
            ]
        )

    assert _count("train.txt") == len(release.split.train)
    assert _count("val.txt") == len(release.split.val)
    assert _count("test.txt") == len(release.split.test)


def test_manifest_uses_canonical_taxonomy_names(tmp_path: Path) -> None:
    """The data.yaml carries the canonical 19-class taxonomy names and count."""
    release, export_root = _assemble_release(tmp_path, with_split=True)
    taxonomy = load_taxonomy()

    data_yaml = build_training_manifest(release, export_root=export_root)
    text = data_yaml.read_text(encoding="utf-8")

    assert f"nc: {taxonomy.num_classes}" in text
    # The first taxonomy class name appears in the names list.
    assert taxonomy.class_names[0] in text


def test_manifest_without_split_degrades_to_flat(tmp_path: Path) -> None:
    """With no split, the manifest falls back to a flat images/ layout."""
    release, export_root = _assemble_release(tmp_path, with_split=False)

    data_yaml = build_training_manifest(release, export_root=export_root)
    text = data_yaml.read_text(encoding="utf-8")

    assert "train: images" in text
    assert "val: images" in text
    assert not (export_root / "train.txt").exists()


def test_manifest_requires_images_dir(tmp_path: Path) -> None:
    """A missing images/ directory raises (the exporter must run first)."""
    release, export_root = _assemble_release(tmp_path, with_split=True)
    # Remove the images dir to simulate a missing export.
    for child in (export_root / "images").iterdir():
        child.unlink()
    (export_root / "images").rmdir()

    with pytest.raises(ValueError, match="images directory not found"):
        build_training_manifest(release, export_root=export_root)
