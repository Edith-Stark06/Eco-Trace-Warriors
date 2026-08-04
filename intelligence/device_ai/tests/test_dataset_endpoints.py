"""End-to-end tests for the ``/dataset`` API surface (milestone M1.2)."""

from __future__ import annotations

from device_ai.configs.settings import Settings


def test_stats_endpoint_reports_populated_dataset(
    dataset_client, populated_dataset: Settings
):
    """GET /dataset/stats analyses raw images and reports duplicates."""
    response = dataset_client.get("/dataset/stats")
    assert response.status_code == 200
    body = response.json()
    assert body["total_images"] == 4
    # a.png and c.png are byte-identical → one duplicate.
    assert body["duplicates"]["images"] >= 1
    assert body["quality"]["dark"] >= 1  # b.png is near-black
    assert body["format_counts"]["PNG"] == 4


def test_validate_endpoint_flags_missing_labels(
    dataset_client, populated_dataset: Settings
):
    """POST /dataset/validate finds images that lack label files."""
    response = dataset_client.post("/dataset/validate", json={"num_classes": 3})
    assert response.status_code == 200
    body = response.json()
    # c.png and d.png have no labels.
    assert "c.png" in body["images_without_labels"]
    assert body["total_boxes"] == 2
    assert body["is_valid"] is False


def test_export_endpoint_writes_coco(dataset_client, populated_dataset: Settings):
    """POST /dataset/export returns the written COCO files."""
    response = dataset_client.post(
        "/dataset/export", json={"format": "coco", "class_names": ["battery", "phone"]}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["format"] == "coco"
    assert "annotations.json" in body["files"]
    export_dir = populated_dataset.dataset_dir / "exports" / "coco"
    assert (export_dir / "annotations.json").exists()


def test_export_endpoint_rejects_unknown_format(
    dataset_client, populated_dataset: Settings
):
    """An unsupported export format is rejected at the schema boundary (422)."""
    response = dataset_client.post("/dataset/export", json={"format": "tfrecord"})
    assert response.status_code == 422


def test_augment_endpoint_generates_variants(
    dataset_client, populated_dataset: Settings
):
    """POST /dataset/augment writes label-preserving variants to disk."""
    response = dataset_client.post("/dataset/augment", json={"operations": ["hflip"]})
    assert response.status_code == 200
    body = response.json()
    assert body["source_count"] == 4
    assert body["num_generated"] == 4
    augmented = populated_dataset.dataset_dir / "augmented"
    assert (augmented / "a__hflip.png").exists()


def test_report_endpoint_writes_json_and_html(
    dataset_client, populated_dataset: Settings
):
    """GET /dataset/report produces both JSON and HTML artifacts on disk."""
    response = dataset_client.get("/dataset/report")
    assert response.status_code == 200
    body = response.json()
    assert "statistics" in body["report"]
    quality_dir = populated_dataset.dataset_dir / "quality"
    assert (quality_dir / "report.json").exists()
    assert (quality_dir / "report.html").exists()


def test_report_endpoint_on_empty_dataset_returns_422(dataset_client):
    """An empty dataset yields the EMPTY_DATASET error envelope."""
    response = dataset_client.get("/dataset/report")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "EMPTY_DATASET"


def test_import_endpoint_missing_source_returns_404(dataset_client):
    """Importing from a non-existent source directory returns 404."""
    response = dataset_client.post(
        "/dataset/import", json={"source": "/no/such/directory"}
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "DATASET_NOT_FOUND"


def test_import_endpoint_ingests_images(dataset_client, dataset_settings, tmp_path):
    """POST /dataset/import copies images from a server-side source directory."""
    from PIL import Image

    source = tmp_path / "incoming"
    source.mkdir()
    Image.new("RGB", (40, 40), (10, 20, 30)).save(source / "x.png")

    response = dataset_client.post("/dataset/import", json={"source": str(source)})
    assert response.status_code == 200
    body = response.json()
    assert body["num_imported"] == 1
    assert (dataset_settings.dataset_dir / "raw" / "x.png").exists()


def test_prediction_endpoints_untouched(dataset_client):
    """The M1.1 prediction surface still responds (no API regressions)."""
    assert dataset_client.get("/health").status_code == 200
    assert dataset_client.get("/version").status_code == 200
