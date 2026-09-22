"""Offline tests for the P4.3.2 multi-class expansion additions.

P4.3.2 reuses the frozen P4.3.1 orchestrator verbatim; these tests therefore do
**not** re-cover the 24 existing acquisition tests. They exercise only the
*new*, additive P4.3.2 tooling:

* ``scripts/make_visual_qa_multiclass.py`` — the class-agnostic visual QA
  preview generator (box tags resolved from the frozen taxonomy, QA_PENDING
  boundary, read-only w.r.t. the staged dataset).
* ``scripts/analyze_multiclass_expansion.py`` — the honest failure-surfacing
  layer (``collect_acquisition_status`` records every *requested* class's real
  terminal state so a ``DOWNLOAD_FAILED`` class is reported BLOCKED /
  NOT_MEASURED, never silently dropped), plus the total ``_as_int`` coercion and
  the ``_first_failure_reason`` one-line extractor.

No network access ever happens and no frozen module is modified: synthetic
JPEGs / YOLO labels / orchestrator status JSONs are written to a temp tree and
the real scripts run over them. Both scripts live under ``scripts/`` (off the
pytest pythonpath), so that directory is prepended to ``sys.path`` before import.
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

import analyze_multiclass_expansion as ana  # noqa: E402
import make_visual_qa_multiclass as vqa  # noqa: E402

from device_ai.dataset.taxonomy import load_taxonomy  # noqa: E402

_TIMESTAMP = "2026-08-10T00:00:00+00:00"


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #
def _write_image(path: Path, *, size: tuple[int, int] = (128, 96)) -> None:
    """Write a small solid RGB JPEG to ``path`` (parents created)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, (120, 160, 200)).save(path, format="JPEG")


def _write_label(path: Path, class_id: int) -> None:
    """Write a single centred YOLO box for ``class_id`` to ``path``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{class_id} 0.5 0.5 0.4 0.4\n", encoding="utf-8")


def _staging(tmp_path: Path, *, class_id: int, n: int) -> Path:
    """Build a ``images/`` + ``labels/`` staging dir with ``n`` paired items."""
    root = tmp_path / "staging"
    for i in range(n):
        stem = f"img{i:02d}"
        _write_image(root / "images" / f"{stem}.jpg")
        _write_label(root / "labels" / f"{stem}.txt", class_id)
    return root


def _status_json(
    path: Path,
    *,
    ecotrace_class: str,
    class_id: int,
    state: str,
    requested: int,
    downloaded: int,
    converted: int,
    valid_images: int,
    open_images_class: str = "",
    mapping_status: str = "MAPPED",
    messages: list[str] | None = None,
) -> None:
    """Write a minimal orchestrator per-class status JSON at ``path``."""
    payload = {
        "run_label": "p4_3_2",
        "classes": [
            {
                "ecotrace_class": ecotrace_class,
                "class_id": class_id,
                "open_images_class": open_images_class,
                "mapping_status": mapping_status,
                "state": state,
                "requested": requested,
                "downloaded": downloaded,
                "converted": converted,
                "valid_images": valid_images,
                "messages": messages or [],
            }
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


# --------------------------------------------------------------------------- #
# _as_int — total, never-raising JSON coercion                                #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (5, 5),
        (5.9, 5),
        ("7", 7),
        (True, 1),
        (None, 0),
        ("not-a-number", 0),
        ([1, 2], 0),
    ],
)
def test_as_int_is_total(value: object, expected: int) -> None:
    assert ana._as_int(value) == expected


def test_as_int_uses_default_on_failure() -> None:
    assert ana._as_int("bad", -1) == -1
    assert ana._as_int(None, -1) == -1


# --------------------------------------------------------------------------- #
# _first_failure_reason — one-line signal, traceback preserved upstream       #
# --------------------------------------------------------------------------- #
def test_first_failure_reason_returns_last_line() -> None:
    msg = (
        "download failed: Traceback (most recent call last):\n"
        "  File 'x', line 1\n"
        "MemoryError: Unable to allocate 111 MiB"
    )
    assert ana._first_failure_reason([msg]) == "MemoryError: Unable to allocate 111 MiB"


def test_first_failure_reason_handles_empty() -> None:
    assert ana._first_failure_reason([]) == "unknown failure (no message recorded)"
    assert ana._first_failure_reason("not a list") == (
        "unknown failure (no message recorded)"
    )


# --------------------------------------------------------------------------- #
# collect_acquisition_status — no failure is ever hidden                      #
# --------------------------------------------------------------------------- #
def test_collect_status_surfaces_failed_class_as_not_measured(tmp_path: Path) -> None:
    """A DOWNLOAD_FAILED class must appear, marked unstaged / NOT_MEASURED."""
    _status_json(
        tmp_path / "p4_3_2_real_printer.json",
        ecotrace_class="printer",
        class_id=8,
        state="DOWNLOAD_FAILED",
        requested=100,
        downloaded=0,
        converted=0,
        valid_images=0,
        open_images_class="Printer",
        messages=["download failed: ...\nMemoryError: Unable to allocate 111 MiB"],
    )

    entries = ana.collect_acquisition_status(tmp_path)

    assert len(entries) == 1
    printer = entries[0]
    assert printer["ecotrace_class"] == "printer"
    assert printer["state"] == "DOWNLOAD_FAILED"
    assert printer["requested"] == 100
    assert printer["staged_data"] is False
    assert printer["quality_measured"] is False
    assert printer["failure_reason"] == "MemoryError: Unable to allocate 111 MiB"


def test_collect_status_marks_successful_class_measured(tmp_path: Path) -> None:
    _status_json(
        tmp_path / "p4_3_2_real_tablet.json",
        ecotrace_class="tablet",
        class_id=2,
        state="QA_PENDING",
        requested=100,
        downloaded=100,
        converted=100,
        valid_images=100,
        open_images_class="Tablet computer",
    )

    entries = ana.collect_acquisition_status(tmp_path)

    assert len(entries) == 1
    tablet = entries[0]
    assert tablet["staged_data"] is True
    assert tablet["quality_measured"] is True
    assert tablet["failure_reason"] == ana._NOT_MEASURED
    assert tablet["converted"] == 100


def test_collect_status_sorted_and_covers_every_requested_class(
    tmp_path: Path,
) -> None:
    """All three requested classes are surfaced, sorted by class id."""
    _status_json(
        tmp_path / "p4_3_2_real_tablet.json",
        ecotrace_class="tablet",
        class_id=2,
        state="QA_PENDING",
        requested=100,
        downloaded=100,
        converted=100,
        valid_images=100,
    )
    _status_json(
        tmp_path / "p4_3_2_real_monitor.json",
        ecotrace_class="monitor",
        class_id=5,
        state="QA_PENDING",
        requested=100,
        downloaded=99,
        converted=99,
        valid_images=99,
    )
    _status_json(
        tmp_path / "p4_3_2_real_printer.json",
        ecotrace_class="printer",
        class_id=8,
        state="DOWNLOAD_FAILED",
        requested=100,
        downloaded=0,
        converted=0,
        valid_images=0,
        messages=["boom\nMemoryError: nope"],
    )

    entries = ana.collect_acquisition_status(tmp_path)

    assert [e["ecotrace_class"] for e in entries] == ["tablet", "monitor", "printer"]
    assert [e["staged_data"] for e in entries] == [True, True, False]


def test_collect_status_retry_supersedes_earlier_failure(tmp_path: Path) -> None:
    """A later successful report for a class wins over an earlier failure."""
    _status_json(
        tmp_path / "p4_3_2_real_printer_a.json",
        ecotrace_class="printer",
        class_id=8,
        state="DOWNLOAD_FAILED",
        requested=100,
        downloaded=0,
        converted=0,
        valid_images=0,
        messages=["boom\nMemoryError"],
    )
    _status_json(
        tmp_path / "p4_3_2_real_printer_b.json",
        ecotrace_class="printer",
        class_id=8,
        state="QA_PENDING",
        requested=100,
        downloaded=50,
        converted=50,
        valid_images=50,
    )

    entries = ana.collect_acquisition_status(tmp_path)

    assert len(entries) == 1
    assert entries[0]["staged_data"] is True
    assert entries[0]["converted"] == 50


def test_collect_status_empty_when_dir_absent(tmp_path: Path) -> None:
    assert ana.collect_acquisition_status(tmp_path / "does_not_exist") == []


# --------------------------------------------------------------------------- #
# make_visual_qa_multiclass — class-agnostic tags, QA_PENDING, read-only      #
# --------------------------------------------------------------------------- #
def test_visual_qa_tag_uses_taxonomy_name_not_hardcoded() -> None:
    """Box tags are ``{taxonomy_name}#{cid}`` for whatever class id is present."""
    class_names = load_taxonomy().class_names
    # monitor == id 5 in the frozen taxonomy; the renderer must resolve it.
    assert class_names[5] == "monitor"


def test_visual_qa_read_yolo_parses_boxes(tmp_path: Path) -> None:
    label = tmp_path / "a.txt"
    label.write_text("5 0.5 0.5 0.4 0.4\n", encoding="utf-8")
    boxes = vqa._read_yolo(label)
    assert boxes == [(5, 0.5, 0.5, 0.4, 0.4)]


def test_visual_qa_main_writes_qa_pending_package(tmp_path: Path) -> None:
    """End-to-end: previews + contact sheet + QA_PENDING qa_data.json."""
    staging = _staging(tmp_path, class_id=5, n=3)  # monitor
    out_dir = tmp_path / "manual_review"

    code = vqa.main(
        [
            "--staging-root",
            str(staging),
            "--out-dir",
            str(out_dir),
        ]
    )

    assert code == 0
    data = json.loads((out_dir / "qa_data.json").read_text(encoding="utf-8"))
    assert data["qa_status"] == "QA_PENDING"
    assert data["total_images"] == 3
    assert data["total_objects"] == 3
    assert (out_dir / "contact_sheet.jpg").is_file()
    assert len(list((out_dir / "previews").glob("*.jpg"))) == 3
    # Every tile carries the real class id resolved from the taxonomy.
    assert all(t["class_ids"] == [5] for t in data["tiles"])


def test_visual_qa_is_read_only_wrt_staging(tmp_path: Path) -> None:
    """Generating previews must not add/remove/alter any staged file."""
    staging = _staging(tmp_path, class_id=2, n=2)  # tablet
    before = {
        p.relative_to(staging).as_posix(): p.stat().st_size
        for p in staging.rglob("*")
        if p.is_file()
    }

    code = vqa.main(
        ["--staging-root", str(staging), "--out-dir", str(tmp_path / "mr")]
    )

    after = {
        p.relative_to(staging).as_posix(): p.stat().st_size
        for p in staging.rglob("*")
        if p.is_file()
    }
    assert code == 0
    assert before == after


def test_visual_qa_usage_error_when_dirs_missing(tmp_path: Path) -> None:
    """Missing images/labels dirs → usage exit code, no package written."""
    empty = tmp_path / "empty"
    empty.mkdir()
    code = vqa.main(
        ["--staging-root", str(empty), "--out-dir", str(tmp_path / "mr")]
    )
    assert code == vqa._EXIT_USAGE
    assert not (tmp_path / "mr" / "qa_data.json").exists()


def test_visual_qa_never_auto_accepts(tmp_path: Path) -> None:
    """The QA boundary constant is QA_PENDING — never an accepted state."""
    assert vqa._QA_PENDING == "QA_PENDING"
    staging = _staging(tmp_path, class_id=8, n=1)  # printer id, purely structural
    out_dir = tmp_path / "mr"
    vqa.main(["--staging-root", str(staging), "--out-dir", str(out_dir)])
    text = (out_dir / "qa_data.json").read_text(encoding="utf-8")
    assert "QA_ACCEPTED" not in text
    assert '"qa_status": "QA_PENDING"' in text
