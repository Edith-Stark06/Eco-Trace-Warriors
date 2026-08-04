"""Unit tests for the OCR pattern matchers and validators (M1.6)."""

from __future__ import annotations

from device_ai.ocr import patterns


class TestLuhnAndIMEI:
    """IMEI extraction and Luhn validation."""

    def test_luhn_valid_accepts_known_imei(self) -> None:
        assert patterns.luhn_valid("490154203237518") is True

    def test_luhn_rejects_altered_digit(self) -> None:
        assert patterns.luhn_valid("490154203237519") is False

    def test_luhn_rejects_non_digits(self) -> None:
        assert patterns.luhn_valid("49015420323751X") is False
        assert patterns.luhn_valid("") is False

    def test_find_imei_luhn_valid_is_strong(self) -> None:
        candidate = patterns.find_imei("IMEI: 490154203237518")
        assert candidate is not None
        assert candidate.value == "490154203237518"
        assert candidate.strength > 0.9

    def test_find_imei_luhn_invalid_is_weak(self) -> None:
        candidate = patterns.find_imei("490154203237519")
        assert candidate is not None
        assert candidate.strength < 0.6

    def test_find_imei_requires_fifteen_digits(self) -> None:
        assert patterns.find_imei("12345") is None

    def test_find_imei_accepts_spaced_digits(self) -> None:
        candidate = patterns.find_imei("49 015420 3237518")
        assert candidate is not None
        assert candidate.value == "490154203237518"


class TestMAC:
    """MAC-address extraction."""

    def test_find_mac_colon_form(self) -> None:
        candidate = patterns.find_mac("MAC 00:1a:2b:3c:4d:5e")
        assert candidate is not None
        assert candidate.value == "00:1A:2B:3C:4D:5E"
        assert candidate.strength > 0.9

    def test_find_mac_hyphen_form_normalized_to_colon(self) -> None:
        candidate = patterns.find_mac("00-1A-2B-3C-4D-5E")
        assert candidate is not None
        assert candidate.value == "00:1A:2B:3C:4D:5E"

    def test_find_mac_none_when_absent(self) -> None:
        assert patterns.find_mac("no address here") is None


class TestConfusionNormalization:
    """Confusion normalization applies only to structured IDs."""

    def test_normalize_maps_letters_to_digits(self) -> None:
        assert patterns.normalize_confusions("OIl SB") == "011 58"

    def test_manufacturer_not_confusion_normalized(self) -> None:
        # "Sony" must not become "50ny": manufacturer matching sees raw text.
        candidate = patterns.find_manufacturer("Sony")
        assert candidate is not None
        assert candidate.value == "Sony"


class TestSerial:
    """Serial-number heuristic."""

    def test_unlabelled_requires_mixed_alnum(self) -> None:
        assert patterns.find_serial("HELLOWORLD") is None
        mixed = patterns.find_serial("ABC12345")
        assert mixed is not None
        assert mixed.value == "ABC12345"

    def test_labelled_relaxes_mixed_requirement(self) -> None:
        candidate = patterns.find_serial("ABCDEFGH", labelled=True)
        assert candidate is not None

    def test_labelled_mixed_is_strongest(self) -> None:
        strong = patterns.find_serial("ABC12345", labelled=True)
        weak = patterns.find_serial("ABC12345", labelled=False)
        assert strong is not None and weak is not None
        assert strong.strength > weak.strength


class TestModel:
    """Model extraction (label-driven only)."""

    def test_model_requires_label(self) -> None:
        assert patterns.find_model("XPS 15", labelled=False) is None

    def test_model_labelled_returns_value(self) -> None:
        candidate = patterns.find_model("XPS 15", labelled=True)
        assert candidate is not None
        assert candidate.value == "XPS 15"


class TestManufacturer:
    """Manufacturer keyword table."""

    def test_case_insensitive_token_match(self) -> None:
        candidate = patterns.find_manufacturer("dell inc.")
        assert candidate is not None
        assert candidate.value == "Dell"

    def test_no_false_positive_inside_word(self) -> None:
        assert patterns.find_manufacturer("Delaware") is None

    def test_known_manufacturers_sorted_and_unique(self) -> None:
        names = patterns.known_manufacturers()
        assert names == tuple(sorted(set(names)))
        assert "Dell" in names and "Apple" in names


class TestLabels:
    """Label detection and stripping."""

    def test_has_serial_label(self) -> None:
        assert patterns.has_serial_label("S/N: ABC") is True
        assert patterns.has_serial_label("nothing") is False

    def test_strip_label_splits_on_colon(self) -> None:
        assert patterns.strip_label("S/N: ABC123") == "ABC123"

    def test_strip_label_splits_on_equals(self) -> None:
        assert patterns.strip_label("MODEL=XPS 15") == "XPS 15"

    def test_strip_label_returns_whole_when_no_separator(self) -> None:
        assert patterns.strip_label("  bare  ") == "bare"
