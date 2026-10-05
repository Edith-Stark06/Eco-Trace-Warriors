"""Render YOLO annotation previews for Dataset v1.0 (Sprint P4.2.2, PART 3).

Draws every bounding box from a YOLO ``.txt`` label onto a copy of its image and
writes the annotated preview into ``output/previews/`` (configurable). Originals
are opened read-only and never modified — each preview is a freshly encoded copy.

Three selection modes:

* ``--image PATH`` — a single image;
* ``--images-root DIR`` — every labelled image beneath a directory;
* ``--images-root DIR --sample N`` — a deterministic random sample of N images
  (seeded via ``--seed`` for reproducibility).

Boxes are parsed through the shared, frozen-backed reader and labelled with the
canonical class name from the frozen taxonomy. Requires Pillow (already a
``device_ai`` runtime dependency).

Exit codes:
    0: previews rendered (or nothing to render).
    2: usage error (bad arguments / missing paths).

Examples:
    python scripts/visualize_annotations.py \
        --image datasets/raw/laptop_field_000001.jpg \
        --labels-root datasets/labels --images-root datasets/raw
    python scripts/visualize_annotations.py \
        --images-root datasets/raw --labels-root datasets/labels \
        --sample 20 --seed 42
"""

from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

from _annotation_toolkit import read_label_boxes
from PIL import Image, ImageDraw

from device_ai.dataset.layout import label_path_for, list_image_paths, relative_path
from device_ai.dataset.taxonomy import load_taxonomy
from device_ai.dataset.validator import YoloBox

# Default output directory for rendered previews (relative to the repo root).
_DEFAULT_OUTPUT = Path("output/previews")
# Box outline colour and width, and the label text colour.
_BOX_COLOR = (255, 0, 0)
_TEXT_COLOR = (255, 255, 255)
_TEXT_BG = (255, 0, 0)
_OUTLINE_WIDTH = 3


def _denormalize(box: YoloBox, width: int, height: int) -> tuple[int, int, int, int]:
    """Convert a normalised YOLO box to pixel ``(left, top, right, bottom)``.

    The result is clamped to the image bounds so a slightly out-of-frame box
    still renders a visible rectangle rather than drawing off-canvas.

    Args:
        box: A parsed YOLO bounding box.
        width: Image width in pixels.
        height: Image height in pixels.

    Returns:
        A pixel-space ``(left, top, right, bottom)`` tuple.
    """
    cx = box.x_center * width
    cy = box.y_center * height
    half_w = box.width * width / 2.0
    half_h = box.height * height / 2.0
    left = int(max(0, min(width - 1, round(cx - half_w))))
    top = int(max(0, min(height - 1, round(cy - half_h))))
    right = int(max(0, min(width - 1, round(cx + half_w))))
    bottom = int(max(0, min(height - 1, round(cy + half_h))))
    return left, top, right, bottom


def render_preview(
    image_path: Path,
    label_path: Path,
    output_path: Path,
    *,
    class_names: tuple[str, ...],
) -> int:
    """Render one annotated preview from an image and its label file.

    Args:
        image_path: Source image (opened read-only).
        label_path: YOLO label file for the image (may not exist).
        output_path: Destination preview path (parents created as needed).
        class_names: Canonical taxonomy class names for labelling boxes.

    Returns:
        The number of boxes drawn (0 when there is no label or no boxes).
    """
    with Image.open(image_path) as opened:
        canvas = opened.convert("RGB")
    width, height = canvas.width, canvas.height
    boxes = read_label_boxes(label_path) if label_path.exists() else []

    draw = ImageDraw.Draw(canvas)
    for box in boxes:
        left, top, right, bottom = _denormalize(box, width, height)
        draw.rectangle(
            (left, top, right, bottom),
            outline=_BOX_COLOR,
            width=_OUTLINE_WIDTH,
        )
        name = (
            class_names[box.class_id]
            if 0 <= box.class_id < len(class_names)
            else str(box.class_id)
        )
        text_pos = (left, max(0, top - 12))
        draw.rectangle(
            (
                text_pos[0],
                text_pos[1],
                text_pos[0] + 6 * len(name) + 4,
                text_pos[1] + 12,
            ),
            fill=_TEXT_BG,
        )
        draw.text((text_pos[0] + 2, text_pos[1]), name, fill=_TEXT_COLOR)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path)
    return len(boxes)


def _select_images(
    args: argparse.Namespace, images_root: Path
) -> list[Path]:
    """Resolve the set of image paths to render from CLI selection flags.

    Args:
        args: Parsed arguments (``image``, ``sample``, ``seed``).
        images_root: The root the images live under.

    Returns:
        The chosen image paths (sorted, or a deterministic random sample).
    """
    if args.image is not None:
        return [args.image]
    images = list_image_paths(images_root)
    if args.sample is not None and args.sample < len(images):
        rng = random.Random(args.seed)
        return sorted(rng.sample(images, args.sample))
    return images


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Render YOLO annotation previews (bounding boxes drawn).",
    )
    parser.add_argument(
        "--image",
        type=Path,
        default=None,
        help="Render a single image (requires --images-root for label pairing).",
    )
    parser.add_argument(
        "--images-root",
        type=Path,
        default=None,
        help="Directory containing the dataset images.",
    )
    parser.add_argument(
        "--labels-root",
        required=True,
        type=Path,
        help="Directory containing the YOLO .txt label files.",
    )
    parser.add_argument(
        "--sample",
        type=int,
        default=None,
        help="Render a deterministic random sample of N images from the root.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="RNG seed for --sample (default 42).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=_DEFAULT_OUTPUT,
        help="Destination directory for previews (default output/previews).",
    )
    return parser.parse_args(argv)


def _resolve_roots(args: argparse.Namespace) -> tuple[Path, Path] | None:
    """Validate and resolve the images root for the chosen selection mode.

    Args:
        args: Parsed arguments.

    Returns:
        A ``(images_root, first_image_or_root)`` pair on success, or ``None``
        when the arguments are invalid (an error is printed to stderr).
    """
    if args.image is not None:
        if not args.image.is_file():
            print(f"error: image not found: {args.image}", file=sys.stderr)
            return None
        images_root = (
            args.images_root if args.images_root is not None else args.image.parent
        )
        return images_root, args.image
    if args.images_root is None:
        print("error: provide --image or --images-root", file=sys.stderr)
        return None
    if not args.images_root.is_dir():
        print(f"error: images root not found: {args.images_root}", file=sys.stderr)
        return None
    return args.images_root, args.images_root


def main(argv: list[str] | None = None) -> int:
    """Entry point for the annotation visualiser.

    Args:
        argv: Optional argument vector (defaults to ``sys.argv``).

    Returns:
        A process exit code (0 success, 2 usage error).
    """
    args = _parse_args(argv)
    if not args.labels_root.is_dir():
        print(f"error: labels root not found: {args.labels_root}", file=sys.stderr)
        return 2
    resolved = _resolve_roots(args)
    if resolved is None:
        return 2
    images_root, _ = resolved

    class_names = load_taxonomy().class_names
    images = _select_images(args, images_root)

    rendered = 0
    total_boxes = 0
    for image_path in images:
        label_path = label_path_for(image_path, images_root, args.labels_root)
        rel = relative_path(image_path, images_root)
        output_path = args.output_dir / rel
        drawn = render_preview(
            image_path, label_path, output_path, class_names=class_names
        )
        rendered += 1
        total_boxes += drawn
        print(f"rendered {rel} ({drawn} boxes) -> {output_path.as_posix()}")

    print(
        f"done: {rendered} preview(s), {total_boxes} box(es) drawn, "
        f"output in {args.output_dir.as_posix()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
