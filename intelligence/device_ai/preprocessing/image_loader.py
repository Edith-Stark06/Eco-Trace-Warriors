"""Image loading: turn raw upload bytes into a rich domain object.

The :class:`LoadedImage` produced here is the single representation of an
uploaded image passed between the validation, preprocessing and inference
layers. It decodes the pixels exactly once (expensive) and caches derived
metadata (dimensions, content hash) so later stages are cheap and pure.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from PIL import Image, UnidentifiedImageError

from ..exceptions import CorruptedImageError
from ..utils.file_utils import file_extension, sanitize_filename
from ..utils.hashing import hash_bytes
from ..utils.image_utils import load_image_from_bytes


@dataclass(slots=True)
class LoadedImage:
    """An uploaded image with decoded pixels and derived metadata.

    Attributes:
        filename: Sanitised original file name (untrusted input made safe).
        content_type: Declared MIME type from the multipart upload.
        raw: Original image bytes as received.
        image: Decoded Pillow image in RGB mode.
        sha256: Content hash of ``raw``, computed once at construction.
    """

    filename: str
    content_type: str
    raw: bytes = field(repr=False)
    image: Image.Image = field(repr=False)
    # Derived once by the factory below. Stored as a field (not a
    # cached_property) because ``slots=True`` dataclasses have no ``__dict__``
    # for cached_property to write to.
    sha256: str = field(default="", repr=False)

    @property
    def size_bytes(self) -> int:
        """Size of the original upload in bytes."""
        return len(self.raw)

    @property
    def width(self) -> int:
        """Decoded image width in pixels."""
        return self.image.width

    @property
    def height(self) -> int:
        """Decoded image height in pixels."""
        return self.image.height

    @property
    def extension(self) -> str:
        """Lower-cased file extension including the leading dot."""
        return file_extension(self.filename)


def load_image(
    raw: bytes,
    *,
    filename: str | None,
    content_type: str | None,
) -> LoadedImage:
    """Decode raw upload bytes into a :class:`LoadedImage`.

    Decoding is forced eagerly so truncated/corrupted uploads fail here
    rather than deep inside inference.

    Args:
        raw: Original image bytes from the multipart upload.
        filename: Client-supplied file name (untrusted; sanitised).
        content_type: Declared MIME type of the upload.

    Returns:
        A fully-decoded :class:`LoadedImage`.

    Raises:
        CorruptedImageError: If the bytes cannot be decoded as an image.
    """
    safe_name = sanitize_filename(filename)
    try:
        image = load_image_from_bytes(raw)
        image.load()  # force decode to surface truncated data now
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise CorruptedImageError(
            f"Image '{safe_name}' is corrupted or not a valid image.",
            details={"filename": safe_name},
        ) from exc

    return LoadedImage(
        filename=safe_name,
        content_type=(content_type or "").lower(),
        raw=raw,
        image=image,
        sha256=hash_bytes(raw),
    )
