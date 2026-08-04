"""Dataset import: ingest source images into the managed tree.

:class:`DatasetImporter` copies supported images from an arbitrary source
directory into a destination sub-folder of the managed dataset (typically
``raw/``). During import it:

* validates each file decodes as a supported image;
* de-duplicates by SHA-256 so identical bytes are never stored twice;
* preserves the source's relative directory structure.

Import is copy-only (the source is never mutated) and returns a structured
:class:`~device_ai.dataset.records.ImportSummary`.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, UnidentifiedImageError

from .hashing import sha256_hash
from .layout import list_image_paths, relative_path
from .records import ImportSummary


class DatasetImporter:
    """Import and de-duplicate images into a managed destination directory."""

    def _is_valid_image(self, path: Path) -> bool:
        """Return whether ``path`` decodes as a supported image."""
        try:
            with Image.open(path) as opened:
                opened.verify()
            return True
        except (UnidentifiedImageError, OSError, ValueError):
            return False

    def import_directory(
        self,
        source_root: Path,
        destination: Path,
        *,
        deduplicate: bool = True,
    ) -> ImportSummary:
        """Import every supported image from ``source_root``.

        Args:
            source_root: Directory of source images (scanned recursively).
            destination: Managed directory to copy images into (created if
                missing). The source's relative layout is preserved beneath
                it.
            deduplicate: When True, images whose SHA-256 was already imported
                (or already present in ``destination``) are skipped.

        Returns:
            An :class:`ImportSummary` describing the outcome.
        """
        destination.mkdir(parents=True, exist_ok=True)

        seen_hashes: set[str] = set()
        if deduplicate:
            # Seed with hashes already present in the destination so repeat
            # imports are idempotent.
            for existing in list_image_paths(destination):
                seen_hashes.add(sha256_hash(existing.read_bytes()))

        imported: list[str] = []
        skipped_duplicates: list[str] = []
        skipped_invalid: list[str] = []

        for path in list_image_paths(source_root):
            source_rel = relative_path(path, source_root)
            if not self._is_valid_image(path):
                skipped_invalid.append(source_rel)
                continue

            data = path.read_bytes()
            digest = sha256_hash(data)
            if deduplicate and digest in seen_hashes:
                skipped_duplicates.append(source_rel)
                continue
            seen_hashes.add(digest)

            out_path = destination / source_rel
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(data)
            imported.append(relative_path(out_path, destination))

        return ImportSummary(
            imported=tuple(sorted(imported)),
            skipped_duplicates=tuple(sorted(skipped_duplicates)),
            skipped_invalid=tuple(sorted(skipped_invalid)),
            destination=destination.as_posix(),
        )
