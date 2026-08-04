"""Unit tests for the barcode/QR readers (milestone M1.6)."""

from __future__ import annotations

from device_ai.ocr.barcode import MockBarcodeReader, OpenCVBarcodeReader
from device_ai.ocr.models import BarcodeResult
from device_ai.preprocessing.image_loader import LoadedImage, load_image

from .conftest import make_image_bytes


def _load(color: tuple[int, int, int] = (10, 20, 30)) -> LoadedImage:
    """Return a decoded LoadedImage for barcode tests."""
    return load_image(
        make_image_bytes(color=color),
        filename="device.png",
        content_type="image/png",
    )


class TestMockBarcodeReader:
    """The deterministic mock reader."""

    def test_metadata(self) -> None:
        reader = MockBarcodeReader()
        assert reader.name == "barcode"
        assert reader.version == "mock-barcode-1.0.0"
        assert reader.is_ready is True

    def test_emits_qr_and_barcode(self) -> None:
        results = MockBarcodeReader().decode(_load())
        kinds = {result.kind for result in results}
        assert kinds == {"qr", "barcode"}

    def test_qr_payload_prefixed(self) -> None:
        results = MockBarcodeReader().decode(_load())
        qr = next(result for result in results if result.kind == "qr")
        assert qr.payload.startswith("SN")
        assert qr.symbology == "QRCODE"

    def test_is_deterministic_for_same_image(self) -> None:
        image = _load()
        assert MockBarcodeReader().decode(image) == MockBarcodeReader().decode(image)

    def test_differs_for_different_images(self) -> None:
        red = MockBarcodeReader().decode(_load((200, 10, 10)))
        blue = MockBarcodeReader().decode(_load((10, 10, 200)))
        assert red != blue

    def test_decode_batch_concatenates(self) -> None:
        reader = MockBarcodeReader()
        results = reader.decode_batch([_load((10, 20, 30)), _load((40, 50, 60))])
        assert len(results) == 4


class TestOpenCVBarcodeReaderNotReady:
    """The real adapter degrades honestly when cv2 is absent."""

    def test_not_ready_without_backend(self) -> None:
        reader = OpenCVBarcodeReader()
        assert reader.is_ready is False
        assert reader.decode(_load()) == []

    def test_version_is_stamped(self) -> None:
        assert OpenCVBarcodeReader().version == "opencv-barcode-1.0.0"


class TestOpenCVBarcodeReaderInjected:
    """The injected decode_fn is used verbatim (fake backend)."""

    def test_injected_reader_is_ready(self) -> None:
        def decode(image: LoadedImage) -> list[BarcodeResult]:
            return [BarcodeResult(kind="qr", payload="INJECTED", symbology="QRCODE")]

        reader = OpenCVBarcodeReader(decode_fn=decode)
        assert reader.is_ready is True

    def test_injected_decode_result_returned(self) -> None:
        def decode(image: LoadedImage) -> list[BarcodeResult]:
            return [BarcodeResult(kind="qr", payload="INJECTED", symbology="QRCODE")]

        reader = OpenCVBarcodeReader(decode_fn=decode)
        results = reader.decode(_load())
        assert [result.payload for result in results] == ["INJECTED"]
