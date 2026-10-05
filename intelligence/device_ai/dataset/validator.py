"""YOLO annotation parsing and validation.

The dataset ships bounding-box annotations in the YOLO text format: one box
per line as ``<class_id> <x_center> <y_center> <width> <height>`` with all
coordinates normalised to ``[0, 1]``.

:class:`AnnotationValidator` parses label files, checks them for structural
and semantic correctness, and cross-references images against labels to
surface orphans in either direction. It never mutates files — validation is
read-only and returns a structured
:class:`~device_ai.dataset.records.AnnotationReport`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .layout import label_path_for, list_image_paths, relative_path
from .records import AnnotationIssue, AnnotationReport

# Every YOLO box line has exactly five whitespace-separated fields.
_YOLO_FIELDS = 5


@dataclass(frozen=True, slots=True)
class YoloBox:
    """A single parsed YOLO bounding box.

    Attributes:
        class_id: Integer class identifier (``>= 0``).
        x_center: Normalised box centre x in ``[0, 1]``.
        y_center: Normalised box centre y in ``[0, 1]``.
        width: Normalised box width in ``(0, 1]``.
        height: Normalised box height in ``(0, 1]``.
    """

    class_id: int
    x_center: float
    y_center: float
    width: float
    height: float


def parse_yolo_line(line: str) -> YoloBox:
    """Parse one YOLO annotation line into a :class:`YoloBox`.

    Args:
        line: A single, non-empty annotation line.

    Returns:
        The parsed bounding box.

    Raises:
        ValueError: If the line is malformed (wrong field count or types).
    """
    fields = line.split()
    if len(fields) != _YOLO_FIELDS:
        raise ValueError(f"expected {_YOLO_FIELDS} fields, found {len(fields)}")
    try:
        class_id = int(fields[0])
        x_center, y_center, width, height = (float(value) for value in fields[1:])
    except ValueError as exc:
        raise ValueError("non-numeric field in annotation") from exc
    return YoloBox(
        class_id=class_id,
        x_center=x_center,
        y_center=y_center,
        width=width,
        height=height,
    )


class AnnotationValidator:
    """Validate YOLO label files and their pairing with images.

    Args:
        num_classes: Optional class count. When provided, class ids outside
            ``[0, num_classes)`` are reported as errors.
    """

    def __init__(self, num_classes: int | None = None) -> None:
        self._num_classes = num_classes

    def _validate_box(
        self, box: YoloBox, *, file: str, line_no: int
    ) -> list[AnnotationIssue]:
        """Return the issues (if any) for a single parsed box."""
        issues: list[AnnotationIssue] = []
        if box.class_id < 0:
            issues.append(
                AnnotationIssue(
                    file=file,
                    line=line_no,
                    code="NEGATIVE_CLASS_ID",
                    message=f"class id {box.class_id} is negative",
                )
            )
        if self._num_classes is not None and box.class_id >= self._num_classes:
            issues.append(
                AnnotationIssue(
                    file=file,
                    line=line_no,
                    code="CLASS_ID_OUT_OF_RANGE",
                    message=(
                        f"class id {box.class_id} outside " f"[0, {self._num_classes})"
                    ),
                )
            )
        for name, value in (
            ("x_center", box.x_center),
            ("y_center", box.y_center),
            ("width", box.width),
            ("height", box.height),
        ):
            if not 0.0 <= value <= 1.0:
                issues.append(
                    AnnotationIssue(
                        file=file,
                        line=line_no,
                        code="COORD_OUT_OF_RANGE",
                        message=f"{name}={value} not in [0, 1]",
                    )
                )
        if box.width <= 0.0 or box.height <= 0.0:
            issues.append(
                AnnotationIssue(
                    file=file,
                    line=line_no,
                    code="NON_POSITIVE_SIZE",
                    message="box width/height must be positive",
                )
            )
        return issues

    def validate_label_file(
        self, path: Path, *, root: Path
    ) -> tuple[list[YoloBox], list[AnnotationIssue]]:
        """Parse and validate a single YOLO label file.

        Args:
            path: Absolute path of the ``.txt`` label file.
            root: Root used to compute the stable relative path.

        Returns:
            A ``(boxes, issues)`` tuple. Malformed lines are skipped (with an
            issue recorded) so a single bad line does not hide the rest.
        """
        file = relative_path(path, root)
        boxes: list[YoloBox] = []
        issues: list[AnnotationIssue] = []
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            issues.append(
                AnnotationIssue(
                    file=file,
                    line=0,
                    code="UNREADABLE_LABEL",
                    message=str(exc),
                )
            )
            return boxes, issues

        for line_no, raw in enumerate(text.splitlines(), start=1):
            stripped = raw.strip()
            if not stripped:
                continue
            try:
                box = parse_yolo_line(stripped)
            except ValueError as exc:
                issues.append(
                    AnnotationIssue(
                        file=file,
                        line=line_no,
                        code="MALFORMED_LINE",
                        message=str(exc),
                    )
                )
                continue
            issues.extend(self._validate_box(box, file=file, line_no=line_no))
            boxes.append(box)
        return boxes, issues

    def validate(
        self,
        *,
        images_root: Path,
        labels_root: Path,
    ) -> AnnotationReport:
        """Validate every image/label pair under the two roots.

        Args:
            images_root: Directory containing the images.
            labels_root: Directory containing YOLO ``.txt`` labels.

        Returns:
            An aggregate :class:`AnnotationReport`.
        """
        issues: list[AnnotationIssue] = []
        class_counts: dict[int, int] = {}
        total_boxes = 0
        images_without_labels: list[str] = []

        image_paths = list_image_paths(images_root)
        matched_labels: set[Path] = set()

        for image_path in image_paths:
            label_path = label_path_for(image_path, images_root, labels_root)
            image_rel = relative_path(image_path, images_root)
            if not label_path.exists():
                images_without_labels.append(image_rel)
                continue
            matched_labels.add(label_path.resolve())
            boxes, file_issues = self.validate_label_file(label_path, root=labels_root)
            issues.extend(file_issues)
            total_boxes += len(boxes)
            for box in boxes:
                class_counts[box.class_id] = class_counts.get(box.class_id, 0) + 1

        # Labels that reference no image (orphans).
        labels_without_images: list[str] = []
        total_labels = 0
        for label_path in sorted(labels_root.rglob("*.txt")):
            if not label_path.is_file():
                continue
            total_labels += 1
            if label_path.resolve() not in matched_labels:
                labels_without_images.append(relative_path(label_path, labels_root))

        for orphan in images_without_labels:
            issues.append(
                AnnotationIssue(
                    file=orphan,
                    line=0,
                    code="MISSING_LABEL",
                    message="image has no matching label file",
                )
            )
        for orphan in labels_without_images:
            issues.append(
                AnnotationIssue(
                    file=orphan,
                    line=0,
                    code="ORPHAN_LABEL",
                    message="label has no matching image",
                )
            )

        return AnnotationReport(
            total_labels=total_labels,
            total_boxes=total_boxes,
            images_without_labels=tuple(images_without_labels),
            labels_without_images=tuple(labels_without_images),
            class_counts=dict(sorted(class_counts.items())),
            issues=tuple(issues),
        )
