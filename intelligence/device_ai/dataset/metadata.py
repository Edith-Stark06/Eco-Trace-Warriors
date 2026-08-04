"""Image quality metrics and per-image metadata generation.

Two responsibilities live here:

* **Quality metrics** — pure functions computing blur (variance of the
  Laplacian), brightness (mean luminance), and the resolution / corruption
  flags, then classifying them against injected
  :class:`~device_ai.dataset.records.QualityThresholds`.
* **Metadata generation** — :class:`MetadataGenerator` turns a directory of
  images into :class:`~device_ai.dataset.records.ImageRecord` objects and a
  serialisable metadata document.

Metrics use only Pillow + NumPy (Laplacian via a hand-rolled convolution) so
the dataset pipeline stays free of the heavier OpenCV dependency.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import numpy as np
from numpy.typing import NDArray
from PIL import Image, UnidentifiedImageError

from ..configs.settings import Settings
from .hashing import (
    average_hash,
    difference_hash,
    perceptual_hash,
    sha256_hash,
)
from .layout import list_image_paths, relative_path
from .records import (
    ImageRecord,
    PerceptualHashes,
    QualityMetrics,
    QualityThresholds,
)

# 3×3 discrete Laplacian kernel (4-neighbour) used for the blur metric.
_LAPLACIAN_KERNEL: NDArray[np.float64] = np.array(
    [[0.0, 1.0, 0.0], [1.0, -4.0, 1.0], [0.0, 1.0, 0.0]],
    dtype=np.float64,
)

# ITU-R BT.601 luma coefficients for perceptual brightness.
_LUMA_WEIGHTS: NDArray[np.float64] = np.array([0.299, 0.587, 0.114])


def thresholds_from_settings(settings: Settings) -> QualityThresholds:
    """Build :class:`QualityThresholds` from application settings.

    Args:
        settings: The active settings.

    Returns:
        The thresholds used to classify quality metrics.
    """
    return QualityThresholds(
        blur=settings.blur_threshold,
        dark=settings.brightness_dark_threshold,
        bright=settings.brightness_bright_threshold,
        min_dimension=settings.min_image_dimension,
    )


def _luminance(image: Image.Image) -> NDArray[np.float64]:
    """Return the luminance plane of an image as a float64 array."""
    rgb = np.asarray(image.convert("RGB"), dtype=np.float64)
    return rgb @ _LUMA_WEIGHTS


def brightness_score(image: Image.Image) -> float:
    """Return the mean luminance of an image in ``[0, 255]``.

    Args:
        image: Source Pillow image.

    Returns:
        Mean luminance rounded to two decimals.
    """
    return round(float(_luminance(image).mean()), 2)


def _convolve2d(plane: NDArray[np.float64]) -> NDArray[np.float64]:
    """Convolve a 2-D plane with the Laplacian kernel (edge-replicated).

    A compact, dependency-free ``'valid'``-style convolution over a
    zero-reflected border — sufficient for a global variance statistic.

    Args:
        plane: A 2-D luminance array.

    Returns:
        The convolved array (same shape as ``plane``).
    """
    padded = np.pad(plane, pad_width=1, mode="reflect")
    result = np.zeros_like(plane)
    for dy in range(3):
        for dx in range(3):
            weight = _LAPLACIAN_KERNEL[dy, dx]
            if weight != 0.0:
                result += (
                    weight * padded[dy : dy + plane.shape[0], dx : dx + plane.shape[1]]
                )
    return result


def blur_score(image: Image.Image) -> float:
    """Return the variance of the Laplacian; higher means sharper.

    Args:
        image: Source Pillow image.

    Returns:
        Variance-of-Laplacian rounded to two decimals.
    """
    plane = _luminance(image)
    if plane.size == 0:
        return 0.0
    laplacian = _convolve2d(plane)
    return round(float(laplacian.var()), 2)


def evaluate_quality(
    image: Image.Image | None,
    *,
    width: int,
    height: int,
    thresholds: QualityThresholds,
    corrupted: bool = False,
) -> QualityMetrics:
    """Compute quality metrics and derive flags for one image.

    Args:
        image: Decoded image, or ``None`` when corrupted.
        width: Image width in pixels (0 when corrupted).
        height: Image height in pixels (0 when corrupted).
        thresholds: Classification thresholds (injected).
        corrupted: Whether the image failed to decode.

    Returns:
        The populated :class:`QualityMetrics`.
    """
    if corrupted or image is None:
        return QualityMetrics(
            blur_score=0.0,
            brightness=0.0,
            is_blurry=False,
            is_dark=False,
            is_bright=False,
            is_low_resolution=False,
            is_corrupted=True,
            issues=("corrupted",),
        )

    blur = blur_score(image)
    brightness = brightness_score(image)
    is_blurry = blur < thresholds.blur
    is_dark = brightness < thresholds.dark
    is_bright = brightness > thresholds.bright
    is_low_res = min(width, height) < thresholds.min_dimension

    issues: list[str] = []
    if is_blurry:
        issues.append("blurry")
    if is_dark:
        issues.append("dark")
    if is_bright:
        issues.append("bright")
    if is_low_res:
        issues.append("low_resolution")

    return QualityMetrics(
        blur_score=blur,
        brightness=brightness,
        is_blurry=is_blurry,
        is_dark=is_dark,
        is_bright=is_bright,
        is_low_resolution=is_low_res,
        is_corrupted=False,
        issues=tuple(sorted(issues)),
    )


class MetadataGenerator:
    """Analyse images into :class:`ImageRecord` metadata.

    The generator decodes each file exactly once, then delegates to the
    hashing and quality helpers. Thresholds are injected so behaviour is
    fully configurable and testable.

    Args:
        thresholds: Quality classification thresholds.
    """

    def __init__(self, thresholds: QualityThresholds) -> None:
        self._thresholds = thresholds

    @classmethod
    def from_settings(cls, settings: Settings) -> MetadataGenerator:
        """Build a generator from application settings.

        Args:
            settings: The active settings.

        Returns:
            A configured :class:`MetadataGenerator`.
        """
        return cls(thresholds_from_settings(settings))

    def analyze_file(self, path: Path, *, root: Path) -> ImageRecord:
        """Analyse a single image file into an :class:`ImageRecord`.

        Decoding failures never raise: the record is returned with the
        ``corrupted`` flag set so batch analysis is resilient.

        Args:
            path: Absolute path of the image file.
            root: Root used to compute the stable relative path.

        Returns:
            The populated :class:`ImageRecord`.
        """
        data = path.read_bytes()
        rel = relative_path(path, root)
        sha = sha256_hash(data)

        try:
            with Image.open(path) as opened:
                opened.load()
                image = opened.convert("RGB")
                image_format = opened.format or ""
                mode = opened.mode
                width, height = opened.width, opened.height
        except (UnidentifiedImageError, OSError, ValueError):
            return ImageRecord(
                relative_path=rel,
                filename=path.name,
                image_format="",
                mode="",
                width=0,
                height=0,
                size_bytes=len(data),
                hashes=PerceptualHashes(sha256=sha, ahash="", dhash="", phash=""),
                quality=evaluate_quality(
                    None,
                    width=0,
                    height=0,
                    thresholds=self._thresholds,
                    corrupted=True,
                ),
            )

        hashes = PerceptualHashes(
            sha256=sha,
            ahash=average_hash(image),
            dhash=difference_hash(image),
            phash=perceptual_hash(image),
        )
        quality = evaluate_quality(
            image,
            width=width,
            height=height,
            thresholds=self._thresholds,
        )
        return ImageRecord(
            relative_path=rel,
            filename=path.name,
            image_format=image_format,
            mode=mode,
            width=width,
            height=height,
            size_bytes=len(data),
            hashes=hashes,
            quality=quality,
        )

    def analyze_directory(self, root: Path) -> list[ImageRecord]:
        """Analyse every supported image beneath ``root``.

        Args:
            root: Directory to scan recursively.

        Returns:
            One :class:`ImageRecord` per image, in sorted path order.
        """
        return [self.analyze_file(path, root=root) for path in list_image_paths(root)]


def record_to_dict(record: ImageRecord) -> dict[str, object]:
    """Convert an :class:`ImageRecord` into a JSON-serialisable dict.

    Args:
        record: The record to serialise.

    Returns:
        A primitive-only mapping mirroring the record's fields.
    """
    return {
        "relative_path": record.relative_path,
        "filename": record.filename,
        "format": record.image_format,
        "mode": record.mode,
        "width": record.width,
        "height": record.height,
        "megapixels": record.megapixels,
        "size_bytes": record.size_bytes,
        "hashes": {
            "sha256": record.hashes.sha256,
            "ahash": record.hashes.ahash,
            "dhash": record.hashes.dhash,
            "phash": record.hashes.phash,
        },
        "quality": {
            "blur_score": record.quality.blur_score,
            "brightness": record.quality.brightness,
            "is_blurry": record.quality.is_blurry,
            "is_dark": record.quality.is_dark,
            "is_bright": record.quality.is_bright,
            "is_low_resolution": record.quality.is_low_resolution,
            "is_corrupted": record.quality.is_corrupted,
            "issues": list(record.quality.issues),
        },
    }


def build_metadata_document(
    records: list[ImageRecord],
    *,
    source: str,
    generated_at: datetime,
) -> dict[str, object]:
    """Build the top-level metadata document for a set of records.

    Args:
        records: Analysed image records.
        source: Human-readable source identifier (e.g. the scanned path).
        generated_at: Timestamp to embed (injected for reproducibility).

    Returns:
        A JSON-serialisable metadata document.
    """
    return {
        "source": source,
        "generated_at": generated_at.isoformat(),
        "image_count": len(records),
        "images": [record_to_dict(record) for record in records],
    }
