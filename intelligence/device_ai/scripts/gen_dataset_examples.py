"""Generate illustrative dataset pipeline artifacts for docs/examples/dataset.

Renders metadata, statistics, and a validation report from a small **synthetic**
dataset — five deterministic PNG images built from fixed arithmetic patterns (no
randomness) so every output is byte-stable. No real dataset is downloaded or
scraped: the images are procedurally generated and combined with an injected
fixed clock so hashes, timestamps, and metrics are reproducible.

The synthetic set is chosen to exercise the pipeline rather than to look pretty:

* four device images, each a **sinusoidal grating** at a distinct orientation
  and spatial frequency (so their perceptual hashes are pairwise distinct),
  optionally modulated by a **fine texture** (so the variance-of-Laplacian
  carries a real *sharp* vs *low-detail* signal), with brightness tuned per
  image so one reads as "bright" and one low-detail image reads as "blurry"; and
* one exact **byte-copy** of the first image — so the structural validator has a
  ``DUPLICATE_HASH`` issue to report and the duplicate detector folds exactly one
  duplicate group into the statistics (no spurious near-duplicates).

At runtime the equivalent files are written under the gitignored ``datasets/``
tree by :class:`~device_ai.dataset.service.DatasetService` methods.

Usage (from ``intelligence/`` with ``PYTHONPATH=.``)::

    python -m device_ai.scripts.gen_dataset_examples
"""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from device_ai.configs.settings import Settings
from device_ai.dataset.duplicates import DuplicateDetector
from device_ai.dataset.image_validation import (
    ImageValidator,
    image_validation_to_dict,
)
from device_ai.dataset.metadata import (
    MetadataGenerator,
    build_metadata_document,
)
from device_ai.dataset.statistics import StatisticsCalculator, statistics_to_dict

_FIXED_CLOCK = datetime(2026, 1, 15, 14, 30, 0, tzinfo=UTC)
_EXAMPLES_DIR = Path(__file__).resolve().parents[1] / "docs" / "examples" / "dataset"


def _fine_texture(
    height: int, width: int, amplitude: float, cell: int
) -> NDArray[np.float64]:
    """Return a zero-mean fine checkerboard, giving high-frequency detail.

    A small-cell checker has a large second derivative, so adding it lifts the
    variance-of-Laplacian (the *sharpness* metric) without shifting the mean
    brightness or the low-frequency structure the perceptual hashes key on.
    """
    ys, xs = np.mgrid[0:height, 0:width]
    checker = ((xs // cell) + (ys // cell)) % 2  # 0/1
    texture: NDArray[np.float64] = (checker.astype(np.float64) - 0.5) * 2.0 * amplitude
    return texture


def _grating(
    size: tuple[int, int],
    *,
    mean: float,
    contrast: float,
    angle_deg: float,
    cycles: float,
    texture: float = 0.0,
    cell: int = 3,
) -> Image.Image:
    """Return a deterministic sinusoidal grating with a distinct orientation.

    Varying ``angle_deg`` and ``cycles`` per image fills the 8×8 aHash/dHash
    thumbnail (and the pHash DCT block) with pairwise-distinct low-frequency
    structure, so distinct images are never mistaken for near-duplicates. The
    optional fine ``texture`` raises the sharpness metric without disturbing the
    grating's low-frequency fingerprint.

    Args:
        size: ``(width, height)`` of the output image.
        mean: Mean luminance in ``[0, 255]`` (controls dark/bright flags).
        contrast: Peak grating amplitude around ``mean``.
        angle_deg: Orientation of the grating in degrees.
        cycles: Number of sinusoid cycles across the image diagonal.
        texture: Amplitude of the optional fine checkerboard overlay (0 = none).
        cell: Cell size of the fine texture, in pixels.
    """
    width, height = size
    ys, xs = np.mgrid[0:height, 0:width]
    theta = np.deg2rad(angle_deg)
    # Project pixel coordinates onto the grating direction, normalised to [0, 1].
    projection = (np.cos(theta) * xs / width) + (np.sin(theta) * ys / height)
    base = mean + contrast * np.sin(2.0 * np.pi * cycles * projection)
    if texture:
        base = base + _fine_texture(height, width, texture, cell)
    clipped = np.clip(base, 0, 255).astype(np.uint8)
    return Image.fromarray(np.stack([clipped] * 3, axis=-1), mode="RGB")


def _build_dataset(images_root: Path) -> None:
    """Populate ``images_root`` with the deterministic synthetic images."""
    images_root.mkdir(parents=True, exist_ok=True)

    # Sharp, mid-tone grating (0°) + fine texture — passes every check.
    laptop = images_root / "laptop_field_000001.png"
    _grating((800, 600), mean=135, contrast=55, angle_deg=0, cycles=4, texture=45).save(
        laptop
    )

    # Sharp, darker grating (60°) + fine texture — also clean.
    _grating(
        (640, 480), mean=105, contrast=45, angle_deg=60, cycles=6, texture=40
    ).save(images_root / "smartphone_lab_000042.png")

    # Sharp but very bright grating (120°) + light texture — flagged "bright".
    _grating(
        (1920, 1080), mean=238, contrast=14, angle_deg=120, cycles=3, texture=6
    ).save(images_root / "tablet_donor_000003.png")

    # Low-detail smooth grating (30°, no texture) — flagged "blurry".
    _grating((1024, 768), mean=150, contrast=55, angle_deg=30, cycles=2).save(
        images_root / "monitor_ewaste_000017.png"
    )

    # Exact byte-copy of the first image — the structural validator reports a
    # DUPLICATE_HASH and the duplicate detector folds exactly one group in.
    shutil.copyfile(laptop, images_root / "laptop_field_000001_copy.png")


def _write_json(path: Path, document: dict[str, object]) -> None:
    """Write ``document`` as pretty, key-sorted, newline-terminated JSON."""
    path.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def main() -> None:
    """Generate the example dataset artifacts."""
    _EXAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    settings = Settings()

    with TemporaryDirectory() as tmpdir:
        images_root = Path(tmpdir) / "images"
        _build_dataset(images_root)

        # PART 1/4 — per-image metadata + quality metrics.
        records = MetadataGenerator.from_settings(settings).analyze_directory(
            images_root
        )
        metadata_doc = build_metadata_document(
            records,
            source="docs/examples/dataset (synthetic)",
            generated_at=_FIXED_CLOCK,
        )
        _write_json(_EXAMPLES_DIR / "metadata.json", metadata_doc)

        # PART 4 — aggregate statistics, with the duplicate group folded in.
        duplicates = DuplicateDetector.from_settings(settings).detect(records)
        stats = StatisticsCalculator().compute(records, duplicates=duplicates)
        _write_json(_EXAMPLES_DIR / "statistics.json", statistics_to_dict(stats))

        # PART 2 — structural validation (surfaces the DUPLICATE_HASH issue).
        report = ImageValidator(settings).validate(images_root=images_root)
        _write_json(
            _EXAMPLES_DIR / "validation_report.json", image_validation_to_dict(report)
        )

    print(f"Wrote example dataset artifacts to {_EXAMPLES_DIR}")


if __name__ == "__main__":
    main()
