"""Perceptual and content hashing for duplicate detection.

Four fingerprints are produced per image:

* **SHA-256** — cryptographic hash of the raw bytes; identifies *exact*
  (byte-for-byte) duplicates.
* **aHash** (average hash) — 64-bit hash from thresholding an 8×8 greyscale
  thumbnail against its mean.
* **dHash** (difference hash) — 64-bit hash from horizontal gradients of a
  9×8 greyscale thumbnail.
* **pHash** (perceptual hash) — 64-bit hash from the low-frequency block of a
  32×32 DCT-II, robust to scaling and mild edits.

Perceptual hashes are compared with :func:`hamming_distance`; a small
distance implies visual similarity (near-duplicate). Implementations use only
Pillow and NumPy so the dataset hot-path has no OpenCV dependency.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from ..utils.hashing import hash_bytes

# Thumbnail edge used by aHash (``_AHASH_SIZE`` × ``_AHASH_SIZE``).
_AHASH_SIZE = 8
# dHash compares each pixel with its right neighbour, needing one extra column.
_DHASH_SIZE = 8
# pHash works on a larger thumbnail then keeps the top-left DCT block.
_PHASH_IMAGE_SIZE = 32
_PHASH_BLOCK = 8

# Number of hex characters in a 64-bit hash (16 nibbles).
_HASH_HEX_WIDTH = 16


def _to_grayscale_array(
    image: Image.Image, size: tuple[int, int]
) -> NDArray[np.float64]:
    """Return a resized greyscale image as a float64 array.

    Args:
        image: Source Pillow image.
        size: ``(width, height)`` to resize to before analysis.

    Returns:
        A float64 array of shape ``(height, width)``.
    """
    grey = image.convert("L").resize(size, Image.Resampling.LANCZOS)
    return np.asarray(grey, dtype=np.float64)


def _bits_to_hex(bits: NDArray[np.bool_]) -> str:
    """Pack a flat boolean array (MSB first) into a zero-padded hex string.

    Args:
        bits: A 1-D boolean array whose length is a multiple of four.

    Returns:
        The lower-case hexadecimal representation.
    """
    value = 0
    for bit in bits:
        value = (value << 1) | int(bit)
    width = max(_HASH_HEX_WIDTH, (bits.size + 3) // 4)
    return f"{value:0{width}x}"


def average_hash(image: Image.Image) -> str:
    """Compute the 64-bit average hash (aHash) of an image.

    Args:
        image: Source Pillow image.

    Returns:
        A 16-character hex string.
    """
    pixels = _to_grayscale_array(image, (_AHASH_SIZE, _AHASH_SIZE))
    bits = pixels > pixels.mean()
    return _bits_to_hex(bits.flatten())


def difference_hash(image: Image.Image) -> str:
    """Compute the 64-bit difference hash (dHash) of an image.

    Args:
        image: Source Pillow image.

    Returns:
        A 16-character hex string.
    """
    pixels = _to_grayscale_array(image, (_DHASH_SIZE + 1, _DHASH_SIZE))
    bits = pixels[:, 1:] > pixels[:, :-1]
    return _bits_to_hex(bits.flatten())


def _dct_1d(matrix: NDArray[np.float64]) -> NDArray[np.float64]:
    """Return the DCT-II of ``matrix`` along its last axis.

    A small, dependency-free DCT-II (matching SciPy's ``dct(norm=None)``)
    implemented via a cosine basis matrix — adequate for 32×32 pHash inputs.
    For output frequency ``f`` and input sample ``i`` the basis coefficient is
    ``cos(pi * (2i + 1) * f / (2n))``.

    Args:
        matrix: A 2-D array; the transform is applied row-wise.

    Returns:
        The transformed array of the same shape.
    """
    n = matrix.shape[-1]
    index = np.arange(n)
    # basis[f, i] with f the output frequency (rows) and i the input sample.
    basis = np.cos(np.pi * (2 * index[None, :] + 1) * index[:, None] / (2 * n))
    transformed: NDArray[np.float64] = matrix @ basis.T * 2.0
    return transformed


def perceptual_hash(image: Image.Image) -> str:
    """Compute the 64-bit perceptual hash (pHash) of an image.

    The image is reduced to greyscale, DCT-transformed, and the low-frequency
    ``8×8`` block (excluding the DC term for the threshold) is compared with
    its median.

    Args:
        image: Source Pillow image.

    Returns:
        A 16-character hex string.
    """
    pixels = _to_grayscale_array(image, (_PHASH_IMAGE_SIZE, _PHASH_IMAGE_SIZE))
    # 2-D DCT-II via two passes of the 1-D transform.
    dct = _dct_1d(_dct_1d(pixels).T).T
    block = dct[:_PHASH_BLOCK, :_PHASH_BLOCK]
    # Exclude the DC coefficient (0, 0) from the median so it does not swamp
    # the low-frequency statistics.
    median = np.median(block.flatten()[1:])
    bits = block > median
    return _bits_to_hex(bits.flatten())


def sha256_hash(data: bytes) -> str:
    """Return the SHA-256 hex digest of raw file bytes.

    Args:
        data: The raw image bytes.

    Returns:
        The 64-character hex digest.
    """
    return hash_bytes(data, algorithm="sha256")


def hamming_distance(hex_a: str, hex_b: str) -> int:
    """Return the Hamming distance between two equal-length hex hashes.

    Args:
        hex_a: First hash as a hex string.
        hex_b: Second hash as a hex string.

    Returns:
        The number of differing bits.

    Raises:
        ValueError: If the two hashes differ in length.
    """
    if len(hex_a) != len(hex_b):
        raise ValueError("Cannot compare hashes of differing length.")
    return bin(int(hex_a, 16) ^ int(hex_b, 16)).count("1")
