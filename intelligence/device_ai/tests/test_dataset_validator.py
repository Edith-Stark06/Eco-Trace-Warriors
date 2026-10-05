"""Tests for YOLO annotation parsing and validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from device_ai.dataset.validator import (
    AnnotationValidator,
    parse_yolo_line,
)


def test_parse_valid_yolo_line():
    """A well-formed line parses into the expected box."""
    box = parse_yolo_line("2 0.5 0.4 0.3 0.2")
    assert box.class_id == 2
    assert box.x_center == 0.5
    assert box.height == 0.2


def test_parse_rejects_wrong_field_count():
    """A line without exactly five fields raises ValueError."""
    with pytest.raises(ValueError):
        parse_yolo_line("0 0.5 0.5 0.5")


def test_parse_rejects_non_numeric():
    """A non-numeric coordinate raises ValueError."""
    with pytest.raises(ValueError):
        parse_yolo_line("0 x 0.5 0.5 0.5")


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_validate_clean_dataset(tmp_path: Path):
    """A matching image/label pair with a valid box reports no issues."""
    from PIL import Image

    images = tmp_path / "images"
    labels = tmp_path / "labels"
    images.mkdir()
    Image.new("RGB", (32, 32), (10, 20, 30)).save(images / "a.png")
    _write(labels / "a.txt", "0 0.5 0.5 0.4 0.4\n")

    report = AnnotationValidator(num_classes=3).validate(
        images_root=images, labels_root=labels
    )
    assert report.is_valid is True
    assert report.total_boxes == 1
    assert report.class_counts == {0: 1}


def test_validate_reports_missing_and_orphan(tmp_path: Path):
    """An image without a label and a label without an image are both flagged."""
    from PIL import Image

    images = tmp_path / "images"
    labels = tmp_path / "labels"
    images.mkdir()
    labels.mkdir()
    Image.new("RGB", (32, 32), (10, 20, 30)).save(images / "a.png")
    _write(labels / "b.txt", "0 0.5 0.5 0.4 0.4\n")

    report = AnnotationValidator().validate(images_root=images, labels_root=labels)
    assert "a.png" in report.images_without_labels
    assert "b.txt" in report.labels_without_images
    codes = {issue.code for issue in report.issues}
    assert {"MISSING_LABEL", "ORPHAN_LABEL"} <= codes


def test_validate_flags_out_of_range_and_class(tmp_path: Path):
    """Out-of-range coordinates and class ids surface as distinct issues."""
    from PIL import Image

    images = tmp_path / "images"
    labels = tmp_path / "labels"
    images.mkdir()
    Image.new("RGB", (32, 32), (10, 20, 30)).save(images / "a.png")
    _write(labels / "a.txt", "9 1.5 0.5 0.4 0.4\n")

    report = AnnotationValidator(num_classes=3).validate(
        images_root=images, labels_root=labels
    )
    codes = {issue.code for issue in report.issues}
    assert "COORD_OUT_OF_RANGE" in codes
    assert "CLASS_ID_OUT_OF_RANGE" in codes
    assert report.is_valid is False


def test_validate_flags_malformed_line(tmp_path: Path):
    """A malformed line is recorded but does not hide subsequent valid lines."""
    from PIL import Image

    images = tmp_path / "images"
    labels = tmp_path / "labels"
    images.mkdir()
    Image.new("RGB", (32, 32), (10, 20, 30)).save(images / "a.png")
    _write(labels / "a.txt", "garbage line\n0 0.5 0.5 0.4 0.4\n")

    report = AnnotationValidator().validate(images_root=images, labels_root=labels)
    codes = {issue.code for issue in report.issues}
    assert "MALFORMED_LINE" in codes
    assert report.total_boxes == 1  # the valid line still parsed


def test_validate_flags_non_positive_size(tmp_path: Path):
    """A zero-width box is flagged as a non-positive size."""
    from PIL import Image

    images = tmp_path / "images"
    labels = tmp_path / "labels"
    images.mkdir()
    Image.new("RGB", (32, 32), (10, 20, 30)).save(images / "a.png")
    _write(labels / "a.txt", "0 0.5 0.5 0.0 0.4\n")

    report = AnnotationValidator().validate(images_root=images, labels_root=labels)
    codes = {issue.code for issue in report.issues}
    assert "NON_POSITIVE_SIZE" in codes
