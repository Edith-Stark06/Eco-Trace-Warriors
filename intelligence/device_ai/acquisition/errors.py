"""Acquisition-pipeline domain exceptions.

These extend the shared :class:`~device_ai.exceptions.DatasetError` hierarchy so
the acquisition pipeline slots cleanly into the existing error taxonomy. They
carry the same stable ``code`` / ``http_status`` contract as the rest of the
Device Intelligence Engine.

None of these should ever be raised to *paper over* missing data: the pipeline
records honest ``BLOCKED`` / ``UNVERIFIED`` outcomes in its result object
instead. They exist for genuinely exceptional conditions (a corrupt archive, a
misconfigured path) and for adapters that must *fail closed*.
"""

from __future__ import annotations

from http import HTTPStatus

from ..exceptions import DatasetError


class AcquisitionError(DatasetError):
    """Base class for automated-acquisition pipeline errors."""

    code = "ACQUISITION_ERROR"
    http_status = HTTPStatus.INTERNAL_SERVER_ERROR


class SourceUnavailableError(AcquisitionError):
    """Raised when a requested source cannot be located or opened.

    Used for a ``--source`` archive/directory that does not exist or cannot be
    read. It is *not* used for the ordinary "no source supplied" case, which is
    a reported ``BLOCKED_NO_SOURCE`` outcome, not an exception.
    """

    code = "ACQUISITION_SOURCE_UNAVAILABLE"
    http_status = HTTPStatus.NOT_FOUND


class UnsupportedFormatError(AcquisitionError):
    """Raised when a local dataset's annotation format cannot be detected.

    The pipeline supports YOLO, COCO and Pascal VOC. Anything else is reported
    with the exact reason rather than being silently coerced.
    """

    code = "ACQUISITION_UNSUPPORTED_FORMAT"
    http_status = HTTPStatus.UNPROCESSABLE_ENTITY
