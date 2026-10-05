"""Content hashing helpers.

Deterministic hashes let the service de-duplicate uploads and correlate an
image with downstream artifacts (e.g. an embedding) without persisting the
raw bytes. Hashing is intentionally isolated here so the algorithm can be
swapped in one place.
"""

from __future__ import annotations

import hashlib
import uuid

# Default digest algorithm. SHA-256 offers a strong, collision-resistant
# fingerprint suitable for content-addressing image uploads.
_DEFAULT_ALGORITHM = "sha256"


def hash_bytes(data: bytes, *, algorithm: str = _DEFAULT_ALGORITHM) -> str:
    """Return the hex digest of ``data``.

    Args:
        data: Raw bytes to hash.
        algorithm: Any algorithm name accepted by :func:`hashlib.new`.

    Returns:
        The hexadecimal digest string.

    Raises:
        ValueError: If ``algorithm`` is not supported by ``hashlib``.
    """
    try:
        digest = hashlib.new(algorithm)
    except ValueError as exc:  # unsupported algorithm name
        raise ValueError(f"Unsupported hash algorithm: {algorithm}") from exc
    digest.update(data)
    return digest.hexdigest()


def short_hash(data: bytes, *, length: int = 12) -> str:
    """Return a truncated hex digest, handy for log-friendly identifiers.

    Args:
        data: Raw bytes to hash.
        length: Number of leading hex characters to keep.

    Returns:
        The first ``length`` characters of the SHA-256 hex digest.
    """
    if length <= 0:
        raise ValueError("length must be positive")
    return hash_bytes(data)[:length]


def new_request_id() -> str:
    """Return a unique, URL-safe request identifier.

    Returns:
        A hex UUID4 string used to correlate logs for a single request.
    """
    return uuid.uuid4().hex


def new_uuid() -> uuid.UUID:
    """Return a fresh random UUID4.

    Returns:
        A :class:`uuid.UUID` instance.
    """
    return uuid.uuid4()
