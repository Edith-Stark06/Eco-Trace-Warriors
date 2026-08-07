"""Render a one-page dashboard for the Dataset v1.0 collection effort.

Phase 4.2.1 — Production Image Collection Toolkit (PART 4).

Aggregates a staging directory of collected images into a single Markdown
(default) or HTML dashboard summarising:

* **total images** and total size;
* **class distribution** and progress toward the Dataset v1.0 targets;
* **contributor statistics** (from a merged provenance manifest, or inferred
  from the staging sub-folder each image sits in);
* **validation failures** grouped by issue code;
* **duplicate statistics** (exact and near-duplicate groups).

Every metric is computed by reusing existing pieces: the sibling
``dataset_progress`` and ``validate_image_batch`` scripts, plus the frozen
``MetadataGenerator`` and ``DuplicateDetector`` from the P4.1.2 pipeline. This
script only assembles and formats their output; it reads the staging set and
writes nothing back to it, and touches no API.

Usage (from the repository root)::

    python scripts/collection_dashboard.py <staging_dir>
        [--manifest merged_manifest.json] [--targets collection_progress.csv]
        [--format markdown|html] [--output dashboard.md]
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path

from _ecotrace_toolkit import REPO_ROOT  # noqa: F401  (ensures device_ai on path)
from dataset_progress import build_progress, load_targets
from device_ai.configs.settings import Settings
from device_ai.dataset.duplicates import DuplicateDetector
from device_ai.dataset.layout import list_image_paths
from device_ai.dataset.metadata import MetadataGenerator
from device_ai.dataset.taxonomy import load_taxonomy
from validate_image_batch import build_report as build_validation_report
from validate_image_batch import validate_batch


def _contributor_stats(
    staging_dir: Path, manifest_path: Path | None
) -> list[dict[str, object]]:
    """Compute per-contributor image counts.

    When a merged provenance manifest is supplied (PART 3 output), contributors
    are read straight from its records. Otherwise each image is attributed to
    the first path segment beneath ``staging_dir`` — the namespace the merge
    step assigns — falling back to ``"(unattributed)"`` for loose files.

    Args:
        staging_dir: The staging directory being summarised.
        manifest_path: Optional merged provenance manifest JSON.

    Returns:
        A list of ``{"contributor", "images"}`` rows sorted by descending count.
    """
    counts: dict[str, int] = {}

    if manifest_path is not None and manifest_path.is_file():
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        records = raw.get("provenance", {}).get("records", raw.get("records", []))
        for record in records:
            name = record.get("contributor") or "(unattributed)"
            counts[name] = counts.get(name, 0) + 1
    else:
        for path in list_image_paths(staging_dir):
            rel = path.relative_to(staging_dir)
            name = rel.parts[0] if len(rel.parts) > 1 else "(unattributed)"
            counts[name] = counts.get(name, 0) + 1

    return [
        {"contributor": name, "images": count}
        for name, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    ]


def build_dashboard(
    staging_dir: Path,
    settings: Settings,
    *,
    targets_path: Path | None,
    manifest_path: Path | None,
) -> dict[str, object]:
    """Assemble every dashboard section into one JSON-serialisable mapping.

    Args:
        staging_dir: Directory of collected images to summarise.
        settings: Injected application settings.
        targets_path: Optional per-class targets CSV.
        manifest_path: Optional merged provenance manifest JSON.

    Returns:
        A primitive-only mapping with the dashboard data.
    """
    taxonomy = load_taxonomy()

    # Class distribution + progress toward v1.0 (reuses PART 2).
    progress = build_progress(staging_dir, taxonomy, load_targets(targets_path))

    # Quality + duplicates (reuses frozen pipeline modules).
    records = MetadataGenerator.from_settings(settings).analyze_directory(staging_dir)
    duplicates = DuplicateDetector.from_settings(settings).detect(records)
    total_size = sum(r.size_bytes for r in records)

    # Validation failures (reuses PART 1).
    issues = validate_batch(staging_dir, settings, quality_blocking=True)
    validation = build_validation_report(staging_dir, issues)

    exact = sum(1 for p in duplicates.pairs if p.exact)
    near = sum(1 for p in duplicates.pairs if not p.exact)

    return {
        "staging_dir": staging_dir.as_posix(),
        "taxonomy_version": taxonomy.version,
        "totals": {
            "total_images": len(records),
            "total_size_mb": round(total_size / (1024 * 1024), 3),
            "missing_classes": progress["summary"]["num_missing_classes"],
            "imbalance_ratio": progress["summary"]["imbalance_ratio"],
        },
        "progress": progress,
        "contributors": _contributor_stats(staging_dir, manifest_path),
        "validation": validation["summary"],
        "duplicates": {
            "total_images": duplicates.total_images,
            "duplicate_images": duplicates.num_duplicates,
            "unique_images": duplicates.num_unique,
            "exact_pairs": exact,
            "near_duplicate_pairs": near,
        },
    }


def render_markdown(dashboard: dict[str, object]) -> str:
    """Render the dashboard as a Markdown document.

    Args:
        dashboard: The mapping produced by :func:`build_dashboard`.

    Returns:
        A Markdown string.
    """
    totals = dashboard["totals"]
    dup = dashboard["duplicates"]
    val = dashboard["validation"]
    lines: list[str] = []
    lines.append("# Dataset v1.0 - Collection Dashboard")
    lines.append("")
    lines.append(f"- **Staging directory:** `{dashboard['staging_dir']}`")
    lines.append(f"- **Taxonomy version:** {dashboard['taxonomy_version']}")
    lines.append(f"- **Total images:** {totals['total_images']}")
    lines.append(f"- **Total size:** {totals['total_size_mb']} MB")
    lines.append(f"- **Missing classes:** {totals['missing_classes']}")
    ratio = totals["imbalance_ratio"]
    lines.append(f"- **Class imbalance (max/min):** {ratio if ratio else 'n/a'}")
    lines.append("")

    lines.append("## Contributors")
    lines.append("")
    lines.append("| Contributor | Images |")
    lines.append("| --- | ---: |")
    for row in dashboard["contributors"]:
        lines.append(f"| {row['contributor']} | {row['images']} |")
    lines.append("")

    lines.append("## Validation failures")
    lines.append("")
    lines.append(f"- **Blocking issues:** {val['blocking']}")
    lines.append(f"- **Warnings:** {val['warnings']}")
    lines.append(f"- **Images with blocking issues:** {val['images_with_blocking_issues']}")
    if val["by_code"]:
        lines.append("")
        lines.append("| Issue code | Count |")
        lines.append("| --- | ---: |")
        for code, count in val["by_code"].items():
            lines.append(f"| {code} | {count} |")
    lines.append("")

    lines.append("## Duplicates")
    lines.append("")
    lines.append(f"- **Exact-duplicate pairs:** {dup['exact_pairs']}")
    lines.append(f"- **Near-duplicate pairs:** {dup['near_duplicate_pairs']}")
    lines.append(f"- **Duplicate images:** {dup['duplicate_images']}")
    lines.append(f"- **Unique images:** {dup['unique_images']}")
    lines.append("")

    lines.append("## Class distribution")
    lines.append("")
    lines.append("| ID | Class | Count | Min target | % of min |")
    lines.append("| ---: | --- | ---: | ---: | ---: |")
    for row in dashboard["progress"]["classes"]:
        pct = row.get("pct_of_min")
        pct_s = f"{pct}%" if pct is not None else "n/a"
        lines.append(
            f"| {row['class_id']} | {row['class_name']} | {row['count']} | "
            f"{row.get('min_target', 'n/a')} | {pct_s} |"
        )
    lines.append("")
    return "\n".join(lines)


def _html_table(headers: list[str], rows: list[list[str]]) -> str:
    """Return a minimal HTML table for the given headers and rows."""
    head = "".join(f"<th>{html.escape(h)}</th>" for h in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{html.escape(str(c))}</td>" for c in row) + "</tr>"
        for row in rows
    )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def render_html(dashboard: dict[str, object]) -> str:
    """Render the dashboard as a self-contained HTML document.

    Args:
        dashboard: The mapping produced by :func:`build_dashboard`.

    Returns:
        An HTML string with inline styling (no external assets).
    """
    totals = dashboard["totals"]
    dup = dashboard["duplicates"]
    val = dashboard["validation"]
    ratio = totals["imbalance_ratio"]

    contributors = _html_table(
        ["Contributor", "Images"],
        [[r["contributor"], r["images"]] for r in dashboard["contributors"]],
    )
    codes = _html_table(
        ["Issue code", "Count"],
        [[code, count] for code, count in val["by_code"].items()],
    )
    classes = _html_table(
        ["ID", "Class", "Count", "Min target", "% of min"],
        [
            [
                row["class_id"],
                row["class_name"],
                row["count"],
                row.get("min_target", "n/a"),
                f"{row['pct_of_min']}%" if row.get("pct_of_min") is not None else "n/a",
            ]
            for row in dashboard["progress"]["classes"]
        ],
    )
    style = (
        "body{font-family:system-ui,Arial,sans-serif;margin:2rem;max-width:60rem}"
        "table{border-collapse:collapse;margin:0.5rem 0}"
        "th,td{border:1px solid #ccc;padding:0.3rem 0.6rem;text-align:left}"
        "th{background:#f2f2f2}h1{margin-bottom:0.2rem}"
    )
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<title>Dataset v1.0 Collection Dashboard</title>"
        f"<style>{style}</style></head><body>"
        "<h1>Dataset v1.0 &mdash; Collection Dashboard</h1>"
        f"<p><b>Staging directory:</b> <code>{html.escape(dashboard['staging_dir'])}</code><br>"
        f"<b>Taxonomy version:</b> {html.escape(str(dashboard['taxonomy_version']))}<br>"
        f"<b>Total images:</b> {totals['total_images']} "
        f"({totals['total_size_mb']} MB)<br>"
        f"<b>Missing classes:</b> {totals['missing_classes']}<br>"
        f"<b>Class imbalance (max/min):</b> {ratio if ratio else 'n/a'}</p>"
        "<h2>Contributors</h2>" + contributors + "<h2>Validation failures</h2>"
        f"<p>Blocking: {val['blocking']} &middot; Warnings: {val['warnings']} &middot; "
        f"Images with blocking issues: {val['images_with_blocking_issues']}</p>"
        + (codes if val["by_code"] else "<p>No validation issues.</p>")
        + "<h2>Duplicates</h2>"
        f"<p>Exact pairs: {dup['exact_pairs']} &middot; "
        f"Near-duplicate pairs: {dup['near_duplicate_pairs']} &middot; "
        f"Duplicate images: {dup['duplicate_images']} &middot; "
        f"Unique images: {dup['unique_images']}</p>"
        "<h2>Class distribution</h2>" + classes + "</body></html>"
    )


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Render a Markdown/HTML dashboard for the Dataset v1.0 collection "
            "effort (totals, class distribution, contributors, validation "
            "failures, duplicates, progress)."
        )
    )
    parser.add_argument(
        "staging_dir", type=Path, help="Directory of collected images to summarise."
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=None,
        metavar="JSON",
        help="Merged provenance manifest (PART 3 output) for contributor stats.",
    )
    parser.add_argument(
        "--targets",
        type=Path,
        default=None,
        metavar="CSV",
        help="Per-class targets CSV (defaults to the packaged template).",
    )
    parser.add_argument(
        "--format",
        choices=("markdown", "html"),
        default="markdown",
        help="Output format (default: markdown).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        metavar="PATH",
        help="Write the dashboard to PATH (otherwise printed to stdout).",
    )
    parser.add_argument(
        "--json",
        type=Path,
        default=None,
        metavar="PATH",
        help="Additionally write the raw dashboard data as JSON to PATH.",
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
    staging_dir: Path = args.staging_dir
    if not staging_dir.is_dir():
        print(f"error: not a directory: {staging_dir}", file=sys.stderr)
        return 2

    settings = Settings()
    dashboard = build_dashboard(
        staging_dir,
        settings,
        targets_path=args.targets,
        manifest_path=args.manifest,
    )

    rendered = (
        render_html(dashboard)
        if args.format == "html"
        else render_markdown(dashboard)
    )

    if args.json is not None:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(dashboard, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())


