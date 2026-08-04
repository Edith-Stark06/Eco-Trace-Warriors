"""Unit tests for the image validator and preprocessing."""

import pytest

from device_ai.configs.settings import Settings
from device_ai.exceptions import (
    CorruptedImageError,
    FileTooLargeError,
    ImageDimensionError,
    NoImagesProvidedError,
    TooManyImagesError,
    UnsupportedMediaTypeError,
)
from device_ai.preprocessing.validator import ImageValidator, RawUpload
from tests.conftest import make_image_bytes


@pytest.fixture()
def validator() -> ImageValidator:
    """A validator with small, test-friendly limits."""
    return ImageValidator(
        Settings(
            max_images=3,
            min_images=1,
            max_file_size=500 * 1024,
            min_image_dimension=32,
            max_image_dimension=1024,
        )
    )


def _upload(data: bytes, name: str = "d.png", mime: str = "image/png") -> RawUpload:
    return RawUpload(filename=name, content_type=mime, data=data)


def test_valid_batch_decodes(validator):
    """A valid batch returns decoded images with metadata."""
    uploads = [_upload(make_image_bytes())]
    loaded = validator.validate_batch(uploads)
    assert len(loaded) == 1
    assert loaded[0].width == 256
    assert loaded[0].height == 256
    assert loaded[0].sha256  # content hash computed


def test_empty_batch_rejected(validator):
    """An empty batch raises NoImagesProvidedError."""
    with pytest.raises(NoImagesProvidedError):
        validator.validate_batch([])


def test_too_many_rejected(validator):
    """Exceeding max_images raises TooManyImagesError."""
    uploads = [_upload(make_image_bytes()) for _ in range(4)]
    with pytest.raises(TooManyImagesError):
        validator.validate_batch(uploads)


def test_large_file_rejected(validator):
    """A file over the size limit raises FileTooLargeError."""
    big = make_image_bytes(size=(1024, 1024), fmt="PNG", noise=True)
    # Ensure it actually exceeds the 500 KB test limit.
    assert len(big) > 500 * 1024
    with pytest.raises(FileTooLargeError):
        validator.validate_batch([_upload(big)])


def test_empty_file_rejected(validator):
    """A zero-byte upload raises FileTooLargeError (empty file)."""
    with pytest.raises(FileTooLargeError):
        validator.validate_batch([_upload(b"")])


def test_invalid_mime_rejected(validator):
    """A disallowed MIME type raises UnsupportedMediaTypeError."""
    with pytest.raises(UnsupportedMediaTypeError):
        validator.validate_batch(
            [_upload(make_image_bytes(), name="a.txt", mime="text/plain")]
        )


def test_corrupted_rejected(validator):
    """Undecodable bytes raise CorruptedImageError."""
    with pytest.raises(CorruptedImageError):
        validator.validate_batch([_upload(b"garbage-bytes")])


def test_small_resolution_rejected(validator):
    """An image below the min dimension raises ImageDimensionError."""
    tiny = make_image_bytes(size=(16, 16))
    with pytest.raises(ImageDimensionError):
        validator.validate_batch([_upload(tiny)])


def test_large_resolution_rejected(validator):
    """An image above the max dimension raises ImageDimensionError."""
    huge = make_image_bytes(size=(2048, 2048), fmt="PNG")
    # Raise the size limit so the dimension check is what triggers.
    v = ImageValidator(
        Settings(max_file_size=50 * 1024 * 1024, max_image_dimension=1024)
    )
    with pytest.raises(ImageDimensionError):
        v.validate_batch([_upload(huge)])


def test_webp_accepted_by_extension(validator):
    """A WEBP upload with a generic MIME but valid extension is accepted."""
    webp = make_image_bytes(fmt="WEBP")
    loaded = validator.validate_batch(
        [_upload(webp, name="d.webp", mime="application/octet-stream")]
    )
    assert len(loaded) == 1
