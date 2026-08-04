"""Deterministic image transforms shared by inference and (later) training.

Using the *same* transform code in training and inference avoids
train/serve skew (``docs/engineering/08_AI.md`` → Pipeline Separation). The
transforms here are intentionally model-agnostic building blocks; each
model adapter composes the ones it needs. EXIF metadata is stripped so no
user-identifying data flows downstream.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from PIL import Image, ImageOps

from ..utils.image_utils import (
    center_crop,
    normalize_image,
    pil_to_numpy,
    resize_image,
)


@dataclass(frozen=True, slots=True)
class PreprocessConfig:
    """Configuration for a preprocessing transform.

    Attributes:
        image_size: Target ``(width, height)`` after resize/crop.
        keep_aspect: Whether to preserve the aspect ratio when resizing.
        center_crop: Whether to center-crop to ``image_size`` after resizing.
        normalize: Whether to apply mean/std normalization.
    """

    image_size: tuple[int, int] = (224, 224)
    keep_aspect: bool = True
    center_crop: bool = True
    normalize: bool = True


def strip_exif(img: Image.Image) -> Image.Image:
    """Return a copy of the image with EXIF orientation applied and removed.

    Applying orientation first ensures pixels are upright; removing EXIF then
    guarantees no location/device metadata is retained.

    Args:
        img: The input image.

    Returns:
        An image with orientation normalised and metadata stripped.
    """
    # ``exif_transpose`` bakes the EXIF orientation into the pixels.
    upright = ImageOps.exif_transpose(img)
    clean = Image.new(upright.mode, upright.size)
    clean.putdata(list(upright.getdata()))
    return clean


def to_model_input(
    img: Image.Image,
    config: PreprocessConfig | None = None,
) -> NDArray[np.float32]:
    """Transform a Pillow image into a model-ready tensor-like array.

    The output layout is channels-first ``(C, H, W)`` float32, matching the
    convention used by PyTorch models the future adapters will load.

    Args:
        img: The input image (any size, RGB).
        config: Transform configuration; defaults to :class:`PreprocessConfig`.

    Returns:
        A float32 array of shape ``(3, H, W)`` ready to batch and feed to a
        model.
    """
    cfg = config or PreprocessConfig()

    processed = strip_exif(img)
    processed = resize_image(processed, cfg.image_size, keep_aspect=cfg.keep_aspect)
    if cfg.center_crop:
        # Only crop when the resized image is large enough on both axes.
        w, h = processed.size
        crop_w, crop_h = cfg.image_size
        if w >= crop_w and h >= crop_h:
            processed = center_crop(processed, cfg.image_size)

    arr = pil_to_numpy(processed).astype(np.float32) / 255.0
    if cfg.normalize:
        arr = normalize_image(arr)

    # HWC -> CHW for model consumption.
    return np.transpose(arr, (2, 0, 1)).copy()


def batch_to_model_input(
    images: list[Image.Image],
    config: PreprocessConfig | None = None,
) -> NDArray[np.float32]:
    """Transform a list of images into a single batched array.

    Args:
        images: Input images.
        config: Transform configuration applied to every image.

    Returns:
        A float32 array of shape ``(N, 3, H, W)``.

    Raises:
        ValueError: If ``images`` is empty.
    """
    if not images:
        raise ValueError("Cannot build a batch from an empty image list.")
    tensors = [to_model_input(img, config) for img in images]
    return np.stack(tensors, axis=0)
