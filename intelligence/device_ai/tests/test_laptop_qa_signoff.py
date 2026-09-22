"""Tests for the Laptop pilot human QA sign-off package builder (P4.2.5).

These exercise the genuinely new logic in
``scripts/build_laptop_qa_signoff.py`` — deriving the outstanding review items
from the frozen remediation manifest + strict image validation, rendering the
before/after evidence, and *proving* the source AND canonical staging are left
byte-identical — without touching any frozen module or the real staging
directories.

A synthetic source staging and a synthetic canonical staging are built in
``tmp_path`` mirroring the real artifact shapes (the same source stems and the
same reviewer statuses the P4.2.4 ingestion recorded), so the real policy
surface (hold QA01; split QA03; add QA04; tighten QA15; exclude QA14; two
Gate-A blur images) is the one under test.

The script lives under ``scripts/`` (not on the pytest pythonpath), so the
scripts directory is prepended to ``sys.path`` before import.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest
from PIL import Image

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCRIPTS_DIR = _REPO_ROOT / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import build_laptop_qa_signoff as sign  # noqa: E402

from device_ai.dataset.hashing import sha256_hash  # noqa: E402

_TIMESTAMP = "2026-08-09T00:00:00+00:00"
_VERSION = "openimages-laptop-human-qa-signoff-test"

# Synthetic source stems mirroring the real pilot's flagged items plus a clean
# control. stem -> (width, height, source_label_text, object_count, qa_id).
_QA04_SOURCE = (
    "0 0.409687 0.653377 0.319375 0.329268\n"
    "0 0.895312 0.340995 0.070625 0.049719\n"
    "0 0.875938 0.296905 0.019375 0.053471\n"
    "0 0.915000 0.264071 0.040000 0.107880\n"
    "0 0.990625 0.358349 0.017500 0.091932\n"
)
_SOURCE_SPEC: dict[str, tuple[int, int, str, int, int]] = {
    "00767fb6565581c6": (768, 1024, "0 0.626667 0.211250 0.743333 0.422500\n", 1, 1),
    "0171ad35f1651698": (1024, 768, "0 0.286133 0.657552 0.572266 0.682292\n", 1, 3),
    "14587a599414300c": (1024, 683, _QA04_SOURCE, 5, 4),
    "79182035199f2b58": (1024, 1024, "0 0.499219 0.499219 0.998438 0.998438\n", 1, 14),
    "936a6d462e9d4873": (1024, 768, "0 0.212110 0.500521 0.424219 0.996875\n", 1, 15),
    "bc3873e0c9ada07c": (1024, 768, "0 0.400000 0.700000 0.150000 0.200000\n", 1, 17),
    "ca77666f682b922f": (1024, 680, "0 0.500000 0.500000 0.300000 0.300000\n", 1, 18),
    "f663d03a10e841bf": (1024, 640, "0 0.500000 0.500000 0.400000 0.300000\n", 1, 21),
}

# Corrected canonical labels for the re-annotated items (box counts matter).
_QA03_CORRECTED = (
    "0 0.131836 0.695312 0.263672 0.609375\n"
    "0 0.239258 0.533854 0.185547 0.338542\n"
    "0 0.361328 0.491536 0.136719 0.240885\n"
    "0 0.444336 0.462240 0.107422 0.195312\n"
    "0 0.512695 0.452474 0.126953 0.162760\n"
)
_QA04_CORRECTED = _QA04_SOURCE + "0 0.583496 0.483163 0.200195 0.219619\n"
_QA15_CORRECTED = "0 0.205078 0.570312 0.410156 0.859375\n"

def _noise_image(path: Path, width: int, height: int) -> None:
    """Write a distinct, non-uniform JPEG (distinct SHA per stem)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.frombytes("RGB", (width, height), os.urandom(width * height * 3))
    img.save(path, format="JPEG", quality=90)


# Canonical stem/label mapping for the retained (non-excluded) source stems, in
# sorted-source-stem order (matching the real deterministic sequence).
_RETAINED_ORDER = [
    "00767fb6565581c6",
    "0171ad35f1651698",
    "14587a599414300c",
    "936a6d462e9d4873",
    "bc3873e0c9ada07c",
    "ca77666f682b922f",
    "f663d03a10e841bf",
]
# stem -> (action, remediation_status, reviewer_status, corrected_label_or_None)
_REMEDIATION: dict[str, tuple[str, str, str, str | None]] = {
    "00767fb6565581c6": (
        "KEEP_REVIEW_PENDING",
        "REVIEW_PENDING",
        "PENDING_REVIEW",
        None,  # held: canonical label == source label
    ),
    "0171ad35f1651698": (
        "REANNOTATE_SPLIT",
        "REMEDIATION_REVIEW_PENDING",
        "PENDING_REVIEW",
        _QA03_CORRECTED,
    ),
    "14587a599414300c": (
        "REANNOTATE_ADD_INSTANCE",
        "REMEDIATION_REVIEW_PENDING",
        "PENDING_REVIEW",
        _QA04_CORRECTED,
    ),
    "936a6d462e9d4873": (
        "REANNOTATE_TIGHTEN",
        "REMEDIATION_REVIEW_PENDING",
        "PENDING_REVIEW",
        _QA15_CORRECTED,
    ),
}


@pytest.fixture
def staging(tmp_path: Path) -> tuple[Path, Path]:
    """Build a synthetic source + canonical staging mirroring the real pilot.

    Returns:
        ``(source_staging, canonical_staging)`` roots under ``tmp_path``.
    """
    source = tmp_path / "openimages_laptop_v1"
    canonical = tmp_path / "openimages_laptop_canonical_v1"
    (source / "images").mkdir(parents=True)
    (source / "labels").mkdir(parents=True)
    (source / "manual_review").mkdir(parents=True)
    (canonical / "images").mkdir(parents=True)
    (canonical / "labels").mkdir(parents=True)
    (canonical / "reports").mkdir(parents=True)
    (canonical / "validation").mkdir(parents=True)

    # --- Source staging: images, labels, qa_data.json (the tile-id map). ---
    sha_by_stem: dict[str, str] = {}
    tiles = []
    for stem, (w, h, label, _count, qa_id) in _SOURCE_SPEC.items():
        img = source / "images" / f"{stem}.jpg"
        _noise_image(img, w, h)
        (source / "labels" / f"{stem}.txt").write_text(label, encoding="utf-8")
        sha_by_stem[stem] = sha256_hash(img.read_bytes())
        tiles.append({"stem": stem, "qa_id": qa_id})
    (source / "manual_review" / "qa_data.json").write_text(
        json.dumps({"tiles": tiles}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    # --- Canonical staging: retained images (byte copies) + canonical labels. ---
    records = []
    seq = 0
    canon_by_stem: dict[str, str] = {}
    for stem in _RETAINED_ORDER:
        w, h, source_label, count, qa_id = _SOURCE_SPEC[stem]
        seq += 1
        canonical_stem = f"laptop_openimages_{seq:06d}"
        canon_by_stem[stem] = f"{canonical_stem}.jpg"
        # Byte-identical copy of the source image.
        (canonical / "images" / f"{canonical_stem}.jpg").write_bytes(
            (source / "images" / f"{stem}.jpg").read_bytes()
        )
        remediation = _REMEDIATION.get(stem)
        if remediation is None:
            action, status, reviewer, corrected = (
                "ACCEPT",
                "ACCEPTED",
                "QA_ACCEPTED",
                None,
            )
            manifest_qa_id = 0  # clean ACCEPTs lose their tile id in the manifest
        else:
            action, status, reviewer, corrected = remediation
            manifest_qa_id = qa_id
        label_text = corrected if corrected is not None else source_label
        (canonical / "labels" / f"{canonical_stem}.txt").write_text(
            label_text, encoding="utf-8"
        )
        records.append(
            {
                "canonical_image_filename": f"{canonical_stem}.jpg",
                "canonical_label_filename": f"{canonical_stem}.txt",
                "canonical_stem": canonical_stem,
                "sequence": f"{seq:06d}",
                "source_stem": stem,
                "source_image_filename": f"{stem}.jpg",
                "source_annotation_filename": f"{stem}.txt",
                "source_sha256": sha_by_stem[stem],
                "source_dataset": "Open Images V7",
                "source_class": "Laptop",
                "ecotrace_class": "laptop",
                "ecotrace_class_id": 0,
                "width": w,
                "height": h,
                "qa_id": manifest_qa_id,
                "qa_decision": "REVIEW" if remediation else "ACCEPT",
                "remediation_action": action,
                "remediation_status": status,
                "reviewer_status": reviewer,
                "original_object_count": count,
                "corrected_object_count": len(label_text.strip().splitlines()),
                "difficult": stem == "0171ad35f1651698",
                "reason": f"synthetic reason for {stem}",
            }
        )

    excl_stem = "79182035199f2b58"
    ew, eh, _elabel, ecount, eqa = _SOURCE_SPEC[excl_stem]
    manifest = {
        "is_dataset_v1": False,
        "is_released": False,
        "records": records,
        "exclusions": [
            {
                "source_stem": excl_stem,
                "source_image_filename": f"{excl_stem}.jpg",
                "source_annotation_filename": f"{excl_stem}.txt",
                "source_sha256": sha_by_stem[excl_stem],
                "source_dataset": "Open Images V7",
                "source_class": "Laptop",
                "ecotrace_class": "laptop",
                "ecotrace_class_id": 0,
                "width": ew,
                "height": eh,
                "object_count": ecount,
                "qa_id": eqa,
                "qa_decision": "REJECT",
                "remediation_action": "EXCLUDE",
                "remediation_status": "EXCLUDED",
                "reviewer_status": "EXCLUDED",
                "reason": f"synthetic exclusion reason for {excl_stem}",
            }
        ],
    }
    (canonical / "reports" / "remediation_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    # --- Strict image validation: the two Gate-A blur images (QA17, QA18). ---
    strict = {
        "batch_dir": str(canonical / "images"),
        "is_valid": False,
        "issues": [
            {
                "code": "IMAGE_BLURRY",
                "file": canon_by_stem["bc3873e0c9ada07c"],
                "message": "blur score 59.96 below threshold",
                "severity": "blocking",
            },
            {
                "code": "IMAGE_BLURRY",
                "file": canon_by_stem["ca77666f682b922f"],
                "message": "blur score 77.04 below threshold",
                "severity": "blocking",
            },
        ],
        "summary": {"blocking": 2},
        "total_images": len(records),
    }
    (canonical / "validation" / "image_validation_strict.json").write_text(
        json.dumps(strict, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return source, canonical


def _run(source: Path, canonical: Path, review: Path) -> int:
    """Invoke the sign-off CLI with injected, deterministic arguments."""
    exit_code: int = sign.main(
        [
            "--source-staging",
            str(source),
            "--canonical-staging",
            str(canonical),
            "--review-root",
            str(review),
            "--signoff-timestamp",
            _TIMESTAMP,
            "--signoff-version",
            _VERSION,
        ]
    )
    return exit_code


def _snapshot(root: Path) -> dict[str, str]:
    """Return a ``relpath -> sha256`` snapshot of every file under ``root``."""
    out: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            out[path.relative_to(root).as_posix()] = sha256_hash(path.read_bytes())
    return out


def _read_json(path: Path) -> dict:
    data: dict = json.loads(path.read_text(encoding="utf-8"))
    return data


# --------------------------------------------------------------------------- #
# The package generation is strictly read-only on source AND canonical         #
# --------------------------------------------------------------------------- #
def test_source_and_canonical_unchanged(staging: tuple[Path, Path], tmp_path: Path) -> None:
    source, canonical = staging
    src_before = _snapshot(source)
    canon_before = _snapshot(canonical)

    assert _run(source, canonical, tmp_path / "review") == sign._EXIT_OK

    assert _snapshot(source) == src_before, "source staging must be byte-identical"
    assert _snapshot(canonical) == canon_before, "canonical staging must be byte-identical"


def test_integrity_document_proves_no_change(
    staging: tuple[Path, Path], tmp_path: Path
) -> None:
    source, canonical = staging
    review = tmp_path / "review"
    assert _run(source, canonical, review) == sign._EXIT_OK

    integrity = _read_json(review / "integrity_verification.json")
    assert integrity["all_unchanged"] is True
    assert integrity["source_staging_unchanged"] is True
    assert integrity["canonical_staging_unchanged"] is True
    # The proof actually inspected files (not a vacuous pass on an empty tree).
    assert integrity["source_files_checked"] > 0
    assert integrity["canonical_files_checked"] > 0
    for diff in (integrity["source_diff"], integrity["canonical_diff"]):
        assert diff == {"added": [], "removed": [], "modified": []}


# --------------------------------------------------------------------------- #
# All expected artifacts are produced under the review root                     #
# --------------------------------------------------------------------------- #
def test_artifacts_written(staging: tuple[Path, Path], tmp_path: Path) -> None:
    source, canonical = staging
    review = tmp_path / "review"
    assert _run(source, canonical, review) == sign._EXIT_OK

    for name in (
        "evidence.json",
        "signoff_template.json",
        "integrity_verification.json",
    ):
        assert (review / name).is_file(), name
    previews = review / "previews"
    assert previews.is_dir()
    assert any(previews.iterdir()), "at least one preview must be rendered"


# --------------------------------------------------------------------------- #
# Exactly the outstanding items are surfaced, with the visual-QA numbering      #
# --------------------------------------------------------------------------- #
def test_review_items_surfaced(staging: tuple[Path, Path], tmp_path: Path) -> None:
    source, canonical = staging
    review = tmp_path / "review"
    assert _run(source, canonical, review) == sign._EXIT_OK

    evidence = _read_json(review / "evidence.json")
    by_id = {e["item_id"]: e for e in evidence["evidence"]}
    assert set(by_id) == {"QA01", "QA03", "QA04", "QA14", "QA15", "QA17", "QA18"}
    assert evidence["items"] == 7

    # Kinds are classified from the frozen manifest actions, not re-decided here.
    assert by_id["QA01"]["kind"] == "review_hold"
    assert by_id["QA03"]["kind"] == "reannotation"
    assert by_id["QA04"]["kind"] == "reannotation"
    assert by_id["QA15"]["kind"] == "reannotation"
    assert by_id["QA14"]["kind"] == "exclusion"
    assert by_id["QA17"]["kind"] == "blur_gate_a"
    assert by_id["QA18"]["kind"] == "blur_gate_a"


# --------------------------------------------------------------------------- #
# The sign-off template certifies nothing: every row is PENDING_REVIEW          #
# --------------------------------------------------------------------------- #
def test_signoff_template_all_pending(
    staging: tuple[Path, Path], tmp_path: Path
) -> None:
    source, canonical = staging
    review = tmp_path / "review"
    assert _run(source, canonical, review) == sign._EXIT_OK

    template = _read_json(review / "signoff_template.json")
    assert template["allowed_statuses"] == ["PENDING_REVIEW", "ACCEPTED", "REJECTED"]
    assert template["items"] == 7
    for row in template["signoff"]:
        assert row["status"] == "PENDING_REVIEW"
        # No human field is ever auto-filled by the tool.
        assert row["human_decision"] == ""
        assert row["reviewer"] == ""
        assert row["date"] == ""
        assert row["notes"] == ""
        # A proposed (non-binding) decision is provided for the reviewer.
        assert row["proposed_decision"]


# --------------------------------------------------------------------------- #
# The COMMITTED sign-off template ships genuinely pending human review          #
# --------------------------------------------------------------------------- #
_COMMITTED_SIGNOFF_TEMPLATE = (
    _REPO_ROOT
    / "dataset_acquisition"
    / "review"
    / "openimages_laptop_human_qa_signoff_v1"
    / "signoff_template.json"
)
_EXPECTED_SIGNOFF_ITEM_IDS = {"QA01", "QA03", "QA04", "QA14", "QA15", "QA17", "QA18"}


def test_committed_signoff_template_is_unfilled() -> None:
    """The committed artifact ships with every human field blank.

    The generator emits ``PENDING_REVIEW`` rows, but the committed file is a
    separate artifact a human can hand-edit; this guards against a decision
    being baked into it before an actual reviewer signs off.
    """
    template = _read_json(_COMMITTED_SIGNOFF_TEMPLATE)
    rows = template["signoff"]
    assert template["items"] == 7
    assert len(rows) == 7
    assert {row["item_id"] for row in rows} == _EXPECTED_SIGNOFF_ITEM_IDS
    for row in rows:
        assert row["status"] == "PENDING_REVIEW", row["item_id"]
        assert row["human_decision"] == "", row["item_id"]
        assert row["reviewer"] == "", row["item_id"]
        assert row["date"] == "", row["item_id"]


# --------------------------------------------------------------------------- #
# Evidence carries exact filenames, SHA-256, counts and coordinates            #
# --------------------------------------------------------------------------- #
def test_evidence_carries_facts_for_corrections(
    staging: tuple[Path, Path], tmp_path: Path
) -> None:
    source, canonical = staging
    review = tmp_path / "review"
    assert _run(source, canonical, review) == sign._EXIT_OK

    by_id = {e["item_id"]: e for e in _read_json(review / "evidence.json")["evidence"]}

    # stem, expected (source count, corrected count, canonical filename).
    expectations = {
        "QA03": ("0171ad35f1651698", 1, 5, "laptop_openimages_000002.jpg"),
        "QA04": ("14587a599414300c", 5, 6, "laptop_openimages_000003.jpg"),
        "QA15": ("936a6d462e9d4873", 1, 1, "laptop_openimages_000004.jpg"),
    }
    for item_id, (stem, orig, corr, canonical_name) in expectations.items():
        entry = by_id[item_id]
        assert entry["source_image_filename"] == f"{stem}.jpg"
        assert entry["canonical_image_filename"] == canonical_name
        # SHA-256 is the real hash of the source image bytes.
        expected_sha = sha256_hash((source / "images" / f"{stem}.jpg").read_bytes())
        assert entry["source_sha256"] == expected_sha
        assert len(entry["source_sha256"]) == 64
        # Object counts match the frozen manifest's original vs corrected counts.
        assert entry["original_object_count"] == orig
        assert entry["corrected_object_count"] == corr
        # Coordinates are present in BOTH normalised and pixel-space form.
        assert len(entry["original_annotation"]) == orig
        assert len(entry["corrected_annotation"]) == corr
        for box in entry["original_annotation"] + entry["corrected_annotation"]:
            assert len(box["normalized_cxcywh"]) == 4
            assert len(box["pixel_xyxy"]) == 4


# --------------------------------------------------------------------------- #
# QA01 held REVIEW_PENDING: original == corrected (annotation unchanged)        #
# --------------------------------------------------------------------------- #
def test_qa01_hold_annotation_unchanged(
    staging: tuple[Path, Path], tmp_path: Path
) -> None:
    source, canonical = staging
    review = tmp_path / "review"
    assert _run(source, canonical, review) == sign._EXIT_OK

    by_id = {e["item_id"]: e for e in _read_json(review / "evidence.json")["evidence"]}
    qa01 = by_id["QA01"]
    assert qa01["original_object_count"] == qa01["corrected_object_count"] == 1
    assert qa01["original_annotation"] == qa01["corrected_annotation"]


# --------------------------------------------------------------------------- #
# The proposed exclusion fabricates no "corrected" annotation                   #
# --------------------------------------------------------------------------- #
def test_exclusion_has_no_corrected_annotation(
    staging: tuple[Path, Path], tmp_path: Path
) -> None:
    source, canonical = staging
    review = tmp_path / "review"
    assert _run(source, canonical, review) == sign._EXIT_OK

    by_id = {e["item_id"]: e for e in _read_json(review / "evidence.json")["evidence"]}
    qa14 = by_id["QA14"]
    assert qa14["kind"] == "exclusion"
    assert qa14["canonical_image_filename"] is None
    assert qa14["corrected_object_count"] is None
    assert qa14["corrected_annotation"] is None
    # Only an "original" preview is rendered (no invented "corrected"/"after").
    assert set(qa14["previews"]) == {"original"}


# --------------------------------------------------------------------------- #
# Re-annotation items get a before/after side-by-side preview                   #
# --------------------------------------------------------------------------- #
def test_reannotation_before_after_previews(
    staging: tuple[Path, Path], tmp_path: Path
) -> None:
    source, canonical = staging
    review = tmp_path / "review"
    assert _run(source, canonical, review) == sign._EXIT_OK

    by_id = {e["item_id"]: e for e in _read_json(review / "evidence.json")["evidence"]}
    for item_id in ("QA03", "QA04", "QA15"):
        previews = by_id[item_id]["previews"]
        assert set(previews) >= {"original", "corrected", "before_after"}
        for rel in previews.values():
            assert (review / rel).is_file(), rel


# --------------------------------------------------------------------------- #
# Nothing is certified / released / promoted to dataset v1                      #
# --------------------------------------------------------------------------- #
def test_outputs_certify_nothing(staging: tuple[Path, Path], tmp_path: Path) -> None:
    source, canonical = staging
    review = tmp_path / "review"
    assert _run(source, canonical, review) == sign._EXIT_OK

    for name in (
        "evidence.json",
        "signoff_template.json",
        "integrity_verification.json",
    ):
        doc = _read_json(review / name)
        assert doc["certifies_pilot"] is False
        assert doc["is_released"] is False
        assert doc["is_dataset_v1"] is False
        assert doc["pilot_status"] == "PILOT_REVIEW_REQUIRED"


# --------------------------------------------------------------------------- #
# Determinism: same inputs -> byte-identical machine-readable artifacts         #
# --------------------------------------------------------------------------- #
def test_json_artifacts_deterministic(
    staging: tuple[Path, Path], tmp_path: Path
) -> None:
    source, canonical = staging
    review_a = tmp_path / "a"
    review_b = tmp_path / "b"
    assert _run(source, canonical, review_a) == sign._EXIT_OK
    assert _run(source, canonical, review_b) == sign._EXIT_OK

    # Every field is byte-stable across runs except ``review_root``, which
    # honestly echoes the (differing) output location; strip it before diffing.
    for name in ("evidence.json", "signoff_template.json"):
        doc_a = _read_json(review_a / name)
        doc_b = _read_json(review_b / name)
        assert doc_a.pop("review_root") == "a"
        assert doc_b.pop("review_root") == "b"
        assert doc_a == doc_b, name


# --------------------------------------------------------------------------- #
# Missing staging is a usage error (exit 2), never a silent pass                #
# --------------------------------------------------------------------------- #
def test_missing_canonical_staging_is_usage_error(
    staging: tuple[Path, Path], tmp_path: Path
) -> None:
    source, _canonical = staging
    exit_code = sign.main(
        [
            "--source-staging",
            str(source),
            "--canonical-staging",
            str(tmp_path / "does_not_exist"),
            "--review-root",
            str(tmp_path / "review"),
            "--signoff-timestamp",
            _TIMESTAMP,
            "--signoff-version",
            _VERSION,
        ]
    )
    assert exit_code == sign._EXIT_USAGE

