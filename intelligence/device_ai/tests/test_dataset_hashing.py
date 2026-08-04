"""Tests for perceptual/content hashing used in duplicate detection."""

import numpy as np
import pytest
from PIL import Image

from device_ai.dataset.hashing import (
    average_hash,
    difference_hash,
    hamming_distance,
    perceptual_hash,
    sha256_hash,
)


def _noise_image(seed: int, size=(200, 200)) -> Image.Image:
    rng = np.random.default_rng(seed)
    arr = rng.integers(0, 256, size=(size[1], size[0], 3), dtype=np.uint8)
    return Image.fromarray(arr, "RGB")


def test_hashes_are_16_hex_chars():
    """Each perceptual hash is a 64-bit (16 hex char) value."""
    image = _noise_image(1)
    for fn in (average_hash, difference_hash, perceptual_hash):
        value = fn(image)
        assert len(value) == 16
        int(value, 16)  # parses as hex


def test_sha256_matches_known_digest():
    """SHA-256 of known bytes matches the reference digest."""
    # echo -n "" | sha256sum
    empty = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    assert sha256_hash(b"") == empty


def test_identical_images_have_zero_distance():
    """Identical images produce identical perceptual hashes."""
    a = _noise_image(5)
    b = _noise_image(5)
    assert hamming_distance(perceptual_hash(a), perceptual_hash(b)) == 0
    assert hamming_distance(difference_hash(a), difference_hash(b)) == 0


def test_scaled_image_is_near_duplicate():
    """A rescaled image stays close in perceptual-hash space."""
    a = _noise_image(9)
    scaled = a.resize((150, 150)).resize((200, 200))
    assert hamming_distance(perceptual_hash(a), perceptual_hash(scaled)) <= 5


def test_unrelated_images_are_distant():
    """Unrelated images differ substantially in every hash."""
    a = _noise_image(1)
    b = _noise_image(2)
    assert hamming_distance(perceptual_hash(a), perceptual_hash(b)) > 10
    assert hamming_distance(average_hash(a), average_hash(b)) > 10
    assert hamming_distance(difference_hash(a), difference_hash(b)) > 10


def test_phash_not_degenerate_across_images():
    """pHash varies across different images (guards the DCT implementation)."""
    hashes = {perceptual_hash(_noise_image(seed)) for seed in range(6)}
    assert len(hashes) > 1


def test_hamming_distance_rejects_mismatched_length():
    """Comparing hashes of different lengths raises ValueError."""
    with pytest.raises(ValueError):
        hamming_distance("00", "0000")
