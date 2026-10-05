"""Fingerprint domain model (milestone M1.5).

A :class:`DeviceFingerprint` is the canonical, storage-agnostic record the
fingerprinting engine produces for a device: its public EcoID, the
**hash-backed fingerprint** derived from a normalized visual embedding, the
embedding itself and provenance metadata (encoder identity, source image
hashes, creation time).

The model is a frozen dataclass with explicit ``to_dict``/``from_dict``
converters so any persistence backend (in-memory, JSON file, a future vector
store or blockchain anchor) can serialize it without the domain layer knowing
about the storage medium.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import cast

from ..utils.hashing import hash_bytes

#: Number of decimal places embeddings are rounded to before hashing. Rounding
#: makes the fingerprint stable against negligible floating-point noise while
#: preserving discriminative power.
_FINGERPRINT_PRECISION = 6


def canonical_embedding_bytes(
    embedding: tuple[float, ...],
    *,
    precision: int = _FINGERPRINT_PRECISION,
) -> bytes:
    """Return a deterministic byte encoding of an embedding vector.

    The vector is rounded to ``precision`` decimals and joined with commas so
    the same vector always yields the same bytes (and therefore the same
    fingerprint), independent of platform float formatting.

    Args:
        embedding: The (normalized) embedding components.
        precision: Decimal places each component is rounded to.

    Returns:
        The canonical UTF-8 byte encoding of the vector.
    """
    return ",".join(f"{value:.{precision}f}" for value in embedding).encode("utf-8")


def compute_fingerprint(
    embedding: tuple[float, ...],
    *,
    precision: int = _FINGERPRINT_PRECISION,
) -> str:
    """Return the hash-backed fingerprint (SHA-256 hex) of an embedding.

    Args:
        embedding: The normalized embedding components.
        precision: Decimal places each component is rounded to before hashing.

    Returns:
        The 64-character hexadecimal SHA-256 digest of the canonical encoding.
    """
    return hash_bytes(canonical_embedding_bytes(embedding, precision=precision))


@dataclass(frozen=True, slots=True)
class DeviceFingerprint:
    """An immutable fingerprint record for a single device.

    Attributes:
        eco_id: Public EcoID (``ET-YYYY-XXXXXXXX``) this fingerprint belongs to.
        fingerprint: Hash-backed identifier (SHA-256 hex of the normalized
            embedding). Two devices with identical embeddings share this value.
        embedding: The L2-normalized embedding vector.
        dimension: Length of ``embedding``.
        encoder_name: Name of the encoder that produced the embedding.
        encoder_version: Version of that encoder.
        metric: Default similarity metric recorded for this fingerprint.
        created_at: UTC timestamp the fingerprint was generated.
        source_hashes: SHA-256 content hashes of the source images (provenance).
        device_type: Optional device type from the detection pipeline (reused,
            never required — kept empty when detection is not run).
        brand: Optional brand from the detection pipeline.
        identity: Optional OCR-derived identity fields (manufacturer, model,
            serial_number, imei, mac_address) reused from the OCR engine
            (milestone M1.6). Empty by default; only populated fields are kept,
            so a fingerprint generated without OCR is byte-identical to before.
    """

    eco_id: str
    fingerprint: str
    embedding: tuple[float, ...]
    dimension: int
    encoder_name: str
    encoder_version: str
    metric: str
    created_at: datetime
    source_hashes: tuple[str, ...] = field(default_factory=tuple)
    device_type: str = ""
    brand: str = ""
    identity: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation of the fingerprint.

        Returns:
            A plain ``dict`` with an ISO-8601 ``created_at`` and list-typed
            sequences, suitable for JSON persistence or an API response. The
            ``identity`` key is emitted only when at least one OCR-derived field
            is present, so records generated without OCR serialize unchanged.
        """
        payload: dict[str, object] = {
            "eco_id": self.eco_id,
            "fingerprint": self.fingerprint,
            "embedding": list(self.embedding),
            "dimension": self.dimension,
            "encoder_name": self.encoder_name,
            "encoder_version": self.encoder_version,
            "metric": self.metric,
            "created_at": self.created_at.isoformat(),
            "source_hashes": list(self.source_hashes),
            "device_type": self.device_type,
            "brand": self.brand,
        }
        if self.identity:
            payload["identity"] = dict(self.identity)
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> DeviceFingerprint:
        """Reconstruct a :class:`DeviceFingerprint` from :meth:`to_dict` output.

        Args:
            data: A mapping previously produced by :meth:`to_dict`.

        Returns:
            The reconstructed fingerprint.
        """
        embedding = cast(Sequence[float], data["embedding"])
        source_hashes = cast(Iterable[object], data.get("source_hashes", ()))
        raw_identity = cast(dict[str, object], data.get("identity", {}))
        return cls(
            eco_id=str(data["eco_id"]),
            fingerprint=str(data["fingerprint"]),
            embedding=tuple(float(v) for v in embedding),
            dimension=int(cast(int, data["dimension"])),
            encoder_name=str(data["encoder_name"]),
            encoder_version=str(data["encoder_version"]),
            metric=str(data["metric"]),
            created_at=datetime.fromisoformat(str(data["created_at"])),
            source_hashes=tuple(str(h) for h in source_hashes),
            device_type=str(data.get("device_type", "")),
            brand=str(data.get("brand", "")),
            identity={str(k): str(v) for k, v in raw_identity.items()},
        )
