"""Tests for the taxonomy accessor and annotation statistics (P4.1.2, PART 4)."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from device_ai.dataset.annotation_statistics import (
    AnnotationStatisticsCalculator,
    annotation_statistics_to_dict,
)
from device_ai.dataset.taxonomy import DeviceTaxonomy, load_taxonomy

# Canonical class-ID ordering (0–18), the frozen contract of the dataset spec.
_EXPECTED_CLASS_NAMES = (
    "laptop",
    "smartphone",
    "tablet",
    "desktop",
    "server",
    "monitor",
    "crt_monitor",
    "television",
    "printer",
    "keyboard",
    "mouse",
    "router",
    "power_supply",
    "cable",
    "camera",
    "game_console",
    "smartwatch",
    "headphones",
    "battery",
)


def _img(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (128, 128), (120, 120, 120)).save(path)


# --- Taxonomy --------------------------------------------------------------


def test_taxonomy_loads_canonical_ordering():
    """The taxonomy is sourced from the component library in class-ID order."""
    tax = load_taxonomy()
    assert tax.version == "1.0.0"
    assert tax.num_classes == 19
    assert tax.class_names == _EXPECTED_CLASS_NAMES


def test_taxonomy_name_and_id_round_trip():
    """name_for and class_id_for are inverse over the taxonomy."""
    tax = load_taxonomy()
    assert tax.name_for(0) == "laptop"
    assert tax.name_for(18) == "battery"
    assert tax.class_id_for("mouse") == 10
    assert tax.name_for(999) == "unknown"
    assert tax.class_id_for("not_a_device") is None


# --- Annotation statistics -------------------------------------------------


def _small_taxonomy() -> DeviceTaxonomy:
    """A trimmed taxonomy keeps assertions on missing-classes compact."""
    return DeviceTaxonomy(version="test-1", class_names=("laptop", "mouse", "tablet"))


def test_class_distribution_covers_all_taxonomy_classes(tmp_path: Path):
    """The distribution lists every class, including zero-count ones."""
    images = tmp_path / "images"
    labels = tmp_path / "labels"
    _img(images / "laptop_field_000001.jpg")
    (labels / "laptop_field_000001.txt").parent.mkdir(parents=True, exist_ok=True)
    (labels / "laptop_field_000001.txt").write_text("0 0.5 0.5 0.4 0.4\n")

    stats = AnnotationStatisticsCalculator(_small_taxonomy()).compute(
        images_root=images, labels_root=labels
    )
    assert len(stats.class_distribution) == 3
    counts = {e.class_name: e.count for e in stats.class_distribution}
    assert counts == {"laptop": 1, "mouse": 0, "tablet": 0}


def test_missing_classes_reported(tmp_path: Path):
    """Classes with zero instances are reported as missing."""
    images = tmp_path / "images"
    labels = tmp_path / "labels"
    _img(images / "laptop_field_000001.jpg")
    (labels).mkdir(parents=True, exist_ok=True)
    (labels / "laptop_field_000001.txt").write_text("0 0.5 0.5 0.4 0.4\n")

    stats = AnnotationStatisticsCalculator(_small_taxonomy()).compute(
        images_root=images, labels_root=labels
    )
    assert stats.missing_classes == ("mouse", "tablet")


def test_annotation_completeness_and_orphans(tmp_path: Path):
    """Completeness reflects labelled images; orphans/gaps are surfaced."""
    images = tmp_path / "images"
    labels = tmp_path / "labels"
    labels.mkdir(parents=True, exist_ok=True)
    _img(images / "laptop_field_000001.jpg")
    (labels / "laptop_field_000001.txt").write_text("0 0.5 0.5 0.4 0.4\n")
    _img(images / "mouse_field_000001.jpg")  # image without a label
    (labels / "ghost.txt").write_text("1 0.5 0.5 0.2 0.2\n")  # orphan label

    stats = AnnotationStatisticsCalculator(_small_taxonomy()).compute(
        images_root=images, labels_root=labels
    )
    assert stats.total_images == 2
    assert stats.total_labelled_images == 1
    assert stats.annotation_completeness == 0.5
    assert stats.images_without_labels == ("mouse_field_000001.jpg",)
    assert stats.orphan_labels == ("ghost.txt",)


def test_bounding_box_stats(tmp_path: Path):
    """Bounding-box geometry is measured across all label files."""
    images = tmp_path / "images"
    labels = tmp_path / "labels"
    labels.mkdir(parents=True, exist_ok=True)
    _img(images / "laptop_field_000001.jpg")
    (labels / "laptop_field_000001.txt").write_text(
        "0 0.5 0.5 0.4 0.6\n1 0.5 0.5 0.2 0.2\n"
    )

    stats = AnnotationStatisticsCalculator(_small_taxonomy()).compute(
        images_root=images, labels_root=labels
    )
    assert stats.total_boxes == 2
    bbox = stats.bounding_box_stats
    assert bbox is not None
    assert bbox.total_boxes == 2
    assert bbox.min_width == 0.2
    assert bbox.max_width == 0.4
    assert bbox.max_area == 0.24  # 0.4 * 0.6


def test_no_boxes_yields_null_bbox_stats(tmp_path: Path):
    """A dataset with images but no labels has no box statistics."""
    images = tmp_path / "images"
    labels = tmp_path / "labels"
    labels.mkdir(parents=True, exist_ok=True)
    _img(images / "laptop_field_000001.jpg")

    stats = AnnotationStatisticsCalculator(_small_taxonomy()).compute(
        images_root=images, labels_root=labels
    )
    assert stats.bounding_box_stats is None
    assert stats.total_boxes == 0


def test_annotation_statistics_to_dict_shape(tmp_path: Path):
    """The serialised statistics carry all PART 4 sections."""
    images = tmp_path / "images"
    labels = tmp_path / "labels"
    labels.mkdir(parents=True, exist_ok=True)
    _img(images / "laptop_field_000001.jpg")
    (labels / "laptop_field_000001.txt").write_text("0 0.5 0.5 0.4 0.4\n")

    payload = annotation_statistics_to_dict(
        AnnotationStatisticsCalculator(_small_taxonomy()).compute(
            images_root=images, labels_root=labels
        )
    )
    assert set(payload) >= {
        "taxonomy_version",
        "num_classes",
        "total_images",
        "total_boxes",
        "annotation_completeness",
        "class_distribution",
        "missing_classes",
        "images_without_labels",
        "orphan_labels",
        "bounding_box_stats",
    }
