"""Dataset export to YOLO, COCO and Pascal VOC formats.

:class:`DatasetExporter` reads analysed images and their YOLO ``.txt`` labels
and writes one of three industry-standard layouts into an export directory:

* **YOLO**  — copies/normalises ``images/`` + ``labels/`` and writes a
  ``data.yaml`` manifest.
* **COCO**  — a single ``annotations.json`` (images, annotations, categories)
  with absolute-pixel bounding boxes.
* **VOC**   — one Pascal VOC ``.xml`` per image under ``Annotations/``.

YOLO's normalised ``(x_center, y_center, w, h)`` boxes are converted to
absolute pixel corners for COCO/VOC using each image's dimensions. The
exporter performs no inference — it is a pure format transformation.
"""

from __future__ import annotations

import json
from pathlib import Path
from xml.etree import ElementTree as ET

from ..exceptions import UnsupportedExportFormatError
from .layout import label_path_for
from .records import ExportResult, ImageRecord
from .validator import AnnotationValidator, YoloBox

# Supported export format identifiers.
SUPPORTED_FORMATS: frozenset[str] = frozenset({"yolo", "coco", "voc"})


def yolo_to_corners(
    box: YoloBox, *, width: int, height: int
) -> tuple[float, float, float, float]:
    """Convert a normalised YOLO box to absolute ``(x_min, y_min, w, h)``.

    Args:
        box: The normalised YOLO bounding box.
        width: Image width in pixels.
        height: Image height in pixels.

    Returns:
        ``(x_min, y_min, box_width, box_height)`` in pixels, clamped to the
        image bounds.
    """
    box_w = box.width * width
    box_h = box.height * height
    x_min = max(0.0, (box.x_center * width) - box_w / 2.0)
    y_min = max(0.0, (box.y_center * height) - box_h / 2.0)
    box_w = min(box_w, width - x_min)
    box_h = min(box_h, height - y_min)
    return round(x_min, 2), round(y_min, 2), round(box_w, 2), round(box_h, 2)


class DatasetExporter:
    """Export analysed images + YOLO labels to a target annotation format.

    Args:
        class_names: Optional ordered class names. When omitted, generic
            ``class_<id>`` names are synthesised on demand.
    """

    def __init__(self, class_names: list[str] | None = None) -> None:
        self._class_names = class_names
        self._validator = AnnotationValidator()

    def _class_name(self, class_id: int) -> str:
        """Return the display name for a class id."""
        if self._class_names and 0 <= class_id < len(self._class_names):
            return self._class_names[class_id]
        return f"class_{class_id}"

    def export(
        self,
        *,
        export_format: str,
        records: list[ImageRecord],
        images_root: Path,
        labels_root: Path,
        destination: Path,
    ) -> ExportResult:
        """Export the dataset in the requested format.

        Args:
            export_format: One of :data:`SUPPORTED_FORMATS`.
            records: Analysed image records to export.
            images_root: Root the records' relative paths are based on.
            labels_root: Directory holding YOLO ``.txt`` labels.
            destination: Directory to write the export into (created if
                missing).

        Returns:
            An :class:`ExportResult` describing the files written.

        Raises:
            UnsupportedExportFormatError: If ``export_format`` is unknown.
        """
        fmt = export_format.lower()
        if fmt not in SUPPORTED_FORMATS:
            raise UnsupportedExportFormatError(
                f"Unsupported export format '{export_format}'. "
                f"Supported: {', '.join(sorted(SUPPORTED_FORMATS))}.",
                details={"format": export_format},
            )
        destination.mkdir(parents=True, exist_ok=True)

        if fmt == "yolo":
            files = self._export_yolo(records, images_root, labels_root, destination)
        elif fmt == "coco":
            files = self._export_coco(records, images_root, labels_root, destination)
        else:
            files = self._export_voc(records, images_root, labels_root, destination)

        return ExportResult(
            export_format=fmt,
            destination=destination.as_posix(),
            files=tuple(sorted(files)),
            image_count=len(records),
        )

    def _boxes_for(
        self, record: ImageRecord, images_root: Path, labels_root: Path
    ) -> list[YoloBox]:
        """Return the parsed YOLO boxes for a record (empty if none/invalid)."""
        image_path = images_root / record.relative_path
        label_path = label_path_for(image_path, images_root, labels_root)
        if not label_path.exists():
            return []
        boxes, _issues = self._validator.validate_label_file(
            label_path, root=labels_root
        )
        return boxes

    def _export_yolo(
        self,
        records: list[ImageRecord],
        images_root: Path,
        labels_root: Path,
        destination: Path,
    ) -> list[str]:
        """Write a YOLO-format export (images/, labels/, data.yaml)."""
        written: list[str] = []
        images_out = destination / "images"
        labels_out = destination / "labels"
        images_out.mkdir(parents=True, exist_ok=True)
        labels_out.mkdir(parents=True, exist_ok=True)

        class_ids: set[int] = set()
        for record in records:
            src_image = images_root / record.relative_path
            if src_image.exists():
                dest_image = images_out / Path(record.relative_path).name
                dest_image.write_bytes(src_image.read_bytes())
                written.append(f"images/{dest_image.name}")

            boxes = self._boxes_for(record, images_root, labels_root)
            class_ids.update(box.class_id for box in boxes)
            label_name = Path(record.relative_path).with_suffix(".txt").name
            lines = [
                f"{b.class_id} {b.x_center} {b.y_center} {b.width} {b.height}"
                for b in boxes
            ]
            (labels_out / label_name).write_text(
                "\n".join(lines) + ("\n" if lines else ""), encoding="utf-8"
            )
            written.append(f"labels/{label_name}")

        max_class = max(class_ids) if class_ids else -1
        names = [self._class_name(i) for i in range(max_class + 1)]
        yaml_lines = [
            "# YOLO dataset manifest generated by EcoTrace DIE",
            "path: .",
            "train: images",
            "val: images",
            f"nc: {len(names)}",
            f"names: {names}",
        ]
        (destination / "data.yaml").write_text(
            "\n".join(yaml_lines) + "\n", encoding="utf-8"
        )
        written.append("data.yaml")
        return written

    def _export_coco(
        self,
        records: list[ImageRecord],
        images_root: Path,
        labels_root: Path,
        destination: Path,
    ) -> list[str]:
        """Write a COCO-format export (single annotations.json)."""
        images: list[dict[str, object]] = []
        annotations: list[dict[str, object]] = []
        class_ids: set[int] = set()
        annotation_id = 1

        for image_id, record in enumerate(records, start=1):
            images.append(
                {
                    "id": image_id,
                    "file_name": Path(record.relative_path).name,
                    "width": record.width,
                    "height": record.height,
                }
            )
            for box in self._boxes_for(record, images_root, labels_root):
                class_ids.add(box.class_id)
                x, y, w, h = yolo_to_corners(
                    box, width=record.width, height=record.height
                )
                annotations.append(
                    {
                        "id": annotation_id,
                        "image_id": image_id,
                        "category_id": box.class_id,
                        "bbox": [x, y, w, h],
                        "area": round(w * h, 2),
                        "iscrowd": 0,
                    }
                )
                annotation_id += 1

        categories = [
            {"id": class_id, "name": self._class_name(class_id)}
            for class_id in sorted(class_ids)
        ]
        document = {
            "info": {"description": "EcoTrace DIE dataset export", "version": "1.0"},
            "images": images,
            "annotations": annotations,
            "categories": categories,
        }
        (destination / "annotations.json").write_text(
            json.dumps(document, indent=2, sort_keys=True), encoding="utf-8"
        )
        return ["annotations.json"]

    def _export_voc(
        self,
        records: list[ImageRecord],
        images_root: Path,
        labels_root: Path,
        destination: Path,
    ) -> list[str]:
        """Write a Pascal VOC export (one XML per image under Annotations/)."""
        written: list[str] = []
        annotations_dir = destination / "Annotations"
        annotations_dir.mkdir(parents=True, exist_ok=True)

        for record in records:
            boxes = self._boxes_for(record, images_root, labels_root)
            xml = self._voc_xml(record, boxes)
            xml_name = Path(record.relative_path).with_suffix(".xml").name
            (annotations_dir / xml_name).write_bytes(xml)
            written.append(f"Annotations/{xml_name}")
        return written

    def _voc_xml(self, record: ImageRecord, boxes: list[YoloBox]) -> bytes:
        """Build the Pascal VOC XML document for one image."""
        annotation = ET.Element("annotation")
        ET.SubElement(annotation, "folder").text = "images"
        ET.SubElement(annotation, "filename").text = Path(record.relative_path).name

        size = ET.SubElement(annotation, "size")
        ET.SubElement(size, "width").text = str(record.width)
        ET.SubElement(size, "height").text = str(record.height)
        depth = 1 if record.mode in {"L", "1"} else 3
        ET.SubElement(size, "depth").text = str(depth)

        for box in boxes:
            x, y, w, h = yolo_to_corners(box, width=record.width, height=record.height)
            obj = ET.SubElement(annotation, "object")
            ET.SubElement(obj, "name").text = self._class_name(box.class_id)
            ET.SubElement(obj, "difficult").text = "0"
            bndbox = ET.SubElement(obj, "bndbox")
            ET.SubElement(bndbox, "xmin").text = str(int(x))
            ET.SubElement(bndbox, "ymin").text = str(int(y))
            ET.SubElement(bndbox, "xmax").text = str(int(x + w))
            ET.SubElement(bndbox, "ymax").text = str(int(y + h))

        ET.indent(annotation, space="  ")
        xml: bytes = ET.tostring(annotation, encoding="utf-8", xml_declaration=True)
        return xml
