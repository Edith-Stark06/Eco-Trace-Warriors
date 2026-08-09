"""Build the human QA sign-off package for the Laptop pilot (Sprint P4.2.5).

This is a **manual-review checkpoint tool**, NOT production tooling and NOT part
of the frozen ``device_ai`` pipeline. It assembles a *reviewer package* for the
canonical Laptop candidate (``openimages_laptop_canonical_v1``) whose pilot
status is ``PILOT_REVIEW_REQUIRED`` — it produces the visual and machine-readable
evidence a human needs to sign off the outstanding items, and it does **nothing
else**:

* It **certifies nothing**. Every reviewable item is emitted ``PENDING_REVIEW``;
  the ``human_decision`` field is always left empty. It does not change any
  ``PENDING_REVIEW``/``REVIEW_PENDING`` to ``ACCEPTED`` and never declares the
  pilot ready for scale.
* It is **strictly read-only** w.r.t. every dataset artifact. It reads the
  source-preserved staging (``openimages_laptop_v1``) and the canonical
  candidate (``openimages_laptop_canonical_v1``) and writes **only** under a
  separate review directory that lives outside the immutable Open Images source.
  A SHA-256 snapshot of the source and canonical images+labels is taken before
  and after rendering and compared, and the comparison is recorded.
* It **invents no metric**. The blur numbers come from the frozen
  :func:`device_ai.dataset.metadata.blur_score` and the frozen blur threshold in
  settings; nothing is scored, graded, or thresholded anew.

Artifacts written under ``--review-root`` (default
``dataset_acquisition/review/openimages_laptop_human_qa_signoff_v1``):

* ``previews/`` — annotated PNG/JPEG evidence:
    - ``qa03``/``qa04``/``qa15`` before (source annotation) + after (corrected
      canonical annotation) + a side-by-side comparison;
    - ``qa01`` the held REVIEW_PENDING image with its box and blur evidence;
    - the three remaining ``IMAGE_BLURRY`` Gate-A images with boxes + blur;
    - ``qa14`` the proposed exclusion with its box and blur evidence.
* ``signoff_template.json`` — one machine-readable row per reviewable item with
  ``status`` in {``PENDING_REVIEW``, ``ACCEPTED``, ``REJECTED``} (all start
  ``PENDING_REVIEW``) and an empty ``human_decision``/``reviewer``/``date``.
* ``evidence.json`` — for every reviewable item: exact source filename,
  canonical filename, source SHA-256, original + corrected object counts and the
  original vs corrected annotation coordinates (normalised and pixel-space).
* ``integrity_verification.json`` — the before/after SHA-256 snapshot proof that
  no source image, source label, canonical image or canonical label changed.

Usage (from repo root):
    python scripts/build_laptop_qa_signoff.py

Exit codes:
    0: package written and the source + canonical staging verified unchanged.
    1: an integrity check failed (a snapshot drifted, a referenced file missing).
    2: usage error (missing staging directories, invalid timestamp).
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from _ecotrace_toolkit import REPO_ROOT  # noqa: F401  (bootstraps device_ai path)
from PIL import Image, ImageDraw, ImageFont

from device_ai.configs.settings import get_settings
from device_ai.dataset.hashing import sha256_hash
from device_ai.dataset.metadata import blur_score

# Exit codes (documented in the module docstring).
_EXIT_OK = 0
_EXIT_ERRORS = 1
_EXIT_USAGE = 2

# Deterministic defaults for the Laptop pilot sign-off package.
_DEFAULT_SOURCE_STAGING = REPO_ROOT / "dataset_acquisition/staging/openimages_laptop_v1"
_DEFAULT_CANONICAL_STAGING = (
    REPO_ROOT / "dataset_acquisition/staging/openimages_laptop_canonical_v1"
)
_DEFAULT_REVIEW_ROOT = (
    REPO_ROOT / "dataset_acquisition/review/openimages_laptop_human_qa_signoff_v1"
)
_DEFAULT_SIGNOFF_TIMESTAMP = "2026-08-09T00:00:00+00:00"
_DEFAULT_SIGNOFF_VERSION = "openimages-laptop-human-qa-signoff-v1"

# The only sign-off states a reviewer may record (machine-readable vocabulary).
_SIGNOFF_STATUSES = ("PENDING_REVIEW", "ACCEPTED", "REJECTED")
_STATUS_PENDING = "PENDING_REVIEW"

# Reviewable-item kinds (drives how each item is rendered and templated).
_KIND_REANNOTATION = "reannotation"
_KIND_REVIEW_HOLD = "review_hold"
_KIND_BLUR_GATE_A = "blur_gate_a"
_KIND_EXCLUSION = "exclusion"

# Rendering palette (BGR-free RGB tuples; this tool owns its own preview style).
_SOURCE_BOX_COLOR = (255, 90, 40)  # orange-red: the ORIGINAL source annotation
_CORRECTED_BOX_COLOR = (0, 220, 60)  # green: the CORRECTED canonical annotation
_LABEL_BG = (0, 0, 0)
_CAPTION_BG = (18, 18, 18)
_CAPTION_FG = (245, 245, 245)
_BLUR_FG = (255, 170, 0)
_BOX_OUTLINE_W = 3

class SignoffError(Exception):
    """A fatal sign-off packaging error (missing artifact, snapshot drift)."""


@dataclass(frozen=True, slots=True)
class ReviewItem:
    """One outstanding item that requires a human sign-off decision.

    The item is keyed on the canonical record already present in the frozen
    remediation manifest, so this tool authors **no** new policy — it only
    surfaces what the P4.2.4 ingestion recorded as still-pending.

    Attributes:
        item_id: Stable id used across all artifacts (e.g. ``QA03``).
        kind: One of the ``_KIND_*`` constants.
        qa_id: The visual-QA tile id (1-based) from the pilot QA report.
        source_stem: The Open Images source stem (e.g. ``0171ad35f1651698``).
        canonical_stem: The canonical stem, or ``None`` for the exclusion.
        issue: Short human-readable statement of the issue under review.
        proposed_decision: The tooling's *proposed* (not applied) decision.
        remediation_status: The remediation manifest status for the item.
        reviewer_status: The remediation manifest reviewer status (PENDING_*).
    """

    item_id: str
    kind: str
    qa_id: int
    source_stem: str
    canonical_stem: str | None
    issue: str
    proposed_decision: str
    remediation_status: str
    reviewer_status: str


@dataclass(slots=True)
class RenderedEvidence:
    """The rendered previews and measured facts for one review item.

    Attributes:
        item: The originating :class:`ReviewItem`.
        source_image_filename: Source image filename (e.g. ``<stem>.jpg``).
        canonical_image_filename: Canonical image filename, or ``None``.
        source_sha256: SHA-256 of the source image bytes.
        width: Decoded image width in pixels.
        height: Decoded image height in pixels.
        blur: Frozen ``blur_score`` of the image.
        is_blurry: Whether ``blur`` is below the frozen threshold.
        original_object_count: Boxes in the source annotation.
        corrected_object_count: Boxes in the canonical annotation (``None`` for
            the exclusion, which has no canonical label).
        original_boxes_norm: Source YOLO boxes (normalised ``cx cy w h``).
        corrected_boxes_norm: Canonical YOLO boxes, or ``None``.
        preview_paths: Mapping of preview role -> written path.
    """

    item: ReviewItem
    source_image_filename: str
    canonical_image_filename: str | None
    source_sha256: str
    width: int
    height: int
    blur: float
    is_blurry: bool
    original_object_count: int
    corrected_object_count: int | None
    original_boxes_norm: tuple[tuple[float, float, float, float], ...]
    corrected_boxes_norm: tuple[tuple[float, float, float, float], ...] | None
    preview_paths: dict[str, str] = field(default_factory=dict)


def snapshot_tree(root: Path) -> dict[str, str]:
    """Return a ``relpath -> sha256`` snapshot of every file under ``root``.

    Used to *prove* (not merely assert) that generating the review package left
    the source and canonical staging byte-identical: the snapshot is taken
    before and after rendering and the two are compared.

    Args:
        root: Directory to snapshot recursively (missing dir -> empty snapshot).

    Returns:
        A sorted mapping of POSIX relative path to SHA-256 of the file bytes.
    """
    out: dict[str, str] = {}
    if not root.is_dir():
        return out
    for path in sorted(root.rglob("*")):
        if path.is_file():
            out[path.relative_to(root).as_posix()] = sha256_hash(path.read_bytes())
    return out


def _diff_snapshots(
    before: dict[str, str], after: dict[str, str]
) -> dict[str, list[str]]:
    """Return the added / removed / modified paths between two snapshots."""
    before_keys = set(before)
    after_keys = set(after)
    modified = sorted(k for k in before_keys & after_keys if before[k] != after[k])
    return {
        "added": sorted(after_keys - before_keys),
        "removed": sorted(before_keys - after_keys),
        "modified": modified,
    }


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Load a truetype font if available, else the Pillow default bitmap font."""
    for name in ("arial.ttf", "DejaVuSans.ttf", "LiberationSans-Regular.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def read_yolo_boxes(
    label_path: Path,
) -> tuple[tuple[float, float, float, float], ...]:
    """Read a YOLO label file into normalised ``(cx, cy, w, h)`` tuples.

    The class id column is intentionally dropped — this tool only draws and
    reports box geometry; the class is fixed (``laptop``) across the pilot.

    Args:
        label_path: Path to a YOLO ``.txt`` label (missing file -> no boxes).

    Returns:
        The parsed normalised boxes in file order.
    """
    boxes: list[tuple[float, float, float, float]] = []
    if not label_path.is_file():
        return ()
    for raw in label_path.read_text(encoding="utf-8").splitlines():
        parts = raw.split()
        if len(parts) != 5:
            continue
        cx, cy, bw, bh = (float(v) for v in parts[1:])
        boxes.append((cx, cy, bw, bh))
    return tuple(boxes)


def _norm_to_pixel_xyxy(
    box: tuple[float, float, float, float], *, width: int, height: int
) -> tuple[float, float, float, float]:
    """Convert a normalised YOLO box to pixel-space ``(x1, y1, x2, y2)``."""
    cx, cy, bw, bh = box
    x1 = (cx - bw / 2) * width
    y1 = (cy - bh / 2) * height
    x2 = (cx + bw / 2) * width
    y2 = (cy + bh / 2) * height
    return (x1, y1, x2, y2)


def _draw_boxes(
    image: Image.Image,
    boxes: tuple[tuple[float, float, float, float], ...],
    *,
    color: tuple[int, int, int],
    tag_prefix: str,
) -> None:
    """Draw normalised YOLO boxes onto an image in-place with numbered tags."""
    draw = ImageDraw.Draw(image)
    font = _font(18)
    for idx, box in enumerate(boxes, start=1):
        x1, y1, x2, y2 = _norm_to_pixel_xyxy(box, width=image.width, height=image.height)
        draw.rectangle([x1, y1, x2, y2], outline=color, width=_BOX_OUTLINE_W)
        tag = f"{tag_prefix}#{idx}"
        tw = draw.textlength(tag, font=font)
        ty = max(0.0, y1 - 20)
        draw.rectangle([x1, ty, x1 + tw + 6, ty + 20], fill=_LABEL_BG)
        draw.text((x1 + 3, ty + 1), tag, fill=color, font=font)


def _caption(
    image: Image.Image, text: str, *, color: tuple[int, int, int]
) -> Image.Image:
    """Return a new image with a caption strip appended below ``image``."""
    strip_h = 30
    out = Image.new("RGB", (image.width, image.height + strip_h), _CAPTION_BG)
    out.paste(image, (0, 0))
    draw = ImageDraw.Draw(out)
    draw.rectangle([0, image.height, image.width, image.height + strip_h], fill=_CAPTION_BG)
    draw.text((6, image.height + 6), text, fill=color, font=_font(15))
    return out


def _load_rgb(image_path: Path) -> Image.Image:
    """Open an image read-only and return an RGB copy (source is never held)."""
    with Image.open(image_path) as opened:
        return opened.convert("RGB")


def _side_by_side(left: Image.Image, right: Image.Image) -> Image.Image:
    """Compose two captioned images side by side with a divider gap."""
    gap = 12
    height = max(left.height, right.height)
    out = Image.new("RGB", (left.width + gap + right.width, height), _CAPTION_BG)
    out.paste(left, (0, 0))
    out.paste(right, (left.width + gap, 0))
    return out


def render_item_previews(
    evidence: RenderedEvidence,
    *,
    source_image_path: Path,
    blur_threshold: float,
    previews_dir: Path,
) -> None:
    """Render the previews for one review item and record their paths.

    Read-only w.r.t. the dataset: it opens the *source* image (the canonical
    image is a verified byte copy, so one decode suffices) and writes only under
    ``previews_dir``. The originals are never modified.

    Args:
        evidence: The evidence record to populate with preview paths.
        source_image_path: Path to the source image to decode.
        blur_threshold: The frozen blur threshold (for the ``[BLURRY]`` mark).
        previews_dir: Output directory for rendered previews.
    """
    previews_dir.mkdir(parents=True, exist_ok=True)
    item = evidence.item
    slug = item.item_id.lower()
    stem = evidence.source_image_filename
    blur_tag = f"blur {evidence.blur:.1f}" + (" [BLURRY]" if evidence.is_blurry else "")
    dims = f"{evidence.width}x{evidence.height}"

    base = _load_rgb(source_image_path)

    original = base.copy()
    _draw_boxes(
        original,
        evidence.original_boxes_norm,
        color=_SOURCE_BOX_COLOR,
        tag_prefix="src",
    )
    orig_caption = (
        f"{item.item_id} ORIGINAL  {stem}  {dims}  "
        f"boxes={evidence.original_object_count}  {blur_tag}"
    )
    original = _caption(
        original, orig_caption, color=_BLUR_FG if evidence.is_blurry else _CAPTION_FG
    )
    orig_path = previews_dir / f"{slug}_original.jpg"
    original.save(orig_path, quality=92)
    evidence.preview_paths["original"] = _posix_rel(orig_path, previews_dir.parents[0])

    # A "corrected"/"after" view + a side-by-side only make sense when a
    # canonical annotation exists (i.e. not for the exclusion).
    if evidence.corrected_boxes_norm is not None:
        corrected = base.copy()
        _draw_boxes(
            corrected,
            evidence.corrected_boxes_norm,
            color=_CORRECTED_BOX_COLOR,
            tag_prefix="fix",
        )
        corr_caption = (
            f"{item.item_id} CORRECTED  {evidence.canonical_image_filename}  {dims}  "
            f"boxes={evidence.corrected_object_count}  {blur_tag}"
        )
        corrected = _caption(
            corrected,
            corr_caption,
            color=_BLUR_FG if evidence.is_blurry else _CAPTION_FG,
        )
        corr_path = previews_dir / f"{slug}_corrected.jpg"
        corrected.save(corr_path, quality=92)
        evidence.preview_paths["corrected"] = _posix_rel(
            corr_path, previews_dir.parents[0]
        )

        # Side-by-side ORIGINAL | CORRECTED for the re-annotations.
        if item.kind == _KIND_REANNOTATION:
            combo = _side_by_side(original, corrected)
            combo_path = previews_dir / f"{slug}_before_after.jpg"
            combo.save(combo_path, quality=92)
            evidence.preview_paths["before_after"] = _posix_rel(
                combo_path, previews_dir.parents[0]
            )


def _posix_rel(path: Path, root: Path) -> str:
    """Return ``path`` relative to ``root`` as POSIX, or its name on failure."""
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.name


def _load_json(path: Path) -> dict[str, object]:
    """Load a JSON document, raising :class:`SignoffError` when missing."""
    if not path.is_file():
        raise SignoffError(f"required artifact not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def derive_review_items(remediation_manifest: dict[str, object]) -> list[ReviewItem]:
    """Derive the outstanding review items from the frozen remediation manifest.

    This tool authors **no** new decisions: an item is "outstanding" iff the
    manifest already marked it ``PENDING_REVIEW`` (the three re-annotations and
    the held REVIEW_PENDING image) or recorded it as the proposed exclusion.
    The three Gate-A blur images are the manifest records whose canonical image
    still trips the frozen blur threshold — resolved later against the strict
    image-validation report, so they are attached in :func:`gather_evidence`.

    Args:
        remediation_manifest: The parsed ``remediation_manifest.json``.

    Returns:
        Review items for the re-annotations, the held image and the exclusion,
        in a stable ``QA``-id order.
    """
    items: list[ReviewItem] = []

    records = remediation_manifest.get("records", [])
    assert isinstance(records, list)
    for rec in records:
        assert isinstance(rec, dict)
        reviewer_status = str(rec["reviewer_status"])
        if reviewer_status != _REVIEWER_PENDING:
            continue
        action = str(rec["remediation_action"])
        kind = _KIND_REVIEW_HOLD if action == "KEEP_REVIEW_PENDING" else _KIND_REANNOTATION
        items.append(
            ReviewItem(
                item_id=f"QA{int(rec['qa_id']):02d}",
                kind=kind,
                qa_id=int(rec["qa_id"]),
                source_stem=str(rec["source_stem"]),
                canonical_stem=str(rec["canonical_stem"]),
                issue=str(rec["reason"]),
                proposed_decision=_proposed_decision_for(action),
                remediation_status=str(rec["remediation_status"]),
                reviewer_status=reviewer_status,
            )
        )

    exclusions = remediation_manifest.get("exclusions", [])
    assert isinstance(exclusions, list)
    for exc in exclusions:
        assert isinstance(exc, dict)
        items.append(
            ReviewItem(
                item_id=f"QA{int(exc['qa_id']):02d}",
                kind=_KIND_EXCLUSION,
                qa_id=int(exc["qa_id"]),
                source_stem=str(exc["source_stem"]),
                canonical_stem=None,
                issue=str(exc["reason"]),
                proposed_decision="EXCLUDE (confirm)",
                remediation_status=str(exc["remediation_status"]),
                reviewer_status=str(exc["reviewer_status"]),
            )
        )

    return sorted(items, key=lambda i: i.qa_id)


# Reviewer status vocabulary echoed from the ingestion tool (kept local so this
# tool depends on the manifest's *data*, not on importing the ingestion module).
_REVIEWER_PENDING = "PENDING_REVIEW"


def _proposed_decision_for(action: str) -> str:
    """Map a remediation action to a short proposed-decision phrase."""
    return {
        "REANNOTATE_SPLIT": "ACCEPT corrected split (5 boxes)",
        "REANNOTATE_ADD_INSTANCE": "ACCEPT corrected add-instance (6 boxes)",
        "REANNOTATE_TIGHTEN": "ACCEPT tightened box",
        "KEEP_REVIEW_PENDING": "Confirm keep as difficult sample, or reject",
    }.get(action, "Review")


def _record_by_stem(
    remediation_manifest: dict[str, object],
) -> dict[str, dict[str, object]]:
    """Index the manifest's retained records by source stem."""
    records = remediation_manifest.get("records", [])
    assert isinstance(records, list)
    out: dict[str, dict[str, object]] = {}
    for rec in records:
        assert isinstance(rec, dict)
        out[str(rec["source_stem"])] = rec
    return out


def _exclusion_by_stem(
    remediation_manifest: dict[str, object],
) -> dict[str, dict[str, object]]:
    """Index the manifest's exclusions by source stem."""
    exclusions = remediation_manifest.get("exclusions", [])
    assert isinstance(exclusions, list)
    out: dict[str, dict[str, object]] = {}
    for exc in exclusions:
        assert isinstance(exc, dict)
        out[str(exc["source_stem"])] = exc
    return out


def load_visual_qa_tile_ids(source_staging: Path) -> dict[str, int]:
    """Return a ``source_stem -> visual-QA tile id`` map (read-only, best effort).

    The pilot's manual-review ``qa_data.json`` is the authoritative source of the
    visual-QA tile numbering (QA01..QA21) that the visual-QA report and this
    sign-off report cross-reference. Clean-ACCEPT images carry ``qa_id = 0`` in
    the remediation manifest (they were never individually flagged), so their
    real tile id must come from here. Missing/malformed file -> empty map (the
    caller falls back to a stem-based label).

    Args:
        source_staging: Root of the source-preserved pilot staging.

    Returns:
        A mapping of source stem to its 1-based visual-QA tile id.
    """
    qa_data_path = source_staging / "manual_review" / "qa_data.json"
    if not qa_data_path.is_file():
        return {}
    try:
        data = json.loads(qa_data_path.read_text(encoding="utf-8"))
    except (ValueError, OSError):  # pragma: no cover - defensive
        return {}
    tiles = data.get("tiles", [])
    if not isinstance(tiles, list):
        return {}
    out: dict[str, int] = {}
    for tile in tiles:
        if isinstance(tile, dict) and "stem" in tile and "qa_id" in tile:
            out[str(tile["stem"])] = int(tile["qa_id"])
    return out


def derive_blur_gate_a_items(
    *,
    strict_validation: dict[str, object],
    remediation_manifest: dict[str, object],
    existing_stems: set[str],
    tile_ids: dict[str, int],
) -> list[ReviewItem]:
    """Derive the remaining ``IMAGE_BLURRY`` Gate-A items from strict validation.

    The strict (blur-blocking) image validation lists exactly the canonical
    images still tripping the frozen blur threshold. Each maps back to a
    manifest record (hence a source stem). QA01 already appears as the held
    REVIEW_PENDING item, so it is not duplicated here.

    Args:
        strict_validation: Parsed ``image_validation_strict.json``.
        remediation_manifest: Parsed ``remediation_manifest.json``.
        existing_stems: Source stems already emitted as review items.
        tile_ids: ``source_stem -> visual-QA tile id`` map (for the item id).

    Returns:
        Gate-A blur review items (in visual-QA tile order).
    """
    canon_to_record: dict[str, dict[str, object]] = {}
    records = remediation_manifest.get("records", [])
    assert isinstance(records, list)
    for rec in records:
        assert isinstance(rec, dict)
        canon_to_record[str(rec["canonical_image_filename"])] = rec

    issues = strict_validation.get("issues", [])
    assert isinstance(issues, list)
    items: list[ReviewItem] = []
    for issue in issues:
        assert isinstance(issue, dict)
        if str(issue.get("code")) != "IMAGE_BLURRY":
            continue
        canonical_image = str(issue["file"])
        rec = canon_to_record.get(canonical_image)
        if rec is None:  # pragma: no cover - strict report references a known file
            raise SignoffError(
                f"strict validation references unknown canonical image: "
                f"{canonical_image}"
            )
        source_stem = str(rec["source_stem"])
        if source_stem in existing_stems:
            # Already surfaced (QA01 is both held REVIEW_PENDING and blurry).
            continue
        tile_id = tile_ids.get(source_stem, 0)
        item_id = f"QA{tile_id:02d}" if tile_id else f"BLUR_{source_stem[:8]}"
        items.append(
            ReviewItem(
                item_id=item_id,
                kind=_KIND_BLUR_GATE_A,
                qa_id=tile_id,
                source_stem=source_stem,
                canonical_stem=str(rec["canonical_stem"]),
                issue=str(issue["message"]) + " (Gate A difficult-sample sign-off required)",
                proposed_decision="Confirm difficult-sample sign-off, or reject",
                remediation_status=str(rec["remediation_status"]),
                reviewer_status=str(rec["reviewer_status"]),
            )
        )
    return sorted(items, key=lambda i: i.qa_id)



def gather_evidence(
    item: ReviewItem,
    *,
    source_staging: Path,
    canonical_staging: Path,
    remediation_manifest: dict[str, object],
    blur_threshold: float,
) -> RenderedEvidence:
    """Collect the measured facts + annotations for one review item (read-only).

    Args:
        item: The review item to gather evidence for.
        source_staging: Root of the source-preserved pilot staging.
        canonical_staging: Root of the canonical candidate staging.
        remediation_manifest: The parsed remediation manifest.
        blur_threshold: The frozen blur threshold.

    Returns:
        The populated :class:`RenderedEvidence` (previews not yet rendered).

    Raises:
        SignoffError: When a referenced source/canonical file is missing.
    """
    records = _record_by_stem(remediation_manifest)
    exclusions = _exclusion_by_stem(remediation_manifest)

    source_image_filename = f"{item.source_stem}.jpg"
    source_image = source_staging / "images" / source_image_filename
    source_label = source_staging / "labels" / f"{item.source_stem}.txt"
    if not source_image.is_file():
        raise SignoffError(f"source image missing: {source_image}")

    image = _load_rgb(source_image)
    width, height = image.width, image.height
    blur = blur_score(image)
    original_boxes = read_yolo_boxes(source_label)

    if item.kind == _KIND_EXCLUSION:
        exc = exclusions[item.source_stem]
        return RenderedEvidence(
            item=item,
            source_image_filename=source_image_filename,
            canonical_image_filename=None,
            source_sha256=str(exc["source_sha256"]),
            width=width,
            height=height,
            blur=blur,
            is_blurry=blur < blur_threshold,
            original_object_count=int(exc["object_count"]),
            corrected_object_count=None,
            original_boxes_norm=original_boxes,
            corrected_boxes_norm=None,
        )

    rec = records[item.source_stem]
    canonical_image_filename = str(rec["canonical_image_filename"])
    canonical_label = (
        canonical_staging / "labels" / str(rec["canonical_label_filename"])
    )
    corrected_boxes = read_yolo_boxes(canonical_label)
    return RenderedEvidence(
        item=item,
        source_image_filename=source_image_filename,
        canonical_image_filename=canonical_image_filename,
        source_sha256=str(rec["source_sha256"]),
        width=width,
        height=height,
        blur=blur,
        is_blurry=blur < blur_threshold,
        original_object_count=int(rec["original_object_count"]),
        corrected_object_count=int(rec["corrected_object_count"]),
        original_boxes_norm=original_boxes,
        corrected_boxes_norm=corrected_boxes,
    )


def _boxes_payload(
    boxes: tuple[tuple[float, float, float, float], ...] | None,
    *,
    width: int,
    height: int,
) -> list[dict[str, object]] | None:
    """Serialise boxes into normalised + pixel-space payloads (or ``None``)."""
    if boxes is None:
        return None
    payload: list[dict[str, object]] = []
    for cx, cy, bw, bh in boxes:
        x1, y1, x2, y2 = _norm_to_pixel_xyxy((cx, cy, bw, bh), width=width, height=height)
        payload.append(
            {
                "normalized_cxcywh": [
                    round(cx, 6),
                    round(cy, 6),
                    round(bw, 6),
                    round(bh, 6),
                ],
                "pixel_xyxy": [round(x1, 2), round(y1, 2), round(x2, 2), round(y2, 2)],
            }
        )
    return payload


def build_evidence_document(
    evidences: list[RenderedEvidence], *, context: dict[str, object]
) -> dict[str, object]:
    """Build the ``evidence.json`` document (one entry per review item).

    For every corrected item the entry carries the exact source filename,
    canonical filename, source SHA-256, original + corrected object counts and
    the original vs corrected annotation coordinates (normalised + pixel-space).
    """
    entries = [
        {
            "item_id": ev.item.item_id,
            "kind": ev.item.kind,
            "qa_id": ev.item.qa_id,
            "source_image_filename": ev.source_image_filename,
            "canonical_image_filename": ev.canonical_image_filename,
            "source_sha256": ev.source_sha256,
            "width": ev.width,
            "height": ev.height,
            "blur_score": ev.blur,
            "is_blurry": ev.is_blurry,
            "original_object_count": ev.original_object_count,
            "corrected_object_count": ev.corrected_object_count,
            "original_annotation": _boxes_payload(
                ev.original_boxes_norm, width=ev.width, height=ev.height
            ),
            "corrected_annotation": _boxes_payload(
                ev.corrected_boxes_norm, width=ev.width, height=ev.height
            ),
            "issue": ev.item.issue,
            "proposed_decision": ev.item.proposed_decision,
            "remediation_status": ev.item.remediation_status,
            "reviewer_status": ev.item.reviewer_status,
            "previews": dict(sorted(ev.preview_paths.items())),
        }
        for ev in evidences
    ]
    return {**context, "items": len(entries), "evidence": entries}


def build_signoff_template(
    evidences: list[RenderedEvidence], *, context: dict[str, object]
) -> dict[str, object]:
    """Build the machine-readable sign-off template.

    Every row starts ``status = PENDING_REVIEW`` with an **empty**
    ``human_decision``, ``reviewer`` and ``date`` — the tool fills none of them.
    """
    rows = [
        {
            "item_id": ev.item.item_id,
            "qa_id": ev.item.qa_id,
            "kind": ev.item.kind,
            "source_image_filename": ev.source_image_filename,
            "canonical_image_filename": ev.canonical_image_filename,
            "issue": ev.item.issue,
            "proposed_decision": ev.item.proposed_decision,
            "status": _STATUS_PENDING,
            "human_decision": "",
            "reviewer": "",
            "date": "",
            "notes": "",
        }
        for ev in evidences
    ]
    return {
        **context,
        "allowed_statuses": list(_SIGNOFF_STATUSES),
        "instructions": (
            "Set 'status' to one of allowed_statuses and fill 'human_decision', "
            "'reviewer' and 'date' by hand. This file starts every item as "
            "PENDING_REVIEW; no field is auto-completed. Certifying the pilot is "
            "out of scope for this package."
        ),
        "items": len(rows),
        "signoff": rows,
    }


def build_integrity_document(
    *,
    source_before: dict[str, str],
    source_after: dict[str, str],
    canonical_before: dict[str, str],
    canonical_after: dict[str, str],
    context: dict[str, object],
) -> dict[str, object]:
    """Build the integrity-verification document (before/after snapshot proof)."""
    source_diff = _diff_snapshots(source_before, source_after)
    canonical_diff = _diff_snapshots(canonical_before, canonical_after)
    source_unchanged = source_before == source_after
    canonical_unchanged = canonical_before == canonical_after
    return {
        **context,
        "source_staging_unchanged": source_unchanged,
        "canonical_staging_unchanged": canonical_unchanged,
        "all_unchanged": source_unchanged and canonical_unchanged,
        "source_files_checked": len(source_after),
        "canonical_files_checked": len(canonical_after),
        "source_diff": source_diff,
        "canonical_diff": canonical_diff,
    }


def _write_json(path: Path, data: dict[str, object]) -> None:
    """Write ``data`` as deterministic JSON (sorted keys, trailing newline)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _context(
    *,
    source_staging: Path,
    canonical_staging: Path,
    review_root: Path,
    blur_threshold: float,
    signoff_version: str,
    signoff_timestamp: str,
) -> dict[str, object]:
    """Assemble the shared provenance echo written into every output document."""
    return {
        "pilot": "openimages-laptop",
        "sprint": "P4.2.5",
        "package": "human-qa-signoff",
        "signoff_version": signoff_version,
        "signoff_timestamp": signoff_timestamp,
        "source_staging": _rel_repo(source_staging),
        "canonical_staging": _rel_repo(canonical_staging),
        "review_root": _rel_repo(review_root),
        "ecotrace_class": "laptop",
        "ecotrace_class_id": 0,
        "blur_threshold": blur_threshold,
        "pilot_status": "PILOT_REVIEW_REQUIRED",
        "is_dataset_v1": False,
        "is_released": False,
        "certifies_pilot": False,
    }


def _rel_repo(path: Path) -> str:
    """Return ``path`` relative to the repo root as POSIX, or its name."""
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.name


def build_package(
    *,
    source_staging: Path,
    canonical_staging: Path,
    review_root: Path,
    blur_threshold: float,
    signoff_version: str,
    signoff_timestamp: str,
) -> dict[str, object]:
    """Assemble the entire sign-off package; return the integrity document.

    Snapshots the source and canonical image+label trees before and after
    rendering so the "no dataset artifact was modified" guarantee is *proven*,
    not merely asserted.

    Raises:
        SignoffError: On any missing artifact or if a snapshot drifts.
    """
    manifest_path = canonical_staging / "reports" / "remediation_manifest.json"
    strict_path = canonical_staging / "validation" / "image_validation_strict.json"
    remediation_manifest = _load_json(manifest_path)
    strict_validation = _load_json(strict_path)

    # The immutable trees we must not disturb: source images+labels AND canonical
    # images+labels. Snapshot each before doing anything else.
    watch_dirs = {
        "source_images": source_staging / "images",
        "source_labels": source_staging / "labels",
        "canonical_images": canonical_staging / "images",
        "canonical_labels": canonical_staging / "labels",
    }
    before = {name: snapshot_tree(path) for name, path in watch_dirs.items()}

    # Derive the review items purely from the frozen manifest + strict report.
    # The visual-QA tile ids restore the QA-NN numbering the manifest drops for
    # clean-ACCEPT images (so the Gate-A blur items read as QA17/QA18, matching
    # the visual-QA report), never inventing a decision.
    tile_ids = load_visual_qa_tile_ids(source_staging)
    items = derive_review_items(remediation_manifest)
    existing_stems = {i.source_stem for i in items}
    items += derive_blur_gate_a_items(
        strict_validation=strict_validation,
        remediation_manifest=remediation_manifest,
        existing_stems=existing_stems,
        tile_ids=tile_ids,
    )
    items.sort(key=lambda i: (i.qa_id, i.kind))

    previews_dir = review_root / "previews"
    evidences: list[RenderedEvidence] = []
    for item in items:
        evidence = gather_evidence(
            item,
            source_staging=source_staging,
            canonical_staging=canonical_staging,
            remediation_manifest=remediation_manifest,
            blur_threshold=blur_threshold,
        )
        render_item_previews(
            evidence,
            source_image_path=source_staging / "images" / evidence.source_image_filename,
            blur_threshold=blur_threshold,
            previews_dir=previews_dir,
        )
        evidences.append(evidence)

    context = _context(
        source_staging=source_staging,
        canonical_staging=canonical_staging,
        review_root=review_root,
        blur_threshold=blur_threshold,
        signoff_version=signoff_version,
        signoff_timestamp=signoff_timestamp,
    )

    _write_json(
        review_root / "evidence.json",
        build_evidence_document(evidences, context=context),
    )
    _write_json(
        review_root / "signoff_template.json",
        build_signoff_template(evidences, context=context),
    )

    # Snapshot again and compare: prove nothing in the watched trees changed.
    after = {name: snapshot_tree(path) for name, path in watch_dirs.items()}
    integrity = build_integrity_document(
        source_before={**before["source_images"], **before["source_labels"]},
        source_after={**after["source_images"], **after["source_labels"]},
        canonical_before={
            **before["canonical_images"],
            **before["canonical_labels"],
        },
        canonical_after={**after["canonical_images"], **after["canonical_labels"]},
        context=context,
    )
    _write_json(review_root / "integrity_verification.json", integrity)

    if not integrity["all_unchanged"]:
        raise SignoffError(
            "integrity check failed: a source/canonical artifact changed while "
            "building the review package"
        )
    return integrity


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Build the human QA sign-off package for the Laptop pilot "
            "(P4.2.5). Read-only on the source AND canonical staging; writes "
            "only under a separate review directory. Certifies nothing: every "
            "item is emitted PENDING_REVIEW."
        )
    )
    parser.add_argument(
        "--source-staging",
        type=Path,
        default=_DEFAULT_SOURCE_STAGING,
        help="Source-preserved pilot staging root (read-only).",
    )
    parser.add_argument(
        "--canonical-staging",
        type=Path,
        default=_DEFAULT_CANONICAL_STAGING,
        help="Canonical candidate staging root (read-only).",
    )
    parser.add_argument(
        "--review-root",
        type=Path,
        default=_DEFAULT_REVIEW_ROOT,
        help="Destination review directory (outside the immutable OID source).",
    )
    parser.add_argument(
        "--blur-threshold",
        type=float,
        default=None,
        help=(
            "Blur threshold for the [BLURRY] mark. Defaults to the frozen "
            "settings value so no new threshold is invented."
        ),
    )
    parser.add_argument(
        "--signoff-version",
        default=_DEFAULT_SIGNOFF_VERSION,
        help="Sign-off package version identifier recorded in every output.",
    )
    parser.add_argument(
        "--signoff-timestamp",
        default=_DEFAULT_SIGNOFF_TIMESTAMP,
        help="Injected ISO-8601 timestamp (the wall clock is never read).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point for the sign-off package builder.

    Args:
        argv: Optional argument vector (defaults to ``sys.argv``).

    Returns:
        A process exit code (0 clean, 1 integrity error, 2 usage error).
    """
    args = _parse_args(argv)
    if not args.source_staging.is_dir():
        print(
            f"error: source staging not found: {args.source_staging}",
            file=sys.stderr,
        )
        return _EXIT_USAGE
    if not args.canonical_staging.is_dir():
        print(
            f"error: canonical staging not found: {args.canonical_staging}",
            file=sys.stderr,
        )
        return _EXIT_USAGE
    try:
        datetime.fromisoformat(args.signoff_timestamp)
    except ValueError:
        print(
            "error: --signoff-timestamp is not valid ISO-8601: "
            f"{args.signoff_timestamp}",
            file=sys.stderr,
        )
        return _EXIT_USAGE

    blur_threshold = (
        args.blur_threshold
        if args.blur_threshold is not None
        else float(get_settings().blur_threshold)
    )

    try:
        integrity = build_package(
            source_staging=args.source_staging,
            canonical_staging=args.canonical_staging,
            review_root=args.review_root,
            blur_threshold=blur_threshold,
            signoff_version=args.signoff_version,
            signoff_timestamp=args.signoff_timestamp,
        )
    except SignoffError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return _EXIT_ERRORS

    print(json.dumps(integrity, indent=2, sort_keys=True))
    print(
        "sign-off package written to "
        f"{_rel_repo(args.review_root)} "
        f"(source_unchanged={integrity['source_staging_unchanged']}, "
        f"canonical_unchanged={integrity['canonical_staging_unchanged']})",
        file=sys.stderr,
    )
    return _EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())








