"""Report dataset-collection progress by taxonomy class.

Phase 4.2.1 — Production Image Collection Toolkit (PART 2).

Scans a directory of collected images, buckets each by the taxonomy class
encoded in its filename (``<class_name>_...``), and reports:

* **per-class counts** — how many images exist for each of the 19 classes;
* **class imbalance** — the ``max/min`` ratio across non-empty classes;
* **missing classes** — taxonomy classes with zero images;
* **progress vs targets** — counts against the per-class ``min_target`` /
  ``recommended_target`` / ``ideal_target`` from ``collection_progress.csv``;
* **collection summary** — totals and how many classes have met each target.

The taxonomy (19 classes, version ``1.0.0``) is read from the code-owned
``load_taxonomy()``; the targets are read from the P4.1.5
``collection_progress.csv`` template (or any CSV with the same columns). The
script reads only — it never writes into the dataset — and outputs both JSON
and Markdown so it can feed both machines and humans.

Usage (from the repository root)::

    python scripts/dataset_progress.py <images_dir>
        [--targets docs/ai/templates/collection_progress.csv]
        [--json progress.json] [--markdown progress.md] [--quiet]
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from _ecotrace_toolkit import class_from_filename
from device_ai.dataset.layout import list_image_paths
from device_ai.dataset.taxonomy import DeviceTaxonomy, load_taxonomy

# Default targets file shipped with the collection workflow (P4.1.5).
_DEFAULT_TARGETS = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "ai"
    / "templates"
    / "collection_progress.csv"
)


@dataclass(frozen=True, slots=True)
class ClassTarget:
    """Per-class collection targets read from the progress CSV.

    Attributes:
        min_target: Minimum images required for the class to count as covered.
        recommended_target: Preferred image count.
        ideal_target: Aspirational image count.
    """

    min_target: int
    recommended_target: int
    ideal_target: int


def load_targets(path: Path | None) -> dict[str, ClassTarget]:
    """Load per-class targets from a ``collection_progress.csv``-shaped file.

    Comment lines (starting with ``#``) and blank lines are skipped. Rows are
    keyed by ``class_name``; malformed numeric fields default to 0 so a partial
    template still yields a usable report.

    Args:
        path: CSV path, or ``None`` to use the packaged default. A missing file
            yields an empty mapping (progress is then reported without targets).

    Returns:
        Mapping of class name to :class:`ClassTarget`.
    """
    if path is None:
        path = _DEFAULT_TARGETS
    if not path.is_file():
        return {}

    def _int(value: str) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    targets: dict[str, ClassTarget] = {}
    lines = [
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    for row in csv.DictReader(lines):
        name = (row.get("class_name") or "").strip()
        if not name:
            continue
        targets[name] = ClassTarget(
            min_target=_int(row.get("min_target", "")),
            recommended_target=_int(row.get("recommended_target", "")),
            ideal_target=_int(row.get("ideal_target", "")),
        )
    return targets


def count_by_class(
    images_dir: Path, taxonomy: DeviceTaxonomy
) -> tuple[dict[str, int], int]:
    """Count images per taxonomy class by parsing filenames.

    Args:
        images_dir: Directory of collected images (scanned recursively).
        taxonomy: The loaded device taxonomy.

    Returns:
        A tuple of (counts keyed by class name for all 19 classes, number of
        images whose class could not be inferred from the filename).
    """
    counts = {name: 0 for name in taxonomy.class_names}
    unclassified = 0
    for path in list_image_paths(images_dir):
        class_name = class_from_filename(path.name, taxonomy.class_names)
        if class_name is None:
            unclassified += 1
        else:
            counts[class_name] += 1
    return counts, unclassified


def _imbalance_ratio(counts: dict[str, int]) -> float | None:
    """Return ``max/min`` across classes that have at least one image.

    Args:
        counts: Per-class image counts.

    Returns:
        The imbalance ratio rounded to two decimals, or ``None`` when fewer
        than one class is populated.
    """
    populated = [c for c in counts.values() if c > 0]
    if not populated:
        return None
    return round(max(populated) / min(populated), 2)


def build_progress(
    images_dir: Path,
    taxonomy: DeviceTaxonomy,
    targets: dict[str, ClassTarget],
) -> dict[str, object]:
    """Assemble the full progress report as a JSON-serialisable mapping.

    Args:
        images_dir: Directory of collected images.
        taxonomy: The loaded device taxonomy.
        targets: Per-class targets (may be empty).

    Returns:
        A primitive-only mapping with per-class rows and a summary.
    """
    counts, unclassified = count_by_class(images_dir, taxonomy)
    classified = sum(counts.values())
    total = classified + unclassified
    missing = [name for name, c in counts.items() if c == 0]

    classes: list[dict[str, object]] = []
    met_min = met_recommended = met_ideal = 0
    for class_id, name in enumerate(taxonomy.class_names):
        count = counts[name]
        target = targets.get(name)
        row: dict[str, object] = {
            "class_id": class_id,
            "class_name": name,
            "count": count,
        }
        if target is not None:
            row["min_target"] = target.min_target
            row["recommended_target"] = target.recommended_target
            row["ideal_target"] = target.ideal_target
            row["pct_of_min"] = (
                round(100 * count / target.min_target, 1)
                if target.min_target
                else None
            )
            if target.min_target and count >= target.min_target:
                met_min += 1
            if target.recommended_target and count >= target.recommended_target:
                met_recommended += 1
            if target.ideal_target and count >= target.ideal_target:
                met_ideal += 1
        classes.append(row)

    return {
        "images_dir": images_dir.as_posix(),
        "taxonomy_version": taxonomy.version,
        "num_classes": taxonomy.num_classes,
        "summary": {
            "total_images": total,
            "classified_images": classified,
            "unclassified_images": unclassified,
            "missing_classes": missing,
            "num_missing_classes": len(missing),
            "imbalance_ratio": _imbalance_ratio(counts),
            "classes_meeting_min": met_min,
            "classes_meeting_recommended": met_recommended,
            "classes_meeting_ideal": met_ideal,
            "has_targets": bool(targets),
        },
        "classes": classes,
    }


def render_markdown(report: dict[str, object]) -> str:
    """Render a progress report as a Markdown document.

    Args:
        report: The mapping produced by :func:`build_progress`.

    Returns:
        A Markdown string.
    """
    summary = report["summary"]
    has_targets = summary["has_targets"]
    lines: list[str] = []
    lines.append("# Dataset Collection Progress")
    lines.append("")
    lines.append(f"- **Images directory:** `{report['images_dir']}`")
    lines.append(
        f"- **Taxonomy:** version {report['taxonomy_version']} "
        f"({report['num_classes']} classes)"
    )
    lines.append(f"- **Total images:** {summary['total_images']}")
    lines.append(f"- **Unclassified images:** {summary['unclassified_images']}")
    ratio = summary["imbalance_ratio"]
    lines.append(
        f"- **Class imbalance (max/min):** {ratio if ratio is not None else 'n/a'}"
    )
    lines.append(
        f"- **Missing classes:** {summary['num_missing_classes']}"
        + (
            f" ({', '.join(summary['missing_classes'])})"
            if summary["missing_classes"]
            else ""
        )
    )
    if has_targets:
        lines.append(
            f"- **Classes meeting min / recommended / ideal:** "
            f"{summary['classes_meeting_min']} / "
            f"{summary['classes_meeting_recommended']} / "
            f"{summary['classes_meeting_ideal']} of {report['num_classes']}"
        )
    lines.append("")

    if has_targets:
        lines.append("| ID | Class | Count | Min | Rec | Ideal | % of Min | Status |")
        lines.append("| ---: | --- | ---: | ---: | ---: | ---: | ---: | --- |")
    else:
        lines.append("| ID | Class | Count | Status |")
        lines.append("| ---: | --- | ---: | --- |")

    for row in report["classes"]:
        count = row["count"]
        if has_targets:
            min_t = row.get("min_target", 0)
            status = "empty" if count == 0 else ("ok" if count >= min_t else "under")
            pct = row.get("pct_of_min")
            pct_s = f"{pct}%" if pct is not None else "n/a"
            lines.append(
                f"| {row['class_id']} | {row['class_name']} | {count} | "
                f"{min_t} | {row.get('recommended_target', 0)} | "
                f"{row.get('ideal_target', 0)} | {pct_s} | {status} |"
            )
        else:
            status = "empty" if count == 0 else "collected"
            lines.append(
                f"| {row['class_id']} | {row['class_name']} | {count} | {status} |"
            )
    lines.append("")
    return "\n".join(lines)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Report dataset-collection progress by taxonomy class: per-class "
            "counts, imbalance, missing classes, and progress vs targets."
        )
    )
    parser.add_argument("images_dir", type=Path, help="Directory of collected images.")
    parser.add_argument(
        "--targets",
        type=Path,
        default=None,
        metavar="CSV",
        help=(
            "Per-class targets CSV (collection_progress.csv shape). Defaults to "
            "the packaged docs/ai/templates/collection_progress.csv."
        ),
    )
    parser.add_argument(
        "--json", type=Path, default=None, metavar="PATH", help="Write JSON to PATH."
    )
    parser.add_argument(
        "--markdown",
        type=Path,
        default=None,
        metavar="PATH",
        help="Write Markdown to PATH.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress stdout (still writes any requested files).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point.

    Args:
        argv: Optional argument vector (defaults to ``sys.argv[1:]``).

    Returns:
        Process exit code: 0 on success, 2 on usage error.
    """
    args = _parse_args(argv)
    images_dir: Path = args.images_dir
    if not images_dir.is_dir():
        print(f"error: not a directory: {images_dir}", file=sys.stderr)
        return 2

    taxonomy = load_taxonomy()
    targets = load_targets(args.targets)
    report = build_progress(images_dir, taxonomy, targets)
    markdown = render_markdown(report)

    if args.json is not None:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    if args.markdown is not None:
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.write_text(markdown + "\n", encoding="utf-8")
    if not args.quiet:
        print(markdown)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())


