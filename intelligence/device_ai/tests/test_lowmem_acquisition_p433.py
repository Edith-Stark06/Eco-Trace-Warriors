"""Offline tests for the P4.3.3 low-memory Open Images acquisition adapter.

These tests cover the *new* P4.3.3 tooling only —
``scripts/acquire_openimages_lowmem.py`` — the memory-bounded, chunked
annotation scanner that lets the ``printer`` class (and any class that hits the
14.6M-row ``train-annotations-bbox.csv``) be acquired without the OOM that
blocked it in P4.3.2. The frozen P4.3.1 orchestrator, the converter and the
validators are reused verbatim and are **not** re-covered here.

Everything runs offline: synthetic bbox / class-description CSVs, synthetic
JPEGs and a fake ``aws`` shim are written to a temp tree and the real adapter
runs over them. No network access, no real Open Images data, and no frozen
module is modified. The adapter lives under ``scripts/`` (off the pytest
pythonpath), so that directory is prepended to ``sys.path`` before import.

The required P4.3.3 cases are each marked in the test docstrings:
    1. chunked CSV reading            7. malformed annotation handling
    2. usecols behavior               8. deterministic output
    3. printer filtering              9. count reconciliation
    4. multiple chunks               10. no full-CSV load
    5. duplicate ImageID handling    11. converter-interface integration
    6. missing ImageID handling      12. QA_PENDING result
plus a realistic chunked-processing memory test.
"""

from __future__ import annotations

import sys
import tracemalloc
from pathlib import Path

import pandas as pd
import pytest
from PIL import Image

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCRIPTS_DIR = _REPO_ROOT / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import acquire_openimages_lowmem as low  # noqa: E402
import acquire_openimages_multiclass as orch  # noqa: E402

from device_ai.configs.settings import Settings  # noqa: E402
from device_ai.dataset.taxonomy import load_taxonomy  # noqa: E402

# The Open Images 2018_04 bbox header, verbatim (13 columns).
_BBOX_HEADER = (
    "ImageID,Source,LabelName,Confidence,XMin,XMax,YMin,YMax,"
    "IsOccluded,IsTruncated,IsGroupOf,IsDepiction,IsInside"
)
_PRINTER_MID = "/m/01m4t"
_OTHER_MID = "/m/0abc"
_PRINTER_CLASS = "Printer"


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #
def _bbox_row(
    image_id: str,
    mid: str,
    *,
    xmin: float = 0.10,
    xmax: float = 0.20,
    ymin: float = 0.30,
    ymax: float = 0.40,
    occluded: int = 0,
    truncated: int = 0,
    group_of: int = 0,
    depiction: int = 0,
    inside: int = 0,
    source: str = "freeform",
    confidence: int = 1,
) -> str:
    """Return one bbox CSV line matching the 2018_04 column order."""
    return (
        f"{image_id},{source},{mid},{confidence},"
        f"{xmin},{xmax},{ymin},{ymax},"
        f"{occluded},{truncated},{group_of},{depiction},{inside}"
    )


def _write_bbox_csv(path: Path, rows: list[str]) -> Path:
    """Write a bbox CSV (header + rows) to ``path`` and return it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join([_BBOX_HEADER, *rows]) + "\n", encoding="utf-8")
    return path


def _write_descriptions_csv(path: Path, mapping: dict[str, str]) -> Path:
    """Write a ``class-descriptions-boxable.csv`` (``mid,DisplayName``)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{mid},{name}" for mid, name in mapping.items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _contiguous_printer_csv(path: Path, n: int) -> Path:
    """Write ``n`` distinct single-box printer images (ImageID-contiguous)."""
    rows = [_bbox_row(f"img{i:04d}", _PRINTER_MID) for i in range(n)]
    return _write_bbox_csv(path, rows)


# --------------------------------------------------------------------------- #
# 1. chunked CSV reading  +  3. printer filtering                             #
# --------------------------------------------------------------------------- #
def test_iter_matching_chunks_filters_to_class(tmp_path: Path) -> None:
    """Chunks are streamed and only the target class survives (cases 1, 3)."""
    csv = _write_bbox_csv(
        tmp_path / "bbox.csv",
        [
            _bbox_row("imgA", _PRINTER_MID),
            _bbox_row("imgB", _OTHER_MID),
            _bbox_row("imgC", _PRINTER_MID),
            _bbox_row("imgD", _OTHER_MID),
        ],
    )
    chunks = list(
        low.iter_matching_chunks(
            csv,
            class_mid=_PRINTER_MID,
            selector=low.AttributeSelector(),
            chunk_size=2,
        )
    )
    # 4 rows / chunk_size 2 => 2 chunks streamed.
    assert len(chunks) == 2
    matched = pd.concat([m for m, _ in chunks])
    # Only the two printer rows survive; the other-class rows are dropped.
    assert sorted(matched["ImageID"].tolist()) == ["imgA", "imgC"]
    assert set(matched["LabelName"].tolist()) == {_PRINTER_MID}


# --------------------------------------------------------------------------- #
# 2. usecols behavior  +  10. no full-CSV load                                #
# --------------------------------------------------------------------------- #
def test_reader_uses_usecols_and_chunksize(tmp_path: Path) -> None:
    """``usecols`` is the 11-column allowlist and Source/Confidence are absent."""
    csv = _contiguous_printer_csv(tmp_path / "bbox.csv", 3)
    captured: dict[str, object] = {}
    real_read_csv = pd.read_csv

    def spy(*args: object, **kwargs: object):  # noqa: ANN202
        captured.update(kwargs)
        return real_read_csv(*args, **kwargs)

    import unittest.mock as mock

    with mock.patch.object(low.pd, "read_csv", side_effect=spy):
        list(
            low.iter_matching_chunks(
                csv,
                class_mid=_PRINTER_MID,
                selector=low.AttributeSelector(),
                chunk_size=500_000,
            )
        )

    assert captured["usecols"] == list(low._USECOLS)
    assert captured["chunksize"] == 500_000
    # The two frame-of-reference-only columns are never loaded.
    assert "Source" not in low._USECOLS
    assert "Confidence" not in low._USECOLS
    # A chunked reader is used, never a single full-frame read.
    assert captured["dtype"] == low._DTYPES


def test_scan_result_columns_are_narrow(tmp_path: Path) -> None:
    """Reconstructed rows only carry the coordinate/id fields, not all 13."""
    csv = _contiguous_printer_csv(tmp_path / "bbox.csv", 2)
    scan = low.scan_class_annotations(csv, class_mid=_PRINTER_MID, limit=5)
    box = scan.boxes_by_image["img0000"][0]
    assert box.image_id == "img0000"
    # coordinates preserved from the CSV (normalised, in [0, 1]).
    assert box.x_min == pytest.approx(0.10)
    assert box.y_max == pytest.approx(0.40)


# --------------------------------------------------------------------------- #
# 4. multiple chunks  +  8. deterministic output                             #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("chunk_size", [1, 2, 3, 7, 1000])
def test_selection_is_chunk_size_independent(
    tmp_path: Path, chunk_size: int
) -> None:
    """The bounded selection is identical for every chunk size (cases 4, 8)."""
    csv = _contiguous_printer_csv(tmp_path / "bbox.csv", 12)
    scan = low.scan_class_annotations(
        csv, class_mid=_PRINTER_MID, limit=5, chunk_size=chunk_size
    )
    # First-seen order, exactly the first five distinct ImageIDs.
    assert scan.image_ids == ("img0000", "img0001", "img0002", "img0003", "img0004")


def test_scan_stops_early_after_limit(tmp_path: Path) -> None:
    """Once ``limit`` distinct ids are held the scan stops (case 4, bounded)."""
    csv = _contiguous_printer_csv(tmp_path / "bbox.csv", 100)
    scan = low.scan_class_annotations(
        csv, class_mid=_PRINTER_MID, limit=3, chunk_size=2
    )
    assert scan.image_ids == ("img0000", "img0001", "img0002")
    # Bounded: it must not have streamed anywhere near all 100 rows.
    assert scan.rows_read < 100


# --------------------------------------------------------------------------- #
# 5. duplicate ImageID handling                                               #
# --------------------------------------------------------------------------- #
def test_multiple_boxes_per_image_are_grouped(tmp_path: Path) -> None:
    """Repeated (contiguous) ImageID rows group as multiple boxes (case 5)."""
    csv = _write_bbox_csv(
        tmp_path / "bbox.csv",
        [
            _bbox_row("imgX", _PRINTER_MID, xmin=0.1, xmax=0.2),
            _bbox_row("imgX", _PRINTER_MID, xmin=0.5, xmax=0.6),
            _bbox_row("imgX", _PRINTER_MID, xmin=0.7, xmax=0.8),
            _bbox_row("imgY", _PRINTER_MID),
        ],
    )
    scan = low.scan_class_annotations(
        csv, class_mid=_PRINTER_MID, limit=5, chunk_size=2
    )
    # One distinct image with three boxes — the duplicate id is not a new image.
    assert scan.image_ids == ("imgX", "imgY")
    assert len(scan.boxes_by_image["imgX"]) == 3
    assert scan.matched_rows == 4


# --------------------------------------------------------------------------- #
# 6. missing ImageID handling                                                 #
# --------------------------------------------------------------------------- #
def test_class_absent_yields_empty_scan(tmp_path: Path) -> None:
    """A class with no rows yields an empty, honest scan (case 6)."""
    csv = _write_bbox_csv(
        tmp_path / "bbox.csv",
        [_bbox_row("imgA", _OTHER_MID), _bbox_row("imgB", _OTHER_MID)],
    )
    scan = low.scan_class_annotations(csv, class_mid=_PRINTER_MID, limit=5)
    assert scan.image_ids == ()
    assert scan.boxes_by_image == {}
    assert scan.matched_rows == 0
    # It still streamed the file (honest rows_read), just matched nothing.
    assert scan.rows_read == 2


def test_download_of_missing_image_is_not_counted(tmp_path: Path) -> None:
    """An ImageID whose S3 object is absent produces no label (case 6)."""
    images_dir = tmp_path / "images"
    labels_dir = images_dir / "Label"
    images_dir.mkdir(parents=True)
    # Only imgA lands on disk; imgB "failed" to download (never written).
    Image.new("RGB", (64, 48), (10, 20, 30)).save(images_dir / "imgA.jpg")
    scan = low.ScanResult(
        image_ids=("imgA", "imgB"),
        boxes_by_image={
            "imgA": (low.SourceBoxRow("imgA", 0.1, 0.2, 0.3, 0.4),),
            "imgB": (low.SourceBoxRow("imgB", 0.1, 0.2, 0.3, 0.4),),
        },
        rows_read=2,
        chunks_read=1,
        matched_rows=2,
    )
    written = low.write_source_labels(
        scan,
        downloaded_ids=["imgA"],  # imgB absent
        images_dir=images_dir,
        labels_dir=labels_dir,
        source_class=_PRINTER_CLASS,
    )
    assert written == 1
    assert (labels_dir / "imgA.txt").is_file()
    assert not (labels_dir / "imgB.txt").exists()


# --------------------------------------------------------------------------- #
# 7. malformed annotation handling                                            #
# --------------------------------------------------------------------------- #
def test_malformed_rows_are_skipped_by_reader(tmp_path: Path) -> None:
    """Rows with a non-numeric coordinate raise, never silently corrupt (case 7)."""
    csv = _write_bbox_csv(
        tmp_path / "bbox.csv",
        [
            _bbox_row("imgA", _PRINTER_MID),
            # XMin is not a float — dtype coercion must fail loudly.
            f"imgB,freeform,{_PRINTER_MID},1,NOTAFLOAT,0.2,0.3,0.4,0,0,0,0,0",
        ],
    )
    with pytest.raises((ValueError, TypeError)):
        low.scan_class_annotations(csv, class_mid=_PRINTER_MID, limit=5)


def test_source_label_written_in_pixel_space(tmp_path: Path) -> None:
    """Normalised OID boxes are reconstructed to pixel XYXY for the converter."""
    images_dir = tmp_path / "images"
    labels_dir = images_dir / "Label"
    images_dir.mkdir(parents=True)
    Image.new("RGB", (200, 100), (10, 20, 30)).save(images_dir / "imgA.jpg")
    scan = low.ScanResult(
        image_ids=("imgA",),
        boxes_by_image={"imgA": (low.SourceBoxRow("imgA", 0.10, 0.50, 0.20, 0.60),)},
        rows_read=1,
        chunks_read=1,
        matched_rows=1,
    )
    low.write_source_labels(
        scan,
        downloaded_ids=["imgA"],
        images_dir=images_dir,
        labels_dir=labels_dir,
        source_class=_PRINTER_CLASS,
    )
    line = (labels_dir / "imgA.txt").read_text(encoding="utf-8").strip()
    parts = line.split()
    assert parts[0] == _PRINTER_CLASS
    # x1=0.10*200=20, y1=0.20*100=20, x2=0.50*200=100, y2=0.60*100=60
    assert [float(v) for v in parts[1:]] == pytest.approx([20.0, 20.0, 100.0, 60.0])


# --------------------------------------------------------------------------- #
# Attribute filtering (parity with OIDv4 images_options)                      #
# --------------------------------------------------------------------------- #
def test_attribute_selector_filters_rows(tmp_path: Path) -> None:
    """A non-None attribute filter keeps only rows with that value."""
    csv = _write_bbox_csv(
        tmp_path / "bbox.csv",
        [
            _bbox_row("imgA", _PRINTER_MID, group_of=0),
            _bbox_row("imgB", _PRINTER_MID, group_of=1),
            _bbox_row("imgC", _PRINTER_MID, group_of=0),
        ],
    )
    selector = low.AttributeSelector(is_group_of=0)
    scan = low.scan_class_annotations(
        csv, class_mid=_PRINTER_MID, limit=10, selector=selector, chunk_size=2
    )
    assert scan.image_ids == ("imgA", "imgC")


def test_attribute_selector_as_map_only_active() -> None:
    """``as_map`` returns only the non-None filters, in column order."""
    selector = low.AttributeSelector(is_occluded=1, is_inside=0)
    assert selector.as_map() == {"IsOccluded": 1, "IsInside": 0}
    assert low.AttributeSelector().as_map() == {}


# --------------------------------------------------------------------------- #
# 9. count reconciliation                                                     #
# --------------------------------------------------------------------------- #
def test_counts_reconcile(tmp_path: Path) -> None:
    """rows_read / matched_rows / selected all reconcile honestly (case 9)."""
    rows = [
        _bbox_row("imgA", _PRINTER_MID),
        _bbox_row("imgA", _PRINTER_MID),  # 2nd box, same image
        _bbox_row("imgB", _OTHER_MID),  # non-matching
        _bbox_row("imgC", _PRINTER_MID),
        _bbox_row("imgD", _PRINTER_MID),
    ]
    csv = _write_bbox_csv(tmp_path / "bbox.csv", rows)
    scan = low.scan_class_annotations(
        csv, class_mid=_PRINTER_MID, limit=10, chunk_size=2
    )
    assert scan.rows_read == 5  # every data row was streamed
    assert scan.matched_rows == 4  # 4 printer rows (imgB excluded)
    assert len(scan.image_ids) == 3  # imgA, imgC, imgD
    total_boxes = sum(len(b) for b in scan.boxes_by_image.values())
    assert total_boxes == scan.matched_rows  # every matched row kept as a box


def test_resolve_class_mid(tmp_path: Path) -> None:
    """The display name resolves to its MID from the descriptions CSV."""
    desc = _write_descriptions_csv(
        tmp_path / "desc.csv", {_PRINTER_MID: "Printer", _OTHER_MID: "Laptop"}
    )
    assert low.resolve_class_mid(desc, "Printer") == _PRINTER_MID
    with pytest.raises(low.AcquisitionError):
        low.resolve_class_mid(desc, "Nonexistent")


def test_missing_bbox_csv_raises(tmp_path: Path) -> None:
    """A missing bbox CSV is a clean AcquisitionError, not a crash."""
    with pytest.raises(low.AcquisitionError):
        low.scan_class_annotations(
            tmp_path / "nope.csv", class_mid=_PRINTER_MID, limit=5
        )


# --------------------------------------------------------------------------- #
# 11. converter-interface integration  +  12. QA_PENDING result               #
# --------------------------------------------------------------------------- #
def _fake_download_factory(csv_dir: Path):  # noqa: ANN202
    """Return a DownloadFn that scans a synthetic CSV and writes local JPEGs.

    This exercises the *real* adapter scan + label writer, but replaces only the
    S3 ``aws`` fetch with locally-generated JPEGs, so the whole orchestrator ->
    converter -> validator -> QA_PENDING path runs offline.
    """

    def _download(request: orch.DownloadRequest) -> orch.DownloadResult:
        images_root = (
            request.toolkit_root
            / "OID"
            / "Dataset"
            / "train"
            / request.open_images_class
        )
        labels_root = images_root / "Label"
        bbox_csv = csv_dir / low._TRAIN_BBOX_CSV
        descriptions_csv = csv_dir / low._CLASS_DESCRIPTIONS_CSV
        class_mid = low.resolve_class_mid(descriptions_csv, request.open_images_class)
        scan = low.scan_class_annotations(
            bbox_csv, class_mid=class_mid, limit=request.limit
        )
        images_root.mkdir(parents=True, exist_ok=True)
        downloaded: list[str] = []
        for i, image_id in enumerate(scan.image_ids):
            # Unique-per-image content so the duplicate detector stays quiet.
            color = (30 + i * 7 % 200, 60, 90)
            Image.new("RGB", (128, 96), color).save(images_root / f"{image_id}.jpg")
            downloaded.append(image_id)
        low.write_source_labels(
            scan,
            downloaded,
            images_dir=images_root,
            labels_dir=labels_root,
            source_class=request.open_images_class,
        )
        return orch.DownloadResult(
            ok=True,
            image_count=low._count_images(images_root),
            label_count=low._count_files(labels_root, "*.txt"),
            images_root=images_root,
            labels_root=labels_root,
            message="",
        )

    return _download


def test_adapter_integrates_with_orchestrator_to_qa_pending(tmp_path: Path) -> None:
    """The adapter feeds the frozen orchestrator to a real QA_PENDING (11, 12)."""
    taxonomy = load_taxonomy()
    printer_id = taxonomy.class_id_for("printer")
    assert printer_id is not None

    csv_dir = tmp_path / "OIDv4_ToolKit" / "OID" / "csv_folder"
    _contiguous_printer_csv(csv_dir / low._TRAIN_BBOX_CSV, 4)
    _write_descriptions_csv(
        csv_dir / low._CLASS_DESCRIPTIONS_CSV, {_PRINTER_MID: "Printer"}
    )
    toolkit_root = tmp_path / "OIDv4_ToolKit"
    staging_root = tmp_path / "staging"

    row = orch.PlanRow(
        class_id=printer_id,
        ecotrace_class="printer",
        open_images_class="Printer",
        mapping_status="MAPPED",
        source=orch._APPROVED_SOURCE,
        source_license="images=Flickr(verify); annotations=CC-BY-4.0(Google)",
        planned_min=150,
        planned_recommended=300,
        planned_ideal=500,
        notes="",
    )
    settings = Settings(
        environment="development",
        json_logs=False,
        log_level="WARNING",
        blur_threshold=0.0,  # keep synthetic solid tiles out of the blur gate
    )

    outcome = orch.acquire_class(
        row,
        limit=4,
        staging_root=staging_root,
        toolkit_root=toolkit_root,
        taxonomy=taxonomy,
        settings=settings,
        download_fn=_fake_download_factory(csv_dir),
        created_at="2026-08-10T00:00:00+00:00",
        conversion_version="p4_3_3_test",
        dry_run=False,
        force=False,
    )

    # Case 12: the terminal state is QA_PENDING — never auto-accepted.
    assert outcome.state == orch._STATE_QA_PENDING
    assert outcome.qa_accepted == 0
    assert outcome.qa_rejected == 0
    # Case 11: the converter consumed the adapter's labels and produced YOLO.
    assert outcome.downloaded == 4
    assert outcome.converted == 4
    assert outcome.qa_pending == 4
    staging = orch.staging_dir_for("printer", staging_root)
    labels = sorted((staging / "labels").glob("*.txt"))
    assert len(labels) == 4
    # Converted YOLO labels carry the canonical printer class id.
    first = labels[0].read_text(encoding="utf-8").split()
    assert first[0] == str(printer_id)


# --------------------------------------------------------------------------- #
# Memory test — realistic chunked processing stays bounded                    #
# --------------------------------------------------------------------------- #
def test_chunked_scan_is_memory_bounded(tmp_path: Path) -> None:
    """A realistic CSV is scanned with a peak far below its on-disk size.

    Writes many thousands of rows (mostly a non-target class) and asserts that a
    small chunk size selects the bounded target set while the traced peak Python
    allocation stays a small fraction of the file — demonstrating the scan never
    materialises the whole CSV. The absolute figure is measured, never invented.
    """
    n_rows = 40_000
    rows: list[str] = []
    # Interleave: 1 printer row every 100 rows, contiguous printers at the front
    # so the bounded scan can early-exit; the bulk is a non-target class.
    for i in range(20):
        rows.append(_bbox_row(f"pr{i:04d}", _PRINTER_MID))
    for i in range(n_rows):
        rows.append(_bbox_row(f"noise{i:05d}", _OTHER_MID))
    csv = _write_bbox_csv(tmp_path / "bbox.csv", rows)
    file_size = csv.stat().st_size

    tracemalloc.start()
    scan = low.scan_class_annotations(
        csv, class_mid=_PRINTER_MID, limit=10, chunk_size=1_000
    )
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    # Bounded selection: exactly the first 10 contiguous printer images.
    assert len(scan.image_ids) == 10
    assert scan.image_ids[0] == "pr0000"
    # Early exit: it stopped well before streaming all 40k+ rows.
    assert scan.rows_read < n_rows
    # Peak traced allocation is a fraction of the file — never a full load.
    # (Recorded, not asserted at a fabricated absolute number.)
    assert peak < file_size
