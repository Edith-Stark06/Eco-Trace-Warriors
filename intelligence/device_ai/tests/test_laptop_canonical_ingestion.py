"""Tests for the Laptop pilot canonical remediation + ingestion (Sprint P4.2.4).

These exercise the genuinely new logic in
``scripts/ingest_laptop_canonical.py`` — remediation-driven exclusion,
re-annotation, canonical filename ingestion, provenance linkage, and the
integrity guards — without touching any frozen module or the real staging
directories. A synthetic source staging is built in ``tmp_path`` using the same
real source stems the remediation spec is keyed on, so the real policy decisions
(exclude QA14; split QA03; add-instance QA04; tighten QA15; hold QA01) are the
ones under test.

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

import ingest_laptop_canonical as ing  # noqa: E402

from device_ai.dataset.hashing import sha256_hash  # noqa: E402
from device_ai.dataset.taxonomy import load_taxonomy  # noqa: E402

_TIMESTAMP = "2026-08-09T00:00:00+00:00"
_VERSION = "openimages-laptop-canonical-test"

# Real source stems the remediation spec keys on, plus two clean controls, with
# the true image dimensions (so the proposed correction boxes validate in-range)
# and a source label whose box count matches the provenance ``object_count``.
_QA04_LINES = (
    "0 0.409687 0.653377 0.319375 0.329268\n"
    "0 0.895312 0.340995 0.070625 0.049719\n"
    "0 0.875938 0.296905 0.019375 0.053471\n"
    "0 0.915000 0.264071 0.040000 0.107880\n"
    "0 0.990625 0.358349 0.017500 0.091932\n"
)
# stem -> (width, height, label_text, object_count)
_SOURCE_SPEC: dict[str, tuple[int, int, str, int]] = {
    # QA01 -- held REVIEW_PENDING (source annotation unchanged).
    "00767fb6565581c6": (768, 1024, "0 0.626667 0.211250 0.743333 0.422500\n", 1),
    # clean control (ACCEPT).
    "00b1a3014b6d62a1": (
        1024,
        768,
        (
            "0 0.401855 0.706380 0.278320 0.401042\n"
            "0 0.700195 0.500000 0.200195 0.300000\n"
        ),
        2,
    ),
    # QA03 -- group box split.
    "0171ad35f1651698": (1024, 768, "0 0.286133 0.657552 0.572266 0.682292\n", 1),
    # QA04 -- missing instance added (five source boxes preserved).
    "14587a599414300c": (1024, 683, _QA04_LINES, 5),
    # QA14 -- excluded (REJECT).
    "79182035199f2b58": (1024, 1024, "0 0.499219 0.499219 0.998438 0.998438\n", 1),
    # QA15 -- loose box tightened.
    "936a6d462e9d4873": (1024, 768, "0 0.212110 0.500521 0.424219 0.996875\n", 1),
    # clean control (ACCEPT).
    "f663d03a10e841bf": (1024, 640, "0 0.500000 0.500000 0.400000 0.300000\n", 1),
}


def _noise_image(path: Path, width: int, height: int) -> None:
    """Write a distinct, non-uniform JPEG (distinct SHA + perceptual hash)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.frombytes("RGB", (width, height), os.urandom(width * height * 3))
    img.save(path, format="JPEG", quality=90)


@pytest.fixture
def source_staging(tmp_path: Path) -> Path:
    """Build a synthetic ``openimages_laptop_v1``-style source staging."""
    root = tmp_path / "openimages_laptop_v1"
    images_dir = root / "images"
    labels_dir = root / "labels"
    prov_dir = root / "provenance"
    for directory in (images_dir, labels_dir, prov_dir):
        directory.mkdir(parents=True, exist_ok=True)

    records = []
    for stem, (width, height, label_text, object_count) in _SOURCE_SPEC.items():
        image_path = images_dir / f"{stem}.jpg"
        _noise_image(image_path, width, height)
        (labels_dir / f"{stem}.txt").write_text(label_text, encoding="utf-8")
        sha = sha256_hash(image_path.read_bytes())
        records.append(
            {
                "stem": stem,
                "source": "Open Images V7",
                "source_class": "Laptop",
                "ecotrace_class": "laptop",
                "ecotrace_class_id": 0,
                "source_image_filename": f"{stem}.jpg",
                "source_annotation_filename": f"{stem}.txt",
                "sha256": sha,
                "width": width,
                "height": height,
                "object_count": object_count,
            }
        )
    manifest = {
        "ecotrace_class": "laptop",
        "ecotrace_class_id": 0,
        "records": records,
        "source": "Open Images V7",
        "taxonomy_version": "1.0.0",
        "total_images": len(records),
    }
    (prov_dir / "provenance_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return root


def _run(source: Path, canonical: Path) -> int:
    """Invoke the ingestion CLI with injected, deterministic arguments."""
    exit_code: int = ing.main(
        [
            "--source-staging",
            str(source),
            "--canonical-staging",
            str(canonical),
            "--remediation-timestamp",
            _TIMESTAMP,
            "--remediation-version",
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


def _manifest(canonical: Path) -> dict:
    manifest: dict = json.loads(
        (canonical / "reports" / "remediation_manifest.json").read_text("utf-8")
    )
    return manifest


def _filename_map(canonical: Path) -> dict:
    filename_map: dict = json.loads(
        (canonical / "reports" / "canonical_filename_map.json").read_text("utf-8")
    )
    return filename_map


# --------------------------------------------------------------------------- #
# Source is never modified                                                    #
# --------------------------------------------------------------------------- #
def test_source_staging_is_unchanged(source_staging: Path, tmp_path: Path) -> None:
    before = _snapshot(source_staging)
    assert _run(source_staging, tmp_path / "canonical") == 0
    after = _snapshot(source_staging)
    assert before == after, "ingestion must not modify the source staging"


# --------------------------------------------------------------------------- #
# QA14 is excluded (and its source copy still exists)                          #
# --------------------------------------------------------------------------- #
def test_qa14_excluded_from_candidate(source_staging: Path, tmp_path: Path) -> None:
    canonical = tmp_path / "canonical"
    assert _run(source_staging, canonical) == 0
    manifest = _manifest(canonical)

    excluded_stems = [e["source_stem"] for e in manifest["exclusions"]]
    assert excluded_stems == ["79182035199f2b58"]
    exclusion = manifest["exclusions"][0]
    assert exclusion["qa_decision"] == "REJECT"
    assert exclusion["remediation_status"] == "EXCLUDED"
    # Recorded provenance for the exclusion (source filename, sha, counts).
    assert exclusion["source_image_filename"] == "79182035199f2b58.jpg"
    assert len(exclusion["source_sha256"]) == 64
    assert exclusion["object_count"] == 1

    # No canonical artifact references the excluded stem.
    retained = {r["source_stem"] for r in manifest["records"]}
    assert "79182035199f2b58" not in retained
    # The source copy is untouched (still present in source staging).
    assert (source_staging / "images" / "79182035199f2b58.jpg").is_file()


# --------------------------------------------------------------------------- #
# QA03 / QA04 / QA15 corrections are represented                              #
# --------------------------------------------------------------------------- #
def test_reannotations_represented(source_staging: Path, tmp_path: Path) -> None:
    canonical = tmp_path / "canonical"
    assert _run(source_staging, canonical) == 0
    records = {r["source_stem"]: r for r in _manifest(canonical)["records"]}

    qa03 = records["0171ad35f1651698"]
    assert qa03["remediation_action"] == "REANNOTATE_SPLIT"
    assert qa03["original_object_count"] == 1
    assert qa03["corrected_object_count"] == 5
    assert qa03["difficult"] is True
    assert qa03["reviewer_status"] == "PENDING_REVIEW"
    assert qa03["remediation_status"] == "REMEDIATION_REVIEW_PENDING"

    qa04 = records["14587a599414300c"]
    assert qa04["remediation_action"] == "REANNOTATE_ADD_INSTANCE"
    assert qa04["original_object_count"] == 5
    assert qa04["corrected_object_count"] == 6
    assert qa04["reviewer_status"] == "PENDING_REVIEW"

    qa15 = records["936a6d462e9d4873"]
    assert qa15["remediation_action"] == "REANNOTATE_TIGHTEN"
    assert qa15["corrected_object_count"] == 1
    assert qa15["reviewer_status"] == "PENDING_REVIEW"

    # The corrected labels exist on disk with the right box counts.
    labels_dir = canonical / "labels"

    def _box_count(label_filename: str) -> int:
        return len(
            (labels_dir / label_filename).read_text().strip().splitlines()
        )

    assert _box_count(qa03["canonical_label_filename"]) == 5
    assert _box_count(qa04["canonical_label_filename"]) == 6
    assert _box_count(qa15["canonical_label_filename"]) == 1


def test_qa04_preserves_source_boxes(source_staging: Path, tmp_path: Path) -> None:
    """The QA04 add-instance keeps the five source boxes and appends one."""
    canonical = tmp_path / "canonical"
    assert _run(source_staging, canonical) == 0
    records = {r["source_stem"]: r for r in _manifest(canonical)["records"]}
    qa04 = records["14587a599414300c"]
    corrected = (
        (canonical / "labels" / qa04["canonical_label_filename"])
        .read_text()
        .strip()
        .splitlines()
    )
    source_lines = (
        (source_staging / "labels" / "14587a599414300c.txt").read_text().splitlines()
    )
    # First five corrected lines are the source boxes verbatim; a sixth is added.
    assert corrected[:5] == source_lines
    assert len(corrected) == 6


# --------------------------------------------------------------------------- #
# QA01 is held REVIEW_PENDING with an unchanged annotation                    #
# --------------------------------------------------------------------------- #
def test_qa01_review_pending_unchanged(source_staging: Path, tmp_path: Path) -> None:
    canonical = tmp_path / "canonical"
    assert _run(source_staging, canonical) == 0
    records = {r["source_stem"]: r for r in _manifest(canonical)["records"]}
    qa01 = records["00767fb6565581c6"]
    assert qa01["remediation_action"] == "KEEP_REVIEW_PENDING"
    assert qa01["remediation_status"] == "REVIEW_PENDING"
    assert qa01["reviewer_status"] == "PENDING_REVIEW"
    assert qa01["original_object_count"] == qa01["corrected_object_count"] == 1
    # Annotation is byte-identical to the source label.
    canonical_label = (
        canonical / "labels" / qa01["canonical_label_filename"]
    ).read_text()
    source_label = (
        source_staging / "labels" / "00767fb6565581c6.txt"
    ).read_text()
    assert canonical_label == source_label


# --------------------------------------------------------------------------- #
# Canonical filenames are deterministic and convention-valid                  #
# --------------------------------------------------------------------------- #
def test_canonical_filenames_deterministic_and_valid(
    source_staging: Path, tmp_path: Path
) -> None:
    assert _run(source_staging, tmp_path / "a") == 0
    assert _run(source_staging, tmp_path / "b") == 0
    map_a = _filename_map(tmp_path / "a")["mapping"]
    map_b = _filename_map(tmp_path / "b")["mapping"]
    assert map_a == map_b, "mapping must be deterministic across runs"

    stem_to_canon = {m["source_stem"]: m["canonical_stem"] for m in map_a}
    # Sequence assigned in sorted source-stem order over RETAINED images only;
    # the excluded QA14 consumes no sequence number (gap-free).
    assert stem_to_canon["00767fb6565581c6"] == "laptop_openimages_000001"
    assert stem_to_canon["00b1a3014b6d62a1"] == "laptop_openimages_000002"
    assert stem_to_canon["0171ad35f1651698"] == "laptop_openimages_000003"
    assert stem_to_canon["14587a599414300c"] == "laptop_openimages_000004"
    assert stem_to_canon["936a6d462e9d4873"] == "laptop_openimages_000005"
    assert stem_to_canon["f663d03a10e841bf"] == "laptop_openimages_000006"
    assert "79182035199f2b58" not in stem_to_canon

    # Every canonical filename satisfies the code-owned collection convention.
    from _ecotrace_toolkit import parse_collection_filename

    class_names = load_taxonomy().class_names
    for m in map_a:
        parsed = parse_collection_filename(m["canonical_image_filename"], class_names)
        assert parsed.is_valid, (m["canonical_image_filename"], parsed.reason)
        assert parsed.class_name == "laptop"


def test_label_bytes_deterministic_across_runs(
    source_staging: Path, tmp_path: Path
) -> None:
    assert _run(source_staging, tmp_path / "a") == 0
    assert _run(source_staging, tmp_path / "b") == 0
    labels_a = _snapshot(tmp_path / "a" / "labels")
    labels_b = _snapshot(tmp_path / "b" / "labels")
    assert labels_a == labels_b


# --------------------------------------------------------------------------- #
# Provenance links source -> canonical and image bytes are identical          #
# --------------------------------------------------------------------------- #
def test_provenance_links_and_byte_identity(
    source_staging: Path, tmp_path: Path
) -> None:
    canonical = tmp_path / "canonical"
    assert _run(source_staging, canonical) == 0
    provenance = json.loads(
        (canonical / "provenance" / "provenance_manifest.json").read_text("utf-8")
    )
    assert provenance["total_images"] == 6
    for rec in provenance["records"]:
        # Every canonical record carries its source linkage + discovered class id.
        assert rec["ecotrace_class"] == "laptop"
        assert rec["ecotrace_class_id"] == 0
        assert rec["source_dataset"] == "Open Images V7"
        assert len(rec["sha256"]) == 64
        # The canonical image is a verbatim byte copy of the source image.
        canonical_image = canonical / "images" / rec["canonical_image_filename"]
        source_image = source_staging / "images" / rec["source_image_filename"]
        assert canonical_image.read_bytes() == source_image.read_bytes()
        assert sha256_hash(canonical_image.read_bytes()) == rec["sha256"]


# --------------------------------------------------------------------------- #
# No duplicate images; image/label pairing complete                           #
# --------------------------------------------------------------------------- #
def test_no_duplicate_images(source_staging: Path, tmp_path: Path) -> None:
    canonical = tmp_path / "canonical"
    assert _run(source_staging, canonical) == 0
    from device_ai.configs.settings import get_settings
    from device_ai.dataset.duplicates import DuplicateDetector
    from device_ai.dataset.metadata import MetadataGenerator

    settings = get_settings()
    records = MetadataGenerator.from_settings(settings).analyze_directory(
        canonical / "images"
    )
    report = DuplicateDetector.from_settings(settings).detect(records)
    assert report.num_duplicates == 0
    assert report.total_images == 6


def test_image_label_pairing_complete(source_staging: Path, tmp_path: Path) -> None:
    canonical = tmp_path / "canonical"
    assert _run(source_staging, canonical) == 0
    images = sorted(p.stem for p in (canonical / "images").glob("*.jpg"))
    labels = sorted(p.stem for p in (canonical / "labels").glob("*.txt"))
    assert images == labels
    assert len(images) == 6


# --------------------------------------------------------------------------- #
# Validation fails honestly: an out-of-frame proposed box is rejected         #
# --------------------------------------------------------------------------- #
def test_out_of_frame_proposed_box_is_rejected(
    monkeypatch: pytest.MonkeyPatch, source_staging: Path, tmp_path: Path
) -> None:
    """A proposed correction box beyond the frame raises, never clips."""
    taxonomy = load_taxonomy()
    records = ing.load_source_records(
        source_staging / "provenance" / "provenance_manifest.json"
    )
    bad = ing.Remediation(
        action=ing._ACTION_TIGHTEN,
        qa_id=15,
        qa_decision="REVIEW",
        reason="deliberately out of frame",
        keep_original_boxes=False,
        added_boxes_px=((0.0, 0.0, 5000.0, 5000.0),),  # exceeds any real frame
    )
    monkeypatch.setitem(ing._REMEDIATION_SPEC, "936a6d462e9d4873", bad)
    with pytest.raises(ing.IngestError):
        ing.plan_ingestion(
            source_records=records,
            source_staging=source_staging,
            source_tag="openimages",
            taxonomy=taxonomy,
        )


def test_sha_mismatch_is_fatal(
    source_staging: Path, tmp_path: Path
) -> None:
    """A tampered source image (SHA drift vs provenance) aborts ingestion."""
    # Corrupt one retained image's bytes after the manifest was written.
    victim = source_staging / "images" / "f663d03a10e841bf.jpg"
    victim.write_bytes(victim.read_bytes() + b"\x00tamper")
    assert _run(source_staging, tmp_path / "canonical") == ing._EXIT_ERRORS


# --------------------------------------------------------------------------- #
# Nothing is marked READY / RELEASED                                          #
# --------------------------------------------------------------------------- #
def test_outputs_assert_not_released(source_staging: Path, tmp_path: Path) -> None:
    canonical = tmp_path / "canonical"
    assert _run(source_staging, canonical) == 0
    for name in (
        "reports/remediation_manifest.json",
        "reports/canonical_filename_map.json",
        "provenance/provenance_manifest.json",
    ):
        doc = json.loads((canonical / name).read_text("utf-8"))
        assert doc["is_dataset_v1"] is False
        assert doc["is_released"] is False
