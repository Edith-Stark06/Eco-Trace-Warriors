"""Image manipulation utilities built on Pillow and OpenCV.

Functions here are reused by the preprocessing pipeline and (later) by
training/evaluation scripts, keeping the actual pixel operations in one
place so they never drift.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING

import numpy as np
from PIL import Image

if TYPE_CHECKING:
    from numpy.typing import NDArray


def _cv2() -> ModuleType:
    """Import OpenCV lazily.

    OpenCV is only required by the BGR/RGB conversion helpers used by future
    model adapters, not by the mock service hot path. Importing it lazily
    keeps the core service runnable with just Pillow + NumPy and avoids
    paying OpenCV's import cost unless a caller actually needs it.

    Returns:
        The imported ``cv2`` module.

    Raises:
        RuntimeError: If OpenCV is not installed.
    """
    try:
        import cv2  # noqa: PLC0415 - intentional lazy import
    except ImportError as exc:  # pragma: no cover - exercised only w/o opencv
        raise RuntimeError(
            "OpenCV (opencv-python-headless) is required for this operation. "
            "Install the model dependencies to enable it."
        ) from exc
    return cv2


def load_image_from_bytes(data: bytes) -> Image.Image:
    """Open an image from raw bytes.

    Args:
        data: Raw image bytes (JPEG/PNG/WebP).

    Returns:
        A Pillow :class:`Image.Image` in RGB mode.

    Raises:
        PIL.UnidentifiedImageError: If the data is not a valid image.
        ValueError: If the image cannot be converted to RGB.
    """
    img = Image.open(BytesIO(data))
    # Convert to RGB so downstream code never deals with palette/CMYK/etc.
    if img.mode != "RGB":
        img = img.convert("RGB")
    return img


def load_image_from_path(path: Path | str) -> Image.Image:
    """Open an image from a file path.

    Args:
        path: Filesystem path to an image file.

    Returns:
        A Pillow :class:`Image.Image` in RGB mode.

    Raises:
        FileNotFoundError: If the path does not exist.
        PIL.UnidentifiedImageError: If the file is not a valid image.
    """
    img = Image.open(path)
    if img.mode != "RGB":
        img = img.convert("RGB")
    return img


def pil_to_numpy(img: Image.Image) -> NDArray[np.uint8]:
    """Convert a Pillow image to a NumPy array (H, W, C) in RGB.

    Args:
        img: A Pillow image.

    Returns:
        A uint8 NumPy array of shape ``(height, width, 3)``.
    """
    return np.array(img, dtype=np.uint8)


def numpy_to_pil(arr: NDArray[np.uint8]) -> Image.Image:
    """Convert a NumPy array (H, W, C) RGB to a Pillow image.

    Args:
        arr: A uint8 array of shape ``(height, width, 3)`` in RGB order.

    Returns:
        A Pillow :class:`Image.Image`.
    """
    return Image.fromarray(arr, mode="RGB")


def pil_to_cv2(img: Image.Image) -> NDArray[np.uint8]:
    """Convert a Pillow image to an OpenCV-compatible NumPy array (BGR).

    Args:
        img: A Pillow image in RGB mode.

    Returns:
        A uint8 NumPy array of shape ``(height, width, 3)`` in BGR order.
    """
    cv2 = _cv2()
    rgb = pil_to_numpy(img)
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


def cv2_to_pil(arr: NDArray[np.uint8]) -> Image.Image:
    """Convert an OpenCV BGR array to a Pillow RGB image.

    Args:
        arr: A uint8 array of shape ``(height, width, 3)`` in BGR order.

    Returns:
        A Pillow :class:`Image.Image` in RGB mode.
    """
    cv2 = _cv2()
    rgb = cv2.cvtColor(arr, cv2.COLOR_BGR2RGB)
    return numpy_to_pil(rgb)


def resize_image(
    img: Image.Image,
    target_size: tuple[int, int],
    *,
    keep_aspect: bool = True,
) -> Image.Image:
    """Resize an image to the given dimensions.

    Args:
        img: The input image.
        target_size: Desired ``(width, height)`` in pixels.
        keep_aspect: If True, preserve the aspect ratio by inscribing the
            image into the target box. If False, stretch to fill exactly.

    Returns:
        The resized image.
    """
    if not keep_aspect:
        return img.resize(target_size, resample=Image.Resampling.LANCZOS)

    # Compute the inscribed dimensions preserving aspect ratio.
    orig_w, orig_h = img.size
    target_w, target_h = target_size
    scale = min(target_w / orig_w, target_h / orig_h)
    new_w = int(orig_w * scale)
    new_h = int(orig_h * scale)
    return img.resize((new_w, new_h), resample=Image.Resampling.LANCZOS)


def center_crop(img: Image.Image, crop_size: tuple[int, int]) -> Image.Image:
    """Crop the center region of an image.

    Args:
        img: The input image.
        crop_size: Desired ``(width, height)`` of the crop.

    Returns:
        The center-cropped image.

    Raises:
        ValueError: If the crop is larger than the input image.
    """
    w, h = img.size
    crop_w, crop_h = crop_size
    if crop_w > w or crop_h > h:
        raise ValueError(f"Crop size {crop_size} exceeds image size {(w, h)}")
    left = (w - crop_w) // 2
    top = (h - crop_h) // 2
    right = left + crop_w
    bottom = top + crop_h
    return img.crop((left, top, right, bottom))


def normalize_image(
    arr: NDArray[np.float32],
    mean: tuple[float, float, float] = (0.485, 0.456, 0.406),
    std: tuple[float, float, float] = (0.229, 0.224, 0.225),
) -> NDArray[np.float32]:
    """Normalize a float32 image array with channel-wise mean/std.

    ImageNet statistics are used by default, suitable for transfer learning
    from most vision models.

    Args:
        arr: A float32 array of shape ``(height, width, 3)`` with values in
            the range [0.0, 1.0].
        mean: Per-channel mean to subtract.
        std: Per-channel standard deviation to divide by.

    Returns:
        The normalized array of the same shape.
    """
    mean_arr = np.array(mean, dtype=np.float32).reshape(1, 1, 3)
    std_arr = np.array(std, dtype=np.float32).reshape(1, 1, 3)
    return (arr - mean_arr) / std_arr


def is_corrupted(data: bytes) -> bool:
    """Check if image bytes are corrupted.

    Attempts to fully decode the image to detect truncated or malformed
    files that would fail during actual inference.

    Args:
        data: Raw image bytes.

    Returns:
        ``True`` if the image cannot be loaded or decoded; ``False`` otherwise.
    """
    try:
        img = Image.open(BytesIO(data))
        img.load()  # force decode to catch truncated images
        return False
    except Exception:
        return True
