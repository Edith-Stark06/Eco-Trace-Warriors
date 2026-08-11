"""Offline tests for the P4.3.4 multi-class human-QA package builder.

These tests exercise ``scripts/build_multiclass_qa_p434.py`` — the read-only
human-QA & candidate-assessment package generator — end to end over *synthetic*
staging trees. No network access happens and no frozen ``device_ai`` module is
modified: synthetic JPEGs / YOLO labels / provenance manifests are written to a
temp tree and the real script runs over them.

The invariants under test are exactly the P4.3.4 guarantees:

* dynamic discovery of acquired classes from provenance manifests (the completed
  ``laptop`` pilot is excluded);
* deterministic, reproducible output (fixed seed + injected timestamp);
* provenance / SHA-256 reconciliation against the manifests;
* strict read-only behaviour w.r.t. **both** the Open Images source and the
  per-class staging trees (before/after snapshot proof);
* every reviewable item emitted ``PENDING_REVIEW`` with blank human fields;
* the tool never auto-accepts / auto-rejects — ``proposed_decision`` is advisory
  and never promotes;
* the Dataset-v1.0 candidate inventory admits only ``QA_ACCEPTED`` items and is
  therefore empty at generation;
* malformed / missing labels and missing artifacts are handled without crashing;
* CLI usage errors return the documented exit code.

Both the builder and its script-level dependencies live under ``scripts/`` (off
the pytest pythonpath), so that directory is prepended to ``sys.path`` before
import.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from PIL import Image

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCRIPTS_DIR = _REPO_ROOT / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import build_multiclass_qa_p434 as qa  # noqa: E402

from device_ai.dataset.hashing import sha256_hash  # noqa: E402

_TIMESTAMP = "2026-08-10T00:00:00+00:00"
_SEED = 20260810


# --------------------------------------------------------------------------- #
# Fixtures / helpers                                                          #
# --------------------------------------------------------------------------- #
def _make_class(
    staging_root: Path,
    source_base: Path,
    *,
    name: str,
    class_id: int,
    source_class: str,
    n: int,
    nested: bool = False,
    with_conversion: bool = True,
    bad_label_stem: str | None = None,
    missing_label_stem: str | None = None,
) -> Path:
    """Create one synthetic per-class staging dir + immutable source tree.

    Returns the per-class staging directory. Every staged image's SHA-256 is
    written into the provenance manifest so reconciliation succeeds.
    """
    parent = staging_root / "openimages_multiclass_v1" if nested else staging_root
    staging = parent / f"openimages_{name}_v1"
    images = staging / "images"
    labels = staging / "labels"
    images.mkdir(parents=True)
    labels.mkdir(parents=True)
    source_images = source_base / name
    source_images.mkdir(parents=True)

    records: list[dict[str, object]] = []
    for i in range(n):
        stem = f"{name}_{i:03d}"
        img_path = images / f"{stem}.jpg"
        Image.new("RGB", (128, 96), (100 + i, 120, 140)).save(img_path, format="JPEG")
        digest = sha256_hash(img_path.read_bytes())

        object_count = 1
        if stem == missing_label_stem:
            object_count = 0
        elif stem == bad_label_stem:
            # Wrong-arity line: _read_yolo skips it, the gate flags it — no crash.
            (labels / f"{stem}.txt").write_text("5 0.5 0.5\n", encoding="utf-8")
        else:
            (labels / f"{stem}.txt").write_text(
                f"{class_id} 0.5 0.5 0.4 0.4\n", encoding="utf-8"
            )

        (source_images / f"{stem}.jpg").write_bytes(b"src-" + stem.encode())
        records.append(
            {
                "stem": stem,
                "sha256": digest,
                "source_image_filename": f"{stem}.jpg",
                "object_count": object_count,
                "width": 128,
                "height": 96,
            }
        )

    manifest = {
        "ecotrace_class": name,
        "ecotrace_class_id": class_id,
        "source": "Open Images V7",
        "source_class": source_class,
        "source_images_root": str(source_images),
        "source_labels_root": str(source_images),
        "taxonomy_version": "test",
        "total_images": n,
        "records": records,
    }
    provenance = staging / "provenance"
    provenance.mkdir(parents=True, exist_ok=True)
    (provenance / "provenance_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    if with_conversion:
        reports = staging / "reports"
        reports.mkdir(parents=True, exist_ok=True)
        (reports / "conversion_report.json").write_text(
            json.dumps({"ok": True}), encoding="utf-8"
        )
    return staging


def _snapshot(root: Path) -> dict[str, str]:
    """Return a ``relpath -> sha256`` snapshot of every file under ``root``."""
    return {
        p.relative_to(root).as_posix(): sha256_hash(p.read_bytes())
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


@pytest.fixture()
def staging(tmp_path: Path) -> Path:
    """A realistic staging root: smartphone top-level + tablet/monitor nested."""
    root = tmp_path / "staging"
    src = tmp_path / "oid_source"
    _make_class(
        root, src, name="smartphone", class_id=1, source_class="Mobile phone", n=3
    )
    _make_class(
        root, src, name="tablet", class_id=2, source_class="Tablet computer", n=4,
        nested=True,
    )
    _make_class(
        root, src, name="monitor", class_id=5, source_class="Computer monitor", n=2,
        nested=True,
    )
    return root


def _run(staging_root: Path, review_root: Path, **extra: str) -> int:
    """Invoke the builder's ``main`` with deterministic defaults."""
    argv = [
        "--staging-root", str(staging_root),
        "--review-root", str(review_root),
        "--timestamp", _TIMESTAMP,
        "--sample-seed", str(_SEED),
    ]
    for key, value in extra.items():
        argv.extend([f"--{key.replace('_', '-')}", value])
    return qa.main(argv)


# --------------------------------------------------------------------------- #
# Part 1 — discovery                                                          #
# --------------------------------------------------------------------------- #
def test_discovery_finds_all_classes_sorted_by_id(staging: Path) -> None:
    classes = qa.discover_classes(staging, exclude=qa._PILOT_CLASS)
    assert [c.ecotrace_class for c in classes] == ["smartphone", "tablet", "monitor"]
    assert [c.class_id for c in classes] == [1, 2, 5]


def test_discovery_excludes_protected_pilot(tmp_path: Path) -> None:
    root = tmp_path / "staging"
    src = tmp_path / "src"
    _make_class(
        root, src, name="tablet", class_id=2, source_class="Tablet computer", n=1
    )
    _make_class(root, src, name="laptop", class_id=0, source_class="Laptop", n=1)
    classes = qa.discover_classes(root, exclude=qa._PILOT_CLASS)
    assert [c.ecotrace_class for c in classes] == ["tablet"]


def test_discovery_empty_when_no_manifests(tmp_path: Path) -> None:
    assert qa.discover_classes(tmp_path, exclude=qa._PILOT_CLASS) == []


# --------------------------------------------------------------------------- #
# snapshot / diff determinism                                                 #
# --------------------------------------------------------------------------- #
def test_snapshot_tree_is_deterministic_and_diffs(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("one", encoding="utf-8")
    (tmp_path / "b.txt").write_text("two", encoding="utf-8")
    before = qa.snapshot_tree(tmp_path)
    assert qa.snapshot_tree(tmp_path) == before  # deterministic
    (tmp_path / "b.txt").write_text("changed", encoding="utf-8")
    (tmp_path / "c.txt").write_text("new", encoding="utf-8")
    diff = qa._diff_snapshots(before, qa.snapshot_tree(tmp_path))
    assert diff == {"added": ["c.txt"], "removed": [], "modified": ["b.txt"]}


def test_snapshot_missing_dir_is_empty(tmp_path: Path) -> None:
    assert qa.snapshot_tree(tmp_path / "nope") == {}


# --------------------------------------------------------------------------- #
# Part 1 — inventory + SHA-256 reconciliation                                 #
# --------------------------------------------------------------------------- #
def test_inventory_counts_and_reconciles(staging: Path) -> None:
    classes = qa.discover_classes(staging, exclude=qa._PILOT_CLASS)
    document, staged = qa.build_inventory(classes, context={"sprint": "P4.3.4"})
    assert document["class_count"] == 3
    assert document["total_images"] == 9
    assert document["all_sha256_reconciled"] is True
    by_class = {e["ecotrace_class"]: e for e in document["classes"]}
    assert by_class["tablet"]["image_count"] == 4
    assert by_class["tablet"]["sha256_reconciled"] is True
    assert staged["tablet"]  # per-stem digests exposed for the integrity check


def test_inventory_flags_sha256_mismatch(tmp_path: Path) -> None:
    root = tmp_path / "staging"
    src = tmp_path / "src"
    staging_dir = _make_class(
        root, src, name="tablet", class_id=2, source_class="Tablet computer", n=2
    )
    manifest_path = staging_dir / "provenance" / "provenance_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["records"][0]["sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    classes = qa.discover_classes(root, exclude=qa._PILOT_CLASS)
    document, _ = qa.build_inventory(classes, context={})
    assert document["all_sha256_reconciled"] is False
    assert document["classes"][0]["sha256_mismatches"] == ["tablet_000"]


# --------------------------------------------------------------------------- #
# Parts 4/5 — sign-off rows: PENDING_REVIEW, blank human fields, advisory      #
# --------------------------------------------------------------------------- #
def test_proposed_decision_is_advisory() -> None:
    assert qa._proposed_decision([], is_blurry=False) == (qa._DECISION_ACCEPTED, "none")
    decision, summary = qa._proposed_decision(["EMPTY_LABEL"], is_blurry=True)
    assert decision == qa._DECISION_REVIEW_REQUIRED
    assert "EMPTY_LABEL" in summary and "BLURRY" in summary


def test_signoff_rows_all_pending_with_blank_human_fields(staging: Path) -> None:
    classes = qa.discover_classes(staging, exclude=qa._PILOT_CLASS)
    tablet = next(c for c in classes if c.ecotrace_class == "tablet")
    tiles, _ = qa.build_visual_qa(
        tablet,
        class_names=qa.load_taxonomy().class_names,
        blur_threshold=100.0,
        class_out_dir=staging.parent / "review" / "tablet",
        page_size=30,
        cols=5,
        cell=320,
    )
    rows = qa.build_signoff_rows(tablet, tiles, issue_map={})
    assert len(rows) == 4
    for row in rows:
        assert row["status"] == "PENDING_REVIEW"
        assert row["human_decision"] == ""
        assert row["reviewer"] == ""
        assert row["review_date"] == ""
        assert row["notes"] == ""
        # Even an ACCEPTED proposal never pre-fills the human status.
        assert row["proposed_decision"] in qa._DECISION_STATES


def test_signoff_document_reports_pending_count(staging: Path) -> None:
    classes = qa.discover_classes(staging, exclude=qa._PILOT_CLASS)
    rows: list[dict[str, object]] = []
    for acquired in classes:
        tiles, _ = qa.build_visual_qa(
            acquired,
            class_names=qa.load_taxonomy().class_names,
            blur_threshold=100.0,
            class_out_dir=staging.parent / "rev" / acquired.ecotrace_class,
            page_size=30,
            cols=5,
            cell=320,
        )
        rows.extend(qa.build_signoff_rows(acquired, tiles, issue_map={}))
    document = qa.build_signoff_document(rows, context={})
    assert document["total_items"] == 9
    assert document["pending_review_count"] == 9
    assert document["allowed_statuses"] == list(qa._DECISION_STATES)


# --------------------------------------------------------------------------- #
# Part 6 — deterministic second-review sample                                 #
# --------------------------------------------------------------------------- #
def _fake_row(name: str, i: int) -> dict[str, object]:
    """Build a minimal sign-off row for the sampling/candidate unit tests."""
    return {
        "item_id": f"{name}_{i:03d}",
        "class": name,
        "source_image_id": f"{name[0]}{i}",
        "canonical_image_filename": f"{name[0]}{i}.jpg",
        "sha256": "x",
        "box_count": 1,
        "proposed_decision": "QA_ACCEPTED",
    }


def test_second_review_sample_is_deterministic_and_representative() -> None:
    rows_by_class = {
        "tablet": [_fake_row("tablet", i) for i in range(1, 11)],
        "monitor": [_fake_row("monitor", i) for i in range(1, 3)],
    }
    first = qa.select_second_review(
        rows_by_class, seed=_SEED, fraction=0.2, context={}
    )
    second = qa.select_second_review(
        rows_by_class, seed=_SEED, fraction=0.2, context={}
    )
    assert first == second  # reproducible
    # Representative: every class contributes at least one item.
    assert set(first["sampled_by_class"]) == {"tablet", "monitor"}
    assert first["sampled_by_class"]["monitor"] == 1  # max(1, round(0.2*2))
    assert all(entry["status"] == "PENDING_REVIEW" for entry in first["sample"])


# --------------------------------------------------------------------------- #
# Part 7 — candidate inventory: only QA_ACCEPTED, empty at generation          #
# --------------------------------------------------------------------------- #
def test_candidate_inventory_excludes_pending_and_proposals() -> None:
    rows = [
        {"item_id": "a", "class": "tablet", "source_image_id": "a",
         "canonical_image_filename": "a.jpg", "sha256": "1",
         "status": "PENDING_REVIEW", "proposed_decision": "QA_ACCEPTED"},
        {"item_id": "b", "class": "tablet", "source_image_id": "b",
         "canonical_image_filename": "b.jpg", "sha256": "2",
         "status": "PENDING_REVIEW", "proposed_decision": "QA_REVIEW_REQUIRED"},
    ]
    document = qa.build_candidate_inventory(rows, context={})
    assert document["promoted_count"] == 0
    assert document["candidates"] == []
    assert document["is_released"] is False
    assert document["dataset_v1_released"] is False


def test_candidate_inventory_admits_only_human_accepted() -> None:
    rows = [
        {"item_id": "a", "class": "tablet", "source_image_id": "a",
         "canonical_image_filename": "a.jpg", "sha256": "1",
         "status": "QA_ACCEPTED", "proposed_decision": "QA_REVIEW_REQUIRED"},
        {"item_id": "b", "class": "tablet", "source_image_id": "b",
         "canonical_image_filename": "b.jpg", "sha256": "2",
         "status": "PENDING_REVIEW", "proposed_decision": "QA_ACCEPTED"},
    ]
    document = qa.build_candidate_inventory(rows, context={})
    assert document["promoted_count"] == 1
    assert [c["item_id"] for c in document["candidates"]] == ["a"]


# --------------------------------------------------------------------------- #
# Part 11 — end-to-end over real (synthetic) data                             #
# --------------------------------------------------------------------------- #
def test_main_writes_full_package(staging: Path, tmp_path: Path) -> None:
    review = tmp_path / "review"
    assert _run(staging, review) == qa._EXIT_OK

    manifest = json.loads(
        (review / "package_manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["class_count"] == 3
    assert manifest["total_reviewable_items"] == 9
    assert manifest["pending_review_count"] == 9
    assert manifest["promoted_count"] == 0
    assert manifest["all_unchanged"] is True
    assert manifest["dataset_v1_released"] is False
    assert "Dataset v1.0 is NOT RELEASED." in manifest["attestations"]

    # Every part is present on disk.
    for rel in (
        "inventory.json", "inventory.md",
        "preqa_report.json", "preqa_report.md",
        "signoff_template.json",
        "second_review_sample.json", "second_review_sample.md",
        "candidate_inventory.json", "candidate_inventory.md",
        "integrity_verification.json",
    ):
        assert (review / rel).is_file(), rel
    # Per-class visual QA material.
    for name in ("smartphone", "tablet", "monitor"):
        assert (review / name / "qa_data.json").is_file()
        assert list((review / name / "previews").glob("*.jpg"))
        assert list((review / name).glob("contact_sheet_p*.jpg"))


def test_main_signoff_all_pending_and_no_accept_string(
    staging: Path, tmp_path: Path
) -> None:
    review = tmp_path / "review"
    assert _run(staging, review) == qa._EXIT_OK
    text = (review / "signoff_template.json").read_text(encoding="utf-8")
    document = json.loads(text)
    assert document["pending_review_count"] == document["total_items"] == 9
    assert all(r["status"] == "PENDING_REVIEW" for r in document["signoff"])
    assert all(r["human_decision"] == "" for r in document["signoff"])
    # The tool never records a human acceptance/rejection.
    assert "QA_REJECTED" not in {r["status"] for r in document["signoff"]}


def test_main_candidate_inventory_is_empty_and_unreleased(
    staging: Path, tmp_path: Path
) -> None:
    review = tmp_path / "review"
    assert _run(staging, review) == qa._EXIT_OK
    document = json.loads(
        (review / "candidate_inventory.json").read_text(encoding="utf-8")
    )
    assert document["promoted_count"] == 0
    md = (review / "candidate_inventory.md").read_text(encoding="utf-8")
    assert "no images have been promoted" in md.lower()
    assert "Dataset v1.0 is NOT released." in md


def test_main_is_read_only_wrt_source_and_staging(
    staging: Path, tmp_path: Path
) -> None:
    src_root = tmp_path / "oid_source"
    before_staging = _snapshot(staging)
    before_source = _snapshot(src_root)

    assert _run(staging, tmp_path / "review") == qa._EXIT_OK

    assert _snapshot(staging) == before_staging
    assert _snapshot(src_root) == before_source
    integrity = json.loads(
        (tmp_path / "review" / "integrity_verification.json").read_text(
            encoding="utf-8"
        )
    )
    assert integrity["source_unchanged"] is True
    assert integrity["staging_unchanged"] is True
    assert integrity["all_unchanged"] is True


def test_main_is_deterministic(staging: Path, tmp_path: Path) -> None:
    review_a = tmp_path / "a"
    review_b = tmp_path / "b"
    assert _run(staging, review_a) == qa._EXIT_OK
    assert _run(staging, review_b) == qa._EXIT_OK
    for rel in (
        "signoff_template.json",
        "second_review_sample.json",
        "candidate_inventory.json",
        "inventory.json",
    ):
        assert (review_a / rel).read_text(encoding="utf-8") == (
            review_b / rel
        ).read_text(encoding="utf-8"), rel


def test_main_handles_malformed_and_missing_labels(tmp_path: Path) -> None:
    root = tmp_path / "staging"
    src = tmp_path / "src"
    _make_class(
        root, src, name="tablet", class_id=2, source_class="Tablet computer", n=3,
        bad_label_stem="tablet_001", missing_label_stem="tablet_002",
    )
    review = tmp_path / "review"
    # Must not crash: malformed line skipped, missing label tolerated.
    assert _run(root, review) == qa._EXIT_OK
    document = json.loads(
        (review / "signoff_template.json").read_text(encoding="utf-8")
    )
    assert document["total_items"] == 3


def test_main_handles_missing_conversion_report(tmp_path: Path) -> None:
    root = tmp_path / "staging"
    src = tmp_path / "src"
    _make_class(
        root, src, name="tablet", class_id=2, source_class="Tablet computer", n=1,
        with_conversion=False,
    )
    review = tmp_path / "review"
    assert _run(root, review) == qa._EXIT_OK
    document = json.loads((review / "inventory.json").read_text(encoding="utf-8"))
    assert document["classes"][0]["conversion_report"] is None


# --------------------------------------------------------------------------- #
# Integrity failure + CLI usage errors                                        #
# --------------------------------------------------------------------------- #
def test_main_fails_on_sha256_mismatch(tmp_path: Path) -> None:
    root = tmp_path / "staging"
    src = tmp_path / "src"
    staging_dir = _make_class(
        root, src, name="tablet", class_id=2, source_class="Tablet computer", n=1
    )
    manifest_path = staging_dir / "provenance" / "provenance_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["records"][0]["sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    assert _run(root, tmp_path / "review") == qa._EXIT_ERRORS
    # Fails fast: no package manifest is emitted.
    assert not (tmp_path / "review" / "package_manifest.json").exists()


def test_main_usage_error_when_staging_missing(tmp_path: Path) -> None:
    code = qa.main(
        ["--staging-root", str(tmp_path / "nope"), "--review-root", str(tmp_path / "r")]
    )
    assert code == qa._EXIT_USAGE


def test_main_usage_error_on_bad_timestamp(staging: Path, tmp_path: Path) -> None:
    code = qa.main(
        [
            "--staging-root", str(staging),
            "--review-root", str(tmp_path / "r"),
            "--timestamp", "not-a-timestamp",
        ]
    )
    assert code == qa._EXIT_USAGE


def test_main_usage_error_on_bad_sample_fraction(staging: Path, tmp_path: Path) -> None:
    code = qa.main(
        [
            "--staging-root", str(staging),
            "--review-root", str(tmp_path / "r"),
            "--sample-fraction", "0",
        ]
    )
    assert code == qa._EXIT_USAGE


def test_main_errors_when_no_classes(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    code = qa.main(
        ["--staging-root", str(empty), "--review-root", str(tmp_path / "r")]
    )
    assert code == qa._EXIT_ERRORS
