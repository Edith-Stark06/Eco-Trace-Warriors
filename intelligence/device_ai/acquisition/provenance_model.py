"""Acquisition provenance — a superset of the frozen ``ProvenanceRecord``.

Spec P4.3.7 §5 requires richer provenance than the code-owned
:class:`~device_ai.dataset.provenance.ProvenanceRecord` (which carries only
``relative_path, source, license, contributor, collection_date, checksum``).
For every imported image we capture:

    SHA-256 · original filename · source dataset · source identifier ·
    source class · taxonomy class + id · license id/raw/url · import timestamp.

:class:`AcquisitionProvenanceRecord` holds all of that and can *project down*
to the frozen record (:meth:`AcquisitionProvenanceRecord.to_frozen_record`) so
the output is compatible with the existing provenance manifest schema.

This module is stdlib-only (``hashlib``) so it stays import-light and testable
without Pillow/numpy. The checksum is a plain SHA-256 of the file bytes —
byte-for-byte identical to
:func:`device_ai.dataset.hashing.sha256_hash` — computed here directly to avoid
pulling the perceptual-hashing (PIL/numpy) dependency into provenance code.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

# Read files in fixed-size chunks so large images do not balloon memory.
_CHUNK_BYTES = 1 << 20  # 1 MiB


def compute_sha256(path: str | Path) -> str:
    """Return the SHA-256 hex digest of a file's bytes (streamed).

    Args:
        path: File to hash.

    Returns:
        Lower-case hex digest, identical to
        :func:`device_ai.dataset.hashing.sha256_hash` over the same bytes.
    """
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(_CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True, slots=True)
class AcquisitionProvenanceRecord:
    """Full attribution for one acquired image (superset of the frozen record).

    Attributes:
        relative_path: POSIX path of the staged image relative to the images
            root (matches ``ImageRecord.relative_path``).
        original_filename: Bare filename as it existed in the source.
        source_dataset: Human-readable source dataset name.
        source_identifier: Stable identifier of the image within the source
            (e.g. the original relative path or record id).
        source_class: The source's own class label for this image.
        taxonomy_class: EcoTrace canonical class name (``router``).
        taxonomy_id: EcoTrace taxonomy id resolved from ``load_taxonomy``.
        license_id: Normalised, accepted license identifier.
        license_raw: The exact license string supplied by the source.
        license_url: Supporting license URL, if any.
        checksum_sha256: SHA-256 of the image bytes at import time.
        import_timestamp: ISO-8601 UTC timestamp of the import operation.
        publisher: Source publisher/contributor, if known.
        source_url: Source URL, if known.
        source_version: Source dataset version, if the source declares one.
        image_width: Pixel width of the staged image (0 when not measured).
        image_height: Pixel height of the staged image (0 when not measured).
        object_count: Number of accepted bounding boxes written to the label.
    """

    relative_path: str
    original_filename: str
    source_dataset: str
    source_identifier: str
    source_class: str
    taxonomy_class: str
    taxonomy_id: int
    license_id: str
    license_raw: str
    license_url: str
    checksum_sha256: str
    import_timestamp: str
    publisher: str = ""
    source_url: str = ""
    source_version: str = ""
    image_width: int = 0
    image_height: int = 0
    object_count: int = 0

    def to_dict(self) -> dict[str, object]:
        """Return a primitive-only, JSON-serialisable mapping (superset)."""
        return {
            "relative_path": self.relative_path,
            "original_filename": self.original_filename,
            "source_dataset": self.source_dataset,
            "source_identifier": self.source_identifier,
            "source_class": self.source_class,
            "taxonomy_class": self.taxonomy_class,
            "taxonomy_id": self.taxonomy_id,
            "license_id": self.license_id,
            "license_raw": self.license_raw,
            "license_url": self.license_url,
            "checksum_sha256": self.checksum_sha256,
            "import_timestamp": self.import_timestamp,
            "publisher": self.publisher,
            "source_url": self.source_url,
            "source_version": self.source_version,
            "image_width": self.image_width,
            "image_height": self.image_height,
            "object_count": self.object_count,
        }

    def to_frozen_record_dict(self) -> dict[str, str]:
        """Project down to the frozen ``ProvenanceRecord`` field shape.

        The frozen manifest keeps six fields; this mapping keeps the output
        interoperable with the existing provenance schema without importing the
        (PIL/numpy-heavy) provenance module.
        """
        return {
            "relative_path": self.relative_path,
            "source": self.source_dataset,
            "license": self.license_id,
            "contributor": self.publisher or self.source_dataset,
            "collection_date": self.import_timestamp,
            "checksum": self.checksum_sha256,
        }


def is_complete(record: AcquisitionProvenanceRecord) -> bool:
    """Whether a record has every mandatory provenance field populated.

    Mandatory: checksum, original filename, source dataset, source identifier,
    source class, taxonomy id (>= 0), a license id, and an import timestamp.
    """
    return bool(
        record.checksum_sha256
        and record.original_filename
        and record.source_dataset
        and record.source_identifier
        and record.source_class
        and record.taxonomy_id >= 0
        and record.license_id
        and record.import_timestamp
    )


def build_manifest_dict(
    records: list[AcquisitionProvenanceRecord],
    *,
    target_class: str,
    import_timestamp: str,
) -> dict[str, object]:
    """Assemble a JSON-serialisable provenance manifest.

    Args:
        records: The per-image provenance records.
        target_class: Canonical taxonomy class name for the batch.
        import_timestamp: ISO-8601 UTC timestamp for the batch.

    Returns:
        A primitive-only mapping with superset records, the frozen-shape
        projection, and completeness accounting.
    """
    complete = sum(1 for record in records if is_complete(record))
    return {
        "target_class": target_class,
        "import_timestamp": import_timestamp,
        "total_records": len(records),
        "complete_records": complete,
        "incomplete_records": len(records) - complete,
        "records": [record.to_dict() for record in records],
        "frozen_shape_records": [record.to_frozen_record_dict() for record in records],
    }
