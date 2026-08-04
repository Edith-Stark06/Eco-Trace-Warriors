"""Unit tests for the OCR domain models (milestone M1.6)."""

from __future__ import annotations

from datetime import UTC, datetime

from device_ai.ocr.models import (
    BarcodeResult,
    ExtractedField,
    FieldSource,
    FieldType,
    OCRExtraction,
    OCRIdentity,
    TextSpan,
)


class TestFieldType:
    """The FieldType str-enum."""

    def test_values_are_declaration_ordered(self) -> None:
        assert FieldType.values() == [
            "manufacturer",
            "model",
            "serial_number",
            "imei",
            "mac_address",
            "qr_code",
            "barcode",
        ]

    def test_is_str_enum(self) -> None:
        assert FieldType.SERIAL_NUMBER == "serial_number"
        assert FieldType("imei") is FieldType.IMEI


class TestTextSpan:
    """TextSpan serialization."""

    def test_to_dict_without_box(self) -> None:
        span = TextSpan(text="Dell", confidence=0.9)
        assert span.to_dict() == {
            "text": "Dell",
            "confidence": 0.9,
            "bounding_box": None,
        }

    def test_to_dict_with_box_becomes_list(self) -> None:
        span = TextSpan(text="Dell", confidence=0.9, bounding_box=(0, 1, 2, 3))
        assert span.to_dict()["bounding_box"] == [0, 1, 2, 3]


class TestBarcodeResult:
    """BarcodeResult serialization + defaults."""

    def test_defaults(self) -> None:
        barcode = BarcodeResult(kind="qr", payload="ABC")
        assert barcode.symbology == ""
        assert barcode.confidence == 1.0

    def test_to_dict(self) -> None:
        barcode = BarcodeResult(kind="qr", payload="ABC", symbology="QRCODE")
        assert barcode.to_dict() == {
            "kind": "qr",
            "payload": "ABC",
            "symbology": "QRCODE",
            "confidence": 1.0,
        }


class TestOCRIdentity:
    """OCRIdentity emptiness + projections."""

    def test_empty_identity(self) -> None:
        identity = OCRIdentity()
        assert identity.is_empty is True
        assert identity.non_empty() == {}

    def test_all_keys_present_in_to_dict(self) -> None:
        assert set(OCRIdentity().to_dict()) == {
            "manufacturer",
            "model",
            "serial_number",
            "imei",
            "mac_address",
        }

    def test_non_empty_drops_blank_fields(self) -> None:
        identity = OCRIdentity(manufacturer="Dell", imei="490154203237518")
        assert identity.is_empty is False
        assert identity.non_empty() == {
            "manufacturer": "Dell",
            "imei": "490154203237518",
        }


class TestExtractedField:
    """ExtractedField serialization."""

    def test_to_dict(self) -> None:
        field = ExtractedField(
            field_type=FieldType.MANUFACTURER,
            value="Dell",
            confidence=0.9,
            raw_text="Dell Inc.",
            source=FieldSource.TEXT,
        )
        assert field.to_dict() == {
            "field_type": "manufacturer",
            "value": "Dell",
            "confidence": 0.9,
            "raw_text": "Dell Inc.",
            "source": "text",
        }


class TestOCRExtraction:
    """OCRExtraction accessors, identity projection and round-trip."""

    def _extraction(self) -> OCRExtraction:
        fields = (
            ExtractedField(FieldType.MANUFACTURER, "Dell", 0.9),
            ExtractedField(FieldType.SERIAL_NUMBER, "ABC12345", 0.8),
            ExtractedField(FieldType.QR_CODE, "SNXYZ", 0.99, source=FieldSource.QR),
        )
        return OCRExtraction(
            fields=fields,
            spans=(TextSpan(text="Dell", confidence=0.9),),
            barcodes=(BarcodeResult(kind="qr", payload="SNXYZ", symbology="QRCODE"),),
            engine_name="ocr",
            engine_version="mock-ocr-m16-1.0.0",
            created_at=datetime(2026, 8, 1, 12, 0, 0, tzinfo=UTC),
            source_hashes=("a" * 64,),
        )

    def test_get_returns_field_or_none(self) -> None:
        extraction = self._extraction()
        found = extraction.get(FieldType.MANUFACTURER)
        assert found is not None and found.value == "Dell"
        assert extraction.get(FieldType.IMEI) is None

    def test_value_of_empty_when_absent(self) -> None:
        extraction = self._extraction()
        assert extraction.value_of(FieldType.MANUFACTURER) == "Dell"
        assert extraction.value_of(FieldType.IMEI) == ""

    def test_identity_projection(self) -> None:
        identity = self._extraction().identity
        assert identity.manufacturer == "Dell"
        assert identity.serial_number == "ABC12345"
        assert identity.imei == ""

    def test_to_dict_includes_identity_key(self) -> None:
        payload = self._extraction().to_dict()
        assert payload["identity"]["manufacturer"] == "Dell"
        assert payload["engine_version"] == "mock-ocr-m16-1.0.0"
        assert payload["created_at"] == "2026-08-01T12:00:00+00:00"
        assert payload["source_hashes"] == ["a" * 64]

    def test_round_trip_from_dict(self) -> None:
        original = self._extraction()
        restored = OCRExtraction.from_dict(original.to_dict())
        assert restored.fields == original.fields
        assert restored.spans == original.spans
        assert restored.barcodes == original.barcodes
        assert restored.engine_name == original.engine_name
        assert restored.engine_version == original.engine_version
        assert restored.created_at == original.created_at
        assert restored.source_hashes == original.source_hashes

    def test_empty_extraction_created_at_none(self) -> None:
        extraction = OCRExtraction()
        payload = extraction.to_dict()
        assert payload["created_at"] is None
        assert payload["fields"] == []
        assert OCRExtraction.from_dict(payload).created_at is None
