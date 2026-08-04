"""Deterministic image augmentation.

:class:`ImageAugmenter` produces new image variants from source images using
a small, well-understood set of label-preserving transforms implemented with
Pillow only (no training-time dependencies):

* ``hflip``      — horizontal mirror.
* ``rotate90``   — 90° clockwise rotation.
* ``brightness`` — fixed brightness gain.
* ``grayscale``  — luminance-preserving greyscale (kept in RGB mode).

Augmentation is offline (writes files to a destination directory) and
deterministic: the same input and operation set always yield identical
outputs, which keeps datasets reproducible. Geometric ops that change
orientation are flagged so callers can avoid them when bounding-box labels
must be preserved.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PIL import Image, ImageEnhance, UnidentifiedImageError

from .layout import list_image_paths
from .records import AugmentationResult

# Brightness multiplier applied by the ``brightness`` operation.
_BRIGHTNESS_FACTOR = 1.25

# Operations whose geometry changes and therefore invalidate YOLO boxes
# unless the labels are transformed in lock-step.
GEOMETRIC_OPERATIONS: frozenset[str] = frozenset({"rotate90"})


def _op_hflip(image: Image.Image) -> Image.Image:
    """Return a horizontally mirrored copy of ``image``."""
    return image.transpose(Image.Transpose.FLIP_LEFT_RIGHT)


def _op_rotate90(image: Image.Image) -> Image.Image:
    """Return ``image`` rotated 90° clockwise."""
    return image.transpose(Image.Transpose.ROTATE_270)


def _op_brightness(image: Image.Image) -> Image.Image:
    """Return ``image`` with a fixed brightness gain applied."""
    return ImageEnhance.Brightness(image).enhance(_BRIGHTNESS_FACTOR)


def _op_grayscale(image: Image.Image) -> Image.Image:
    """Return a greyscale version of ``image`` kept in RGB mode."""
    return image.convert("L").convert("RGB")


# Registry of available operations. Public so callers/tests can introspect.
OPERATIONS: dict[str, Callable[[Image.Image], Image.Image]] = {
    "hflip": _op_hflip,
    "rotate90": _op_rotate90,
    "brightness": _op_brightness,
    "grayscale": _op_grayscale,
}

# Default operation set: label-preserving transforms only.
DEFAULT_OPERATIONS: tuple[str, ...] = ("hflip", "brightness", "grayscale")


class ImageAugmenter:
    """Generate augmented image variants using deterministic transforms.

    Args:
        operations: Ordered operation names to apply per source image.
            Each name must be a key of :data:`OPERATIONS`.

    Raises:
        ValueError: If any operation name is unknown.
    """

    def __init__(self, operations: tuple[str, ...] = DEFAULT_OPERATIONS) -> None:
        unknown = [name for name in operations if name not in OPERATIONS]
        if unknown:
            raise ValueError(
                f"Unknown augmentation operation(s): {', '.join(unknown)}. "
                f"Available: {', '.join(sorted(OPERATIONS))}."
            )
        self._operations = operations

    @property
    def operations(self) -> tuple[str, ...]:
        """The operation names applied to each source image."""
        return self._operations

    def augment_image(self, image: Image.Image) -> dict[str, Image.Image]:
        """Apply every configured operation to a single image.

        Args:
            image: Source Pillow image (converted to RGB internally).

        Returns:
            Mapping of operation name → augmented image.
        """
        rgb = image.convert("RGB")
        return {name: OPERATIONS[name](rgb) for name in self._operations}

    def augment_directory(
        self,
        source_root: Path,
        destination: Path,
    ) -> AugmentationResult:
        """Augment every supported image beneath ``source_root``.

        Each variant is written to ``destination`` as
        ``<stem>__<operation>.png``. Unreadable source images are skipped.

        Args:
            source_root: Directory of source images (scanned recursively).
            destination: Directory to write augmented variants into (created
                if missing).

        Returns:
            An :class:`AugmentationResult` summarising the run.
        """
        destination.mkdir(parents=True, exist_ok=True)
        generated: list[str] = []
        source_count = 0

        for path in list_image_paths(source_root):
            try:
                with Image.open(path) as opened:
                    opened.load()
                    variants = self.augment_image(opened)
            except (UnidentifiedImageError, OSError, ValueError):
                continue
            source_count += 1
            for name, variant in variants.items():
                out_name = f"{path.stem}__{name}.png"
                out_path = destination / out_name
                variant.save(out_path, format="PNG")
                generated.append(out_name)

        return AugmentationResult(
            generated=tuple(sorted(generated)),
            source_count=source_count,
            operations=self._operations,
            destination=destination.as_posix(),
        )
