"""Tests for image-structural validation (Sprint P4.1.2, PART 2)."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from device_ai.configs.settings import Settings
from device_ai.dataset.image_validation import (
    ImageValidator,
    image_validation_to_dict,
)


def _img(path: Path, size: tuple[int, int] = (128, 96), colour=(120, 120, 120)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, colour).save(path)


def _validator(**kwargs) -> ImageValidator:
    return ImageValidator(Settings(), **kwargs)


def test_clean_directory_is_valid(tmp_path: Path):
    """A directory of well-formed images produces no issues."""
    root = tmp_path / "raw"
    _img(root / "laptop_field_000001.jpg")
    _img(root / "mouse_field_000001.png", (64, 64))

    report = _validator().validate(images_root=root)
    assert report.is_valid
    assert report.total_images == 2
    assert report.issues == ()


def test_unsupported_extension_is_flagged(tmp_path: Path):
    """Non-image files are reported and excluded from the image count."""
    root = tmp_path / "raw"
    _img(root / "laptop_field_000001.jpg")
    (root / "notes.txt").write_text("not an image")

    report = _validator().validate(images_root=root)
    assert "notes.txt" in report.unsupported_extensions
    assert report.total_images == 1
    assert any(i.code == "UNSUPPORTED_EXTENSION" for i in report.issues)


def test_undersized_image_is_flagged(tmp_path: Path):
    """Images below the minimum dimension are reported."""
    root = tmp_path / "raw"
    _img(root / "tiny.jpg", (16, 16))

    report = _validator().validate(images_root=root)
    assert "tiny.jpg" in report.undersized
    assert any(i.code == "RESOLUTION_TOO_SMALL" for i in report.issues)


def test_oversized_resolution_is_flagged(tmp_path: Path):
    """Images above the maximum dimension are reported."""
    root = tmp_path / "raw"
    _img(root / "huge.jpg", (256, 256))
    # A tight max makes a normal image "oversized" without allocating a 12k image.
    report = ImageValidator(Settings(max_image_dimension=128)).validate(
        images_root=root
    )
    assert "huge.jpg" in report.oversized_resolution
    assert any(i.code == "RESOLUTION_TOO_LARGE" for i in report.issues)


def test_invalid_aspect_ratio_is_flagged(tmp_path: Path):
    """Extreme aspect ratios outside the configured bounds are reported."""
    root = tmp_path / "raw"
    _img(root / "banner.jpg", (1000, 50))

    report = _validator().validate(images_root=root)
    assert "banner.jpg" in report.invalid_aspect_ratio
    assert any(i.code == "INVALID_ASPECT_RATIO" for i in report.issues)


def test_custom_aspect_ratio_bounds(tmp_path: Path):
    """Aspect-ratio bounds are injectable without touching settings."""
    root = tmp_path / "raw"
    _img(root / "wide.jpg", (200, 100))  # ratio 2.0

    strict = _validator(max_aspect_ratio=1.5).validate(images_root=root)
    lenient = _validator(max_aspect_ratio=3.0).validate(images_root=root)
    assert "wide.jpg" in strict.invalid_aspect_ratio
    assert lenient.invalid_aspect_ratio == ()


def test_oversized_file_is_flagged(tmp_path: Path):
    """Files exceeding the byte-size limit are reported."""
    root = tmp_path / "raw"
    _img(root / "laptop_field_000001.jpg")
    report = ImageValidator(Settings(max_file_size=1)).validate(images_root=root)
    assert "laptop_field_000001.jpg" in report.oversized_files
    assert any(i.code == "FILE_TOO_LARGE" for i in report.issues)


def test_duplicate_filenames_are_flagged(tmp_path: Path):
    """The same bare filename at two paths is reported for both."""
    root = tmp_path / "raw"
    _img(root / "laptop_field_000001.jpg", (128, 96), (10, 20, 30))
    _img(root / "sub" / "laptop_field_000001.jpg", (128, 96), (200, 180, 160))

    report = _validator().validate(images_root=root)
    assert "laptop_field_000001.jpg" in report.duplicate_filenames
    dup_issues = [i for i in report.issues if i.code == "DUPLICATE_FILENAME"]
    assert len(dup_issues) == 2


def test_duplicate_hashes_are_flagged(tmp_path: Path):
    """Byte-identical images are reported as content duplicates."""
    root = tmp_path / "raw"
    _img(root / "a.jpg", (128, 96), (10, 20, 30))
    _img(root / "sub" / "b.jpg", (128, 96), (10, 20, 30))

    report = _validator().validate(images_root=root)
    assert report.duplicate_hashes  # the later of the two is flagged
    assert any(i.code == "DUPLICATE_HASH" for i in report.issues)


def test_missing_root_yields_empty_report(tmp_path: Path):
    """A non-existent images root produces a valid, empty report."""
    report = _validator().validate(images_root=tmp_path / "does_not_exist")
    assert report.total_images == 0
    assert report.total_files_scanned == 0
    assert report.is_valid


def test_to_dict_summary_counts(tmp_path: Path):
    """The serialised report exposes a summary with per-check counts."""
    root = tmp_path / "raw"
    _img(root / "tiny.jpg", (16, 16))
    (root / "notes.txt").write_text("x")

    payload = image_validation_to_dict(_validator().validate(images_root=root))
    assert payload["is_valid"] is False
    assert payload["summary"]["undersized"] == 1
    assert payload["summary"]["unsupported_extensions"] == 1
    assert payload["summary"]["total_issues"] >= 2
