"""Local-dataset format detection and normalisation (YOLO / COCO / Pascal VOC).

Offline ingestion accepts a local archive/directory and must recognise its
annotation format, then normalise every box to the YOLO convention
(``class x_center y_center width height`` with coordinates in ``[0, 1]``) while
preserving each box's *source* class label so the semantic gate can rule on it.

Supported: **YOLO** (``images/`` + ``labels/`` with a ``data.yaml`` names map),
**COCO** (a JSON with ``images``/``annotations``/``categories``), and
**Pascal VOC** (per-image ``.xml`` with ``<size>``/``<object>``/``<bndbox>``).
Anything else yields an ``unknown`` detection carrying the exact reason — the
pipeline reports it rather than coercing.

Pillow is imported *lazily* and only as a fallback when an annotation omits the
image dimensions needed to normalise absolute (COCO/VOC) coordinates; YOLO
parsing and all detection are dependency-free.
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

# Detected format names.
FORMAT_YOLO = "yolo"
FORMAT_COCO = "coco"
FORMAT_VOC = "voc"
FORMAT_UNKNOWN = "unknown"

_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


@dataclass(frozen=True, slots=True)
class SourceBox:
    """One bounding box as read from a source annotation.

    Coordinates are already normalised to ``[0, 1]`` (YOLO convention). The
    source class is preserved verbatim for the semantic gate.
    """

    source_class_id: int | None
    source_class_name: str
    x_center: float
    y_center: float
    width: float
    height: float


@dataclass(frozen=True, slots=True)
class SourceAnnotation:
    """All boxes for a single source image."""

    image_path: Path
    image_rel: str
    boxes: tuple[SourceBox, ...]
    image_width: int
    image_height: int


@dataclass(frozen=True, slots=True)
class DetectedFormat:
    """Result of sniffing a local dataset root.

    Attributes:
        format_name: One of ``yolo``/``coco``/``voc``/``unknown``.
        supported: Whether the pipeline can ingest this format.
        images_dir: Directory holding the source images (best-effort).
        annotations_ref: Path to the annotation file (COCO) or directory
            (YOLO labels / VOC xml).
        class_names: Mapping of source class id -> name where known.
        detail: Exact reason / description (populated for ``unknown``).
    """

    format_name: str
    supported: bool
    images_dir: Path | None
    annotations_ref: Path | None
    class_names: dict[int, str] = field(default_factory=dict)
    detail: str = ""

    def to_dict(self) -> dict[str, object]:
        """Return a primitive-only, JSON-serialisable mapping."""
        return {
            "format_name": self.format_name,
            "supported": self.supported,
            "images_dir": self.images_dir.as_posix() if self.images_dir else "",
            "annotations_ref": (
                self.annotations_ref.as_posix() if self.annotations_ref else ""
            ),
            "class_names": {str(k): v for k, v in sorted(self.class_names.items())},
            "detail": self.detail,
        }


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------


def _find_dir(root: Path, *names: str) -> Path | None:
    """Return the first existing sub-directory matching any of ``names``."""
    for name in names:
        candidate = root / name
        if candidate.is_dir():
            return candidate
    # Also search one level down (archives often nest under a top folder).
    for child in sorted(p for p in root.iterdir() if p.is_dir()):
        for name in names:
            candidate = child / name
            if candidate.is_dir():
                return candidate
    return None


def _load_yaml_names(path: Path) -> dict[int, str]:
    """Extract a ``names`` map from a YOLO ``data.yaml`` (list or dict form)."""
    try:
        import yaml  # lazy: PyYAML is a project dependency
    except ImportError:
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict) or "names" not in data:
        return {}
    names = data["names"]
    if isinstance(names, list):
        return {i: str(n) for i, n in enumerate(names)}
    if isinstance(names, dict):
        out: dict[int, str] = {}
        for key, value in names.items():
            try:
                out[int(key)] = str(value)
            except (TypeError, ValueError):
                continue
        return out
    return {}


def _detect_yolo(root: Path) -> DetectedFormat | None:
    """Detect a YOLO layout; require a names map to be usable."""
    images_dir = _find_dir(root, "images", "JPEGImages", "imgs")
    labels_dir = _find_dir(root, "labels", "annotations", "anns")
    yaml_file = next(
        (
            p
            for p in sorted(root.rglob("*.y*ml"))
            if p.name.lower() in {"data.yaml", "data.yml", "dataset.yaml", "dataset.yml"}
        ),
        None,
    )
    has_label_txt = labels_dir is not None and any(labels_dir.rglob("*.txt"))
    if not (yaml_file or (images_dir and has_label_txt)):
        return None

    class_names = _load_yaml_names(yaml_file) if yaml_file else {}
    if not class_names:
        return DetectedFormat(
            format_name=FORMAT_YOLO,
            supported=False,
            images_dir=images_dir,
            annotations_ref=labels_dir,
            detail=(
                "YOLO layout detected but no class-names map (data.yaml `names`); "
                "numeric ids cannot establish the source class semantically"
            ),
        )
    return DetectedFormat(
        format_name=FORMAT_YOLO,
        supported=True,
        images_dir=images_dir,
        annotations_ref=labels_dir,
        class_names=class_names,
        detail="YOLO layout with data.yaml names map",
    )


def _detect_coco(root: Path) -> DetectedFormat | None:
    """Detect a COCO annotations JSON."""
    for path in sorted(root.rglob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        if {"images", "annotations", "categories"} <= set(data):
            class_names = {
                int(c["id"]): str(c.get("name", ""))
                for c in data.get("categories", [])
                if isinstance(c, dict) and "id" in c
            }
            images_dir = _find_dir(root, "images", "JPEGImages") or path.parent
            return DetectedFormat(
                format_name=FORMAT_COCO,
                supported=True,
                images_dir=images_dir,
                annotations_ref=path,
                class_names=class_names,
                detail=f"COCO annotations JSON: {path.name}",
            )
    return None


def _detect_voc(root: Path) -> DetectedFormat | None:
    """Detect Pascal VOC per-image XML annotations."""
    for path in sorted(root.rglob("*.xml")):
        try:
            tree = ET.parse(path)  # noqa: S314 - local, trusted fixture/archive
        except ET.ParseError:
            continue
        node = tree.getroot()
        if node.tag == "annotation" and node.find("object") is not None:
            anns_dir = _find_dir(root, "Annotations") or path.parent
            images_dir = _find_dir(root, "JPEGImages", "images") or root
            return DetectedFormat(
                format_name=FORMAT_VOC,
                supported=True,
                images_dir=images_dir,
                annotations_ref=anns_dir,
                detail="Pascal VOC XML annotations",
            )
    return None


def detect_format(root: Path) -> DetectedFormat:
    """Sniff the annotation format of a local dataset root.

    Args:
        root: Directory containing an extracted/self-hosted dataset.

    Returns:
        A :class:`DetectedFormat`. When nothing matches, ``format_name`` is
        ``unknown`` and ``detail`` states exactly why.
    """
    if not root.is_dir():
        return DetectedFormat(
            format_name=FORMAT_UNKNOWN,
            supported=False,
            images_dir=None,
            annotations_ref=None,
            detail=f"source root is not a directory: {root}",
        )
    for detector in (_detect_yolo, _detect_coco, _detect_voc):
        detected = detector(root)
        if detected is not None:
            return detected
    return DetectedFormat(
        format_name=FORMAT_UNKNOWN,
        supported=False,
        images_dir=None,
        annotations_ref=None,
        detail=(
            "no supported annotation format found (expected YOLO images+labels "
            "with data.yaml, COCO images/annotations/categories JSON, or Pascal "
            "VOC object XML)"
        ),
    )


# ---------------------------------------------------------------------------
# Parsing / normalisation
# ---------------------------------------------------------------------------


def _iter_images(images_dir: Path) -> list[Path]:
    """Return sorted image files under ``images_dir`` (recursive)."""
    return sorted(
        p
        for p in images_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in _IMAGE_EXTS
    )


def _image_dimensions(path: Path) -> tuple[int, int]:
    """Return ``(width, height)`` for an image, or ``(0, 0)`` on failure.

    Pillow is imported lazily here — the only place that needs it.
    """
    try:
        from PIL import Image  # lazy
    except ImportError:
        return (0, 0)
    try:
        with Image.open(path) as img:
            return int(img.width), int(img.height)
    except Exception:  # noqa: BLE001 - unreadable image -> unknown dims
        return (0, 0)


def _rel(path: Path, root: Path) -> str:
    """POSIX path of ``path`` relative to ``root`` (falls back to the name)."""
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.name


def parse_yolo(detected: DetectedFormat, root: Path) -> list[SourceAnnotation]:
    """Parse a detected YOLO dataset into source annotations."""
    images_dir = detected.images_dir or root
    labels_dir = detected.annotations_ref or (root / "labels")
    names = detected.class_names
    annotations: list[SourceAnnotation] = []

    for image_path in _iter_images(images_dir):
        rel = _rel(image_path, images_dir)
        label_path = labels_dir / Path(rel).with_suffix(".txt")
        if not label_path.exists():
            label_path = labels_dir / (image_path.stem + ".txt")
        boxes: list[SourceBox] = []
        if label_path.exists():
            for line in label_path.read_text(encoding="utf-8").splitlines():
                fields = line.split()
                if len(fields) != 5:
                    continue
                try:
                    cid = int(fields[0])
                    xc, yc, bw, bh = (float(v) for v in fields[1:])
                except ValueError:
                    continue
                boxes.append(
                    SourceBox(
                        source_class_id=cid,
                        source_class_name=names.get(cid, str(cid)),
                        x_center=xc,
                        y_center=yc,
                        width=bw,
                        height=bh,
                    )
                )
        annotations.append(
            SourceAnnotation(
                image_path=image_path,
                image_rel=rel,
                boxes=tuple(boxes),
                image_width=0,
                image_height=0,
            )
        )
    return annotations


def parse_coco(detected: DetectedFormat, root: Path) -> list[SourceAnnotation]:
    """Parse a detected COCO dataset into source annotations."""
    assert detected.annotations_ref is not None
    data = json.loads(detected.annotations_ref.read_text(encoding="utf-8"))
    images_dir = detected.images_dir or root

    categories = {
        int(c["id"]): str(c.get("name", "")) for c in data.get("categories", [])
    }
    images = {
        int(img["id"]): img
        for img in data.get("images", [])
        if isinstance(img, dict) and "id" in img
    }
    boxes_by_image: dict[int, list[SourceBox]] = {}
    for ann in data.get("annotations", []):
        if not isinstance(ann, dict) or "image_id" not in ann or "bbox" not in ann:
            continue
        img_id = int(ann["image_id"])
        meta = images.get(img_id)
        if meta is None:
            continue
        width = int(meta.get("width", 0)) or 0
        height = int(meta.get("height", 0)) or 0
        if width <= 0 or height <= 0:
            width, height = _image_dimensions(
                images_dir / str(meta.get("file_name", ""))
            )
        if width <= 0 or height <= 0:
            continue
        x, y, bw, bh = (float(v) for v in ann["bbox"][:4])
        cid = int(ann.get("category_id", -1))
        boxes_by_image.setdefault(img_id, []).append(
            SourceBox(
                source_class_id=cid,
                source_class_name=categories.get(cid, str(cid)),
                x_center=(x + bw / 2) / width,
                y_center=(y + bh / 2) / height,
                width=bw / width,
                height=bh / height,
            )
        )

    annotations: list[SourceAnnotation] = []
    for img_id, meta in sorted(images.items()):
        file_name = str(meta.get("file_name", ""))
        image_path = images_dir / file_name
        annotations.append(
            SourceAnnotation(
                image_path=image_path,
                image_rel=file_name or f"image_{img_id}",
                boxes=tuple(boxes_by_image.get(img_id, [])),
                image_width=int(meta.get("width", 0)) or 0,
                image_height=int(meta.get("height", 0)) or 0,
            )
        )
    return annotations


def parse_voc(detected: DetectedFormat, root: Path) -> list[SourceAnnotation]:
    """Parse a detected Pascal VOC dataset into source annotations."""
    anns_dir = detected.annotations_ref or root
    images_dir = detected.images_dir or root
    annotations: list[SourceAnnotation] = []

    for xml_path in sorted(anns_dir.rglob("*.xml")):
        try:
            tree = ET.parse(xml_path)  # noqa: S314 - local, trusted archive
        except ET.ParseError:
            continue
        node = tree.getroot()
        size = node.find("size")
        width = int(float(size.findtext("width", "0"))) if size is not None else 0
        height = int(float(size.findtext("height", "0"))) if size is not None else 0
        filename = node.findtext("filename", "") or (xml_path.stem + ".jpg")
        image_path = images_dir / filename
        if width <= 0 or height <= 0:
            width, height = _image_dimensions(image_path)
        boxes: list[SourceBox] = []
        for obj in node.findall("object"):
            name = (obj.findtext("name", "") or "").strip()
            bnd = obj.find("bndbox")
            if bnd is None or width <= 0 or height <= 0:
                continue
            xmin = float(bnd.findtext("xmin", "0"))
            ymin = float(bnd.findtext("ymin", "0"))
            xmax = float(bnd.findtext("xmax", "0"))
            ymax = float(bnd.findtext("ymax", "0"))
            boxes.append(
                SourceBox(
                    source_class_id=None,
                    source_class_name=name,
                    x_center=(xmin + xmax) / 2 / width,
                    y_center=(ymin + ymax) / 2 / height,
                    width=(xmax - xmin) / width,
                    height=(ymax - ymin) / height,
                )
            )
        annotations.append(
            SourceAnnotation(
                image_path=image_path,
                image_rel=filename,
                boxes=tuple(boxes),
                image_width=width,
                image_height=height,
            )
        )
    return annotations


def parse_annotations(detected: DetectedFormat, root: Path) -> list[SourceAnnotation]:
    """Dispatch to the parser matching ``detected.format_name``.

    Raises:
        ValueError: If the format is unknown/unsupported.
    """
    if detected.format_name == FORMAT_YOLO and detected.supported:
        return parse_yolo(detected, root)
    if detected.format_name == FORMAT_COCO:
        return parse_coco(detected, root)
    if detected.format_name == FORMAT_VOC:
        return parse_voc(detected, root)
    raise ValueError(f"cannot parse unsupported format: {detected.detail}")


def distinct_source_labels(annotations: list[SourceAnnotation]) -> list[str]:
    """Return the sorted set of distinct source class labels across boxes."""
    labels = {
        box.source_class_name for ann in annotations for box in ann.boxes
    }
    return sorted(labels)
