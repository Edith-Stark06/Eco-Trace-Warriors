"""Class-agnostic visual QA preview generator (P4.3.2 multi-class expansion).

A manual-review checkpoint tool — **not** production tooling and **not** part of
the frozen pipeline. For one per-class staging directory it renders one
annotated preview per staged image (converted YOLO boxes overlaid, captioned
with source/canonical filename, box count, dimensions, blur and a QA item id),
tiles them into a single contact sheet, and writes a deterministic
``qa_data.json`` describing every tile.

It is a direct, class-agnostic generalisation of the laptop pilot's
``make_visual_qa.py``: the box tag and canonical class name are resolved from
the **frozen taxonomy** (never hardcoded), and the blur metric reuses the frozen
``device_ai.dataset.metadata.blur_score`` so numbers agree with P4.2.1 / the
pilot. It is strictly read-only w.r.t. the staged dataset: it reads
``images/`` + ``labels/`` and writes previews only under the output directory.

Generating previews is **not** QA sign-off: every image stays ``QA_PENDING``
until a human reviewer records a decision. The emitted ``qa_data.json`` carries
``"qa_status": "QA_PENDING"`` to make that explicit.

Usage (from repo root, with ``$BATCH`` = the multi-class staging batch dir
``dataset_acquisition/staging/openimages_multiclass_v1``):
    python scripts/make_visual_qa_multiclass.py \
        --staging-root $BATCH/openimages_tablet_v1 \
        --out-dir      $BATCH/openimages_tablet_v1/manual_review

Exit codes:
    0: previews + contact sheet + qa_data.json written.
    2: usage error (staging images/labels not found).
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from _ecotrace_toolkit import REPO_ROOT  # noqa: F401  (triggers device_ai bootstrap)
from PIL import Image, ImageDraw, ImageFont

from device_ai.dataset.metadata import blur_score
from device_ai.dataset.taxonomy import load_taxonomy

_EXIT_OK = 0
_EXIT_USAGE = 2

_BOX_COLOR = (0, 220, 60)
_BOX_OUTLINE_W = 3
_LABEL_BG = (0, 0, 0)
_LABEL_FG = (255, 255, 255)
_CAPTION_BG = (18, 18, 18)
_CAPTION_FG = (245, 245, 245)
_BLUR_FG = (255, 170, 0)

_QA_PENDING = "QA_PENDING"


@dataclass(frozen=True, slots=True)
class Tile:
    """One rendered preview ready for the contact sheet and qa_data.json."""

    qa_id: int
    stem: str
    filename: str
    width: int
    height: int
    box_count: int
    blur: float
    is_blurry: bool
    class_ids: tuple[int, ...]
    preview_path: Path


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Return a truetype font if available, else the PIL default."""
    for name in ("arial.ttf", "DejaVuSans.ttf", "LiberationSans-Regular.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _read_yolo(label_path: Path) -> list[tuple[int, float, float, float, float]]:
    """Parse a YOLO label file into ``(class_id, cx, cy, w, h)`` tuples."""
    boxes: list[tuple[int, float, float, float, float]] = []
    if not label_path.exists():
        return boxes
    for raw in label_path.read_text(encoding="utf-8").splitlines():
        parts = raw.split()
        if len(parts) != 5:
            continue
        cid = int(parts[0])
        cx, cy, bw, bh = (float(v) for v in parts[1:])
        boxes.append((cid, cx, cy, bw, bh))
    return boxes


def _draw_caption(
    draw: ImageDraw.ImageDraw,
    text: str,
    *,
    width: int,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    color: tuple[int, int, int],
) -> None:
    """Draw a single-line caption bar across the top of a preview."""
    draw.rectangle([0, 0, width, 26], fill=_LABEL_BG)
    draw.text((6, 4), text, fill=color, font=font)


def render_preview(
    *,
    image_path: Path,
    label_path: Path,
    qa_id: int,
    blur_threshold: float,
    class_names: tuple[str, ...],
    out_dir: Path,
) -> Tile:
    """Render a single annotated preview and return its Tile metadata.

    Box tags use the canonical class name from the frozen taxonomy, so the
    same renderer serves every class without modification.
    """
    with Image.open(image_path) as opened:
        image = opened.convert("RGB")
    width, height = image.width, image.height
    blur = blur_score(image)
    is_blurry = blur < blur_threshold

    boxes = _read_yolo(label_path)
    draw = ImageDraw.Draw(image)
    font = _font(18)
    class_ids: list[int] = []
    for cid, cx, cy, bw, bh in boxes:
        class_ids.append(cid)
        x1 = (cx - bw / 2) * width
        y1 = (cy - bh / 2) * height
        x2 = (cx + bw / 2) * width
        y2 = (cy + bh / 2) * height
        draw.rectangle([x1, y1, x2, y2], outline=_BOX_COLOR, width=_BOX_OUTLINE_W)
        name = class_names[cid] if 0 <= cid < len(class_names) else str(cid)
        tag = f"{name}#{cid}"
        tw = draw.textlength(tag, font=font)
        ty = max(0.0, y1 - 20)
        draw.rectangle([x1, ty, x1 + tw + 6, ty + 20], fill=_LABEL_BG)
        draw.text((x1 + 3, ty + 1), tag, fill=_BOX_COLOR, font=font)

    caption = (
        f"QA{qa_id:02d}  {image_path.name}  {width}x{height}  "
        f"boxes={len(boxes)}  blur={blur:.1f}"
        + ("  [BLURRY]" if is_blurry else "")
    )
    _draw_caption(
        draw,
        caption,
        width=width,
        font=_font(16),
        color=_BLUR_FG if is_blurry else _LABEL_FG,
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    preview_path = out_dir / f"qa{qa_id:02d}_{image_path.stem}.jpg"
    image.save(preview_path, quality=90)
    return Tile(
        qa_id=qa_id,
        stem=image_path.stem,
        filename=image_path.name,
        width=width,
        height=height,
        box_count=len(boxes),
        blur=blur,
        is_blurry=is_blurry,
        class_ids=tuple(class_ids),
        preview_path=preview_path,
    )


def build_contact_sheet(
    tiles: list[Tile], *, cols: int, cell: int, out_path: Path
) -> None:
    """Tile all previews into one contact sheet image."""
    rows = (len(tiles) + cols - 1) // cols
    pad = 10
    cap_h = 34
    cell_h = cell + cap_h
    sheet_w = cols * cell + (cols + 1) * pad
    sheet_h = rows * cell_h + (rows + 1) * pad
    sheet = Image.new("RGB", (sheet_w, sheet_h), (30, 30, 30))
    draw = ImageDraw.Draw(sheet)
    font = _font(15)
    small = _font(13)

    for i, tile in enumerate(tiles):
        r, c = divmod(i, cols)
        x = pad + c * (cell + pad)
        y = pad + r * (cell_h + pad)
        with Image.open(tile.preview_path) as prev:
            thumb = prev.convert("RGB")
            thumb.thumbnail((cell, cell))
        ox = x + (cell - thumb.width) // 2
        oy = y + (cell - thumb.height) // 2
        sheet.paste(thumb, (ox, oy))
        draw.rectangle([x, y, x + cell, y + cell], outline=(70, 70, 70), width=1)
        cy = y + cell + 2
        draw.rectangle([x, cy, x + cell, cy + cap_h], fill=_CAPTION_BG)
        draw.text(
            (x + 3, cy + 1),
            f"QA{tile.qa_id:02d}  {tile.stem[:14]}",
            fill=_CAPTION_FG,
            font=font,
        )
        line2 = f"{tile.width}x{tile.height}  boxes={tile.box_count}"
        draw.text((x + 3, cy + 17), line2, fill=_CAPTION_FG, font=small)
        if tile.is_blurry:
            bt = f"blur {tile.blur:.0f} [BLURRY]"
            btw = draw.textlength(bt, font=small)
            draw.text((x + cell - btw - 3, cy + 17), bt, fill=_BLUR_FG, font=small)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out_path, quality=92)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--staging-root", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--blur-threshold", type=float, default=100.0)
    parser.add_argument("--cols", type=int, default=5)
    parser.add_argument("--cell", type=int, default=360)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Generate per-image previews, the contact sheet and a QA data JSON.

    Args:
        argv: Optional argument vector (defaults to ``sys.argv``).

    Returns:
        Process exit code (0 success, 2 usage error).
    """
    args = _parse_args(argv)
    images_dir = args.staging_root / "images"
    labels_dir = args.staging_root / "labels"
    if not images_dir.is_dir() or not labels_dir.is_dir():
        print(
            f"error: staging images/labels not found under {args.staging_root}",
            file=sys.stderr,
        )
        return _EXIT_USAGE

    class_names = load_taxonomy().class_names
    previews_dir = args.out_dir / "previews"
    image_paths = sorted(
        p for p in images_dir.iterdir() if p.suffix in {".jpg", ".png"}
    )
    tiles: list[Tile] = []
    for qa_id, image_path in enumerate(image_paths, start=1):
        label_path = labels_dir / f"{image_path.stem}.txt"
        tiles.append(
            render_preview(
                image_path=image_path,
                label_path=label_path,
                qa_id=qa_id,
                blur_threshold=args.blur_threshold,
                class_names=class_names,
                out_dir=previews_dir,
            )
        )

    sheet_path = args.out_dir / "contact_sheet.jpg"
    build_contact_sheet(tiles, cols=args.cols, cell=args.cell, out_path=sheet_path)

    data = {
        "qa_status": _QA_PENDING,
        "blur_threshold": args.blur_threshold,
        "total_images": len(tiles),
        "total_objects": sum(t.box_count for t in tiles),
        "blurry_count": sum(1 for t in tiles if t.is_blurry),
        "contact_sheet": sheet_path.as_posix(),
        "tiles": [
            {
                "qa_id": t.qa_id,
                "stem": t.stem,
                "filename": t.filename,
                "width": t.width,
                "height": t.height,
                "box_count": t.box_count,
                "class_ids": list(t.class_ids),
                "blur": t.blur,
                "is_blurry": t.is_blurry,
                "preview": t.preview_path.as_posix(),
            }
            for t in tiles
        ],
    }
    (args.out_dir / "qa_data.json").write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        f"wrote {len(tiles)} preview(s), contact sheet and qa_data.json "
        f"(QA_PENDING) under {args.out_dir.as_posix()}"
    )
    return _EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
