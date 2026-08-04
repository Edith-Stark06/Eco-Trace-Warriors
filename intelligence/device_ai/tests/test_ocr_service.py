"""Tests for the OCRService orchestration facade (milestone M1.6)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from device_ai.ocr.backends import MockOCRBackend
from device_ai.ocr.barcode import MockBarcodeReader
from device_ai.ocr.models import BarcodeResult, FieldType, TextSpan
from device_ai.ocr.parser import OCRParser
from device_ai.ocr.service import OCRService
from device_ai.preprocessing.image_loader import LoadedImage, load_image

from .conftest import make_image_bytes

_FIXED_CLOCK: Callable[[], datetime] = lambda: datetime(  # noqa: E731
    2026, 8, 1, 12, 0, 0, tzinfo=UTC
)


def _load(color: tuple[int, int, int] = (10, 20, 30)) -> LoadedImage:
    """Return a decoded LoadedImage for service tests."""
    return load_image(
        make_image_bytes(color=color),
        filename="device.png",
        content_type="image/png",
    )


def _service(*, with_barcode: bool = True) -> OCRService:
    """Build a service wired to the mock backend/reader and a fixed clock."""
    return OCRService(
        backend=MockOCRBackend(),
        parser=OCRParser(),
        barcode_reader=MockBarcodeReader() if with_barcode else None,
        clock=_FIXED_CLOCK,
    )


class TestExtract:
    """extract() over a batch of images."""

    def test_stamps_engine_identity_and_time(self) -> None:
        extraction = _service().extract([_load()])
        assert extraction.engine_name == "ocr"
        assert extraction.engine_version == "mock-ocr-m16-1.0.0"
        assert extraction.created_at == _FIXED_CLOCK()

    def test_records_sorted_source_hashes(self) -> None:
        image = _load()
        extraction = _service().extract([image])
        assert extraction.source_hashes == (image.sha256,)

    def test_extracts_full_identity(self) -> None:
        identity = _service().extract([_load()]).identity
        assert identity.manufacturer == "Dell"
        assert identity.model
        assert identity.serial_number
        assert identity.imei
        assert identity.mac_address

    def test_barcodes_present_when_reader_configured(self) -> None:
        extraction = _service(with_barcode=True).extract([_load()])
        assert len(extraction.barcodes) > 0

    def test_barcodes_absent_when_no_reader(self) -> None:
        extraction = _service(with_barcode=False).extract([_load()])
        assert extraction.barcodes == ()

    def test_is_deterministic(self) -> None:
        first = _service().extract([_load()])
        second = _service().extract([_load()])
        assert first.to_dict() == second.to_dict()


class TestParse:
    """parse() over client-supplied spans/barcodes (no images)."""

    def test_parse_spans_only(self) -> None:
        extraction = _service().parse([TextSpan(text="Dell Inc.", confidence=1.0)])
        assert extraction.value_of(FieldType.MANUFACTURER) == "Dell"
        assert extraction.source_hashes == ()

    def test_parse_stamps_engine_identity(self) -> None:
        extraction = _service().parse([TextSpan(text="Dell", confidence=1.0)])
        assert extraction.engine_version == "mock-ocr-m16-1.0.0"
        assert extraction.created_at == _FIXED_CLOCK()

    def test_parse_with_barcodes(self) -> None:
        extraction = _service().parse(
            [],
            [BarcodeResult(kind="qr", payload="490154203237518")],
        )
        assert extraction.value_of(FieldType.IMEI) == "490154203237518"


class TestIdentityFor:
    """identity_for() convenience for the fingerprint seam."""

    def test_returns_identity_projection(self) -> None:
        identity = _service().identity_for([_load()])
        assert identity.manufacturer == "Dell"
        assert not identity.is_empty
