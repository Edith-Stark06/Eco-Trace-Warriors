"""Tests for the /ocr/* endpoints (milestone M1.6).

These assert the new OCR surface works end to end against the mock backend and
reader, and — critically — that the frozen ``/predict`` contract and the M1.5
fingerprint routes are untouched (backward compatibility).
"""

from __future__ import annotations

from device_ai.ocr.models import FieldType

from .conftest import make_image_bytes


def _files(*images: tuple[str, bytes, str]) -> list:
    """Build a multipart file list for the ``images`` field."""
    return [("images", (name, data, mime)) for name, data, mime in images]


class TestExtractEndpoint:
    """POST /ocr/extract."""

    def test_extract_single_image(self, ocr_client, png_bytes) -> None:
        response = ocr_client.post(
            "/ocr/extract", files=_files(("device.png", png_bytes, "image/png"))
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["engine_name"] == "ocr"
        assert data["engine_version"] == "mock-ocr-m16-1.0.0"
        assert data["identity"]["manufacturer"] == "Dell"
        assert data["identity"]["imei"]
        assert len(data["source_hashes"]) == 1
        assert isinstance(data["fields"], list) and data["fields"]

    def test_extract_is_deterministic(self, ocr_client, png_bytes) -> None:
        first = ocr_client.post(
            "/ocr/extract", files=_files(("d.png", png_bytes, "image/png"))
        ).json()
        second = ocr_client.post(
            "/ocr/extract", files=_files(("d.png", png_bytes, "image/png"))
        ).json()
        assert first["fields"] == second["fields"]
        assert first["identity"] == second["identity"]

    def test_extract_rejects_no_images(self, ocr_client) -> None:
        response = ocr_client.post("/ocr/extract", files=[])
        assert response.status_code == 422
        assert response.json()["success"] is False

    def test_extract_rejects_too_many_images(self, ocr_client) -> None:
        images = [
            (f"img_{i}.png", make_image_bytes(color=(i * 10, 100, 100)), "image/png")
            for i in range(7)  # limit is 6
        ]
        response = ocr_client.post("/ocr/extract", files=_files(*images))
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "TOO_MANY_IMAGES"


class TestParseEndpoint:
    """POST /ocr/parse."""

    def test_parse_spans_returns_fields(self, ocr_client) -> None:
        response = ocr_client.post(
            "/ocr/parse",
            json={
                "spans": [
                    {"text": "Dell Inc.", "confidence": 0.95},
                    {"text": "S/N: ABC12345", "confidence": 0.9},
                    {"text": "IMEI: 490154203237518", "confidence": 0.9},
                ]
            },
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["identity"]["manufacturer"] == "Dell"
        assert data["identity"]["serial_number"] == "ABC12345"
        assert data["identity"]["imei"] == "490154203237518"
        assert data["source_hashes"] == []

    def test_parse_with_barcodes(self, ocr_client) -> None:
        response = ocr_client.post(
            "/ocr/parse",
            json={
                "spans": [],
                "barcodes": [
                    {"kind": "qr", "payload": "490154203237518", "symbology": "QRCODE"}
                ],
            },
        )
        assert response.status_code == 200
        assert response.json()["identity"]["imei"] == "490154203237518"

    def test_parse_empty_body_is_valid(self, ocr_client) -> None:
        response = ocr_client.post("/ocr/parse", json={})
        assert response.status_code == 200
        data = response.json()
        assert data["fields"] == []

    def test_parse_rejects_out_of_range_confidence(self, ocr_client) -> None:
        response = ocr_client.post(
            "/ocr/parse",
            json={"spans": [{"text": "Dell", "confidence": 2.0}]},
        )
        assert response.status_code == 422
        assert response.json()["success"] is False


class TestFieldsEndpoint:
    """GET /ocr/fields."""

    def test_lists_all_field_types(self, ocr_client) -> None:
        response = ocr_client.get("/ocr/fields")
        assert response.status_code == 200
        assert response.json()["field_types"] == FieldType.values()


class TestBackwardCompatibility:
    """The OCR router must not disturb existing surfaces."""

    def test_predict_contract_unchanged(self, ocr_client, png_bytes) -> None:
        response = ocr_client.post(
            "/predict", files=_files(("device.png", png_bytes, "image/png"))
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["eco_id"].startswith("ET-")
        assert set(data["ocr"].keys()) == {"serial_number", "model"}
        assert data["model_version"] == "1.0.0"

    def test_fingerprint_generate_still_works(self, ocr_client, png_bytes) -> None:
        response = ocr_client.post(
            "/fingerprint/generate",
            files=_files(("device.png", png_bytes, "image/png")),
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["eco_id"].startswith("ET-2026-")
        # No OCR identity was supplied, so the fingerprint identity stays empty.
        assert data["identity"] == {}
