"""Unit tests for the OCR parser normalization layer (milestone M1.6)."""

from __future__ import annotations

from device_ai.ocr.models import (
    BarcodeResult,
    FieldSource,
    FieldType,
    TextSpan,
)
from device_ai.ocr.parser import OCRParser


def _parser() -> OCRParser:
    return OCRParser()


class TestSpanParsing:
    """Field extraction from text spans."""

    def test_manufacturer_from_span(self) -> None:
        extraction = _parser().parse([TextSpan(text="Dell Inc.", confidence=1.0)])
        assert extraction.value_of(FieldType.MANUFACTURER) == "Dell"

    def test_labelled_serial_beats_bare_token(self) -> None:
        extraction = _parser().parse([TextSpan(text="S/N: ABC12345", confidence=1.0)])
        serial = extraction.get(FieldType.SERIAL_NUMBER)
        assert serial is not None
        assert serial.value == "ABC12345"

    def test_labelled_model_extracted(self) -> None:
        extraction = _parser().parse([TextSpan(text="Model: XPS 15", confidence=1.0)])
        model = extraction.get(FieldType.MODEL)
        assert model is not None
        assert model.value == "XPS 15"

    def test_unlabelled_model_not_extracted(self) -> None:
        extraction = _parser().parse([TextSpan(text="XPS 15", confidence=1.0)])
        assert extraction.get(FieldType.MODEL) is None

    def test_valid_imei_extracted_with_high_confidence(self) -> None:
        extraction = _parser().parse(
            [TextSpan(text="IMEI: 490154203237518", confidence=1.0)]
        )
        imei = extraction.get(FieldType.IMEI)
        assert imei is not None
        assert imei.value == "490154203237518"
        assert imei.confidence > 0.9

    def test_mac_extracted_and_normalized(self) -> None:
        extraction = _parser().parse(
            [TextSpan(text="MAC 00-1a-2b-3c-4d-5e", confidence=1.0)]
        )
        mac = extraction.get(FieldType.MAC_ADDRESS)
        assert mac is not None
        assert mac.value == "00:1A:2B:3C:4D:5E"


class TestConfidenceCombination:
    """Confidence combines recognition strength and pattern strength."""

    def test_low_recognition_confidence_lowers_field_confidence(self) -> None:
        strong = _parser().parse([TextSpan(text="Dell", confidence=1.0)])
        weak = _parser().parse([TextSpan(text="Dell", confidence=0.5)])
        assert (
            weak.get(FieldType.MANUFACTURER).confidence
            < strong.get(FieldType.MANUFACTURER).confidence
        )

    def test_confidence_is_clamped_to_one(self) -> None:
        # IMEI label applies a >1.0 boost; result must never exceed 1.0.
        extraction = _parser().parse(
            [TextSpan(text="IMEI: 490154203237518", confidence=1.0)]
        )
        assert extraction.get(FieldType.IMEI).confidence <= 1.0


class TestBestSelection:
    """Highest-confidence candidate wins per field type."""

    def test_strongest_manufacturer_span_wins(self) -> None:
        extraction = _parser().parse(
            [
                TextSpan(text="Dell", confidence=0.4),
                TextSpan(text="Dell", confidence=0.95),
            ]
        )
        winners = [
            f for f in extraction.fields if f.field_type is FieldType.MANUFACTURER
        ]
        assert len(winners) == 1
        assert winners[0].confidence >= 0.9


class TestBarcodeParsing:
    """Barcode/QR payloads become fields and are mined for IDs."""

    def test_qr_becomes_qr_code_field(self) -> None:
        extraction = _parser().parse(
            [],
            [BarcodeResult(kind="qr", payload="HELLOQR", symbology="QRCODE")],
        )
        qr = extraction.get(FieldType.QR_CODE)
        assert qr is not None
        assert qr.value == "HELLOQR"
        assert qr.source is FieldSource.QR

    def test_barcode_becomes_barcode_field(self) -> None:
        extraction = _parser().parse(
            [],
            [BarcodeResult(kind="barcode", payload="012345678905", symbology="EAN13")],
        )
        barcode = extraction.get(FieldType.BARCODE)
        assert barcode is not None
        assert barcode.source is FieldSource.BARCODE

    def test_embedded_imei_mined_from_barcode(self) -> None:
        extraction = _parser().parse(
            [],
            [BarcodeResult(kind="qr", payload="490154203237518")],
        )
        imei = extraction.get(FieldType.IMEI)
        assert imei is not None
        assert imei.value == "490154203237518"

    def test_embedded_serial_mined_when_no_imei(self) -> None:
        extraction = _parser().parse(
            [],
            [BarcodeResult(kind="qr", payload="ABC12345")],
        )
        serial = extraction.get(FieldType.SERIAL_NUMBER)
        assert serial is not None
        assert serial.value == "ABC12345"


class TestEmptyInput:
    """Parsing nothing yields an empty extraction."""

    def test_no_spans_no_barcodes(self) -> None:
        extraction = _parser().parse([])
        assert extraction.fields == ()
        assert extraction.spans == ()
        assert extraction.barcodes == ()


class TestSampleSpansFixture:
    """The shared sample_spans fixture drives a full identity extraction."""

    def test_full_identity_from_sample_spans(self, sample_spans) -> None:
        extraction = _parser().parse(list(sample_spans))
        identity = extraction.identity
        assert identity.manufacturer == "Dell"
        assert identity.serial_number
        assert identity.imei == "490154203237518"
        assert identity.mac_address == "00:1A:2B:3C:4D:5E"
