"""Annotation statistics for Dataset v1.0 (Sprint P4.2.2, PART 2).

This CLI composes the **frozen** P4.1.2
:class:`~device_ai.dataset.annotation_statistics.AnnotationStatisticsCalculator`
(class distribution, bounding-box min/max/mean, orphan/missing labels,
completeness) and layers the distribution/aggregate views the sprint asks for
but the frozen calculator does not itself expose:

* bounding-box **width**, **height** and **object-size (area)** histograms;
* per-image object counts, surfacing **images with many annotations**;
* **per-class averages** (mean boxes per image that contains the class).

Every box is parsed through the shared, frozen-backed reader, so no parsing is
re-implemented. Output is machine-readable JSON and a human-readable Markdown
report.

Exit codes:
    0: statistics generated.
    2: usage error (missing directories).

Examples:
    python scripts/annotation_statistics.py \
        --images-root datasets/raw --labels-root datasets/labels
    python scripts/annotation_statistics.py \
        --images-root datasets/raw --labels-root datasets/labels \
        --many-threshold 10 --bins 10 --json-out stats.json --md-out stats.md
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from _annotation_toolkit import iter_label_boxes

from device_ai.dataset.annotation_statistics import (
    AnnotationStatisticsCalculator,
    annotation_statistics_to_dict,
)
from device_ai.dataset.layout import label_path_for, list_image_paths, relative_path
from device_ai.dataset.taxonomy import load_taxonomy

# Default number of buckets for the width/height/area histograms.
_DEFAULT_BINS = 10
# Default per-image box count at or above which an image is "heavily annotated".
_DEFAULT_MANY_THRESHOLD = 10


def _histogram(values: list[float], *, bins: int) -> list[dict[str, object]]:
    """Bucket ``values`` over ``[0, 1]`` into ``bins`` equal-width buckets.

    Widths, heights and areas are all normalised YOLO quantities in ``[0, 1]``,
    so a fixed ``[0, 1]`` domain keeps histograms comparable across datasets.
    The final bucket is closed on the right so a value of exactly ``1.0`` lands
    in the last bucket rather than overflowing.

    Args:
        values: Normalised values in ``[0, 1]``.
        bins: Number of equal-width buckets (>= 1).

    Returns:
        One row per bucket with ``range`` and ``count`` keys.
    """
    bins = max(1, bins)
    counts = [0] * bins
    for value in values:
        clamped = min(max(value, 0.0), 1.0)
        index = min(int(clamped * bins), bins - 1)
        counts[index] += 1
    rows: list[dict[str, object]] = []
    for i, count in enumerate(counts):
        lo = round(i / bins, 4)
        hi = round((i + 1) / bins, 4)
        rows.append({"range": f"{lo:.4f}-{hi:.4f}", "count": count})
    return rows


def _collect_geometry(
    *, images_root: Path, labels_root: Path
) -> tuple[list[float], list[float], list[float], list[tuple[str, int]]]:
    """Gather box widths, heights, areas and per-image box counts.

    Args:
        images_root: Directory containing the images.
        labels_root: Directory containing the YOLO ``.txt`` labels.

    Returns:
        ``(widths, heights, areas, per_image_counts)`` where each per-image
        entry is ``(image_relative_path, box_count)`` for labelled images only.
    """
    widths: list[float] = []
    heights: list[float] = []
    areas: list[float] = []
    per_image: list[tuple[str, int]] = []
    for image_path in list_image_paths(images_root):
        label_path = label_path_for(image_path, images_root, labels_root)
        if not label_path.exists():
            continue
        count = 0
        for _, box in iter_label_boxes(label_path):
            widths.append(box.width)
            heights.append(box.height)
            areas.append(box.width * box.height)
            count += 1
        per_image.append((relative_path(image_path, images_root), count))
    return widths, heights, areas, per_image


def _per_class_averages(
    *, images_root: Path, labels_root: Path, class_names: tuple[str, ...]
) -> list[dict[str, object]]:
    """Compute the mean number of boxes per image that contains each class.

    Args:
        images_root: Directory containing the images.
        labels_root: Directory containing the YOLO ``.txt`` labels.
        class_names: Canonical taxonomy class names (index == class id).

    Returns:
        One row per class with ``class_id``, ``class_name``, ``images_present``,
        ``total_boxes`` and ``avg_boxes_per_image``.
    """
    images_present = [0] * len(class_names)
    total_boxes = [0] * len(class_names)
    for image_path in list_image_paths(images_root):
        label_path = label_path_for(image_path, images_root, labels_root)
        if not label_path.exists():
            continue
        per_class: dict[int, int] = {}
        for _, box in iter_label_boxes(label_path):
            if 0 <= box.class_id < len(class_names):
                per_class[box.class_id] = per_class.get(box.class_id, 0) + 1
        for class_id, count in per_class.items():
            images_present[class_id] += 1
            total_boxes[class_id] += count
    rows: list[dict[str, object]] = []
    for class_id, name in enumerate(class_names):
        present = images_present[class_id]
        boxes = total_boxes[class_id]
        avg = round(boxes / present, 4) if present else 0.0
        rows.append(
            {
                "class_id": class_id,
                "class_name": name,
                "images_present": present,
                "total_boxes": boxes,
                "avg_boxes_per_image": avg,
            }
        )
    return rows


def build_statistics(
    *,
    images_root: Path,
    labels_root: Path,
    bins: int,
    many_threshold: int,
) -> dict[str, object]:
    """Assemble the full annotation-statistics payload.

    Args:
        images_root: Directory containing the images.
        labels_root: Directory containing the YOLO ``.txt`` labels.
        bins: Histogram bucket count.
        many_threshold: Per-image box count flagged as heavily annotated.

    Returns:
        A JSON-serialisable statistics document.
    """
    taxonomy = load_taxonomy()
    calculator = AnnotationStatisticsCalculator(taxonomy)
    core = calculator.compute(images_root=images_root, labels_root=labels_root)

    widths, heights, areas, per_image = _collect_geometry(
        images_root=images_root, labels_root=labels_root
    )
    many = sorted(
        (
            {"image": path, "boxes": count}
            for path, count in per_image
            if count >= many_threshold
        ),
        key=lambda row: (-int(row["boxes"]), str(row["image"])),
    )
    labelled_counts = [count for _, count in per_image]
    avg_boxes_per_labelled = (
        round(sum(labelled_counts) / len(labelled_counts), 4)
        if labelled_counts
        else 0.0
    )

    return {
        "core": annotation_statistics_to_dict(core),
        "object_count": core.total_boxes,
        "avg_boxes_per_labelled_image": avg_boxes_per_labelled,
        "histograms": {
            "bins": max(1, bins),
            "width": _histogram(widths, bins=bins),
            "height": _histogram(heights, bins=bins),
            "area": _histogram(areas, bins=bins),
        },
        "many_annotations": {
            "threshold": many_threshold,
            "count": len(many),
            "images": many,
        },
        "per_class_averages": _per_class_averages(
            images_root=images_root,
            labels_root=labels_root,
            class_names=taxonomy.class_names,
        ),
    }


def _render_histogram(title: str, rows: list[dict[str, object]]) -> list[str]:
    """Render one histogram as Markdown table lines."""
    lines = [f"### {title}", "", "| Range | Count |", "| --- | --- |"]
    lines.extend(f"| {row['range']} | {row['count']} |" for row in rows)
    lines.append("")
    return lines


def render_markdown(payload: dict[str, object]) -> str:
    """Render the statistics payload as a human-readable Markdown report.

    Args:
        payload: The dict produced by :func:`build_statistics`.

    Returns:
        A Markdown document (ASCII only).
    """
    core = payload["core"]
    assert isinstance(core, dict)
    hist = payload["histograms"]
    assert isinstance(hist, dict)
    many = payload["many_annotations"]
    assert isinstance(many, dict)

    lines = [
        "# Annotation Statistics",
        "",
        f"- Taxonomy version: {core['taxonomy_version']}",
        f"- Total images: {core['total_images']}",
        f"- Labelled images: {core['total_labelled_images']}",
        f"- Total objects (boxes): {payload['object_count']}",
        f"- Mean boxes per labelled image: {payload['avg_boxes_per_labelled_image']}",
        f"- Annotation completeness: {core['annotation_completeness']}",
        f"- Images without labels: {len(core['images_without_labels'])}",
        f"- Orphan labels: {len(core['orphan_labels'])}",
        "",
        "## Class distribution",
        "",
        "| ID | Class | Count |",
        "| --- | --- | --- |",
    ]
    dist = core["class_distribution"]
    assert isinstance(dist, list)
    for entry in dist:
        assert isinstance(entry, dict)
        lines.append(
            f"| {entry['class_id']} | {entry['class_name']} | {entry['count']} |"
        )

    lines.extend(["", "## Per-class averages", ""])
    lines.append("| ID | Class | Images w/ class | Total boxes | Avg boxes/image |")
    lines.append("| --- | --- | --- | --- | --- |")
    per_class = payload["per_class_averages"]
    assert isinstance(per_class, list)
    for row in per_class:
        assert isinstance(row, dict)
        lines.append(
            f"| {row['class_id']} | {row['class_name']} | "
            f"{row['images_present']} | {row['total_boxes']} | "
            f"{row['avg_boxes_per_image']} |"
        )

    lines.extend(["", "## Bounding-box distributions", ""])
    lines.extend(_render_histogram("Width", hist["width"]))
    lines.extend(_render_histogram("Height", hist["height"]))
    lines.extend(_render_histogram("Object size (area)", hist["area"]))

    lines.extend(
        [
            "## Images with many annotations",
            "",
            f"Threshold: {many['threshold']} boxes. Flagged: {many['count']} images.",
            "",
        ]
    )
    images = many["images"]
    assert isinstance(images, list)
    if images:
        lines.append("| Image | Boxes |")
        lines.append("| --- | --- |")
        for row in images:
            assert isinstance(row, dict)
            lines.append(f"| `{row['image']}` | {row['boxes']} |")
    else:
        lines.append("None.")
    lines.append("")
    return "\n".join(lines)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Generate annotation statistics for Dataset v1.0.",
    )
    parser.add_argument(
        "--images-root",
        required=True,
        type=Path,
        help="Directory containing the dataset images.",
    )
    parser.add_argument(
        "--labels-root",
        required=True,
        type=Path,
        help="Directory containing the YOLO .txt label files.",
    )
    parser.add_argument(
        "--bins",
        type=int,
        default=_DEFAULT_BINS,
        help=f"Histogram bucket count (default {_DEFAULT_BINS}).",
    )
    parser.add_argument(
        "--many-threshold",
        type=int,
        default=_DEFAULT_MANY_THRESHOLD,
        help=(
            "Per-image box count at or above which an image is flagged as "
            f"heavily annotated (default {_DEFAULT_MANY_THRESHOLD})."
        ),
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        default=None,
        help="Optional path to write the JSON statistics.",
    )
    parser.add_argument(
        "--md-out",
        type=Path,
        default=None,
        help="Optional path to write the Markdown report.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point for the annotation statistics tool.

    Args:
        argv: Optional argument vector (defaults to ``sys.argv``).

    Returns:
        A process exit code (0 success, 2 usage error).
    """
    args = _parse_args(argv)
    if not args.images_root.is_dir():
        print(f"error: images root not found: {args.images_root}", file=sys.stderr)
        return 2
    if not args.labels_root.is_dir():
        print(f"error: labels root not found: {args.labels_root}", file=sys.stderr)
        return 2

    payload = build_statistics(
        images_root=args.images_root,
        labels_root=args.labels_root,
        bins=args.bins,
        many_threshold=args.many_threshold,
    )
    text = json.dumps(payload, indent=2, sort_keys=True)
    if args.json_out is not None:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(text + "\n", encoding="utf-8")
    if args.md_out is not None:
        args.md_out.parent.mkdir(parents=True, exist_ok=True)
        args.md_out.write_text(render_markdown(payload), encoding="utf-8")

    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
