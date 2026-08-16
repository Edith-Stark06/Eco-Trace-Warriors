"""Tests for the P4.3.7 router-acquisition pipeline (spec §13).

Coverage:

* license gate (permissive / restricted / missing / unknown),
* semantic gate (explicit router vs. ambiguous / different-device / generic),
* combined source verification (:func:`verify_source`),
* local-archive format detection + ingestion for YOLO / COCO / Pascal VOC,
* provenance completeness,
* bounding-box geometry validation,
* frozen-``DuplicateDetector`` integration (self / against protected data),
* frozen-``DatasetSplitter`` integration (VERIFIED / CLASS_ABSENT / empty),
* automated QA three-valued grading (AUTO_ACCEPT / UNVERIFIED / AUTO_REJECT),
* connectivity behaviour (offline never probes; no-network -> UNAVAILABLE),
* end-to-end :func:`run_pipeline` orchestration, and
* the ``acquire_main`` CLI (usage errors, offline discover/verify, dry-run).

Every fixture is a *tiny synthetic dataset* built inside ``tmp_path`` — PIL noise
images plus hand-written YOLO / COCO / VOC annotations. Nothing here ever touches
the real dataset, the protected P4.3.5 / P4.3.6 trees, or the network: the
connectivity probe is dependency-injected and offline mode never probes. These
fixtures MUST NEVER enter the dataset; they exist only for the duration of a test.
"""

from __future__ import annotations

import json

import pytest

from device_ai.acquisition import (
    EXPECTED_CLASS_ID,
    EXPECTED_NUM_CLASSES,
    MODE_OFFLINE,
    MODE_ONLINE,
    AcquisitionConfig,
    LocalSourceSpec,
    run_pipeline,
    run_preflight,
    verify_source,
)
from device_ai.acquisition.adapters.base import (
    MECHANISM_LOCAL_ARCHIVE,
    SourceCandidate,
)
from device_ai.acquisition.cli import acquire_main
from device_ai.acquisition.dedup import (
    SKIPPED_EMPTY_BATCH,
    SKIPPED_NO_PROTECTED_DATA,
    run_dedup,
)
from device_ai.acquisition.formats import (
    FORMAT_COCO,
    FORMAT_UNKNOWN,
    FORMAT_VOC,
    FORMAT_YOLO,
    SourceBox,
    detect_format,
    distinct_source_labels,
    parse_annotations,
)
from device_ai.acquisition.ingest import ingest_source, validate_box_geometry
from device_ai.acquisition.licenses import evaluate_license
from device_ai.acquisition.network import (
    ONLINE,
    SKIPPED_OFFLINE,
    UNAVAILABLE,
    check_connectivity,
)
from device_ai.acquisition.pipeline import (
    STATUS_BLOCKED_NO_SOURCE,
    STATUS_BLOCKED_NO_VERIFIED_SOURCE,
    STATUS_DRY_RUN_OK,
    STATUS_WAVE_VALIDATED,
)
from device_ai.acquisition.provenance_model import build_manifest_dict, is_complete
from device_ai.acquisition.qa import run_automated_qa
from device_ai.acquisition.splitting import (
    BLOCKED_EMPTY,
    CLASS_ABSENT,
    VERIFIED,
    run_split,
)
from device_ai.configs.settings import Settings

from .conftest import write_image

# A fixed, explicit import timestamp — never generated at run time (the pipeline
# injects its own; these unit calls pass this deterministic value).
TS = "2026-08-16T00:00:00+00:00"
ROUTER_ID = EXPECTED_CLASS_ID  # frozen 11; asserted against load_taxonomy below
NUM_CLASSES = EXPECTED_NUM_CLASSES  # frozen 19


@pytest.fixture
def frozen_settings() -> Settings:
    """A fresh Settings carrying the frozen defaults (70/20/10, seed 42, ham 5).

    Constructed explicitly so the tests never depend on the process-wide
    ``get_settings()`` cache that sibling test modules may have mutated.
    """
    return Settings()


# ---------------------------------------------------------------------------
# Synthetic source builders (tmp_path only — never real production images)
# ---------------------------------------------------------------------------


def _yolo_source(
    root,
    specs,
    *,
    source_label: str = "router",
    box: str = "0.5 0.5 0.4 0.4",
    with_license: bool = False,
):
    """Build a minimal YOLO tree under ``root``.

    Args:
        root: Directory to create the ``images/``, ``labels/`` and ``data.yaml``.
        specs: One entry per image, each a dict with ``stem`` plus either
            ``seed`` (a deterministic noise image) or ``color`` (a solid fill).
            An optional ``label`` overrides the single-line label body/class.
        source_label: The class name recorded under ``names: {0: ...}``.
        box: Default YOLO box body for the single class-0 line.
        with_license: When true, embeds ``license: CC-BY-4.0`` in ``data.yaml``.
    """
    images = root / "images"
    labels = root / "labels"
    labels.mkdir(parents=True, exist_ok=True)
    for spec in specs:
        stem = spec["stem"]
        if "seed" in spec:
            write_image(images / f"{stem}.png", noise=True, seed=spec["seed"])
        else:
            write_image(images / f"{stem}.png", color=spec["color"])
        (labels / f"{stem}.txt").write_text(
            spec.get("label", f"0 {box}\n"), encoding="utf-8"
        )
    lines = ["names:", f"  0: {source_label}"]
    if with_license:
        lines.append("license: CC-BY-4.0")
    (root / "data.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return root


def _coco_source(root, *, source_label: str = "router"):
    """Build a minimal COCO tree: ``images/`` + a single annotations JSON."""
    images = root / "images"
    write_image(images / "c0.png", noise=True, seed=101)
    write_image(images / "c1.png", noise=True, seed=102)
    data = {
        "images": [
            {"id": 1, "file_name": "c0.png", "width": 128, "height": 128},
            {"id": 2, "file_name": "c1.png", "width": 128, "height": 128},
        ],
        "annotations": [
            {"id": 1, "image_id": 1, "category_id": 5, "bbox": [10, 10, 40, 40]},
            {"id": 2, "image_id": 2, "category_id": 5, "bbox": [20, 20, 30, 30]},
        ],
        "categories": [{"id": 5, "name": source_label}],
    }
    (root / "annotations.json").write_text(json.dumps(data), encoding="utf-8")
    return root


def _voc_source(root, *, source_label: str = "router"):
    """Build a minimal Pascal VOC tree: ``JPEGImages/`` + ``Annotations/``."""
    write_image(root / "JPEGImages" / "a0.png", noise=True, seed=201)
    anns = root / "Annotations"
    anns.mkdir(parents=True, exist_ok=True)
    xml = (
        "<annotation><filename>a0.png</filename>"
        "<size><width>128</width><height>128</height><depth>3</depth></size>"
        f"<object><name>{source_label}</name>"
        "<bndbox><xmin>10</xmin><ymin>10</ymin><xmax>70</xmax><ymax>70</ymax></bndbox>"
        "</object></annotation>"
    )
    (anns / "a0.xml").write_text(xml, encoding="utf-8")
    return root


def _ingest(src_root, *, images_root, labels_root, license_raw="CC-BY-4.0"):
    """Detect + parse + ingest a local source into a staging layout."""
    detected = detect_format(src_root)
    annotations = parse_annotations(detected, src_root)
    return ingest_source(
        annotations,
        detected=detected,
        images_root=images_root,
        labels_root=labels_root,
        source_dataset="fixture-dataset",
        source_url="",
        publisher="",
        license_decision=evaluate_license(license_raw),
        taxonomy_class="router",
        taxonomy_id=ROUTER_ID,
        import_timestamp=TS,
    )


def _count(root, suffix):
    """Count files with ``suffix`` under ``root`` (0 when the root is absent)."""
    if not root.is_dir():
        return 0
    return sum(1 for p in root.rglob(f"*{suffix}") if p.is_file())


# ---------------------------------------------------------------------------
# Frozen-contract sanity
# ---------------------------------------------------------------------------


def test_taxonomy_router_id_is_frozen_eleven():
    """The canonical loader resolves 'router' to id 11 (never assumed)."""
    from device_ai.dataset.taxonomy import load_taxonomy

    taxonomy = load_taxonomy()
    assert taxonomy.class_id_for("router") == 11
    assert taxonomy.num_classes == NUM_CLASSES


def test_preflight_passes_on_clean_layout(tmp_path, frozen_settings):
    """Preflight clears every frozen check with a tmp output layout."""
    config = AcquisitionConfig.default(root=tmp_path)
    result = run_preflight(config, settings=frozen_settings)
    assert result.passed, [c.to_dict() for c in result.failures]


# ---------------------------------------------------------------------------
# License gate
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "normalized"),
    [
        ("CC-BY-4.0", "cc-by"),
        ("CC0-1.0", "cc0"),
        ("Apache-2.0", "apache-2.0"),
        ("public domain", "public-domain"),
        ("team-owned", "team-owned"),
    ],
)
def test_license_permissive_accepted(raw, normalized):
    decision = evaluate_license(raw)
    assert decision.accepted is True
    assert decision.verdict == "ACCEPTED"
    assert decision.normalized_id == normalized


@pytest.mark.parametrize(
    "raw",
    ["CC-BY-NC-4.0", "CC-BY-ND-4.0", "proprietary", "all rights reserved"],
)
def test_license_restricted_rejected(raw):
    decision = evaluate_license(raw)
    assert decision.accepted is False
    assert decision.verdict == "REJECTED"


@pytest.mark.parametrize("raw", ["", "   ", "some-weird-license-2.3"])
def test_license_missing_or_unknown_is_unverified(raw):
    """Absent/unknown licenses fail closed to UNVERIFIED — never inferred."""
    decision = evaluate_license(raw)
    assert decision.accepted is False
    assert decision.verdict == "UNVERIFIED"


# ---------------------------------------------------------------------------
# Semantic gate
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw", ["router", "wifi-router", "wireless router", "dual-band router"]
)
def test_semantic_explicit_router_accepted(raw):
    from device_ai.acquisition.semantics import evaluate_source_label

    decision = evaluate_source_label(raw)
    assert decision.accepted is True
    assert decision.category == "explicit-router"


@pytest.mark.parametrize(
    ("raw", "category"),
    [
        ("modem/router", "ambiguous-combined"),
        ("access-point/router", "ambiguous-combined"),
        ("modem", "different-device"),
        ("gateway", "different-device"),
        ("switch", "different-device"),
        ("access point", "different-device"),
        ("networking device", "too-generic"),
        ("", "too-generic"),
        ("laptop", "not-router"),
    ],
)
def test_semantic_non_router_rejected(raw, category):
    from device_ai.acquisition.semantics import evaluate_source_label

    decision = evaluate_source_label(raw)
    assert decision.accepted is False
    assert decision.category == category


# ---------------------------------------------------------------------------
# Combined source verification
# ---------------------------------------------------------------------------


def _candidate(*, license_raw="CC-BY-4.0", bbox_available=True):
    return SourceCandidate(
        name="fixture",
        publisher="",
        url="",
        version="",
        license_raw=license_raw,
        license_url="",
        source_class="",
        bbox_available=bbox_available,
        image_identifier="images",
        annotation_identifier="labels",
        download_mechanism=MECHANISM_LOCAL_ARCHIVE,
        adapter="local-archive",
    )


def test_verify_source_accepts_permissive_bbox_router():
    verdict = verify_source(_candidate(), labels=["router"])
    assert verdict.accepted is True
    assert verdict.verdict == "ACCEPTED"


def test_verify_source_unverified_when_license_missing():
    verdict = verify_source(_candidate(license_raw=""), labels=["router"])
    assert verdict.verdict == "UNVERIFIED"
    assert verdict.accepted is False


def test_verify_source_rejects_classification_only():
    verdict = verify_source(_candidate(bbox_available=False), labels=["router"])
    assert verdict.verdict == "REJECTED"


def test_verify_source_rejects_non_router_labels():
    verdict = verify_source(_candidate(), labels=["modem"])
    assert verdict.verdict == "REJECTED"


def test_verify_source_defers_when_labels_unknown():
    """No declared labels + license/bbox ok -> UNVERIFIED (deferred to ingest)."""
    verdict = verify_source(_candidate(), labels=None)
    assert verdict.verdict == "UNVERIFIED"


# ---------------------------------------------------------------------------
# Format detection
# ---------------------------------------------------------------------------


def test_detect_format_yolo(tmp_path):
    src = _yolo_source(tmp_path / "y", [{"stem": "i0", "seed": 1}])
    detected = detect_format(src)
    assert detected.format_name == FORMAT_YOLO
    assert detected.supported is True
    assert detected.class_names == {0: "router"}


def test_detect_format_coco(tmp_path):
    detected = detect_format(_coco_source(tmp_path / "c"))
    assert detected.format_name == FORMAT_COCO
    assert detected.supported is True


def test_detect_format_voc(tmp_path):
    detected = detect_format(_voc_source(tmp_path / "v"))
    assert detected.format_name == FORMAT_VOC
    assert detected.supported is True


def test_detect_format_unknown(tmp_path):
    (tmp_path / "empty").mkdir()
    detected = detect_format(tmp_path / "empty")
    assert detected.format_name == FORMAT_UNKNOWN
    assert detected.supported is False


def test_yolo_without_names_map_unsupported(tmp_path):
    """A YOLO layout with no data.yaml names map is detected but unsupported."""
    root = tmp_path / "y"
    write_image(root / "images" / "i0.png", noise=True, seed=1)
    (root / "labels").mkdir(parents=True, exist_ok=True)
    (root / "labels" / "i0.txt").write_text("0 0.5 0.5 0.4 0.4\n", encoding="utf-8")
    detected = detect_format(root)
    assert detected.format_name == FORMAT_YOLO
    assert detected.supported is False


# ---------------------------------------------------------------------------
# Local-archive ingestion
# ---------------------------------------------------------------------------


def test_ingest_yolo_stages_router(tmp_path):
    src = _yolo_source(
        tmp_path / "src", [{"stem": "i0", "seed": 1}, {"stem": "i1", "seed": 2}]
    )
    images_root = tmp_path / "stage" / "images"
    labels_root = tmp_path / "stage" / "labels"
    outcome = _ingest(src, images_root=images_root, labels_root=labels_root)

    assert outcome.images_retained == 2
    assert outcome.boxes_staged == 2
    assert _count(images_root, ".png") == 2
    # Labels are rewritten at the frozen taxonomy id (11), not the source id (0).
    label_text = next(labels_root.rglob("*.txt")).read_text(encoding="utf-8")
    assert label_text.startswith(f"{ROUTER_ID} ")


def test_ingest_coco_stages_router(tmp_path):
    src = _coco_source(tmp_path / "src")
    images_root = tmp_path / "stage" / "images"
    labels_root = tmp_path / "stage" / "labels"
    outcome = _ingest(src, images_root=images_root, labels_root=labels_root)
    assert outcome.images_retained == 2
    assert outcome.boxes_staged == 2


def test_ingest_voc_stages_router(tmp_path):
    src = _voc_source(tmp_path / "src")
    images_root = tmp_path / "stage" / "images"
    labels_root = tmp_path / "stage" / "labels"
    outcome = _ingest(src, images_root=images_root, labels_root=labels_root)
    assert outcome.images_retained == 1
    assert outcome.boxes_staged == 1


def test_ingest_refuses_non_accepted_license(tmp_path):
    """Ingesting under a non-accepted license is a hard error, never silent."""
    src = _yolo_source(tmp_path / "src", [{"stem": "i0", "seed": 1}])
    with pytest.raises(ValueError):
        _ingest(
            src,
            images_root=tmp_path / "stage" / "images",
            labels_root=tmp_path / "stage" / "labels",
            license_raw="",  # -> UNVERIFIED -> not accepted
        )


def test_ingest_semantic_rejects_non_router_boxes(tmp_path):
    """A source whose only label is non-router stages nothing (per-box gate)."""
    src = _yolo_source(
        tmp_path / "src", [{"stem": "i0", "seed": 1}], source_label="laptop"
    )
    images_root = tmp_path / "stage" / "images"
    labels_root = tmp_path / "stage" / "labels"
    outcome = _ingest(src, images_root=images_root, labels_root=labels_root)
    assert outcome.boxes_staged == 0
    assert outcome.images_retained == 0
    assert outcome.boxes_semantically_rejected >= 1
    assert _count(images_root, ".png") == 0


# ---------------------------------------------------------------------------
# Provenance completeness
# ---------------------------------------------------------------------------


def test_provenance_is_complete_for_every_staged_image(tmp_path):
    src = _yolo_source(
        tmp_path / "src", [{"stem": "i0", "seed": 1}, {"stem": "i1", "seed": 2}]
    )
    outcome = _ingest(
        src,
        images_root=tmp_path / "stage" / "images",
        labels_root=tmp_path / "stage" / "labels",
    )
    assert len(outcome.provenance) == 2
    assert outcome.provenance_complete == 2
    assert all(is_complete(record) for record in outcome.provenance)

    manifest = build_manifest_dict(
        outcome.provenance, target_class="router", import_timestamp=TS
    )
    assert manifest["total_records"] == 2
    assert manifest["complete_records"] == 2
    assert manifest["incomplete_records"] == 0


# ---------------------------------------------------------------------------
# Bounding-box geometry validation
# ---------------------------------------------------------------------------


def _box(**kw):
    base = dict(
        source_class_id=0,
        source_class_name="router",
        x_center=0.5,
        y_center=0.5,
        width=0.4,
        height=0.4,
    )
    base.update(kw)
    return SourceBox(**base)


def test_valid_box_geometry_passes():
    assert validate_box_geometry(_box()) == ""


def test_box_center_out_of_range_rejected():
    assert validate_box_geometry(_box(x_center=1.5)) != ""


def test_box_non_positive_size_rejected():
    assert validate_box_geometry(_box(width=0.0)) != ""


def test_box_extends_past_edge_rejected():
    # centre 0.9 + half-width 0.2 -> right edge 1.1, outside the unit square.
    assert validate_box_geometry(_box(x_center=0.9, width=0.4)) != ""


# ---------------------------------------------------------------------------
# Frozen deduplication integration
# ---------------------------------------------------------------------------


def test_dedup_flags_intra_batch_duplicate(tmp_path, frozen_settings):
    """Byte-identical staged images (same seed) collapse to one duplicate."""
    images = tmp_path / "images"
    write_image(images / "a.png", noise=True, seed=1)
    write_image(images / "b.png", noise=True, seed=1)  # identical bytes
    outcome = run_dedup(
        batch_images_root=images, protected_roots=(), settings=frozen_settings
    )
    assert outcome.status == SKIPPED_NO_PROTECTED_DATA
    assert outcome.batch_scanned == 2
    assert outcome.num_batch_duplicates == 1


def test_dedup_flags_batch_copy_of_protected(tmp_path, frozen_settings):
    """A new image duplicating protected data is flagged; protected is retained."""
    protected = tmp_path / "protected"
    write_image(protected / "p0.png", noise=True, seed=1)
    images = tmp_path / "images"
    write_image(images / "dup.png", noise=True, seed=1)  # copy of protected
    write_image(images / "uniq.png", noise=True, seed=2)  # unique
    outcome = run_dedup(
        batch_images_root=images,
        protected_roots=(("prot", protected),),
        settings=frozen_settings,
    )
    assert outcome.status == "COMPLETED"
    assert outcome.protected_scanned == 1
    assert outcome.batch_scanned == 2
    assert outcome.batch_duplicates == ("dup.png",)
    assert "uniq.png" not in outcome.batch_duplicates


def test_dedup_skips_empty_batch(tmp_path, frozen_settings):
    empty = tmp_path / "images"
    empty.mkdir()
    outcome = run_dedup(
        batch_images_root=empty, protected_roots=(), settings=frozen_settings
    )
    assert outcome.status == SKIPPED_EMPTY_BATCH
    assert outcome.num_batch_duplicates == 0


# ---------------------------------------------------------------------------
# Frozen split integration
# ---------------------------------------------------------------------------


def _write_labels(labels_root, count, class_id=ROUTER_ID):
    labels_root.mkdir(parents=True, exist_ok=True)
    identifiers = []
    for i in range(count):
        stem = f"img_{i:02d}"
        (labels_root / f"{stem}.txt").write_text(
            f"{class_id} 0.5 0.5 0.4 0.4\n", encoding="utf-8"
        )
        identifiers.append(f"{stem}.png")
    return identifiers


def test_split_verified_with_twelve_images(tmp_path, frozen_settings):
    labels_root = tmp_path / "labels"
    identifiers = _write_labels(labels_root, 12)
    outcome = run_split(
        identifiers,
        labels_root=labels_root,
        taxonomy_id=ROUTER_ID,
        num_classes=NUM_CLASSES,
        settings=frozen_settings,
    )
    assert outcome.status == VERIFIED
    assert outcome.verified is True
    assert outcome.deterministic and outcome.disjoint and outcome.complete
    assert outcome.counts == {"train": 8, "val": 2, "test": 2}
    assert all(outcome.class_present.values())


def test_split_class_absent_when_val_empty(tmp_path, frozen_settings):
    """N=2 -> 1/0/1: the class is absent from the empty val split (reported as-is)."""
    labels_root = tmp_path / "labels"
    identifiers = _write_labels(labels_root, 2)
    outcome = run_split(
        identifiers,
        labels_root=labels_root,
        taxonomy_id=ROUTER_ID,
        num_classes=NUM_CLASSES,
        settings=frozen_settings,
    )
    assert outcome.status == CLASS_ABSENT
    assert outcome.verified is False
    assert outcome.class_present.get("val") is False


def test_split_blocked_on_empty_input(tmp_path, frozen_settings):
    outcome = run_split(
        [],
        labels_root=tmp_path / "labels",
        taxonomy_id=ROUTER_ID,
        num_classes=NUM_CLASSES,
        settings=frozen_settings,
    )
    assert outcome.status == BLOCKED_EMPTY
    assert outcome.verified is False


# ---------------------------------------------------------------------------
# Automated QA
# ---------------------------------------------------------------------------


def _stage_one(images_root, labels_root, *, stem, label, **image_kw):
    write_image(images_root / f"{stem}.png", **image_kw)
    labels_root.mkdir(parents=True, exist_ok=True)
    if label is not None:
        (labels_root / f"{stem}.txt").write_text(label, encoding="utf-8")


def test_qa_auto_accepts_clean_router_images(tmp_path, frozen_settings):
    src = _yolo_source(
        tmp_path / "src",
        [{"stem": "i0", "seed": 1}, {"stem": "i1", "seed": 2}, {"stem": "i2", "seed": 3}],
    )
    images_root = tmp_path / "stage" / "images"
    labels_root = tmp_path / "stage" / "labels"
    _ingest(src, images_root=images_root, labels_root=labels_root)
    qa = run_automated_qa(
        images_root=images_root,
        labels_root=labels_root,
        taxonomy_id=ROUTER_ID,
        num_classes=NUM_CLASSES,
        settings=frozen_settings,
    )
    assert len(qa.accepted) == 3
    assert qa.rejected == ()
    assert qa.unverified == ()
    assert qa.status == "AUTO_QA_PASSED"


def test_qa_marks_dark_image_unverified(tmp_path, frozen_settings):
    """A verifiable-quality concern (dark/blurry) -> UNVERIFIED, never accepted."""
    src = _yolo_source(
        tmp_path / "src",
        [{"stem": "i0", "seed": 1}, {"stem": "i1", "seed": 2}, {"stem": "dark", "color": (5, 5, 5)}],
    )
    images_root = tmp_path / "stage" / "images"
    labels_root = tmp_path / "stage" / "labels"
    _ingest(src, images_root=images_root, labels_root=labels_root)
    qa = run_automated_qa(
        images_root=images_root,
        labels_root=labels_root,
        taxonomy_id=ROUTER_ID,
        num_classes=NUM_CLASSES,
        settings=frozen_settings,
    )
    assert len(qa.accepted) == 2
    assert len(qa.unverified) == 1


def test_qa_auto_rejects_wrong_class(tmp_path, frozen_settings):
    images_root = tmp_path / "images"
    labels_root = tmp_path / "labels"
    _stage_one(
        images_root, labels_root, stem="x", label="0 0.5 0.5 0.4 0.4\n", noise=True, seed=7
    )
    qa = run_automated_qa(
        images_root=images_root,
        labels_root=labels_root,
        taxonomy_id=ROUTER_ID,
        num_classes=NUM_CLASSES,
        settings=frozen_settings,
    )
    assert "x.png" in qa.rejected
    assert "x.png" not in qa.accepted


def test_qa_auto_rejects_duplicate(tmp_path, frozen_settings):
    images_root = tmp_path / "images"
    labels_root = tmp_path / "labels"
    _stage_one(
        images_root,
        labels_root,
        stem="d",
        label=f"{ROUTER_ID} 0.5 0.5 0.4 0.4\n",
        noise=True,
        seed=8,
    )
    qa = run_automated_qa(
        images_root=images_root,
        labels_root=labels_root,
        taxonomy_id=ROUTER_ID,
        num_classes=NUM_CLASSES,
        duplicate_paths=("d.png",),
        settings=frozen_settings,
    )
    assert "d.png" in qa.rejected


def test_qa_auto_rejects_missing_label(tmp_path, frozen_settings):
    images_root = tmp_path / "images"
    labels_root = tmp_path / "labels"
    _stage_one(images_root, labels_root, stem="m", label=None, noise=True, seed=9)
    qa = run_automated_qa(
        images_root=images_root,
        labels_root=labels_root,
        taxonomy_id=ROUTER_ID,
        num_classes=NUM_CLASSES,
        settings=frozen_settings,
    )
    assert "m.png" in qa.rejected


# ---------------------------------------------------------------------------
# Connectivity — offline never probes; no-network fails closed
# ---------------------------------------------------------------------------


def test_connectivity_offline_never_probes():
    calls: list[int] = []

    def probe():
        calls.append(1)
        return True

    result = check_connectivity(offline=True, probe=probe)
    assert result.status == SKIPPED_OFFLINE
    assert result.probed is False
    assert result.online is False
    assert calls == []  # the probe must never be invoked in offline mode


def test_connectivity_online_probe_true():
    result = check_connectivity(offline=False, probe=lambda: True)
    assert result.status == ONLINE
    assert result.online is True
    assert result.probed is True


def test_connectivity_online_probe_false():
    result = check_connectivity(offline=False, probe=lambda: False)
    assert result.status == UNAVAILABLE
    assert result.online is False


def test_connectivity_probe_exception_is_unavailable():
    def boom():
        raise OSError("no route to host")

    result = check_connectivity(offline=False, probe=boom)
    assert result.status == UNAVAILABLE
    assert result.online is False


# ---------------------------------------------------------------------------
# End-to-end pipeline (hermetic: injected probe / readiness / timestamp / env)
# ---------------------------------------------------------------------------


def _readiness_incomplete(**_kwargs):
    """A stand-in readiness auditor (router wave is expected INCOMPLETE)."""
    return {"overall": "INCOMPLETE"}


def test_pipeline_offline_valid_source_validates_wave(tmp_path, frozen_settings):
    src = _yolo_source(
        tmp_path / "src", [{"stem": f"i{i:02d}", "seed": i + 1} for i in range(12)]
    )
    config = AcquisitionConfig.default(root=tmp_path)
    result = run_pipeline(
        config=config,
        mode=MODE_OFFLINE,
        local_source=LocalSourceSpec(path=src, license_raw="CC-BY-4.0"),
        coordinates=None,
        env={},
        readiness_audit=_readiness_incomplete,
        timestamp=TS,
        settings=frozen_settings,
    )
    assert result.status == STATUS_WAVE_VALIDATED
    assert not result.blockers
    # 12 images staged with class-11 labels; provenance manifest written.
    assert _count(config.images_root, ".png") == 12
    assert _count(config.labels_root, ".txt") == 12
    assert config.provenance_path.exists()
    manifest = json.loads(config.provenance_path.read_text(encoding="utf-8"))
    assert manifest["total_records"] == 12
    # Protected trees are absent throughout and remain untouched.
    for _label, root in config.protected_roots:
        assert not root.exists()


def test_pipeline_offline_no_source_blocks_on_source(tmp_path, frozen_settings):
    config = AcquisitionConfig.default(root=tmp_path)
    result = run_pipeline(
        config=config,
        mode=MODE_OFFLINE,
        local_source=None,
        coordinates=None,
        env={},
        readiness_audit=_readiness_incomplete,
        timestamp=TS,
        settings=frozen_settings,
    )
    assert result.status == STATUS_BLOCKED_NO_SOURCE
    assert any("no local source" in b.lower() for b in result.blockers)
    assert _count(config.images_root, ".png") == 0


def test_pipeline_rejects_ambiguous_labels(tmp_path, frozen_settings):
    src = _yolo_source(
        tmp_path / "src", [{"stem": "i0", "seed": 1}], source_label="modem/router"
    )
    config = AcquisitionConfig.default(root=tmp_path)
    result = run_pipeline(
        config=config,
        mode=MODE_OFFLINE,
        local_source=LocalSourceSpec(path=src, license_raw="CC-BY-4.0"),
        coordinates=None,
        env={},
        readiness_audit=_readiness_incomplete,
        timestamp=TS,
        settings=frozen_settings,
    )
    assert result.status == STATUS_BLOCKED_NO_VERIFIED_SOURCE
    assert _count(config.images_root, ".png") == 0


def test_pipeline_rejects_missing_license(tmp_path, frozen_settings):
    src = _yolo_source(tmp_path / "src", [{"stem": "i0", "seed": 1}])  # no license
    config = AcquisitionConfig.default(root=tmp_path)
    result = run_pipeline(
        config=config,
        mode=MODE_OFFLINE,
        local_source=LocalSourceSpec(path=src, license_raw=""),
        coordinates=None,
        env={},
        readiness_audit=_readiness_incomplete,
        timestamp=TS,
        settings=frozen_settings,
    )
    assert result.status == STATUS_BLOCKED_NO_VERIFIED_SOURCE
    assert _count(config.images_root, ".png") == 0


def test_pipeline_dry_run_writes_nothing(tmp_path, frozen_settings):
    src = _yolo_source(
        tmp_path / "src", [{"stem": "i0", "seed": 1}, {"stem": "i1", "seed": 2}]
    )
    config = AcquisitionConfig.default(root=tmp_path)
    result = run_pipeline(
        config=config,
        mode=MODE_OFFLINE,
        local_source=LocalSourceSpec(path=src, license_raw="CC-BY-4.0"),
        coordinates=None,
        env={},
        dry_run=True,
        readiness_audit=_readiness_incomplete,
        timestamp=TS,
        settings=frozen_settings,
    )
    assert result.status == STATUS_DRY_RUN_OK
    assert not config.provenance_path.exists()
    assert _count(config.images_root, ".png") == 0


def test_pipeline_online_no_coordinates_blocks_on_source(tmp_path, frozen_settings):
    """Online + no coordinates/creds/local source -> blocked by SOURCE, not network."""
    config = AcquisitionConfig.default(root=tmp_path)
    calls: list[int] = []

    def probe():
        calls.append(1)
        return True

    result = run_pipeline(
        config=config,
        mode=MODE_ONLINE,
        local_source=None,
        coordinates=None,
        env={},
        probe=probe,
        readiness_audit=_readiness_incomplete,
        timestamp=TS,
        settings=frozen_settings,
    )
    assert result.status == STATUS_BLOCKED_NO_SOURCE
    assert len(calls) == 1  # single connectivity probe; no real network access


# ---------------------------------------------------------------------------
# CLI (acquire_main) — exit codes only, always under a tmp --repo-root
# ---------------------------------------------------------------------------


def test_cli_offline_without_source_is_usage_error(tmp_path):
    rc = acquire_main(["run", "--mode", "offline", "--repo-root", str(tmp_path)])
    assert rc == 2


def test_cli_nonexistent_source_is_usage_error(tmp_path):
    rc = acquire_main(
        [
            "run",
            "--mode",
            "offline",
            "--source",
            str(tmp_path / "does_not_exist"),
            "--repo-root",
            str(tmp_path),
        ]
    )
    assert rc == 2


def test_cli_discover_offline_returns_ok(tmp_path):
    rc = acquire_main(["discover", "--mode", "offline", "--repo-root", str(tmp_path)])
    assert rc == 0


def test_cli_verify_offline_returns_ok(tmp_path):
    rc = acquire_main(["verify", "--mode", "offline", "--repo-root", str(tmp_path)])
    assert rc == 0


def test_cli_report_without_prior_run_is_usage_error(tmp_path):
    rc = acquire_main(["report", "--repo-root", str(tmp_path)])
    assert rc == 2


def test_cli_run_offline_dry_run_returns_ok(tmp_path):
    src = _yolo_source(
        tmp_path / "src", [{"stem": "i0", "seed": 1}, {"stem": "i1", "seed": 2}]
    )
    rc = acquire_main(
        [
            "run",
            "--mode",
            "offline",
            "--source",
            str(src),
            "--license",
            "CC-BY-4.0",
            "--dry-run",
            "--repo-root",
            str(tmp_path),
        ]
    )
    assert rc == 0
