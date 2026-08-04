"""Tests for the POST /fingerprint/* endpoints (milestone M1.5)."""

from tests.conftest import make_image_bytes


def _files(*images: tuple[str, bytes, str]) -> list:
    """Build a multipart file list for the ``images`` field."""
    return [("images", (name, data, mime)) for name, data, mime in images]


def test_generate_single_image(fingerprint_client, png_bytes):
    """POST /fingerprint/generate with a valid image yields a fingerprint."""
    response = fingerprint_client.post(
        "/fingerprint/generate",
        files=_files(("device.png", png_bytes, "image/png")),
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["eco_id"].startswith("ET-2026-")
    assert len(data["fingerprint"]) == 64
    assert isinstance(data["embedding"], list)
    assert len(data["embedding"]) == data["dimension"] == 512
    assert data["encoder_name"] == "clip"
    assert data["encoder_version"] == "mock-clip-1.0.0"
    assert data["metric"] == "cosine"
    assert isinstance(data["created_at"], str)
    assert isinstance(data["source_hashes"], list)
    assert data["device_type"] == ""
    assert data["brand"] == ""


def test_generate_with_device_metadata(fingerprint_client, png_bytes):
    """device_type and brand form fields are recorded in the fingerprint."""
    response = fingerprint_client.post(
        "/fingerprint/generate",
        files=_files(("device.png", png_bytes, "image/png")),
        data={"device_type": "Laptop", "brand": "Dell"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["device_type"] == "Laptop"
    assert data["brand"] == "Dell"


def test_generate_multiple_images(fingerprint_client, png_bytes, jpeg_bytes):
    """Multiple images are aggregated into a single fingerprint."""
    response = fingerprint_client.post(
        "/fingerprint/generate",
        files=_files(
            ("front.png", png_bytes, "image/png"),
            ("back.jpg", jpeg_bytes, "image/jpeg"),
        ),
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert len(data["source_hashes"]) == 2


def test_generate_is_deterministic(fingerprint_client, png_bytes):
    """Identical images produce an identical fingerprint hash."""
    first = fingerprint_client.post(
        "/fingerprint/generate", files=_files(("d.png", png_bytes, "image/png"))
    ).json()
    second = fingerprint_client.post(
        "/fingerprint/generate", files=_files(("d.png", png_bytes, "image/png"))
    ).json()
    assert first["fingerprint"] == second["fingerprint"]
    assert first["embedding"] == second["embedding"]
    # EcoID is unique per call.
    assert first["eco_id"] != second["eco_id"]


def test_generate_rejects_no_images(fingerprint_client):
    """A request with no images is rejected (FastAPI validation)."""
    response = fingerprint_client.post("/fingerprint/generate", files=[])
    assert response.status_code == 422
    body = response.json()
    assert body["success"] is False


def test_generate_rejects_too_many_images(fingerprint_client):
    """More than MAX_IMAGES images are rejected with TOO_MANY_IMAGES."""
    images = [
        (f"img_{i}.png", make_image_bytes(color=(i * 10, 100, 100)), "image/png")
        for i in range(7)  # limit is 6
    ]
    response = fingerprint_client.post("/fingerprint/generate", files=_files(*images))
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "TOO_MANY_IMAGES"


def test_get_stored_fingerprint(fingerprint_client, png_bytes):
    """GET /fingerprint/{eco_id} returns a previously generated fingerprint."""
    generated = fingerprint_client.post(
        "/fingerprint/generate", files=_files(("d.png", png_bytes, "image/png"))
    ).json()
    eco_id = generated["eco_id"]
    response = fingerprint_client.get(f"/fingerprint/{eco_id}")
    assert response.status_code == 200
    assert response.json() == generated


def test_get_unknown_eco_id_returns_404(fingerprint_client):
    """GET with an unknown EcoID yields 404 with FINGERPRINT_NOT_FOUND."""
    response = fingerprint_client.get("/fingerprint/ET-2026-DEADBEEF")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "FINGERPRINT_NOT_FOUND"


def test_compare_identical_fingerprints_matches(fingerprint_client, png_bytes):
    """Comparing identical stored fingerprints yields a MATCH decision."""
    eco_id = fingerprint_client.post(
        "/fingerprint/generate", files=_files(("d.png", png_bytes, "image/png"))
    ).json()["eco_id"]
    response = fingerprint_client.post(
        "/fingerprint/compare",
        json={"left_eco_id": eco_id, "right_eco_id": eco_id},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["left_eco_id"] == eco_id
    assert data["right_eco_id"] == eco_id
    assert data["metric"] == "cosine"
    assert data["similarity"] == 1.0
    assert data["distance"] == 0.0
    assert data["threshold"] == 0.85
    assert data["decision"] == "match"
    assert data["is_match"] is True


def test_compare_distinct_fingerprints_below_threshold(fingerprint_client):
    """Visually distinct devices score low and produce NO_MATCH."""
    left = fingerprint_client.post(
        "/fingerprint/generate",
        files=_files(("a.png", make_image_bytes(color=(10, 20, 30)), "image/png")),
    ).json()["eco_id"]
    right = fingerprint_client.post(
        "/fingerprint/generate",
        files=_files(("b.png", make_image_bytes(color=(200, 100, 50)), "image/png")),
    ).json()["eco_id"]
    response = fingerprint_client.post(
        "/fingerprint/compare",
        json={"left_eco_id": left, "right_eco_id": right},
    )
    assert response.status_code == 200
    data = response.json()
    # Mock encoder is deterministic; different colors → distinct embeddings.
    assert data["similarity"] < 0.85
    assert data["decision"] == "no_match"
    assert data["is_match"] is False


def test_compare_with_metric_override(fingerprint_client, png_bytes):
    """The compare request accepts an optional metric override."""
    eco_id = fingerprint_client.post(
        "/fingerprint/generate", files=_files(("d.png", png_bytes, "image/png"))
    ).json()["eco_id"]
    response = fingerprint_client.post(
        "/fingerprint/compare",
        json={"left_eco_id": eco_id, "right_eco_id": eco_id, "metric": "euclidean"},
    )
    assert response.status_code == 200
    assert response.json()["metric"] == "euclidean"


def test_compare_unknown_left_eco_id_returns_404(fingerprint_client, png_bytes):
    """Comparing with an unknown left EcoID yields 404."""
    right = fingerprint_client.post(
        "/fingerprint/generate", files=_files(("d.png", png_bytes, "image/png"))
    ).json()["eco_id"]
    response = fingerprint_client.post(
        "/fingerprint/compare",
        json={"left_eco_id": "ET-2026-DEADBEEF", "right_eco_id": right},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "FINGERPRINT_NOT_FOUND"


def test_predict_endpoint_still_works(fingerprint_client, png_bytes):
    """The existing /predict contract is backward compatible (milestone M1.5)."""
    response = fingerprint_client.post(
        "/predict", files=_files(("device.png", png_bytes, "image/png"))
    )
    assert response.status_code == 200, response.text
    data = response.json()
    # Assert the M1.1 contract shape remains unchanged.
    assert data["eco_id"].startswith("ET-")
    assert isinstance(data["device_type"], str) and data["device_type"]
    assert isinstance(data["brand"], str) and data["brand"]
    assert 0.0 <= data["confidence"] <= 1.0
    assert set(data["condition"].keys()) == {"label", "score"}
    assert set(data["ocr"].keys()) == {"serial_number", "model"}
    assert isinstance(data["materials"], dict) and data["materials"]
    assert data["embedding_id"].startswith("mock_embedding")
    assert data["model_version"] == "1.0.0"
