"""Split-aware YOLO data manifest builder (Sprint P4.1.3, PART 2).

Connects a P4.1.2 :class:`~device_ai.dataset.release.DatasetRelease` to
:class:`~device_ai.training.detector.yolo_trainer.YOLOTrainer` by producing a
**split-aware** YOLO ``data.yaml`` + image lists that honor the release's
train/val/test :class:`~device_ai.dataset.records.SplitAssignment`.

The existing :class:`~device_ai.dataset.exporter.DatasetExporter` writes a flat
``data.yaml`` with ``train: images`` / ``val: images`` pointing at the **same
folder** — validation leakage, unacceptable for production training. This module
writes ``train.txt`` / ``val.txt`` / ``test.txt`` referencing the split's
assigned images and a ``data.yaml`` pointing at those lists, so the trainer sees
the intended partitioning.

Class names are read from the canonical
:class:`~device_ai.dataset.taxonomy.DeviceTaxonomy` (the single source of truth:
the component profile library's insertion-order keys), so the manifest never
hardcodes or duplicates the 19-class device list.

This is pure composition: it reuses the release, split assignment, and taxonomy
without modifying any of them. It performs minimal I/O (writes 4 text files) and
does not re-implement the exporter, image copier, or label parser.
"""

from __future__ import annotations

from pathlib import Path

from ...dataset.records import SplitAssignment
from ...dataset.release import DatasetRelease
from ...dataset.taxonomy import DeviceTaxonomy, load_taxonomy


def write_split_lists(
    split: SplitAssignment,
    *,
    images_dir: Path,
    destination: Path,
) -> tuple[Path, Path, Path]:
    """Write train.txt / val.txt / test.txt with relative image paths.

    Each list contains one ``<images_dir>/<relative_path>`` per line, where
    ``relative_path`` comes from the split's train/val/test tuples. The paths
    are written relative to the YOLO dataset root (the ``destination``'s
    parent), so ``data.yaml`` + these lists form a self-contained, relocatable
    dataset manifest.

    Args:
        split: The train/val/test partitioning from a release.
        images_dir: The YOLO export's images directory name (typically
            ``images``), used to prefix each relative path so YOLO resolves
            them correctly.
        destination: Directory to write the list files into (created if
            missing).

    Returns:
        A ``(train.txt, val.txt, test.txt)`` tuple of the written paths.
    """
    destination.mkdir(parents=True, exist_ok=True)

    train_txt = destination / "train.txt"
    val_txt = destination / "val.txt"
    test_txt = destination / "test.txt"

    # Each line is "<images_dir>/<relative_path>" so YOLO finds the image
    # relative to the dataset root (the parent of both images/ and the txt).
    train_txt.write_text(
        "\n".join(f"{images_dir.name}/{path}" for path in split.train) + "\n",
        encoding="utf-8",
    )
    val_txt.write_text(
        "\n".join(f"{images_dir.name}/{path}" for path in split.val) + "\n",
        encoding="utf-8",
    )
    test_txt.write_text(
        "\n".join(f"{images_dir.name}/{path}" for path in split.test) + "\n",
        encoding="utf-8",
    )

    return train_txt, val_txt, test_txt


def build_data_yaml(
    taxonomy: DeviceTaxonomy,
    *,
    train_txt: Path,
    val_txt: Path,
    test_txt: Path,
    destination: Path,
) -> Path:
    """Write a split-aware YOLO data.yaml referencing the train/val/test lists.

    The produced manifest points ``train`` / ``val`` / ``test`` at the provided
    list files (relative to the dataset root), so Ultralytics loads exactly the
    images the release's split assigned. Class names are taken from the
    canonical ``taxonomy`` so the manifest never hardcodes the device list.

    Args:
        taxonomy: The canonical device taxonomy supplying class names and count.
        train_txt: Path to the train.txt list (written by
            :func:`write_split_lists`).
        val_txt: Path to the val.txt list.
        test_txt: Path to the test.txt list.
        destination: Directory to write ``data.yaml`` into (the YOLO dataset
            root; typically the parent of ``images/`` and the txt files).

    Returns:
        The path of the written ``data.yaml``.
    """
    destination.mkdir(parents=True, exist_ok=True)
    data_yaml = destination / "data.yaml"

    # Paths are written relative to the dataset root (destination).
    train_rel = train_txt.relative_to(destination).as_posix()
    val_rel = val_txt.relative_to(destination).as_posix()
    test_rel = test_txt.relative_to(destination).as_posix()

    # Class names come from the taxonomy's insertion-order keys (the single
    # source of truth: the component profile library).
    names = list(taxonomy.class_names)

    lines = [
        "# YOLO dataset manifest (split-aware, P4.1.3)",
        "# Generated from a P4.1.2 DatasetRelease with an honored SplitAssignment.",
        f"# Taxonomy version: {taxonomy.version}",
        "",
        "path: .",
        f"train: {train_rel}",
        f"val: {val_rel}",
        f"test: {test_rel}",
        "",
        f"nc: {taxonomy.num_classes}",
        f"names: {names}",
    ]
    data_yaml.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return data_yaml


def build_training_manifest(
    release: DatasetRelease,
    *,
    export_root: Path,
    taxonomy: DeviceTaxonomy | None = None,
) -> Path:
    """Build a split-aware YOLO training manifest from a P4.1.2 release.

    Writes ``train.txt``, ``val.txt``, ``test.txt`` (image lists honoring the
    release's split) and a ``data.yaml`` referencing them under ``export_root``,
    so the trainer sees the intended train/val/test partitioning instead of
    validation leakage.

    When the release carries no split (``release.split is None``), the manifest
    degrades to a flat layout with ``train: images`` (mirroring the existing
    exporter) so the function is always callable. A production run with a real
    dataset should always supply a split.

    Args:
        release: The P4.1.2 dataset release carrying the split assignment,
            taxonomy version, and version metadata.
        export_root: The YOLO export's root directory (the parent of
            ``images/``). The manifest files are written here, and the
            ``data.yaml``'s ``path: .`` anchors paths to this directory.
        taxonomy: Optional pre-loaded taxonomy; defaults to loading the
            packaged canonical taxonomy. Injected for testing.

    Returns:
        The path of the written ``data.yaml``.

    Raises:
        ValueError: If ``export_root / "images"`` does not exist (the exporter
            must run first).
    """
    images_dir = export_root / "images"
    if not images_dir.exists():
        raise ValueError(
            f"YOLO export images directory not found: {images_dir}. "
            f"Run the dataset exporter first."
        )

    tax = taxonomy if taxonomy is not None else load_taxonomy()

    if release.split is None:
        # No split available; degrade to a flat manifest (train/val/test all
        # point at the same images/ folder). This is validation leakage, but
        # it mirrors the existing exporter's behavior when no split is supplied.
        # A real production run should always carry a split.
        data_yaml = export_root / "data.yaml"
        names = list(tax.class_names)
        lines = [
            "# YOLO dataset manifest (flat, no split available)",
            f"# Taxonomy version: {tax.version}",
            "",
            "path: .",
            "train: images",
            "val: images",
            "test: images",
            "",
            f"nc: {tax.num_classes}",
            f"names: {names}",
        ]
        data_yaml.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return data_yaml

    # Split-aware: write the image lists and a data.yaml referencing them.
    train_txt, val_txt, test_txt = write_split_lists(
        release.split, images_dir=images_dir, destination=export_root
    )
    return build_data_yaml(
        tax,
        train_txt=train_txt,
        val_txt=val_txt,
        test_txt=test_txt,
        destination=export_root,
    )
