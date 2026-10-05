"""Provenance tracking for dataset collection (Sprint P4.1.2, PART 1).

Extends the import pipeline with source attribution: every imported image carries
metadata about where it came from, its license, who contributed it, and when it
was collected. This closes the audit trail from a dataset version back to the
original source, satisfying data-governance and reproducibility requirements.

The :class:`ProvenanceRecord` value object is the unit of attribution; the
:class:`ProvenanceCollector` wraps the existing
:class:`~device_ai.dataset.importer.DatasetImporter` to attach provenance during
import without modifying the importer itself.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from .hashing import sha256_hash
from .importer import DatasetImporter
from .records import ImportSummary

if TYPE_CHECKING:
    from ..configs.settings import Settings


@dataclass(frozen=True, slots=True)
class ProvenanceRecord:
    """Attribution metadata for a single imported image.

    Attributes:
        relative_path: POSIX path of the image relative to the dataset root;
            matches :attr:`~device_ai.dataset.records.ImageRecord.relative_path`.
        source: Human-readable source identifier (e.g. ``"field_collection_2026"``,
            ``"partner_ewaste_india"``, ``"web_scrape_openclipart"``).
        license: License identifier (e.g. ``"CC-BY-4.0"``, ``"proprietary"``,
            ``"public_domain"``); empty when unknown.
        contributor: Name or identifier of the person/organization that
            collected or provided the image; empty when unknown.
        collection_date: ISO-8601 UTC timestamp of when the image was collected
            or received; empty when unknown.
        checksum: SHA-256 hex digest of the image file at import time, for
            tamper detection and cross-version tracking.
    """

    relative_path: str
    source: str
    license: str
    contributor: str
    collection_date: str
    checksum: str


@dataclass(frozen=True, slots=True)
class ProvenanceManifest:
    """Complete provenance manifest for a set of imported images.

    Attributes:
        records: Provenance records keyed by ``relative_path``.
        default_source: The source identifier used when none was explicitly
            supplied for an image.
        default_license: The license identifier used when none was explicitly
            supplied.
        default_contributor: The contributor identifier used when none was
            explicitly supplied.
        import_timestamp: ISO-8601 UTC timestamp of the import operation.
    """

    records: dict[str, ProvenanceRecord]
    default_source: str
    default_license: str
    default_contributor: str
    import_timestamp: str


class ProvenanceCollector:
    """Wraps :class:`~device_ai.dataset.importer.DatasetImporter` with provenance.

    Composes the existing importer to preserve its copy-and-deduplicate logic
    while layering provenance attribution on top. Every successfully imported
    image gets a :class:`ProvenanceRecord` stamped with its source, license,
    contributor, collection date, and SHA-256 checksum.

    The collector supports bulk defaults (all images in an import share the same
    source/license/contributor) and per-image overrides (via an optional mapping).

    Args:
        settings: Application settings (injected).
        clock: Clock function returning the current UTC datetime; injected for
            reproducible testing (default: live ``datetime.now(UTC)``).
    """

    def __init__(
        self,
        settings: Settings,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._settings = settings
        self._clock = clock
        self._importer = DatasetImporter()

    def import_with_provenance(
        self,
        source_root: str | Path,
        destination: str | Path,
        *,
        source: str,
        license_id: str = "",
        contributor: str = "",
        collection_date: str = "",
        deduplicate: bool = True,
        per_image_metadata: dict[str, dict[str, str]] | None = None,
    ) -> tuple[ImportSummary, ProvenanceManifest]:
        """Import images and generate a provenance manifest.

        Delegates the actual file copy and deduplication to the wrapped
        :class:`~device_ai.dataset.importer.DatasetImporter`, then constructs
        a :class:`ProvenanceRecord` for every successfully imported image using
        the bulk defaults and any per-image overrides.

        Args:
            source_root: Directory containing the source images to import.
            destination: Target directory (e.g. ``datasets/raw/``).
            source: Source identifier for this import batch (required).
            license_id: Default license identifier for all images.
            contributor: Default contributor identifier for all images.
            collection_date: ISO-8601 UTC timestamp of collection; when empty,
                the import timestamp is used as a fallback.
            deduplicate: Whether to skip exact SHA-256 duplicates (default: True).
            per_image_metadata: Optional dict mapping relative source paths to
                dicts of ``{"source": ..., "license": ..., "contributor": ...,
                "collection_date": ...}`` for per-image overrides. Any missing
                key falls back to the bulk default.

        Returns:
            A tuple of (:class:`~device_ai.dataset.records.ImportSummary`,
            :class:`ProvenanceManifest`). The summary describes what was imported;
            the manifest records attribution for every imported image.
        """
        # Perform the actual import using the existing importer.
        summary = self._importer.import_directory(
            Path(source_root),
            Path(destination),
            deduplicate=deduplicate,
        )

        # Stamp the import timestamp once for the entire batch.
        import_timestamp = self._clock().isoformat()
        effective_collection_date = collection_date or import_timestamp

        # Build provenance records for every successfully imported image.
        records: dict[str, ProvenanceRecord] = {}
        per_image = per_image_metadata or {}

        for relative_path in summary.imported:
            # Fetch per-image overrides if present.
            overrides = per_image.get(relative_path, {})
            effective_source = overrides.get("source", source)
            effective_license = overrides.get("license", license_id)
            effective_contributor = overrides.get("contributor", contributor)
            effective_date = overrides.get("collection_date", effective_collection_date)

            # The importer already computed SHA-256 during deduplication;
            # retrieve it from the destination file.
            destination_path = Path(destination) / relative_path
            checksum = self._compute_checksum(destination_path)

            records[relative_path] = ProvenanceRecord(
                relative_path=relative_path,
                source=effective_source,
                license=effective_license,
                contributor=effective_contributor,
                collection_date=effective_date,
                checksum=checksum,
            )

        manifest = ProvenanceManifest(
            records=records,
            default_source=source,
            default_license=license_id,
            default_contributor=contributor,
            import_timestamp=import_timestamp,
        )

        return summary, manifest

    def _compute_checksum(self, path: Path) -> str:
        """Compute SHA-256 hex digest of a file."""
        return sha256_hash(path.read_bytes())

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> ProvenanceCollector:
        """Construct a collector from application settings.

        Args:
            settings: Application settings.
            clock: Optional clock override for testing.

        Returns:
            A configured :class:`ProvenanceCollector`.
        """
        kwargs = {}
        if clock is not None:
            kwargs["clock"] = clock
        return cls(settings, **kwargs)


def provenance_to_dict(record: ProvenanceRecord) -> dict[str, str]:
    """Convert a :class:`ProvenanceRecord` to a JSON-serialisable dict.

    Args:
        record: The provenance record.

    Returns:
        A primitive-only mapping.
    """
    return {
        "relative_path": record.relative_path,
        "source": record.source,
        "license": record.license,
        "contributor": record.contributor,
        "collection_date": record.collection_date,
        "checksum": record.checksum,
    }


def manifest_to_dict(manifest: ProvenanceManifest) -> dict[str, object]:
    """Convert a :class:`ProvenanceManifest` to a JSON-serialisable dict.

    Args:
        manifest: The provenance manifest.

    Returns:
        A primitive-only mapping with a ``records`` list.
    """
    return {
        "records": [provenance_to_dict(rec) for rec in manifest.records.values()],
        "default_source": manifest.default_source,
        "default_license": manifest.default_license,
        "default_contributor": manifest.default_contributor,
        "import_timestamp": manifest.import_timestamp,
        "total_images": len(manifest.records),
    }
