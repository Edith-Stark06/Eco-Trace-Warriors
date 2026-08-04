"""Tests for the POST /predict endpoint (mock predictions)."""

from tests.conftest import make_image_bytes


def _files(*images: tuple[str, bytes, str]) -> list:
    """Build a multipart file list for the ``images`` field."""
    return [("images", (name, data, mime)) for name, data, mime in images]


def test_predict_single_image(client, png_bytes):
    """A single valid image yields a well-formed prediction."""
    response = client.post(
        "/predict",
        files=_files(("device.png", png_bytes, "image/png")),
    )
    assert response.status_code == 200, response.text
    data = response.json()

    # Contract shape mirrors the milestone reference payload.
    assert data["eco_id"].startswith("ET-")
    assert len(data["eco_id"].split("-")) == 3
    assert isinstance(data["device_type"], str) and data["device_type"]
    assert isinstance(data["brand"], str) and data["brand"]
    assert 0.0 <= data["confidence"] <= 1.0
    assert set(data["condition"].keys()) == {"label", "score"}
    assert 0.0 <= data["condition"]["score"] <= 1.0
    assert set(data["ocr"].keys()) == {"serial_number", "model"}
    assert isinstance(data["materials"], dict) and data["materials"]
    assert 0.0 <= data["carbon_score"] <= 100.0
    assert data["embedding_id"].startswith("mock_embedding")
    assert data["model_version"] == "1.0.0"


def test_predict_multiple_images(client, png_bytes, jpeg_bytes):
    """Multiple valid images are accepted (within the limit)."""
    response = client.post(
        "/predict",
        files=_files(
            ("front.png", png_bytes, "image/png"),
            ("back.jpg", jpeg_bytes, "image/jpeg"),
        ),
    )
    assert response.status_code == 200, response.text


def test_predict_is_deterministic(client, png_bytes):
    """The same image yields the same prediction (excluding the EcoID)."""
    first = client.post(
        "/predict", files=_files(("d.png", png_bytes, "image/png"))
    ).json()
    second = client.post(
        "/predict", files=_files(("d.png", png_bytes, "image/png"))
    ).json()

    # EcoID is unique per call; everything else is content-derived.
    for key in ("device_type", "brand", "confidence", "materials", "embedding_id"):
        assert first[key] == second[key]
    assert first["eco_id"] != second["eco_id"]


def test_predict_no_images(client):
    """A request with no images is rejected."""
    response = client.post("/predict", files=[])
    # FastAPI treats the missing required field as a validation error.
    assert response.status_code == 422
    body = response.json()
    assert body["success"] is False
    assert "error" in body


def test_predict_too_many_images(client, png_bytes):
    """More than MAX_IMAGES images are rejected with TOO_MANY_IMAGES."""
    images = [
        (f"img_{i}.png", make_image_bytes(color=(i * 10, 100, 100)), "image/png")
        for i in range(7)  # limit is 6
    ]
    response = client.post("/predict", files=_files(*images))
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "TOO_MANY_IMAGES"


def test_predict_rejects_large_file(client):
    """An image exceeding MAX_FILE_SIZE is rejected with FILE_TOO_LARGE."""
    # test_settings caps files at 1 MB; a noisy 2000x2000 PNG exceeds that.
    big = make_image_bytes(size=(2000, 2000), fmt="PNG", noise=True)
    response = client.post("/predict", files=_files(("big.png", big, "image/png")))
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "FILE_TOO_LARGE"


def test_predict_rejects_invalid_mime(client, png_bytes):
    """A disallowed MIME type is rejected with UNSUPPORTED_MEDIA_TYPE."""
    response = client.post(
        "/predict",
        files=_files(("note.txt", png_bytes, "text/plain")),
    )
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "UNSUPPORTED_MEDIA_TYPE"


def test_predict_rejects_corrupted_image(client):
    """Corrupted image bytes are rejected with CORRUPTED_IMAGE."""
    response = client.post(
        "/predict",
        files=_files(("broken.png", b"not-a-real-image", "image/png")),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "CORRUPTED_IMAGE"


def test_predict_response_has_request_id_header(client, png_bytes):
    """Every response carries an X-Request-ID correlation header."""
    response = client.post("/predict", files=_files(("d.png", png_bytes, "image/png")))
    assert response.headers.get("X-Request-ID")
