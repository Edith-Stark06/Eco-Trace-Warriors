"""Automated QA — three-valued, never silently accepting.

This wave is explicitly designed to run **without human verification**, so the QA
stage must be honest about what automation can and cannot establish. Every staged
image gets exactly one of:

* ``AUTO_ACCEPT`` — every automated check that *can* decide, did, and passed:
  the frozen Gate A (:class:`~device_ai.dataset.image_validation.ImageValidator`)
  and Gate B (:class:`~device_ai.dataset.validator.AnnotationValidator`) raised no
  issue against it, its label carries at least one box, every box sits at the
  target taxonomy id, and it was not flagged by the frozen duplicate detector.
* ``AUTO_REJECT`` — a definite automated failure (structural image issue, invalid
  or missing annotation, wrong class id, duplicate).
* ``UNVERIFIED`` — automation *cannot* establish correctness. Quality flags
  (blurry / too dark / too bright / low resolution) fall here: they are not
  defects that automation can adjudicate, and treating them as clean would be
  exactly the "silent conversion of uncertainty to acceptance" this stage forbids.

**What ``AUTO_ACCEPT`` does and does not mean.** It means the sample is
structurally sound *and* its class label was established by the source's own
bounding-box semantics, which cleared the license and semantic gates before
ingestion. It does **not** mean a human (or a model) looked at the pixels and
confirmed a router is present: ``visual_verification`` is always
``NOT_PERFORMED``. A batch that passes automated QA is therefore
``AUTO_QA_PASSED`` — never "human QA approved" and never release-approved.

Only ``AUTO_ACCEPT`` images enter the accepted set that is split and audited.
``UNVERIFIED`` and ``AUTO_REJECT`` images stay in staging with their status
recorded so a later human pass can adjudicate them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

# Decisions (stable, machine-readable).
AUTO_ACCEPT = "AUTO_ACCEPT"
AUTO_REJECT = "AUTO_REJECT"
UNVERIFIED = "UNVERIFIED"

#: Recorded on every decision: automation never confirms the depicted object.
VISUAL_VERIFICATION = "NOT_PERFORMED"

#: Quality flags that automation cannot adjudicate -> UNVERIFIED, never accepted.
_UNVERIFIABLE_QUALITY_FLAGS = ("is_blurry", "is_dark", "is_bright", "is_low_resolution")


@dataclass(frozen=True, slots=True)
class ImageQA:
    """The automated QA decision for one staged image.

    Attributes:
        relative_path: Staged image path (relative to the images root).
        decision: :data:`AUTO_ACCEPT`, :data:`AUTO_REJECT` or :data:`UNVERIFIED`.
        reasons: Every contributing reason (empty only for a clean accept).
        gate_a_codes: Frozen image-validation issue codes affecting this image.
        gate_b_codes: Frozen annotation-validation issue codes affecting it.
        box_count: Boxes found in its staged label.
        quality_flags: Frozen quality flags that were raised.
        visual_verification: Always :data:`VISUAL_VERIFICATION`.
    """

    relative_path: str
    decision: str
    reasons: tuple[str, ...] = ()
    gate_a_codes: tuple[str, ...] = ()
    gate_b_codes: tuple[str, ...] = ()
    box_count: int = 0
    quality_flags: tuple[str, ...] = ()
    visual_verification: str = VISUAL_VERIFICATION

    def to_dict(self) -> dict[str, object]:
        """Return a primitive-only, JSON-serialisable mapping."""
        return {
            "relative_path": self.relative_path,
            "decision": self.decision,
            "reasons": list(self.reasons),
            "gate_a_codes": list(self.gate_a_codes),
            "gate_b_codes": list(self.gate_b_codes),
            "box_count": self.box_count,
            "quality_flags": list(self.quality_flags),
            "visual_verification": self.visual_verification,
        }


@dataclass(frozen=True, slots=True)
class QAOutcome:
    """Aggregate automated-QA result for the batch.

    Attributes:
        decisions: Per-image decisions in sorted path order.
        gate_a_valid: Whether frozen Gate A reported no issue at all.
        gate_b_valid: Whether frozen Gate B reported no issue at all.
        gate_a_summary: Serialised Gate A summary from the frozen reporter.
        gate_b_summary: Serialised Gate B summary.
        total_boxes: Boxes counted across every staged label.
        class_counts: Frozen Gate B class-id histogram of the staged labels.
    """

    decisions: list[ImageQA] = field(default_factory=list)
    gate_a_valid: bool = False
    gate_b_valid: bool = False
    gate_a_summary: dict[str, object] = field(default_factory=dict)
    gate_b_summary: dict[str, object] = field(default_factory=dict)
    total_boxes: int = 0
    class_counts: dict[int, int] = field(default_factory=dict)

    @property
    def accepted(self) -> tuple[str, ...]:
        """Paths that cleared automated QA (the only set that is promoted)."""
        return tuple(
            d.relative_path for d in self.decisions if d.decision == AUTO_ACCEPT
        )

    @property
    def rejected(self) -> tuple[str, ...]:
        """Paths automation definitively rejected."""
        return tuple(
            d.relative_path for d in self.decisions if d.decision == AUTO_REJECT
        )

    @property
    def unverified(self) -> tuple[str, ...]:
        """Paths automation could not adjudicate."""
        return tuple(
            d.relative_path for d in self.decisions if d.decision == UNVERIFIED
        )

    @property
    def status(self) -> str:
        """Batch-level QA status (never a human or release approval)."""
        if not self.decisions:
            return "NO_IMAGES"
        return "AUTO_QA_PASSED" if self.accepted else "AUTO_QA_NO_ACCEPTED_IMAGES"

    def to_dict(self) -> dict[str, object]:
        """Return a primitive-only, JSON-serialisable mapping."""
        return {
            "status": self.status,
            "basis": (
                "structural frozen gates (A+B) + source-verified bbox semantics; "
                "no visual confirmation of the depicted object was performed"
            ),
            "visual_verification": VISUAL_VERIFICATION,
            "human_qa": "NOT_PERFORMED",
            "total_images": len(self.decisions),
            "auto_accepted": len(self.accepted),
            "auto_rejected": len(self.rejected),
            "unverified": len(self.unverified),
            "gate_a_valid": self.gate_a_valid,
            "gate_b_valid": self.gate_b_valid,
            "gate_a_summary": self.gate_a_summary,
            "gate_b_summary": self.gate_b_summary,
            "total_boxes": self.total_boxes,
            "class_counts": {str(k): v for k, v in sorted(self.class_counts.items())},
            "decisions": [d.to_dict() for d in self.decisions],
        }


def _codes_by_stem(issues: object) -> dict[str, set[str]]:
    """Map a file stem to the issue codes recorded against it.

    Issues are keyed by stem because Gate A reports image paths while Gate B
    reports label paths for the same sample.
    """
    mapped: dict[str, set[str]] = {}
    if not isinstance(issues, list):
        return mapped
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        stem = Path(str(issue.get("file", ""))).stem
        if stem:
            mapped.setdefault(stem, set()).add(str(issue.get("code", "")))
    return mapped


def run_automated_qa(
    *,
    images_root: Path,
    labels_root: Path,
    taxonomy_id: int,
    num_classes: int,
    duplicate_paths: tuple[str, ...] = (),
    settings: object | None = None,
) -> QAOutcome:
    """Grade every staged image with the frozen gates (three-valued).

    Args:
        images_root: Staged images root.
        labels_root: Staged labels root.
        taxonomy_id: The target class id every box must carry.
        num_classes: Taxonomy size, passed to the frozen annotation validator so
            out-of-range class ids are reported by the frozen check.
        duplicate_paths: Batch paths the frozen duplicate detector flagged.
        settings: Optional injected settings (defaults to ``get_settings()``).

    Returns:
        A :class:`QAOutcome`.
    """
    from ..configs.settings import get_settings
    from ..dataset.image_validation import ImageValidator, image_validation_to_dict
    from ..dataset.layout import list_image_paths, relative_path
    from ..dataset.metadata import MetadataGenerator
    from ..dataset.validator import AnnotationValidator

    active = settings if settings is not None else get_settings()

    image_report = ImageValidator(active).validate(images_root=images_root)  # type: ignore[arg-type]
    image_payload = image_validation_to_dict(image_report)
    annotation_report = AnnotationValidator(num_classes=num_classes).validate(
        images_root=images_root, labels_root=labels_root
    )

    gate_a_codes = _codes_by_stem(image_payload.get("issues"))
    gate_b_codes = _codes_by_stem(
        [
            {"file": issue.file, "code": issue.code}
            for issue in annotation_report.issues
        ]
    )

    generator = MetadataGenerator.from_settings(active)  # type: ignore[arg-type]
    validator = AnnotationValidator(num_classes=num_classes)
    duplicates = set(duplicate_paths)

    decisions: list[ImageQA] = []
    for image_path in list_image_paths(images_root):
        rel = relative_path(image_path, images_root)
        stem = Path(rel).stem
        reasons: list[str] = []

        a_codes = tuple(sorted(gate_a_codes.get(stem, set())))
        b_codes = tuple(sorted(gate_b_codes.get(stem, set())))

        label_path = (labels_root / rel).with_suffix(".txt")
        boxes: list = []
        if label_path.exists():
            boxes, _ = validator.validate_label_file(label_path, root=labels_root)
        else:
            reasons.append("no staged label file for this image")

        record = generator.analyze_file(image_path, root=images_root)
        quality_flags = tuple(
            flag
            for flag in _UNVERIFIABLE_QUALITY_FLAGS
            if getattr(record.quality, flag, False)
        )

        wrong_class = sorted({b.class_id for b in boxes if b.class_id != taxonomy_id})

        if a_codes:
            reasons.append(f"frozen image validation: {', '.join(a_codes)}")
        if b_codes:
            reasons.append(f"frozen annotation validation: {', '.join(b_codes)}")
        if rel in duplicates:
            reasons.append("flagged by the frozen duplicate detector")
        if not boxes:
            reasons.append("no valid bounding box in the staged label")
        if wrong_class:
            reasons.append(
                f"box class id(s) {wrong_class} != target taxonomy id {taxonomy_id}"
            )

        if reasons:
            decision = AUTO_REJECT
        elif quality_flags:
            decision = UNVERIFIED
            reasons.append(
                "image quality flag(s) "
                f"{', '.join(quality_flags)} cannot be adjudicated automatically; "
                "held as UNVERIFIED rather than accepted"
            )
        else:
            decision = AUTO_ACCEPT

        decisions.append(
            ImageQA(
                relative_path=rel,
                decision=decision,
                reasons=tuple(reasons),
                gate_a_codes=a_codes,
                gate_b_codes=b_codes,
                box_count=len(boxes),
                quality_flags=quality_flags,
            )
        )

    return QAOutcome(
        decisions=decisions,
        gate_a_valid=bool(image_report.is_valid),
        gate_b_valid=bool(annotation_report.is_valid),
        gate_a_summary=dict(image_payload.get("summary", {}))  # type: ignore[arg-type]
        if isinstance(image_payload.get("summary"), dict)
        else {},
        gate_b_summary={
            "total_labels": annotation_report.total_labels,
            "total_boxes": annotation_report.total_boxes,
            "images_without_labels": list(annotation_report.images_without_labels),
            "labels_without_images": list(annotation_report.labels_without_images),
            "is_valid": annotation_report.is_valid,
            "issue_count": len(annotation_report.issues),
        },
        total_boxes=annotation_report.total_boxes,
        class_counts=dict(annotation_report.class_counts),
    )
