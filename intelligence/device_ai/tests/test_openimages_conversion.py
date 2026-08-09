"""Tests for the Open Images -> EcoTrace YOLO converter (Phase 4 Laptop pilot).

These exercise the conversion logic in ``scripts/convert_openimages_to_yolo.py``
against the ten sprint-mandated scenarios: a normal box, a boundary-touching
box, multiple boxes, normalised-coordinate correctness, invalid source
coordinates, a missing source image, a missing source label, an unknown source
class, a wrong taxonomy mapping, and deterministic conversion.

The converter lives under ``scripts/`` (not on the pytest pythonpath), so the
scripts directory is prepended to ``sys.path`` before import. No frozen module or
production interface is touched.
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

import convert_openimages_to_yolo as conv  # noqa: E402

from device_ai.dataset.taxonomy import load_taxonomy  # noqa: E402

_TIMESTAMP = "2026-08-08T00:00:00+00:00"
_VERSION = "openimages-laptop-test"


@pytest.fixture
def taxonomy():
    return load_taxonomy()


@pytest.fixture
def laptop_map():
    return {"Laptop": "laptop"}


def _write_image(path: Path, *, size: tuple[int, int] = (1000, 500)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, (40, 60, 80)).save(path)


def _pilot(
    tmp_path: Path, labels: dict[str, str], *, images: dict[str, tuple[int, int]]
) -> tuple[Path, Path]:
    """Build a source pilot: images root + sibling Label dir.

    Args:
        tmp_path: The pytest temp dir.
        labels: Mapping of stem -> label file text (written verbatim).
        images: Mapping of stem -> image (width, height); a stem present here
            gets a real JPEG, a stem absent does not.

    Returns:
        ``(images_root, labels_root)``.
    """
    images_root = tmp_path / "src"
    labels_root = images_root / "Label"
    images_root.mkdir(parents=True, exist_ok=True)
    labels_root.mkdir(parents=True, exist_ok=True)
    for stem, size in images.items():
        _write_image(images_root / f"{stem}.jpg", size=size)
    for stem, text in labels.items():
        (labels_root / f"{stem}.txt").write_text(text, encoding="utf-8")
    return images_root, labels_root


def _run(tmp_path, images_root, labels_root, laptop_map, taxonomy):
    return conv.convert_dataset(
        source_images_root=images_root,
        source_labels_root=labels_root,
        source_to_canonical=laptop_map,
        taxonomy=taxonomy,
        source_name="Open Images V7",
        conversion_version=_VERSION,
        conversion_timestamp=_TIMESTAMP,
    )


# --------------------------------------------------------------------------- #
# 1. Normal box                                                               #
# --------------------------------------------------------------------------- #
def test_normal_box_converts(taxonomy):
    box = conv.SourceBox("Laptop", 100.0, 50.0, 300.0, 250.0)
    converted = conv.convert_box(box, image_width=1000, image_height=500, class_id=0)
    # centre = ((100+300)/2, (50+250)/2) = (200, 150) -> (0.2, 0.3)
    assert converted.class_id == 0
    assert converted.x_center == pytest.approx(0.2)
    assert converted.y_center == pytest.approx(0.3)
    assert converted.width == pytest.approx(0.2)
    assert converted.height == pytest.approx(0.4)


# --------------------------------------------------------------------------- #
# 2. Boundary box (touches image edges -> still valid)                        #
# --------------------------------------------------------------------------- #
def test_boundary_box_is_valid(taxonomy):
    box = conv.SourceBox("Laptop", 0.0, 0.0, 1000.0, 500.0)
    converted = conv.convert_box(box, image_width=1000, image_height=500, class_id=0)
    assert converted.x_center == pytest.approx(0.5)
    assert converted.y_center == pytest.approx(0.5)
    assert converted.width == pytest.approx(1.0)
    assert converted.height == pytest.approx(1.0)


# --------------------------------------------------------------------------- #
# 3. Multiple boxes in one label                                             #
# --------------------------------------------------------------------------- #
def test_multiple_boxes(tmp_path, laptop_map, taxonomy):
    label = (
        "Laptop 100 50 300 250\n"
        "Laptop 400 100 600 400\n"
        "Laptop 0 0 1000 500\n"
    )
    images_root, labels_root = _pilot(
        tmp_path, {"a": label}, images={"a": (1000, 500)}
    )
    result = _run(tmp_path, images_root, labels_root, laptop_map, taxonomy)
    (conversion,) = result.conversions
    assert conversion.ok
    assert conversion.source_object_count == 3
    assert conversion.converted_object_count == 3
    assert len(conversion.yolo_lines) == 3


# --------------------------------------------------------------------------- #
# 4. Normalised coordinate correctness (formula exactness)                    #
# --------------------------------------------------------------------------- #
def test_normalized_coordinate_correctness():
    box = conv.SourceBox("Laptop", 195.84, 0.0, 766.719744, 432.64)
    converted = conv.convert_box(box, image_width=1024, image_height=683, class_id=0)
    # Output is rounded to 6 places for determinism, so compare against the
    # rounded exact formula results.
    assert converted.x_center == round((195.84 + 766.719744) / 2 / 1024, 6)
    assert converted.y_center == round((0.0 + 432.64) / 2 / 683, 6)
    assert converted.width == round((766.719744 - 195.84) / 1024, 6)
    assert converted.height == round((432.64 - 0.0) / 683, 6)
    line = conv.format_yolo_line(converted)
    assert line.startswith("0 ")
    assert len(line.split()) == 5


# --------------------------------------------------------------------------- #
# 5. Invalid source coordinates (out of frame -> rejected, not clipped)       #
# --------------------------------------------------------------------------- #
def test_invalid_coordinates_are_rejected():
    box = conv.SourceBox("Laptop", 100.0, 50.0, 1200.0, 250.0)  # x2 > width
    with pytest.raises(conv.ConversionError) as exc:
        conv.convert_box(box, image_width=1000, image_height=500, class_id=0)
    assert exc.value.code == "COORD_OUT_OF_RANGE"


def test_non_positive_size_is_rejected():
    box = conv.SourceBox("Laptop", 300.0, 50.0, 100.0, 250.0)  # x2 <= x1
    with pytest.raises(conv.ConversionError) as exc:
        conv.convert_box(box, image_width=1000, image_height=500, class_id=0)
    assert exc.value.code == "NON_POSITIVE_SIZE"


def test_invalid_coordinates_void_whole_image(tmp_path, laptop_map, taxonomy):
    label = "Laptop 100 50 300 250\nLaptop 100 50 1200 250\n"
    images_root, labels_root = _pilot(
        tmp_path, {"a": label}, images={"a": (1000, 500)}
    )
    result = _run(tmp_path, images_root, labels_root, laptop_map, taxonomy)
    (conversion,) = result.conversions
    assert not conversion.ok
    assert conversion.converted_object_count == 0
    assert any(e.code == "COORD_OUT_OF_RANGE" for e in conversion.errors)


# --------------------------------------------------------------------------- #
# 6. Missing source image (orphan label)                                      #
# --------------------------------------------------------------------------- #
def test_missing_source_image(tmp_path, laptop_map, taxonomy):
    # Label 'b' has no matching image.
    images_root, labels_root = _pilot(
        tmp_path,
        {"a": "Laptop 100 50 300 250\n", "b": "Laptop 10 10 20 20\n"},
        images={"a": (1000, 500)},
    )
    result = _run(tmp_path, images_root, labels_root, laptop_map, taxonomy)
    codes = [e["code"] for e in result.errors["errors"]]
    assert "MISSING_SOURCE_IMAGE" in codes


# --------------------------------------------------------------------------- #
# 7. Missing source label                                                     #
# --------------------------------------------------------------------------- #
def test_missing_source_label(tmp_path, laptop_map, taxonomy):
    images_root, labels_root = _pilot(
        tmp_path, {}, images={"a": (1000, 500)}
    )
    result = _run(tmp_path, images_root, labels_root, laptop_map, taxonomy)
    (conversion,) = result.conversions
    assert not conversion.ok
    assert any(e.code == "MISSING_SOURCE_LABEL" for e in conversion.errors)


# --------------------------------------------------------------------------- #
# 8. Unknown source class                                                     #
# --------------------------------------------------------------------------- #
def test_unknown_source_class(taxonomy):
    with pytest.raises(conv.ConversionError) as exc:
        conv.resolve_class_id(
            "Spaceship",
            source_to_canonical={"Laptop": "laptop"},
            taxonomy=taxonomy,
        )
    assert exc.value.code == "UNKNOWN_SOURCE_CLASS"


# --------------------------------------------------------------------------- #
# 9. Wrong taxonomy mapping (canonical name not in taxonomy)                  #
# --------------------------------------------------------------------------- #
def test_wrong_taxonomy_mapping(taxonomy):
    with pytest.raises(conv.ConversionError) as exc:
        conv.resolve_class_id(
            "Laptop",
            source_to_canonical={"Laptop": "not-a-real-class"},
            taxonomy=taxonomy,
        )
    assert exc.value.code == "WRONG_TAXONOMY_MAPPING"


def test_laptop_class_id_is_discovered_not_assumed(taxonomy):
    _, class_id = conv.resolve_class_id(
        "Laptop",
        source_to_canonical={"Laptop": "laptop"},
        taxonomy=taxonomy,
    )
    # Discovered from the frozen taxonomy; capitalised 'Laptop' is not a name.
    assert class_id == taxonomy.class_id_for("laptop")
    assert taxonomy.class_id_for("Laptop") is None


# --------------------------------------------------------------------------- #
# 10. Deterministic conversion                                                #
# --------------------------------------------------------------------------- #
def test_deterministic_conversion(tmp_path, laptop_map, taxonomy):
    label = "Laptop 100 50 300 250\nLaptop 400 100 600 400\n"
    images_root, labels_root = _pilot(
        tmp_path, {"a": label}, images={"a": (1000, 500)}
    )
    first = _run(tmp_path, images_root, labels_root, laptop_map, taxonomy)
    second = _run(tmp_path, images_root, labels_root, laptop_map, taxonomy)
    assert first.conversions[0].yolo_lines == second.conversions[0].yolo_lines
    assert json.dumps(first.provenance, sort_keys=True) == json.dumps(
        second.provenance, sort_keys=True
    )
    assert json.dumps(first.report, sort_keys=True) == json.dumps(
        second.report, sort_keys=True
    )


# --------------------------------------------------------------------------- #
# End-to-end: staging is written, source untouched                           #
# --------------------------------------------------------------------------- #
def test_write_outputs_stages_only_clean_conversions(
    tmp_path, laptop_map, taxonomy
):
    images_root, labels_root = _pilot(
        tmp_path,
        {
            "good": "Laptop 100 50 300 250\n",
            "bad": "Laptop 100 50 1200 250\n",  # out of frame
        },
        images={"good": (1000, 500), "bad": (1000, 500)},
    )
    result = _run(tmp_path, images_root, labels_root, laptop_map, taxonomy)
    staging = tmp_path / "staging"
    outputs = conv.write_outputs(result, staging_root=staging)

    assert (outputs["images_dir"] / "good.jpg").exists()
    assert (outputs["labels_dir"] / "good.txt").exists()
    assert not (outputs["images_dir"] / "bad.jpg").exists()
    assert not (outputs["labels_dir"] / "bad.txt").exists()

    # Source is never modified: the source images have no sibling YOLO labels
    # and the Label dir still holds the originals verbatim.
    assert (labels_root / "bad.txt").read_text(encoding="utf-8") == (
        "Laptop 100 50 1200 250\n"
    )

    manifest = json.loads(outputs["provenance"].read_text(encoding="utf-8"))
    assert manifest["total_images"] == 1
    (record,) = manifest["records"]
    assert record["source"] == "Open Images V7"
    assert record["source_class"] == "Laptop"
    assert record["ecotrace_class"] == "laptop"
    assert record["ecotrace_class_id"] == taxonomy.class_id_for("laptop")
    assert record["sha256"]
    assert record["width"] == 1000
    assert record["height"] == 500
    assert record["conversion_version"] == _VERSION
    assert record["conversion_timestamp"] == _TIMESTAMP


def test_malformed_line_is_reported(tmp_path, laptop_map, taxonomy):
    images_root, labels_root = _pilot(
        tmp_path, {"a": "Laptop 100 50 300\n"}, images={"a": (1000, 500)}
    )
    result = _run(tmp_path, images_root, labels_root, laptop_map, taxonomy)
    (conversion,) = result.conversions
    assert not conversion.ok
    assert any(e.code == "MALFORMED_LINE" for e in conversion.errors)
