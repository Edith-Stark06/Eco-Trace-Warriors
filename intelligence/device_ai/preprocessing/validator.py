"""Upload validation.

Validates a batch of uploaded images against the service constraints:
count bounds, per-file size, MIME type / extension allow-list, decodability
(corruption) and resolution bounds. Validation is separated from decoding
and inference so each concern is independently testable.

The validator is constructed with a :class:`Settings` instance
(dependency injection) rather than reading configuration globally, so tests
can exercise it with custom limits.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..configs.settings import (
    ALLOWED_IMAGE_EXTENSIONS,
    ALLOWED_IMAGE_MIME_TYPES,
    Settings,
)
from ..exceptions import (
    FileTooLargeError,
    ImageDimensionError,
    NoImagesProvidedError,
    TooManyImagesError,
    UnsupportedMediaTypeError,
)
from .image_loader import LoadedImage, load_image


@dataclass(frozen=True, slots=True)
class RawUpload:
    """A single not-yet-decoded upload from the transport layer.

    Attributes:
        filename: Client-supplied file name (untrusted).
        content_type: Declared MIME type from the multipart part.
        data: Raw bytes of the upload.
    """

    filename: str | None
    content_type: str | None
    data: bytes


class ImageValidator:
    """Validate uploaded images against configured constraints.

    Args:
        settings: Application settings supplying the limits to enforce.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def validate_batch(self, uploads: list[RawUpload]) -> list[LoadedImage]:
        """Validate and decode a batch of uploads.

        The batch-level count check runs first (cheap), then each upload is
        validated for size and MIME type before the (more expensive) decode
        and resolution checks.

        Args:
            uploads: The raw uploads received in the request.

        Returns:
            A list of validated, decoded :class:`LoadedImage` objects in the
            same order as the input.

        Raises:
            NoImagesProvidedError: If ``uploads`` is empty (or below minimum).
            TooManyImagesError: If more than ``max_images`` were supplied.
            FileTooLargeError: If any upload exceeds ``max_file_size``.
            UnsupportedMediaTypeError: If any upload has a disallowed type.
            CorruptedImageError: If any upload cannot be decoded.
            ImageDimensionError: If any image is outside resolution bounds.
        """
        self._validate_count(uploads)
        return [self._validate_one(upload) for upload in uploads]

    def _validate_count(self, uploads: list[RawUpload]) -> None:
        """Enforce the minimum and maximum image-count constraints."""
        count = len(uploads)
        if count < self._settings.min_images:
            raise NoImagesProvidedError(
                "At least " f"{self._settings.min_images} image(s) must be provided.",
                details={"received": count, "min": self._settings.min_images},
            )
        if count > self._settings.max_images:
            raise TooManyImagesError(
                f"At most {self._settings.max_images} images are allowed.",
                details={"received": count, "max": self._settings.max_images},
            )

    def _validate_one(self, upload: RawUpload) -> LoadedImage:
        """Validate a single upload and return the decoded image."""
        self._validate_size(upload)
        self._validate_media_type(upload)
        # Decoding also acts as the corruption check (raises on bad data).
        loaded = load_image(
            upload.data,
            filename=upload.filename,
            content_type=upload.content_type,
        )
        self._validate_dimensions(loaded)
        return loaded

    def _validate_size(self, upload: RawUpload) -> None:
        """Reject empty uploads and those exceeding the size limit."""
        size = len(upload.data)
        if size == 0:
            raise FileTooLargeError(
                "Uploaded file is empty.",
                details={"filename": upload.filename, "size": 0},
            )
        if size > self._settings.max_file_size:
            raise FileTooLargeError(
                "File exceeds the maximum allowed size of "
                f"{self._settings.max_file_size_mb:.1f} MB.",
                details={
                    "filename": upload.filename,
                    "size": size,
                    "max_file_size": self._settings.max_file_size,
                },
            )

    def _validate_media_type(self, upload: RawUpload) -> None:
        """Reject uploads whose MIME type or extension is not allowed."""
        content_type = (upload.content_type or "").lower().split(";")[0].strip()
        extension = ""
        if upload.filename and "." in upload.filename:
            extension = "." + upload.filename.rsplit(".", 1)[-1].lower()

        mime_ok = content_type in ALLOWED_IMAGE_MIME_TYPES
        ext_ok = extension in ALLOWED_IMAGE_EXTENSIONS

        # Require the declared MIME type to be valid; the extension acts as a
        # secondary guard. Accept when the MIME type is allowed, or when it is
        # missing/generic but the extension is clearly a supported image.
        generic = content_type in {"", "application/octet-stream"}
        if not (mime_ok or (generic and ext_ok)):
            raise UnsupportedMediaTypeError(
                "Unsupported media type. Allowed types: "
                f"{', '.join(sorted(ALLOWED_IMAGE_MIME_TYPES))}.",
                details={
                    "filename": upload.filename,
                    "content_type": upload.content_type,
                    "extension": extension,
                },
            )

    def _validate_dimensions(self, loaded: LoadedImage) -> None:
        """Reject images outside the configured resolution bounds."""
        min_dim = self._settings.min_image_dimension
        max_dim = self._settings.max_image_dimension
        if loaded.width < min_dim or loaded.height < min_dim:
            raise ImageDimensionError(
                f"Image resolution too small; minimum is {min_dim}px per side.",
                details={
                    "filename": loaded.filename,
                    "width": loaded.width,
                    "height": loaded.height,
                },
            )
        if loaded.width > max_dim or loaded.height > max_dim:
            raise ImageDimensionError(
                f"Image resolution too large; maximum is {max_dim}px per side.",
                details={
                    "filename": loaded.filename,
                    "width": loaded.width,
                    "height": loaded.height,
                },
            )
