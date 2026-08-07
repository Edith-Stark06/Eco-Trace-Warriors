"""Merge contributor image folders into one staging dataset with provenance.

Phase 4.2.1 — Production Image Collection Toolkit (PART 3).

Each contributor submits their own folder of images. This script imports every
folder into a single staging directory, **namespacing each contributor's images
under their own sub-folder** so identical filenames from different contributors
never collide, and stamps a provenance record (source, license, contributor,
collection date, SHA-256) on every imported image. The result is one combined
provenance manifest for the merged staging set.

The import, de-duplication and provenance stamping all reuse the **frozen**
``ProvenanceCollector`` (which wraps ``DatasetImporter``) from the P4.1.2
pipeline. This script only orchestrates per-contributor calls and merges their
manifests; it adds no import or hashing logic and copies files (never moves or
mutates the sources).

Batches are described either with repeatable ``--batch`` flags or a JSON spec:

    python scripts/merge_collection_batches.py <staging_dir>
        --batch alice=inbox/alice --batch bob=inbox/bob
        --source field_collection_2026 --license CC-BY-4.0

    python scripts/merge_collection_batches.py <staging_dir> --spec batches.json

where ``batches.json`` is a list of objects with keys ``path`` (required),
``contributor``, ``source``, ``license`` and ``collection_date``.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from _ecotrace_toolkit import REPO_ROOT  # noqa: F401  (ensures device_ai on path)
from device_ai.configs.settings import Settings
from device_ai.dataset.provenance import ProvenanceCollector, provenance_to_dict


@dataclass(frozen=True, slots=True)
class BatchSpec:
    """A single contributor batch to merge.

    Attributes:
        path: Source folder of the contributor's images.
        contributor: Contributor identifier; also the staging sub-folder name.
        source: Source identifier for provenance (defaults applied by caller).
        license_id: License identifier for provenance.
        collection_date: ISO-8601 collection date, or empty for import time.
    """

    path: Path
    contributor: str
    source: str
    license_id: str
    collection_date: str


def _safe_name(name: str) -> str:
    """Return a filesystem-safe sub-folder name for a contributor id.

    Keeps alphanumerics, dash, underscore and dot; replaces every other
    character with an underscore so a contributor id can never escape the
    staging directory or collide with path separators.

    Args:
        name: The raw contributor identifier.

    Returns:
        A sanitised name safe to use as a single path segment.
    """
    cleaned = "".join(c if (c.isalnum() or c in "-_.") else "_" for c in name.strip())
    cleaned = cleaned.strip("._") or "contributor"
    return cleaned


def merge_batches(
    staging_dir: Path,
    batches: list[BatchSpec],
    settings: Settings,
    *,
    deduplicate: bool = True,
) -> dict[str, object]:
    """Import every batch into ``staging_dir`` and merge their provenance.

    Each batch is imported into ``staging_dir/<contributor>/`` via the frozen
    :class:`ProvenanceCollector`, so filenames from different contributors never
    collide. The per-batch manifests are merged into one manifest keyed by the
    staging-relative path (``<contributor>/<relative_path>``).

    Args:
        staging_dir: Destination staging directory (created if missing).
        batches: The contributor batches to merge.
        settings: Injected application settings.
        deduplicate: Whether to skip exact SHA-256 duplicates within each batch.

    Returns:
        A JSON-serialisable merge report: per-batch summaries plus the combined
        provenance manifest.
    """
    collector = ProvenanceCollector.from_settings(settings)
    staging_dir.mkdir(parents=True, exist_ok=True)

    merged_records: dict[str, dict[str, str]] = {}
    batch_reports: list[dict[str, object]] = []
    total_imported = total_dupes = total_invalid = 0

    for batch in batches:
        namespace = _safe_name(batch.contributor)
        destination = staging_dir / namespace
        summary, manifest = collector.import_with_provenance(
            batch.path,
            destination,
            source=batch.source,
            license_id=batch.license_id,
            contributor=batch.contributor,
            collection_date=batch.collection_date,
            deduplicate=deduplicate,
        )

        for rel, record in manifest.records.items():
            staged_rel = f"{namespace}/{rel}"
            record_dict = provenance_to_dict(record)
            record_dict["relative_path"] = staged_rel
            merged_records[staged_rel] = record_dict

        total_imported += len(summary.imported)
        total_dupes += len(summary.skipped_duplicates)
        total_invalid += len(summary.skipped_invalid)
        batch_reports.append(
            {
                "contributor": batch.contributor,
                "namespace": namespace,
                "source_path": batch.path.as_posix(),
                "destination": destination.as_posix(),
                "source": batch.source,
                "license": batch.license_id,
                "collection_date": batch.collection_date,
                "imported": len(summary.imported),
                "skipped_duplicates": len(summary.skipped_duplicates),
                "skipped_invalid": len(summary.skipped_invalid),
            }
        )

    return {
        "staging_dir": staging_dir.as_posix(),
        "num_batches": len(batches),
        "summary": {
            "total_imported": total_imported,
            "total_skipped_duplicates": total_dupes,
            "total_skipped_invalid": total_invalid,
            "total_provenance_records": len(merged_records),
        },
        "batches": batch_reports,
        "provenance": {
            "records": [merged_records[key] for key in sorted(merged_records)],
            "total_images": len(merged_records),
        },
    }


def _parse_batch_flag(value: str) -> tuple[str, Path]:
    """Parse a ``contributor=path`` ``--batch`` flag.

    Args:
        value: The raw flag value.

    Returns:
        A ``(contributor, path)`` tuple.

    Raises:
        argparse.ArgumentTypeError: If the value is not ``name=path``.
    """
    if "=" not in value:
        raise argparse.ArgumentTypeError(
            f"expected contributor=path, got '{value}'"
        )
    contributor, _, path = value.partition("=")
    contributor = contributor.strip()
    path = path.strip()
    if not contributor or not path:
        raise argparse.ArgumentTypeError(
            f"expected non-empty contributor=path, got '{value}'"
        )
    return contributor, Path(path)


def _specs_from_args(args: argparse.Namespace) -> list[BatchSpec]:
    """Build the list of :class:`BatchSpec` from parsed CLI arguments.

    Supports either repeated ``--batch contributor=path`` flags (which inherit
    the bulk ``--source``/``--license``/``--collection-date`` defaults) or a
    ``--spec`` JSON file (whose per-entry keys override the bulk defaults).

    Args:
        args: Parsed arguments.

    Returns:
        The resolved batch specifications.

    Raises:
        ValueError: If neither batches nor a spec were supplied, or the spec is
            malformed.
    """
    specs: list[BatchSpec] = []

    if args.spec is not None:
        raw = json.loads(args.spec.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            raise ValueError("spec file must contain a JSON list of batch objects")
        for entry in raw:
            path = entry.get("path")
            if not path:
                raise ValueError("each spec entry requires a 'path'")
            contributor = str(entry.get("contributor") or Path(path).name)
            specs.append(
                BatchSpec(
                    path=Path(path),
                    contributor=contributor,
                    source=str(entry.get("source") or args.source),
                    license_id=str(entry.get("license") or args.license),
                    collection_date=str(entry.get("collection_date") or ""),
                )
            )

    for contributor, path in args.batch or []:
        specs.append(
            BatchSpec(
                path=path,
                contributor=contributor,
                source=args.source,
                license_id=args.license,
                collection_date=args.collection_date,
            )
        )

    if not specs:
        raise ValueError("provide at least one --batch or a --spec file")
    return specs


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Merge contributor image folders into one staging dataset while "
            "preserving provenance (reuses the frozen ProvenanceCollector)."
        )
    )
    parser.add_argument(
        "staging_dir", type=Path, help="Destination staging directory."
    )
    parser.add_argument(
        "--batch",
        action="append",
        type=_parse_batch_flag,
        metavar="CONTRIBUTOR=PATH",
        help="A contributor batch; repeatable. Inherits the bulk defaults.",
    )
    parser.add_argument(
        "--spec",
        type=Path,
        default=None,
        metavar="JSON",
        help="JSON list of batch objects (path/contributor/source/license/date).",
    )
    parser.add_argument(
        "--source",
        default="collection",
        help="Default provenance source for --batch entries.",
    )
    parser.add_argument(
        "--license",
        default="",
        help="Default provenance license identifier for --batch entries.",
    )
    parser.add_argument(
        "--collection-date",
        default="",
        help="Default ISO-8601 collection date for --batch entries.",
    )
    parser.add_argument(
        "--no-deduplicate",
        action="store_true",
        help="Do not skip exact SHA-256 duplicates within a batch.",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=None,
        metavar="PATH",
        help="Write the merged provenance manifest + report JSON to PATH.",
    )
    parser.add_argument(
        "--quiet", action="store_true", help="Suppress the human-readable summary."
    )
    return parser.parse_args(argv)


def _print_human(report: dict[str, object]) -> None:
    """Print a concise human-readable summary of a merge report."""
    summary = report["summary"]
    print(f"Staging dir: {report['staging_dir']}")
    print(f"Batches merged: {report['num_batches']}")
    print(
        f"Imported: {summary['total_imported']}   "
        f"Skipped dup: {summary['total_skipped_duplicates']}   "
        f"Skipped invalid: {summary['total_skipped_invalid']}"
    )
    print(f"Provenance records: {summary['total_provenance_records']}")
    for batch in report["batches"]:
        print(
            f"  - {batch['contributor']} -> {batch['namespace']}/: "
            f"{batch['imported']} imported, "
            f"{batch['skipped_duplicates']} dup, "
            f"{batch['skipped_invalid']} invalid"
        )


def main(argv: list[str] | None = None) -> int:
    """CLI entry point.

    Args:
        argv: Optional argument vector (defaults to ``sys.argv[1:]``).

    Returns:
        Process exit code: 0 on success, 2 on usage error.
    """
    args = _parse_args(argv)
    try:
        specs = _specs_from_args(args)
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    missing = [str(s.path) for s in specs if not s.path.is_dir()]
    if missing:
        print(
            "error: batch source is not a directory: " + ", ".join(missing),
            file=sys.stderr,
        )
        return 2

    settings = Settings()
    report = merge_batches(
        args.staging_dir,
        specs,
        settings,
        deduplicate=not args.no_deduplicate,
    )

    if args.manifest is not None:
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    if not args.quiet:
        _print_human(report)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())


