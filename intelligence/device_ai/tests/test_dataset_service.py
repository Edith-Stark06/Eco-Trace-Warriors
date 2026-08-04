"""Integration test exercising the full DatasetService orchestration."""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
from PIL import Image

from device_ai.dataset.service import DatasetService


def _fixed_clock():
    return datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)


def _seed_raw(settings) -> None:
    """Write a small raw dataset (with one exact duplicate) plus a label."""
    raw = settings.dataset_dir / "raw"
    labels = settings.dataset_dir / "labels"
    raw.mkdir(parents=True, exist_ok=True)
    labels.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(1)
    arr = rng.integers(0, 256, size=(64, 64, 3), dtype=np.uint8)
    Image.fromarray(arr, "RGB").save(raw / "a.png")
    (raw / "dup.png").write_bytes((raw / "a.png").read_bytes())  # exact duplicate
    rng2 = np.random.default_rng(2)
    Image.fromarray(
        rng2.integers(0, 256, size=(64, 64, 3), dtype=np.uint8), "RGB"
    ).save(raw / "b.png")
    (labels / "a.txt").write_text("0 0.5 0.5 0.4 0.4\n", encoding="utf-8")


def test_service_full_pipeline(dataset_settings):
    """analyze → dedup → validate → split → augment → export → version → report."""
    _seed_raw(dataset_settings)
    service = DatasetService(dataset_settings, clock=_fixed_clock)

    records = service.analyze()
    assert len(records) == 3

    duplicates = service.detect_duplicates(records)
    assert duplicates.num_duplicates == 1

    annotations = service.validate_annotations()
    assert annotations.total_boxes == 1

    metadata_path = service.generate_metadata(records, source="raw")
    assert metadata_path.exists()

    assignment = service.split(records, ratios=(0.34, 0.33, 0.33), seed=0)
    assert sum(assignment.counts.values()) == 3
    assert (dataset_settings.dataset_dir / "splits" / "split.json").exists()

    augmentation = service.augment(operations=("hflip",))
    assert augmentation.num_generated == 3

    for fmt in ("yolo", "coco", "voc"):
        result = service.export(export_format=fmt, records=records)
        assert result.file_count >= 1
        assert (dataset_settings.dataset_dir / "exports" / fmt).is_dir()

    version = service.create_version(records, note="integration")
    assert version.version == "v1"
    assert version.image_count == 3

    document, json_path, html_path = service.build_report()
    assert json_path.exists()
    assert html_path.exists()
    assert document["statistics"]["total_images"] == 3


def test_service_report_timestamp_is_injected(dataset_settings):
    """The injected clock drives reproducible report timestamps."""
    _seed_raw(dataset_settings)
    service = DatasetService(dataset_settings, clock=_fixed_clock)
    document, _json_path, _html_path = service.build_report()
    assert document["generated_at"] == _fixed_clock().isoformat()
