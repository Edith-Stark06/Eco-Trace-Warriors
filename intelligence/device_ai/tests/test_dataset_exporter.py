"""Tests for dataset export to YOLO, COCO and Pascal VOC."""

from __future__ import annotations

import json
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest
from PIL import Image

from device_ai.dataset.exporter import DatasetExporter, yolo_to_corners
from device_ai.dataset.metadata import MetadataGenerator
from device_ai.dataset.records import QualityThresholds
from device_ai.dataset.validator import YoloBox
from device_ai.exceptions import UnsupportedExportFormatError

_THRESHOLDS = QualityThresholds(blur=100.0, dark=40.0, bright=220.0, min_dimension=8)


def _dataset(tmp_path: Path) -> tuple[Path, Path, list]:
    """Build a tiny image+label dataset and return (images, labels, records)."""
    images = tmp_path / "images"
    labels = tmp_path / "labels"
    images.mkdir()
    labels.mkdir()
    Image.new("RGB", (100, 100), (30, 60, 90)).save(images / "a.png")
    (labels / "a.txt").write_text("0 0.5 0.5 0.4 0.2\n", encoding="utf-8")
    records = MetadataGenerator(_THRESHOLDS).analyze_directory(images)
    return images, labels, records


def test_yolo_to_corners_centres_box():
    """A centred normalised box maps to the expected pixel corner + size."""
    box = YoloBox(class_id=0, x_center=0.5, y_center=0.5, width=0.4, height=0.2)
    x, y, w, h = yolo_to_corners(box, width=100, height=100)
    assert (x, y, w, h) == (30.0, 40.0, 40.0, 20.0)


def test_export_yolo_writes_images_labels_and_manifest(tmp_path: Path):
    """YOLO export produces images/, labels/ and a data.yaml manifest."""
    images, labels, records = _dataset(tmp_path)
    dest = tmp_path / "out"
    result = DatasetExporter(class_names=["battery"]).export(
        export_format="yolo",
        records=records,
        images_root=images,
        labels_root=labels,
        destination=dest,
    )
    assert result.export_format == "yolo"
    assert (dest / "data.yaml").exists()
    assert (dest / "images" / "a.png").exists()
    assert (dest / "labels" / "a.txt").exists()
    assert "battery" in (dest / "data.yaml").read_text(encoding="utf-8")


def test_export_coco_is_valid_json(tmp_path: Path):
    """COCO export writes a single annotations.json with pixel bboxes."""
    images, labels, records = _dataset(tmp_path)
    dest = tmp_path / "out"
    DatasetExporter().export(
        export_format="coco",
        records=records,
        images_root=images,
        labels_root=labels,
        destination=dest,
    )
    document = json.loads((dest / "annotations.json").read_text(encoding="utf-8"))
    assert len(document["images"]) == 1
    assert len(document["annotations"]) == 1
    assert document["annotations"][0]["bbox"] == [30.0, 40.0, 40.0, 20.0]
    assert document["categories"][0]["id"] == 0


def test_export_voc_writes_wellformed_xml(tmp_path: Path):
    """VOC export writes one parseable XML per image under Annotations/."""
    images, labels, records = _dataset(tmp_path)
    dest = tmp_path / "out"
    DatasetExporter(class_names=["battery"]).export(
        export_format="voc",
        records=records,
        images_root=images,
        labels_root=labels,
        destination=dest,
    )
    xml_path = dest / "Annotations" / "a.xml"
    assert xml_path.exists()
    root = ET.fromstring(xml_path.read_bytes())
    assert root.tag == "annotation"
    assert root.findtext("object/name") == "battery"
    assert root.findtext("size/width") == "100"


def test_export_rejects_unknown_format(tmp_path: Path):
    """An unsupported format raises UnsupportedExportFormatError."""
    images, labels, records = _dataset(tmp_path)
    with pytest.raises(UnsupportedExportFormatError):
        DatasetExporter().export(
            export_format="tfrecord",
            records=records,
            images_root=images,
            labels_root=labels,
            destination=tmp_path / "out",
        )
