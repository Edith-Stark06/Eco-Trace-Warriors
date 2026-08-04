"""Tests for the OpenCLIP encoder adapter (milestone M1.5)."""

import pytest

from device_ai.exceptions import EncoderNotReadyError
from device_ai.inference.clip_encoder import CLIPEncoder
from device_ai.preprocessing.image_loader import load_image

from .conftest import make_image_bytes


def test_encoder_without_backend_is_not_ready():
    """When no backend is installed or injected, the encoder is not ready."""
    encoder = CLIPEncoder()
    assert encoder.is_ready is False


def test_encoder_with_injected_encode_fn_is_ready():
    """When encode_fn is injected, the encoder is immediately ready."""

    def fake_encode(images):  # noqa: ARG001 - signature match required
        return [[0.6, 0.8]]

    encoder = CLIPEncoder(encode_fn=fake_encode)
    assert encoder.is_ready is True


def test_not_ready_encoder_raises_on_embed():
    """Calling embed() when not ready raises the typed error."""
    encoder = CLIPEncoder()
    image = load_image(
        make_image_bytes(), filename="device.png", content_type="image/png"
    )
    with pytest.raises(EncoderNotReadyError):
        encoder.embed([image])


def test_aggregation_mean_pools_and_normalizes():
    """The encoder mean-pools per-image embeddings and L2-normalizes."""

    def fake_encode(images):  # noqa: ARG001 - signature match required
        # Two images, each 3-dimensional.
        return [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]

    encoder = CLIPEncoder(encode_fn=fake_encode, dimension=3)
    image = load_image(
        make_image_bytes(), filename="device.png", content_type="image/png"
    )
    vector = encoder.embed([image, image])
    # Mean: (0.5, 0.5, 0.0); normalized: (1/√2, 1/√2, 0.0).
    assert vector.dimension == 3
    assert vector.normalized is True
    assert vector.values == pytest.approx((0.7071067811865475, 0.7071067811865475, 0.0))


def test_aggregation_of_single_image_normalizes():
    """A single-image batch is normalized without pooling."""

    def fake_encode(images):  # noqa: ARG001 - signature match required
        return [[3.0, 4.0]]

    encoder = CLIPEncoder(encode_fn=fake_encode, dimension=2)
    image = load_image(
        make_image_bytes(), filename="device.png", content_type="image/png"
    )
    vector = encoder.embed([image])
    # Normalized: (3/5, 4/5) = (0.6, 0.8).
    assert vector.values == pytest.approx((0.6, 0.8))


def test_empty_batch_returns_zero_vector():
    """An empty batch (defensive edge case) returns a zero vector."""

    def fake_encode(images):  # noqa: ARG001 - signature match required
        return []

    encoder = CLIPEncoder(encode_fn=fake_encode, dimension=512)
    vector = encoder.embed([])
    assert vector.dimension == 512
    assert vector.normalized is True
    assert all(component == 0.0 for component in vector.values)


def test_encoder_name_and_version():
    """The encoder exposes its name and a version derived from the model name."""
    encoder = CLIPEncoder(model_name="ViT-B-32")
    assert encoder.name == "clip"
    assert encoder.version == "openclip-vit-b-32-1.0.0"
