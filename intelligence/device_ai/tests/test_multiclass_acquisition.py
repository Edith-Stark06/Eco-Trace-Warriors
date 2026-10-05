"""Tests for the multi-class Open Images acquisition orchestrator (P4.3.1).

These exercise ``scripts/acquire_openimages_multiclass.py`` against the fifteen
sprint-mandated scenarios: taxonomy loading, valid mapping, invalid mapping, an
unmapped source class, dry-run, per-class isolation, manifest parsing,
resumability, count aggregation, no fabricated success, provenance propagation,
invalid config, a zero-converted result, multiple classes and limit handling.

No network access ever happens: the download step is dependency-injected, so a
fake writes synthetic JPEGs + pixel-XYXY labels to a temp OID-style tree and the
orchestrator drives the *real* frozen converter/validators over them. The
orchestrator lives under ``scripts/`` (off the pytest pythonpath), so that
directory is prepended to ``sys.path`` before import. No frozen module is touched.
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

import acquire_openimages_multiclass as acq  # noqa: E402

from device_ai.configs.settings import Settings  # noqa: E402
from device_ai.dataset.taxonomy import load_taxonomy  # noqa: E402

_TIMESTAMP = "2026-08-09T00:00:00+00:00"
_VERSION = "openimages-multiclass-test"


# --------------------------------------------------------------------------- #
# Fixtures & helpers                                                          #
# --------------------------------------------------------------------------- #
@pytest.fixture
def taxonomy():
    return load_taxonomy()


@pytest.fixture
def settings():
    return Settings()


def _entries(
    prefix: str,
    oid: str,
    count: int,
    *,
    size: tuple[int, int] = (640, 480),
    out_of_frame: bool = False,
) -> list[tuple[str, tuple[int, int], str]]:
    """Build a synthetic download pool: (stem, size, pixel-XYXY label text).

    Each label names ``oid`` as its source class so the converter's
    source->canonical map resolves it. ``out_of_frame`` produces a box that
    spills past the frame so conversion rejects it (never clips).
    """
    box = f"{oid} 100 50 2000 300" if out_of_frame else f"{oid} 100 50 400 300"
    return [(f"{prefix}_{i}", size, box) for i in range(count)]


def _make_download(pool_by_class):
    """Return an offline download_fn that materialises a synthetic pool.

    The returned callable records every :class:`acq.DownloadRequest` it receives
    on its ``.calls`` attribute. A class absent from ``pool_by_class`` yields a
    failed download; an empty list yields a successful-but-empty download.
    """
    calls: list[acq.DownloadRequest] = []

    def _download(request: acq.DownloadRequest) -> acq.DownloadResult:
        calls.append(request)
        images_root = (
            request.toolkit_root
            / "OID"
            / "Dataset"
            / "train"
            / request.open_images_class
        )
        labels_root = images_root / "Label"
        pool = pool_by_class.get(request.open_images_class)
        if pool is None:
            return acq.DownloadResult(
                ok=False,
                image_count=0,
                label_count=0,
                images_root=images_root,
                labels_root=labels_root,
                message="synthetic: class unavailable",
            )
        images_root.mkdir(parents=True, exist_ok=True)
        labels_root.mkdir(parents=True, exist_ok=True)
        take = pool[: request.limit]
        for index, (stem, size, text) in enumerate(take):
            # Distinct colour per image so content SHA-256 differs and the
            # frozen DuplicateDetector does not flag them as duplicates.
            colour = ((index * 37) % 256, (index * 73) % 256, (index * 113) % 256)
            Image.new("RGB", size, colour).save(images_root / f"{stem}.jpg")
            (labels_root / f"{stem}.txt").write_text(text, encoding="utf-8")
        return acq.DownloadResult(
            ok=True,
            image_count=len(take),
            label_count=len(take),
            images_root=images_root,
            labels_root=labels_root,
            message="",
        )

    _download.calls = calls
    return _download


def _row(taxonomy, name, *, mapping="MAPPED", oid=None, source=acq._APPROVED_SOURCE):
    """Build a :class:`acq.PlanRow` for ``name`` with sensible defaults."""
    class_id = taxonomy.class_id_for(name)
    assert class_id is not None
    if oid is not None:
        open_images = oid
    elif mapping == "MAPPED":
        open_images = name.capitalize()
    else:
        open_images = ""
    return acq.PlanRow(
        class_id=class_id,
        ecotrace_class=name,
        open_images_class=open_images,
        mapping_status=mapping,
        source=source if mapping == "MAPPED" else "",
        source_license="images=per-image-Flickr(VARY-verify); annotations=CC-BY-4.0",
        planned_min=150,
        planned_recommended=300,
        planned_ideal=500,
        notes="",
    )


def _acquire(row, download_fn, tmp_path, taxonomy, settings, **kwargs):
    """Run :func:`acq.acquire_class` with test defaults."""
    params = {
        "limit": 5,
        "dry_run": False,
        "force": False,
        "created_at": _TIMESTAMP,
        "conversion_version": _VERSION,
    }
    params.update(kwargs)
    return acq.acquire_class(
        row,
        staging_root=tmp_path / "staging",
        toolkit_root=tmp_path / "tk",
        taxonomy=taxonomy,
        settings=settings,
        download_fn=download_fn,
        **params,
    )


def _args(tmp_path, *extra):
    """Build a parsed args namespace pointed entirely at temp locations."""
    return acq._parse_args(
        [
            "--staging-root",
            str(tmp_path / "staging"),
            "--toolkit-root",
            str(tmp_path / "tk"),
            "--status-out",
            str(tmp_path / "status.json"),
            *extra,
        ]
    )


# --------------------------------------------------------------------------- #
# 1. Taxonomy loading drives plan validation                                  #
# --------------------------------------------------------------------------- #
def test_shipped_plan_validates_against_dynamic_taxonomy(taxonomy):
    rows = acq.load_plan(acq._DEFAULT_PLAN)
    issues = acq.validate_plan(rows, taxonomy)
    assert issues == []
    # Every taxonomy class is represented exactly once (dynamic, not hardcoded).
    assert len(rows) == taxonomy.num_classes


# --------------------------------------------------------------------------- #
# 2. Valid mapping acquires to QA_PENDING                                      #
# --------------------------------------------------------------------------- #
def test_valid_mapping_acquires_to_qa_pending(tmp_path, taxonomy, settings):
    download = _make_download({"Printer": _entries("printer", "Printer", 4)})
    outcome = _acquire(
        _row(taxonomy, "printer", oid="Printer"),
        download,
        tmp_path,
        taxonomy,
        settings,
    )
    assert outcome.state == acq._STATE_QA_PENDING
    assert outcome.downloaded == 4
    assert outcome.converted == 4
    assert outcome.valid_images == 4
    assert outcome.valid_annotations == 4
    assert outcome.duplicates == 0
    assert outcome.conversion_errors == 0
    # Human QA is never performed here.
    assert outcome.qa_pending == 4
    assert outcome.qa_accepted == 0
    assert outcome.qa_rejected == 0
    staging = acq.staging_dir_for("printer", tmp_path / "staging")
    assert (staging / "images").is_dir()
    assert len(list((staging / "images").glob("*.jpg"))) == 4
    assert len(list((staging / "labels").glob("*.txt"))) == 4


# --------------------------------------------------------------------------- #
# 3. Invalid mapping is reported                                               #
# --------------------------------------------------------------------------- #
def test_invalid_mapping_is_reported(taxonomy):
    rows = list(acq.load_plan(acq._DEFAULT_PLAN))
    # Corrupt the printer row: MAPPED but with no Open Images class.
    for index, row in enumerate(rows):
        if row.ecotrace_class == "printer":
            rows[index] = acq.PlanRow(
                class_id=row.class_id,
                ecotrace_class="printer",
                open_images_class="",
                mapping_status="MAPPED",
                source=acq._APPROVED_SOURCE,
                source_license=row.source_license,
                planned_min=row.planned_min,
                planned_recommended=row.planned_recommended,
                planned_ideal=row.planned_ideal,
                notes=row.notes,
            )
    issues = acq.validate_plan(rows, taxonomy)
    codes = {(i.ecotrace_class, i.code) for i in issues}
    assert ("printer", "MAPPED_WITHOUT_SOURCE_CLASS") in codes


def test_taxonomy_mismatch_is_reported(taxonomy):
    bad = _row(taxonomy, "printer", oid="Printer")
    bad = acq.PlanRow(
        class_id=(bad.class_id + 1) % taxonomy.num_classes,
        ecotrace_class="printer",
        open_images_class="Printer",
        mapping_status="MAPPED",
        source=acq._APPROVED_SOURCE,
        source_license=bad.source_license,
        planned_min=1,
        planned_recommended=1,
        planned_ideal=1,
        notes="",
    )
    issues = acq.validate_plan([bad], taxonomy)
    assert any(i.code == "TAXONOMY_MISMATCH" for i in issues)


# --------------------------------------------------------------------------- #
# 4. Unmapped source class is blocked (never downloaded)                       #
# --------------------------------------------------------------------------- #
def test_unmapped_class_is_blocked(tmp_path, taxonomy, settings):
    download = _make_download({})  # any download would be an error
    outcome = _acquire(
        _row(taxonomy, "battery", mapping="UNMAPPED"),
        download,
        tmp_path,
        taxonomy,
        settings,
    )
    assert outcome.state == acq._STATE_BLOCKED
    assert outcome.downloaded == 0
    assert download.calls == []  # blocked before any download
    assert not acq.staging_dir_for("battery", tmp_path / "staging").exists()


# --------------------------------------------------------------------------- #
# 5. Dry-run has no side effects                                               #
# --------------------------------------------------------------------------- #
def test_dry_run_has_no_side_effects(tmp_path, taxonomy, settings):
    download = _make_download({"Printer": _entries("printer", "Printer", 3)})
    outcome = _acquire(
        _row(taxonomy, "printer", oid="Printer"),
        download,
        tmp_path,
        taxonomy,
        settings,
        dry_run=True,
    )
    assert outcome.state == acq._STATE_DRY_RUN
    assert download.calls == []
    assert not acq.staging_dir_for("printer", tmp_path / "staging").exists()


# --------------------------------------------------------------------------- #
# 6. Per-class directory isolation                                             #
# --------------------------------------------------------------------------- #
def test_per_class_directory_isolation(tmp_path, taxonomy, settings):
    download = _make_download(
        {
            "Printer": _entries("printer", "Printer", 2),
            "Computer keyboard": _entries("keyboard", "Computer keyboard", 3),
        }
    )
    _acquire(
        _row(taxonomy, "printer", oid="Printer"),
        download,
        tmp_path,
        taxonomy,
        settings,
    )
    _acquire(
        _row(taxonomy, "keyboard", oid="Computer keyboard"),
        download,
        tmp_path,
        taxonomy,
        settings,
    )
    printer_dir = acq.staging_dir_for("printer", tmp_path / "staging")
    keyboard_dir = acq.staging_dir_for("keyboard", tmp_path / "staging")
    assert printer_dir != keyboard_dir
    printer_stems = {p.stem for p in (printer_dir / "images").glob("*.jpg")}
    keyboard_stems = {p.stem for p in (keyboard_dir / "images").glob("*.jpg")}
    assert all(s.startswith("printer_") for s in printer_stems)
    assert all(s.startswith("keyboard_") for s in keyboard_stems)
    assert printer_stems.isdisjoint(keyboard_stems)


# --------------------------------------------------------------------------- #
# 7. Manifest parsing                                                          #
# --------------------------------------------------------------------------- #
def test_manifest_parsing_skips_comments_and_types_fields():
    rows = acq.load_plan(acq._DEFAULT_PLAN)
    by_name = {r.ecotrace_class: r for r in rows}
    laptop = by_name["laptop"]
    assert laptop.class_id == 0
    assert laptop.mapping_status == "MAPPED"
    assert laptop.open_images_class == "Laptop"
    assert isinstance(laptop.planned_min, int)
    battery = by_name["battery"]
    assert battery.mapping_status == "UNMAPPED"
    assert battery.open_images_class == ""


def test_manifest_missing_file_raises(tmp_path):
    with pytest.raises(acq.PlanError):
        acq.load_plan(tmp_path / "nope.csv")


# --------------------------------------------------------------------------- #
# 8. Resumability                                                             #
# --------------------------------------------------------------------------- #
def test_resumability_skips_then_forces(tmp_path, taxonomy, settings):
    download = _make_download({"Printer": _entries("printer", "Printer", 3)})
    row = _row(taxonomy, "printer", oid="Printer")
    first = _acquire(row, download, tmp_path, taxonomy, settings)
    assert first.state == acq._STATE_QA_PENDING
    assert len(download.calls) == 1

    # Re-run without --force: skipped as already acquired, no new download.
    second = _acquire(row, download, tmp_path, taxonomy, settings)
    assert second.state == acq._STATE_ALREADY
    assert len(download.calls) == 1

    # Re-run with --force: downloads again.
    third = _acquire(row, download, tmp_path, taxonomy, settings, force=True)
    assert third.state == acq._STATE_QA_PENDING
    assert len(download.calls) == 2


# --------------------------------------------------------------------------- #
# 9. Count aggregation                                                        #
# --------------------------------------------------------------------------- #
def test_count_aggregation(taxonomy):
    staging = Path("dataset_acquisition/staging/x")
    printer_row = _row(taxonomy, "printer", oid="Printer")
    camera_row = _row(taxonomy, "camera", oid="Camera")
    ok = acq._with(
        acq._base_outcome(printer_row, staging, requested=5),
        state=acq._STATE_QA_PENDING,
        downloaded=5,
        converted=5,
        valid_images=5,
        qa_pending=5,
    )
    empty = acq._with(
        acq._base_outcome(camera_row, staging, requested=5),
        state=acq._STATE_DOWNLOAD_EMPTY,
        downloaded=0,
    )
    payload = acq.build_status_payload([ok, empty], context={"run_label": "t"})
    summary = payload["summary"]
    assert summary["classes_selected"] == 2
    assert summary["total_requested"] == 10
    assert summary["total_downloaded"] == 5
    assert summary["total_converted"] == 5
    assert summary["total_qa_pending"] == 5
    assert summary["total_qa_accepted"] == 0
    assert summary["by_state"][acq._STATE_QA_PENDING] == 1
    assert summary["by_state"][acq._STATE_DOWNLOAD_EMPTY] == 1


# --------------------------------------------------------------------------- #
# 10. No fabricated success (failed & empty downloads)                         #
# --------------------------------------------------------------------------- #
def test_failed_download_is_not_a_success(tmp_path, taxonomy, settings):
    download = _make_download({})  # Printer absent -> ok=False
    outcome = _acquire(
        _row(taxonomy, "printer", oid="Printer"),
        download,
        tmp_path,
        taxonomy,
        settings,
    )
    assert outcome.state == acq._STATE_DOWNLOAD_FAILED
    assert outcome.downloaded == 0
    assert outcome.qa_pending == 0
    staging = acq.staging_dir_for("printer", tmp_path / "staging")
    assert not (staging / "images").exists()


def test_empty_download_is_not_a_success(tmp_path, taxonomy, settings):
    download = _make_download({"Printer": []})  # ok but zero images
    outcome = _acquire(
        _row(taxonomy, "printer", oid="Printer"),
        download,
        tmp_path,
        taxonomy,
        settings,
    )
    assert outcome.state == acq._STATE_DOWNLOAD_EMPTY
    assert outcome.downloaded == 0
    assert outcome.qa_pending == 0


# --------------------------------------------------------------------------- #
# 11. Provenance propagation                                                  #
# --------------------------------------------------------------------------- #
def test_provenance_propagation(tmp_path, taxonomy, settings):
    download = _make_download({"Printer": _entries("printer", "Printer", 2)})
    _acquire(
        _row(taxonomy, "printer", oid="Printer"),
        download,
        tmp_path,
        taxonomy,
        settings,
    )
    manifest_path = (
        acq.staging_dir_for("printer", tmp_path / "staging")
        / "provenance"
        / "provenance_manifest.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["source"] == acq._APPROVED_SOURCE
    assert manifest["ecotrace_class"] == "printer"
    assert manifest["ecotrace_class_id"] == taxonomy.class_id_for("printer")
    assert manifest["total_images"] == 2
    record = manifest["records"][0]
    assert record["source_class"] == "Printer"
    assert record["source_image_filename"].endswith(".jpg")
    assert len(record["sha256"]) == 64
    assert record["conversion_timestamp"] == _TIMESTAMP


# --------------------------------------------------------------------------- #
# 12. Invalid config is rejected                                              #
# --------------------------------------------------------------------------- #
def test_run_rejects_bad_timestamp(tmp_path):
    download = _make_download({"Printer": _entries("printer", "Printer", 1)})
    args = _args(tmp_path, "--class", "printer", "--created-at", "not-a-date")
    assert acq.run(args, download_fn=download) == acq._EXIT_USAGE


def test_run_rejects_forbidden_staging_root(tmp_path):
    download = _make_download({"Printer": _entries("printer", "Printer", 1)})
    forbidden = _REPO_ROOT / "intelligence" / "device_ai" / "datasets"
    args = acq._parse_args(
        [
            "--class",
            "printer",
            "--staging-root",
            str(forbidden),
            "--toolkit-root",
            str(tmp_path / "tk"),
            "--status-out",
            str(tmp_path / "status.json"),
        ]
    )
    assert acq.run(args, download_fn=download) == acq._EXIT_USAGE


def test_run_rejects_unknown_class(tmp_path):
    download = _make_download({})
    args = _args(tmp_path, "--class", "not_a_real_class")
    assert acq.run(args, download_fn=download) == acq._EXIT_USAGE


def test_run_requires_a_selector(tmp_path):
    download = _make_download({})
    args = _args(tmp_path)
    assert acq.run(args, download_fn=download) == acq._EXIT_USAGE


# --------------------------------------------------------------------------- #
# 13. Zero-converted result (download ok, conversion rejects every box)        #
# --------------------------------------------------------------------------- #
def test_zero_converted_is_conversion_failed(tmp_path, taxonomy, settings):
    download = _make_download(
        {"Printer": _entries("printer", "Printer", 2, out_of_frame=True)}
    )
    outcome = _acquire(
        _row(taxonomy, "printer", oid="Printer"),
        download,
        tmp_path,
        taxonomy,
        settings,
    )
    assert outcome.state == acq._STATE_CONVERSION_FAILED
    assert outcome.downloaded == 2
    assert outcome.converted == 0
    assert outcome.conversion_errors >= 2
    assert outcome.qa_pending == 0


# --------------------------------------------------------------------------- #
# 14. Multiple classes via run()                                              #
# --------------------------------------------------------------------------- #
def test_multiple_classes_via_run(tmp_path):
    download = _make_download(
        {
            "Printer": _entries("printer", "Printer", 3),
            "Computer keyboard": _entries("keyboard", "Computer keyboard", 2),
        }
    )
    args = _args(tmp_path, "--classes", "printer", "keyboard", "--limit", "10")
    code = acq.run(args, download_fn=download)
    assert code == acq._EXIT_OK
    payload = json.loads((tmp_path / "status.json").read_text(encoding="utf-8"))
    assert payload["is_released"] is False
    assert payload["is_dataset_v1"] is False
    assert payload["summary"]["classes_selected"] == 2
    states = {c["ecotrace_class"]: c["state"] for c in payload["classes"]}
    assert states["printer"] == acq._STATE_QA_PENDING
    assert states["keyboard"] == acq._STATE_QA_PENDING


# --------------------------------------------------------------------------- #
# 15. Limit handling                                                          #
# --------------------------------------------------------------------------- #
def test_limit_caps_and_reports_honestly(tmp_path, taxonomy, settings):
    # Pool of 5, limit 3 -> exactly 3 requested and downloaded.
    download = _make_download({"Printer": _entries("printer", "Printer", 5)})
    outcome = _acquire(
        _row(taxonomy, "printer", oid="Printer"),
        download,
        tmp_path,
        taxonomy,
        settings,
        limit=3,
    )
    assert download.calls[0].limit == 3
    assert outcome.requested == 3
    assert outcome.downloaded == 3


def test_limit_reports_fewer_than_requested(tmp_path, taxonomy, settings):
    # Pool of 2, limit 10 -> honest 2 downloaded against a requested 10.
    download = _make_download({"Printer": _entries("printer", "Printer", 2)})
    outcome = _acquire(
        _row(taxonomy, "printer", oid="Printer"),
        download,
        tmp_path,
        taxonomy,
        settings,
        limit=10,
    )
    assert outcome.requested == 10
    assert outcome.downloaded == 2
    assert outcome.state == acq._STATE_QA_PENDING


# --------------------------------------------------------------------------- #
# Bonus: pilot class is protected; --list works                               #
# --------------------------------------------------------------------------- #
def test_pilot_class_is_protected(tmp_path, taxonomy, settings):
    download = _make_download({"Laptop": _entries("laptop", "Laptop", 3)})
    outcome = _acquire(
        _row(taxonomy, "laptop", oid="Laptop"),
        download,
        tmp_path,
        taxonomy,
        settings,
        force=True,  # even --force must not touch the pilot
    )
    assert outcome.state == acq._STATE_ALREADY
    assert download.calls == []


def test_list_option_returns_ok(tmp_path, capsys):
    download = _make_download({})
    args = _args(tmp_path, "--list")
    assert acq.run(args, download_fn=download) == acq._EXIT_OK
    out = capsys.readouterr().out
    assert "Dataset v1.0 is not released" in out
    assert "laptop" in out
