"""Unit tests for the OCR text-recognition backends (milestone M1.6)."""

from __future__ import annotations

from device_ai.ocr.backends import EasyOCRBackend, MockOCRBackend
from device_ai.ocr.patterns import luhn_valid
from device_ai.preprocessing.image_loader import LoadedImage, load_image

from .conftest import make_image_bytes


def _load(color: tuple[int, int, int] = (10, 20, 30)) -> LoadedImage:
    """Return a decoded LoadedImage for backend tests."""
    return load_image(
        make_image_bytes(color=color),
        filename="device.png",
        content_type="image/png",
    )


class TestMockOCRBackend:
    """The deterministic mock backend."""

    def test_metadata(self) -> None:
        backend = MockOCRBackend()
        assert backend.name == "ocr"
        assert backend.version == "mock-ocr-m16-1.0.0"
        assert backend.is_ready is True

    def test_emits_labelled_identity_spans(self) -> None:
        spans = MockOCRBackend().recognize(_load())
        texts = [span.text for span in spans]
        assert any(text == "Dell" for text in texts)
        assert any(text.startswith("Model:") for text in texts)
        assert any(text.startswith("S/N:") for text in texts)
        assert any(text.startswith("IMEI:") for text in texts)
        assert any(text.startswith("MAC:") for text in texts)

    def test_emitted_imei_is_luhn_valid(self) -> None:
        spans = MockOCRBackend().recognize(_load())
        imei_span = next(s for s in spans if s.text.startswith("IMEI:"))
        digits = imei_span.text.split(":", 1)[1].strip()
        assert luhn_valid(digits) is True

    def test_is_deterministic_for_same_image(self) -> None:
        image = _load()
        first = MockOCRBackend().recognize(image)
        second = MockOCRBackend().recognize(image)
        assert first == second

    def test_differs_for_different_images(self) -> None:
        red = MockOCRBackend().recognize(_load((200, 10, 10)))
        blue = MockOCRBackend().recognize(_load((10, 10, 200)))
        assert red != blue

    def test_recognize_batch_concatenates(self) -> None:
        backend = MockOCRBackend()
        images = [_load((10, 20, 30)), _load((40, 50, 60))]
        batch = backend.recognize_batch(images)
        assert len(batch) == len(backend.recognize(images[0])) + len(
            backend.recognize(images[1])
        )


class TestEasyOCRBackendNotReady:
    """The real adapter degrades honestly when easyocr is absent."""

    def test_not_ready_without_backend(self) -> None:
        # No recognize_fn and no easyocr installed → not ready, never raises.
        backend = EasyOCRBackend()
        assert backend.is_ready is False
        assert backend.recognize_batch([_load()]) == []

    def test_version_is_stamped(self) -> None:
        assert EasyOCRBackend().version == "easyocr-1.7.2"


class TestEasyOCRBackendInjected:
    """The injected recognize_fn maps rows → spans (fake backend)."""

    def test_injected_backend_is_ready(self, fake_ocr_backend) -> None:
        assert fake_ocr_backend.is_ready is True

    def test_maps_rows_to_spans(self, fake_ocr_backend) -> None:
        spans = fake_ocr_backend.recognize_batch([_load()])
        texts = [span.text for span in spans]
        assert "Dell" in texts
        assert "S/N: ABC12345" in texts

    def test_maps_bounding_box(self, fake_ocr_backend) -> None:
        spans = fake_ocr_backend.recognize_batch([_load()])
        first = next(s for s in spans if s.text == "Dell")
        assert first.bounding_box == (0, 0, 10, 5)

    def test_min_confidence_filters_rows(self) -> None:
        def recognize(images):  # noqa: ANN001, ANN202 - local test stub
            rows = [
                ([[0, 0], [1, 0], [1, 1], [0, 1]], "keep", 0.9),
                ([[0, 0], [1, 0], [1, 1], [0, 1]], "drop", 0.1),
            ]
            return [rows for _ in images]

        backend = EasyOCRBackend(min_confidence=0.5, recognize_fn=recognize)
        texts = [span.text for span in backend.recognize_batch([_load()])]
        assert texts == ["keep"]

    def test_accepts_flat_row_list(self) -> None:
        def recognize(images):  # noqa: ANN001, ANN202 - local test stub
            # A single flat list of rows (not grouped per image).
            return [([[0, 0], [2, 0], [2, 2], [0, 2]], "flat", 0.8)]

        backend = EasyOCRBackend(recognize_fn=recognize)
        spans = backend.recognize_batch([_load()])
        assert [s.text for s in spans] == ["flat"]
