"""Tests for image quality metrics and metadata generation."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from PIL import Image

from device_ai.dataset.metadata import (
    MetadataGenerator,
    blur_score,
    brightness_score,
    build_metadata_document,
    evaluate_quality,
    record_to_dict,
    thresholds_from_settings,
)
from device_ai.dataset.records import QualityThresholds

_THRESHOLDS = QualityThresholds(blur=100.0, dark=40.0, bright=220.0, min_dimension=32)


def _noise(seed: int, size=(96, 96)) -> Image.Image:
    rng = np.random.default_rng(seed)
    arr = rng.integers(0, 256, size=(size[1], size[0], 3), dtype=np.uint8)
    return Image.fromarray(arr, "RGB")


def test_brightness_of_black_and_white():
    """Brightness spans the full 0..255 range for black/white fills."""
    assert brightness_score(Image.new("RGB", (16, 16), (0, 0, 0))) == 0.0
    assert brightness_score(Image.new("RGB", (16, 16), (255, 255, 255))) == 255.0


def test_solid_image_has_zero_blur():
    """A flat image has no Laplacian response, hence zero variance."""
    assert blur_score(Image.new("RGB", (32, 32), (128, 128, 128))) == 0.0


def test_noise_image_is_sharper_than_solid():
    """A noisy image yields a far higher variance-of-Laplacian."""
    assert blur_score(_noise(3)) > blur_score(Image.new("RGB", (96, 96), (100, 0, 0)))


def test_evaluate_quality_flags_dark_image():
    """A near-black image trips the dark flag and reports the issue."""
    metrics = evaluate_quality(
        Image.new("RGB", (64, 64), (5, 5, 5)),
        width=64,
        height=64,
        thresholds=_THRESHOLDS,
    )
    assert metrics.is_dark is True
    assert "dark" in metrics.issues
    assert metrics.is_clean is False


def test_evaluate_quality_flags_low_resolution():
    """An image below the minimum dimension is flagged low-resolution."""
    metrics = evaluate_quality(
        _noise(1, size=(16, 16)),
        width=16,
        height=16,
        thresholds=_THRESHOLDS,
    )
    assert metrics.is_low_resolution is True
    assert "low_resolution" in metrics.issues


def test_evaluate_quality_corrupted_short_circuits():
    """A corrupted image is flagged and carries the single 'corrupted' issue."""
    metrics = evaluate_quality(
        None, width=0, height=0, thresholds=_THRESHOLDS, corrupted=True
    )
    assert metrics.is_corrupted is True
    assert metrics.issues == ("corrupted",)


def test_clean_image_has_no_issues():
    """A bright, sharp, adequately sized image trips no flags."""
    metrics = evaluate_quality(_noise(7), width=96, height=96, thresholds=_THRESHOLDS)
    assert metrics.is_clean is True
    assert metrics.issues == ()


def test_thresholds_from_settings(dataset_settings):
    """Thresholds are lifted straight from settings fields."""
    thresholds = thresholds_from_settings(dataset_settings)
    assert thresholds.blur == dataset_settings.blur_threshold
    assert thresholds.min_dimension == dataset_settings.min_image_dimension


def test_metadata_generator_analyzes_directory(tmp_path: Path):
    """The generator produces one record per image in sorted path order."""
    _noise(1).save(tmp_path / "b.png")
    _noise(2).save(tmp_path / "a.png")
    generator = MetadataGenerator(_THRESHOLDS)
    records = generator.analyze_directory(tmp_path)
    assert [r.relative_path for r in records] == ["a.png", "b.png"]
    assert all(len(r.hashes.sha256) == 64 for r in records)
    assert all(r.width == 96 for r in records)


def test_metadata_generator_survives_corrupted_file(tmp_path: Path):
    """A non-image file is recorded as corrupted rather than raising."""
    bad = tmp_path / "broken.png"
    bad.write_bytes(b"not a real png")
    generator = MetadataGenerator(_THRESHOLDS)
    record = generator.analyze_file(bad, root=tmp_path)
    assert record.quality.is_corrupted is True
    assert record.width == 0
    assert record.hashes.phash == ""


def test_record_to_dict_is_primitive(tmp_path: Path):
    """The serialised record contains only JSON-friendly primitives."""
    _noise(5).save(tmp_path / "x.png")
    generator = MetadataGenerator(_THRESHOLDS)
    record = generator.analyze_file(tmp_path / "x.png", root=tmp_path)
    payload = record_to_dict(record)
    assert payload["filename"] == "x.png"
    assert isinstance(payload["hashes"], dict)
    assert isinstance(payload["quality"]["issues"], list)


def test_build_metadata_document_embeds_timestamp(tmp_path: Path):
    """The document embeds the injected timestamp and image count."""
    _noise(5).save(tmp_path / "x.png")
    generator = MetadataGenerator(_THRESHOLDS)
    records = generator.analyze_directory(tmp_path)
    when = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
    document = build_metadata_document(records, source="raw", generated_at=when)
    assert document["source"] == "raw"
    assert document["generated_at"] == when.isoformat()
    assert document["image_count"] == 1
    assert len(document["images"]) == 1
