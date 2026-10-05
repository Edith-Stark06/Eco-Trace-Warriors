"""Tests for augmentation, import and layout helpers."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from device_ai.dataset.augmenter import (
    DEFAULT_OPERATIONS,
    GEOMETRIC_OPERATIONS,
    ImageAugmenter,
)
from device_ai.dataset.importer import DatasetImporter
from device_ai.dataset.layout import (
    DatasetLayout,
    label_path_for,
    list_image_paths,
    relative_path,
)


def _noise(seed: int, size=(48, 48)) -> Image.Image:
    rng = np.random.default_rng(seed)
    arr = rng.integers(0, 256, size=(size[1], size[0], 3), dtype=np.uint8)
    return Image.fromarray(arr, "RGB")


# --- Augmenter -------------------------------------------------------------


def test_augment_image_produces_one_variant_per_operation():
    """Each configured operation yields exactly one variant image."""
    augmenter = ImageAugmenter(("hflip", "grayscale"))
    variants = augmenter.augment_image(_noise(1))
    assert set(variants) == {"hflip", "grayscale"}


def test_hflip_is_a_horizontal_mirror():
    """The hflip variant equals a manual left-right flip."""
    image = _noise(2)
    variant = ImageAugmenter(("hflip",)).augment_image(image)["hflip"]
    expected = image.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    assert np.array_equal(np.asarray(variant), np.asarray(expected))


def test_augment_directory_writes_named_variants(tmp_path: Path):
    """Augmenting a directory writes ``<stem>__<op>.png`` for each variant."""
    src = tmp_path / "src"
    dest = tmp_path / "aug"
    src.mkdir()
    _noise(1).save(src / "a.png")
    result = ImageAugmenter(("hflip", "grayscale")).augment_directory(src, dest)
    assert result.source_count == 1
    assert result.num_generated == 2
    assert (dest / "a__hflip.png").exists()
    assert (dest / "a__grayscale.png").exists()


def test_default_operations_are_label_preserving():
    """The default operation set excludes geometry-changing transforms."""
    assert not (set(DEFAULT_OPERATIONS) & GEOMETRIC_OPERATIONS)


def test_unknown_operation_rejected():
    """An unknown operation name raises ValueError at construction."""
    with pytest.raises(ValueError):
        ImageAugmenter(("hflip", "solarize"))


# --- Importer --------------------------------------------------------------


def test_import_copies_and_preserves_structure(tmp_path: Path):
    """Import copies images into the destination, preserving sub-folders."""
    src = tmp_path / "src"
    dest = tmp_path / "raw"
    (src / "nested").mkdir(parents=True)
    _noise(1).save(src / "a.png")
    _noise(2).save(src / "nested" / "b.png")

    summary = DatasetImporter().import_directory(src, dest)
    assert summary.num_imported == 2
    assert (dest / "a.png").exists()
    assert (dest / "nested" / "b.png").exists()


def test_import_deduplicates_identical_bytes(tmp_path: Path):
    """Byte-identical images are imported once and the rest are skipped."""
    src = tmp_path / "src"
    dest = tmp_path / "raw"
    src.mkdir()
    _noise(1).save(src / "a.png")
    # exact byte copy
    (src / "copy.png").write_bytes((src / "a.png").read_bytes())

    summary = DatasetImporter().import_directory(src, dest, deduplicate=True)
    assert summary.num_imported == 1
    assert len(summary.skipped_duplicates) == 1


def test_import_skips_invalid_files(tmp_path: Path):
    """A non-decodable file is skipped and reported as invalid."""
    src = tmp_path / "src"
    dest = tmp_path / "raw"
    src.mkdir()
    _noise(1).save(src / "a.png")
    (src / "broken.png").write_bytes(b"nonsense")

    summary = DatasetImporter().import_directory(src, dest)
    assert summary.num_imported == 1
    assert "broken.png" in summary.skipped_invalid


def test_import_is_idempotent(tmp_path: Path):
    """Re-importing into a populated destination adds nothing new."""
    src = tmp_path / "src"
    dest = tmp_path / "raw"
    src.mkdir()
    _noise(1).save(src / "a.png")
    DatasetImporter().import_directory(src, dest)
    second = DatasetImporter().import_directory(src, dest)
    assert second.num_imported == 0


# --- Layout ----------------------------------------------------------------


def test_layout_ensure_creates_all_subdirs(dataset_settings):
    """``ensure`` creates the full managed sub-directory tree."""
    layout = DatasetLayout.from_settings(dataset_settings).ensure()
    for path in layout.all_subdirs():
        assert path.is_dir()
    assert layout.raw.name == "raw"
    assert layout.exports.name == "exports"


def test_layout_subdir_rejects_unknown_name(dataset_settings):
    """Requesting an unknown sub-directory name raises ValueError."""
    layout = DatasetLayout.from_settings(dataset_settings)
    with pytest.raises(ValueError):
        layout.subdir("nonexistent")


def test_list_image_paths_is_sorted_and_filtered(tmp_path: Path):
    """Only supported extensions are returned, in sorted order."""
    _noise(1).save(tmp_path / "b.png")
    _noise(2).save(tmp_path / "a.png")
    (tmp_path / "notes.txt").write_text("ignore me", encoding="utf-8")
    paths = list_image_paths(tmp_path)
    assert [p.name for p in paths] == ["a.png", "b.png"]


def test_relative_path_falls_back_to_name(tmp_path: Path):
    """A path outside the root falls back to the bare file name."""
    assert relative_path(Path("/elsewhere/x.png"), tmp_path) == "x.png"


def test_label_path_mirrors_image_path(tmp_path: Path):
    """The label path mirrors the image's relative location with .txt."""
    images = tmp_path / "images"
    labels = tmp_path / "labels"
    label = label_path_for(images / "sub" / "a.png", images, labels)
    assert label == labels / "sub" / "a.txt"
